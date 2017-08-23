import os

import requests.utils

from . import __name__, __version__

OCSPDASH_API_VERSION = 'v0'

OCSPDASH_DIRECTORY = os.path.join(os.path.expanduser('~'), '.ocspdash')

if not os.path.exists(OCSPDASH_DIRECTORY):
    os.makedirs(OCSPDASH_DIRECTORY)

OCSPDASH_DATABASE_PATH = os.path.join(OCSPDASH_DIRECTORY, 'ocspdash.db')
OCSPDASH_DATABASE_CONNECTION = 'sqlite:///' + OCSPDASH_DATABASE_PATH

CENSYS_RATE_LIMIT = 0.2  # max requests per second

OCSPDASH_USER_AGENT = ' '.join([requests.utils.default_user_agent(), f'{__name__}/{__version__}'])
