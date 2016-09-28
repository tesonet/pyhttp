"""Benchmark summary related utilities."""

from typing import List, Dict


def warn_sigint() -> None:
    print('\x1b[1;101;92m')
    print('!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!')
    print('!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!')
    print('!!!!                                          !!!!')
    print('!!!!  WARNING:                                !!!!')
    print('!!!!  CTR+C is DETECTED                       !!!!')
    print('!!!!  You terminating your benchmark session  !!!!')
    print('!!!!                                          !!!!')
    print('!!!!  This will make benchmark                !!!!')
    print('!!!!  results meaningless.                    !!!!')
    print('!!!!                                          !!!!')
    print('!!!!  DO NOT PUBLISH THESE RESULTS OR         !!!!')
    print('!!!!  MAKE ANY DECISIONS BASED ON THEM        !!!!')
    print('!!!!                                          !!!!')
    print('!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!')
    print('!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!')
    print('\x1b[2;47;37m')


class BenchmarkResults:
    def __init__(self, min_doc_len: int, avg_doc_len: int, max_doc_len: int,
                 concurrency: int, completed_requests: int, reqs_per_sec: int,
                 min_conn_time: int, avg_conn_time: int, max_conn_time: int,
                 status_codes: Dict[int, int]) -> None:
        self.min_doc_len = min_doc_len
        self.avg_doc_len = avg_doc_len
        self.max_doc_len = max_doc_len
        self.concurrency = concurrency
        self.completed_requests = completed_requests
        self.reqs_per_sec = reqs_per_sec
        self.min_conn_time = min_conn_time
        self.avg_conn_time = avg_conn_time
        self.max_conn_time = max_conn_time
        self.status_codes = status_codes


def make_benchmark_results(stats: list, times: List[float],
                 concurrency: int) -> BenchmarkResults:
    retcode = {}
    retcode[200] = 0
    retcode[404] = 0
    retcode[500] = 0

    size = []
    time = []

    completed_results = 0
    for stat in stats:
        if 'size' in stat:
            size.append(stat['size'])
            completed_results = completed_results + 1

        if 'time' in stat:
            time.append(stat['time'])

        if 'status' in stat:
            inc(retcode, stat['status'])

    return BenchmarkResults(
            min(size), avg(size), max(size), concurrency, completed_results,
            completed_results / (times[4] - times[3]),
            min(time), avg(time), max(time), retcode)


def results_to_str(stats: list, times: List[float], concurrency: int) -> None:
    results = make_benchmark_results(stats, times, concurrency)
    lines = [
        'Document Length:    [min: %d, avg: %f, max: %d] Bytes' \
            % (results.min_doc_len, results.avg_doc_len, results.max_doc_len),
        'Concurrency Level:    %d' % (results.concurrency),
        'Complete requests:    %d' % (results.completed_requests),
        'Requests per second:    %f [#/sec] (mean)' % (results.reqs_per_sec),
        'Connection Times Total:    [min: %f, avg: %f, max: %f] seconds' \
            % (results.min_conn_time, results.avg_conn_time,
               results.max_conn_time),
        'Status codes:',
    ]
    for status_code, count in results.status_codes.items():
        lines.append('\t%s %d' % (status_code, count))

    return '\n'.join(lines)


def inc(array, index):
    if not index in array:
        array[index] = 0
    array[index] = array[index] + 1


def avg(iter):
    return sum(iter) / len(iter)
