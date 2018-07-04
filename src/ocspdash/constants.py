# -*- coding: utf-8 -*-

"""Constants used by OCSPdash."""

import os
import uuid

import requests.utils

__all__ = [
    'NAMESPACE_OCSPDASH_KID',
    'OCSPDASH_API_VERSION',
    'OCSPDASH_DIRECTORY',
    'OCSPDASH_DEFAULT_CONNECTION',
    'OCSPDASH_CONNECTION',
    'CENSYS_RATE_LIMIT',
    'OCSPDASH_USER_AGENT_IDENTIFIER',
    'OCSPDASH_USER_AGENT',
    'OCSP_RESULTS_JWT_CLAIM',
    'OCSP_JWT_ALGORITHM',
]

VERSION = '0.1.0-dev'

NAMESPACE_OCSPDASH_KID = uuid.UUID('c81dcfc6-2131-4d05-8ea4-4e5ad8123696')

OCSPDASH_API_VERSION = 'v0'

#: The directory in which data for OCSP Dashboard is stored. Can be set from the environment variable
#: ``OCSPDASH_DIRECTORY`` or defaults to ``~/.ocspdash``
OCSPDASH_DIRECTORY = os.environ.get('OCSPDASH_DIRECTORY', os.path.join(os.path.expanduser('~'), '.ocspdash'))

if not os.path.exists(OCSPDASH_DIRECTORY):
    os.makedirs(OCSPDASH_DIRECTORY)

OCSPDASH_DEFAULT_CONNECTION = 'sqlite:///' + os.path.join(OCSPDASH_DIRECTORY, 'ocspdash.db')
OCSPDASH_CONNECTION = os.environ.get('OCSPDASH_CONNECTION', OCSPDASH_DEFAULT_CONNECTION)

#: The rate limit for connecting to Censys. Can be set from the environmental variable ``OCSPDASH_RATE`` or defaults
# to ``0.2``.
CENSYS_RATE_LIMIT = float(os.environ.get('OCSPDASH_RATE', 0.2))  # max requests per second

OCSPDASH_USER_AGENT_IDENTIFIER = f'OCSPdash/{VERSION}'
OCSPDASH_USER_AGENT = ' '.join([requests.utils.default_user_agent(), OCSPDASH_USER_AGENT_IDENTIFIER])

OCSP_RESULTS_JWT_CLAIM = os.environ.get('OCSPDASH_RESULTS_JWT_CLAIM', 'res')
OCSP_JWT_ALGORITHM = os.environ.get('OCSPDASH_JWT_ALGORITHM', 'ES512')
