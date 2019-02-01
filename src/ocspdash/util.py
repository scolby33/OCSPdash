# -*- coding: utf-8 -*-

"""Miscellaneous utilities for OCSPdash."""

import collections
import hashlib
import logging
import threading
import time
import uuid
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


class OrderedDefaultDict(collections.OrderedDict):
    """A defaultdict with OrderedDict as its base class."""

    def __init__(self, default_factory: Callable = None, *args, **kwargs) -> None:
        """Create a dict with a default factory that remembers insertion order.

        :param default_factory: The default factory is called without arguments when a key is missing
        """
        if not (default_factory is None or callable(default_factory)):
            raise TypeError('first argument must be callable or None')
        super().__init__(*args, **kwargs)
        self.default_factory = default_factory  # called by __missing__

    def __missing__(self, key):
        if self.default_factory is None:
            raise KeyError(key)
        self[key] = value = self.default_factory()
        return value

    def __reduce__(self):  # for pickle support
        args = (self.default_factory,) if self.default_factory else tuple()
        return self.__class__, args, None, None, self.items()

    def __repr__(self):
        return '%s(%r, %r)' % (
            self.__class__.__name__,
            self.default_factory,
            list(self.items()),
        )


def uuid5(namespace: uuid.UUID, name: Union[str, bytes]) -> uuid.UUID:
    """Generate a UUID from the SHA-1 hash of a namespace UUID and a name.

    Unlike the stdlib version, the name can be bytes. If it is a str, this function delgates to the stdlib.

    :param namespace: The UUID namespace identifier
    :param name: The name, which is a str or bytes

    :returns: The UUID version 5
    """
    if isinstance(name, str):
        return uuid.uuid5(namespace, name)
    else:
        hash = hashlib.sha1(namespace.bytes + name).digest()
        return uuid.UUID(bytes=hash[:16], version=5)


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
        last_time_called: float = 0.0

        @wraps(func)
        def rate_limited_function(*args, **kwargs):
            with lock:
                nonlocal last_time_called
                elapsed = time.perf_counter() - last_time_called
                left_to_wait = min_interval - elapsed
                if left_to_wait > 0:
                    logger.debug('throttling %.2fs', left_to_wait)
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
