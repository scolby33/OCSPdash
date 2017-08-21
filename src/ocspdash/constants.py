import os

OCSPDASH_DIRECTORY = os.path.join(os.path.expanduser('~'), '.ocspdash')

if not os.path.exists(OCSPDASH_DIRECTORY):
    os.makedirs(OCSPDASH_DIRECTORY)

OCSPDASH_DATABASE_PATH = os.path.join(OCSPDASH_DIRECTORY, 'ocspdash.db')
OCSPDASH_DATABASE_CONNECTION = 'sqlite:///' + OCSPDASH_DATABASE_PATH
