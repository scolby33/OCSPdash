# -*- coding: utf-8 -*-

import os

import requests.utils

__all__ = [
    'OCSPDASH_API_VERSION',
    'OCSPDASH_DIRECTORY',
    'OCSPDASH_CONNECTION',
    'CENSYS_RATE_LIMIT',
    'OCSPDASH_USER_AGENT',
]

VERSION = '0.1.0-dev'

OCSPDASH_API_VERSION = 'v0'

#: The directory in which data for OCSP Dashboard is stored. Can be set from the environment variable
#: ``OCSPDASH_DIRECTORY`` or defaults to ``~/.ocspdash``
OCSPDASH_DIRECTORY = os.environ.get('OCSPDASH_DIRECTORY', os.path.join(os.path.expanduser('~'), '.ocspdash'))

if not os.path.exists(OCSPDASH_DIRECTORY):
    os.makedirs(OCSPDASH_DIRECTORY)

OCSPDASH_CONNECTION = 'sqlite:///' + os.path.join(OCSPDASH_DIRECTORY, 'ocspdash.db')

#: The rate limit for connecting to Censys. Can be set from the environmental variable ``OCSPDASH_RATE`` or defaults
# to ``0.2``.
CENSYS_RATE_LIMIT = float(os.environ.get('OCSPDASH_RATE', 0.2))  # max requests per second

OCSPDASH_USER_AGENT = ' '.join([requests.utils.default_user_agent(), f'OCSPdash/{VERSION}'])
