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

from . import summary, cli


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
                sock.close()
            self.pyhttp.output.put(stat_char)


class Timeline:
    def __init__(self) -> None:
        self.log = []

        self._last_event = None

    def start(self, event: str) -> None:
        self._last_event = {'event': event, 'started': time.time()}

    def finish(self) -> None:
        """Finishes last event."""
        self._last_event['finished'] = time.time()
        self._last_event['duration'] = self._last_event['finished'] - \
                                       self._last_event['started']
        self.log.append(self._last_event)
        self._last_event = None


class HttpPerformanceTest():
    def __init__(self):
        self.args = cli.parse_args(sys.argv[1:])
        self.stats = None
        self.timeline = Timeline()

    def print_timeline(self) -> None:
        for timestamp in self.timeline.log:
            print('{:.6f}s {}'.format(timestamp['duration'],
                                      timestamp['event']))

    def print_statistics(self):
        global exit_using_ctr_c
        if exit_using_ctr_c:
            summary.warn_sigint()

        self.print_timeline()
        print("=====================")
        print(summary.results_to_str(
            self.stats, self.timeline.log[-1]['duration'],
            self.args.concurrency
        ))
        print("=====================")
        if exit_using_ctr_c:
            print('\x1b[0m')

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

        self.timeline.start('Init data')
        for i in range(self.args.requests):
            self.tasks.put(i)

        for i in range(self.args.concurrency):
            self.tasks.put(None)
        self.timeline.finish()

        self.timeline.start('Create threads')
        for i in range(self.args.concurrency):
            thread = worker(self)
            threads.append(thread)
        self.timeline.finish()

        self.timeline.start('Run threads')
        for thread in threads:
            thread.start()

        thread_waiter = thread_waiter_worker(threads)
        thread_waiter.start()
        self.timeline.finish()

        self.timeline.start('Run tests')
        time.sleep(100000000)
        if not exit_using_ctr_c:
            thread_waiter.join()
        self.timeline.finish()

        self.output.put(None)
        self.output.join()

    def run(self):
        global exit_using_ctr_c

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
