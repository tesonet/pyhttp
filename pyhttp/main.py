import os
import sys
import time
import queue
import struct
import signal
import socket
import pycurl
import io
import threading
import argparse

from . import summary


exit_using_ctr_c = False


def signal_handler(signal, frame):
    global exit_using_ctr_c
    exit_using_ctr_c = True

def signal_handler_USR1(signal, frame):
    pass

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGUSR1, signal_handler_USR1)



"""
Thread dedicated for outputing results/stats. This prevents from stopping main
threads on I/O, sync, flush
"""
class output_worker(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.output_queue = queue.Queue()

    def put(self, message):
        self.output_queue.put(message)

    def run(self):
        time_of_last_flush = time.time()
        while True:
            msg = self.output_queue.get()
            if msg == None:
                break
            sys.stdout.write(msg)
            time_now = time.time()
            # flush once per 1/5th second or less
            if time_now > time_of_last_flush + 0.2:
                sys.stdout.flush()
                time_of_last_flush = time_now
        # finalize output stream
        sys.stdout.write('\n')
        sys.stdout.flush()

class thread_waiter_worker(threading.Thread):
    def __init__(self, threads):
        threading.Thread.__init__(self)
        self.threads = threads

    def run(self):
        for thread in self.threads:
            thread.join()
        os.kill(os.getpid(), signal.SIGUSR1)

class worker(threading.Thread):
    def __init__(self, pyhttp):
        threading.Thread.__init__(self)
        self.pyhttp = pyhttp
        self.args = pyhttp.args

    # if our pycurl does not have WRITEDATA
    def buffer_write(self, buffer):
        self.buffer_len = self.buffer_len + len(buffer)

    def run(self):
        while True:
            task_id = self.pyhttp.tasks.get()
            if task_id == None:
                break

            request_status = -1
            request_time = -1
            stat_char = '.'

            curl = pycurl.Curl()
            curl.setopt(pycurl.CAINFO, "")
            curl.setopt(pycurl.URL, self.args.url)
            self.buffer_len = 0
            curl.setopt(pycurl.WRITEFUNCTION, self.buffer_write)
            curl.setopt(pycurl.CONNECTTIMEOUT, self.args.timeout)
            curl.setopt(pycurl.SSL_VERIFYPEER, False)
            curl.setopt(pycurl.SSL_VERIFYHOST, False)
            curl.setopt(pycurl.TIMEOUT, self.args.timeout)

            if self.args.proxy != None:
                curl.setopt(pycurl.PROXY, self.args.proxy)
            if self.args.proxy_auth != None:
                curl.setopt(pycurl.PROXYUSERPWD, self.args.proxy_auth)
            if len(self.args.header) > 0:
                curl.setopt(pycurl.HTTPHEADER, self.args.header)

            try:
                curl.perform()
                request_time = curl.getinfo(curl.TOTAL_TIME)
                request_status = curl.getinfo(curl.RESPONSE_CODE)
            except pycurl.error as e:
                if e.args[0] == 56 and e.args[1] == 'Received HTTP code 407 from proxy after CONNECT':
                    request_status = 407
                    request_time = 0
                    stat_char = 'A'
                elif e.args[0] == 28:
                    request_status = 'C28'
                    request_time = self.args.timeout
                    stat_char = 'T'
                elif e.args[0] == 35:
                    # gnutls_handshake() failed: The TLS connection was non-properly terminated.
                    request_status = 'C35'
                    request_time = self.args.timeout
                    stat_char = 's'
                elif e.args[0] == 7:
                    # Failed to connect() to host or proxy.
                    request_status = -599
                    request_time = 0
                    stat_char = 'C'
                else:
                    raise

            self.pyhttp.stats[task_id] = {
                'size': self.buffer_len,
                'status': str(request_status),
                'time': request_time
            }
            fd = curl.getinfo(curl.LASTSOCKET)
            if fd != -1:
                sock = socket.fromfd(fd, 0, 0)

            curl.close()
            if fd != -1:
                if self.args.end_with_shutdown:
                    sock.shutdown(socket.SHUT_RDWR)
                if self.args.end_with_RST:
                    socket_SO_LINGER_value = struct.pack('ii', 1, 0)
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, socket_SO_LINGER_value)
                sock.close()
            self.pyhttp.output.put(stat_char)


