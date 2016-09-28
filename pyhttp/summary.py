"""Benchmark summary related utilities."""

from typing import List


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


def results_to_str(stats: list, times: List[float], concurrency: int) -> None:
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

    lines = [
        'Document Length:    [min: %d, avg: %f, max: %d] Bytes' % (min(size), avg(size), max(size)),
        'Concurrency Level:    %d' % (concurrency),
        'Complete requests:    %d' % (completed_results),
        'Requests per second:    %f [#/sec] (mean)' % (completed_results / (times[4] - times[3])),
        'Connection Times Total:    [min: %f, avg: %f, max: %f] seconds' % (min(time), avg(time), max(time)),
        'Status codes:',
    ]
    for code in retcode:
        lines.append('\t%s %d' % (code, retcode[code]))

    return '\n'.join(lines)


def inc(array, index):
    if not index in array:
        array[index] = 0
    array[index] = array[index] + 1


def avg(iter):
    return sum(iter) / len(iter)
