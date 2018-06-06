# -*- coding: utf-8 -*-

"""Miscellaneous utilities for OCSPdash."""

import logging
import threading
import time
from functools import wraps
from json import JSONEncoder
from typing import Callable, Union

import censys.certificates
from requests import Session

from ocspdash.constants import CENSYS_RATE_LIMIT, OCSPDASH_USER_AGENT

logger = logging.getLogger(__name__)

requests_session = Session()
requests_session.headers.update({'User-Agent': OCSPDASH_USER_AGENT})


class ToJSONCustomEncoder(JSONEncoder):
    """A customized JSON encoder that first tries to use the `to_json` attribute to encode an object."""

    def default(self, obj):  # noqa: 401
        """Try to use the `to_json` attribute to encode before trying the default."""
        to_json = getattr(obj, 'to_json', None)
        if to_json:
            return to_json()
        else:
            return super().default(obj)


def rate_limited(max_per_second: Union[int, float]) -> Callable:
    """Create a decorator to rate-limit a function or method. Only one call will be allowed at a time.

    :param max_per_second: The maximum number of calls to the function that will be allowed per second
    """
    lock = threading.Lock()
    min_interval = 1.0 / max_per_second

    def decorate(func: Callable) -> Callable:
        """Decorate the function to rate limit it.

        :param func: The function being decorated
        """
        last_time_called = 0

        @wraps(func)
        def rate_limited_function(*args, **kwargs):
            with lock:
                nonlocal last_time_called
                elapsed = time.perf_counter() - last_time_called
                left_to_wait = min_interval - elapsed
                if left_to_wait > 0:
                    logger.debug(f'throttling {left_to_wait:f}s... ')
                    time.sleep(left_to_wait)

                last_time_called = time.perf_counter()
                return func(*args, **kwargs)

        return rate_limited_function

    return decorate


censys_rate_limit = rate_limited(CENSYS_RATE_LIMIT)


class RateLimitedCensysCertificates(censys.certificates.CensysCertificates):
    """A :class:`censys.certificates.CensysCertificates` subclass with the :meth:`search` and :meth:`report` methods rate-limited to :data:`CENSYS_RATE_LIMIT` calls/sec."""

    @censys_rate_limit
    def search(self, *args, **kwargs):
        """Call the superclass' search method while remaining under the global rate limit."""
        return super().search(*args, **kwargs)

    @censys_rate_limit
    def report(self, *args, **kwargs):
        """Call the superclass' report method while remaining under the global rate limit."""
        return super().report(*args, **kwargs)