class HttpPerformanceTest():
    def __init__(self):
        self.args = None
        self.stats = None

    def arguments_parse(self):
        parser = argparse.ArgumentParser()
        parser.add_argument('-c', '--concurrency', metavar='N', default=1, type=int, help='Number of multiple requests to perform at a time')
        parser.add_argument('-H', '--header', metavar='custom-header', default=[], nargs='*', type=str, help='Append extra headers to the request.')
        parser.add_argument('-n', '--requests', metavar='N', default=1, type=int, help='Number of requests to perform for the benchmarking session')
        parser.add_argument('-P', '--proxy-auth', metavar='proxy-auth-username:password', type=str, help='Supply BASIC Authentication credentials to a proxy en-route.')
        parser.add_argument('-X', '--proxy', metavar='proxy:port', type=str, help='Use a proxy server for the requests.')
        parser.add_argument('--end-with-RST', action='store_true', help='Finish TCP session with RST')
        parser.add_argument('--end-with-shutdown', action='store_true', help='Call shutdown before close')
        parser.add_argument('-t', '--timeout', metavar='timeout', default=30, type=int, help='Maximum number of seconds to wait before the socket times out.')
        parser.add_argument('url', metavar='URL', type=str)
        parser.add_argument('-o', '--output', metavar='results.json', type=str,
                            help='Write benchmark results to csv file.')
        self.args = parser.parse_args()

    def print_timeline_item(self, idx: int, msg: str) -> None:
        time_start = self.benchmark_timeline[idx]
        time_end = self.benchmark_timeline[idx + 1]
        time_diff = "Uknown   "
        if time_start != None and time_end != None:
            time_diff = "%fs" % (time_end - time_start)
        print("%s %s" % (time_diff, msg))

    def print_statistics(self):
        global exit_using_ctr_c
        if exit_using_ctr_c:
            summary.warn_sigint()

        self.print_timeline_item(0, "Structures init")
        self.print_timeline_item(1, "Threads create")
        self.print_timeline_item(2, "Threads run")
        self.print_timeline_item(3, "... test ... threads join.")
        print("=====================")
        print(summary.results_to_str(self.stats, self.benchmark_timeline,
                                     self.args.concurrency))
        print("=====================")
        if exit_using_ctr_c:
            print('\x1b[0m')
        print('done')

        if self.args.output:
            write_to(
                self.args.output,
                summary.results_to_json(self.stats, self.benchmark_timeline,
                                        self.args.concurrency)
            )

    def init(self):
        self.stats = [{}] * self.args.requests
        self.tasks = queue.Queue()
        self.benchmark_timeline = [None] * 5
        self.output = output_worker()
        self.output.start()

    def benchmark(self):
        global exit_using_ctr_c

        threads = []

        self.benchmark_timeline[0] = time.time()
        for i in range(self.args.requests):
            self.tasks.put(i)

        for i in range(self.args.concurrency):
            self.tasks.put(None)

        self.benchmark_timeline[1] = time.time()
        for i in range(self.args.concurrency):
            thread = worker(self)
            threads.append(thread)

        self.benchmark_timeline[2] = time.time()
        for thread in threads:
            thread.start()

        thread_waiter = thread_waiter_worker(threads)
        thread_waiter.start()

        self.benchmark_timeline[3] = time.time()
        time.sleep(100000000)
        if not exit_using_ctr_c:
            thread_waiter.join()

        self.benchmark_timeline[4] = time.time()
        self.output.put(None)
        self.output.join()

    def run(self):
        global exit_using_ctr_c

        self.arguments_parse()
        self.init()
        self.benchmark()
        self.print_statistics()
        if exit_using_ctr_c:
            os._exit(1)

def main():
    HttpPerformanceTest().run()


def write_to(fname: str, text: str) -> None:
    with open(fname, 'w') as f:
        f.write(text)


if __name__ == '__main__':
    main()
