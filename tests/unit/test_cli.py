from hamcrest import assert_that, is_
import pytest

from pyhttp.cli import parse_args


def describe_parse_args():
    def it_returns_parsed_arguments():
        args = parse_args(['-c', '100', 'http://example.com'])

        assert_that(args.concurrency, is_(100))
        assert_that(args.url, is_('http://example.com'))
