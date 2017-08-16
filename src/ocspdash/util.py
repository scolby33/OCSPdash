from functools import wraps
import logging
import threading
import time
from typing import Callable, Union

import censys.certificates

logger = logging.getLogger(__name__)


def rate_limited(max_per_second: Union[int, float]) -> Callable:
    """Decorator to rate-limit a function or method. Only one call will be allowed at a time.

    :param max_per_second: The maximum number of calls to the function that will be allowed per second
    """
    lock = threading.Lock()
    min_interval = 1.0 / max_per_second

    def decorate(func: Callable) -> Callable:
        """Decorate the function to rate limit it

        :param func: The function being decorated
        """
        last_time_called = 0

        @wraps(func)
        def rate_limited_function(*args, **kwargs):
            lock.acquire()
            nonlocal last_time_called
            try:
                elapsed = time.perf_counter() - last_time_called
                left_to_wait = min_interval - elapsed
                if left_to_wait > 0:
                    logger.debug(f'throttling {left_to_wait:f}s... ')
                    time.sleep(left_to_wait)

                last_time_called = time.perf_counter()
                return func(*args, **kwargs)
            finally:
                lock.release()

        return rate_limited_function

    return decorate

censys_rate_limit = rate_limited(0.4)


class RateLimitedCensysCertificates(censys.certificates.CensysCertificates):
    """A :class:`censys.certificates.CensysCertificates` subclass with the :meth:`search` and :meth:`report` methods rate-limited to 0.4 calls/sec"""
    @censys_rate_limit
    def search(self, *args, **kwargs):
        return super().search(*args, **kwargs)

    @censys_rate_limit
    def report(self, *args, **kwargs):
        return super().report(*args, **kwargs)
