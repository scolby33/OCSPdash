# -*- coding: utf-8 -*-

import os

from ocspdash.constants import OCSPDASH_CONNECTION


class DefaultConfig(object):
    SECRET_KEY = os.environ.get('OCSPDASH_SECRET_KEY', 'test key')
    DEBUG = os.environ.get('OCSPDASH_DEBUG', False)

    CENSYS_API_ID = os.environ.get('CENSYS_API_ID')
    CENSYS_API_SECRET = os.environ.get('CENSYS_API_SECRET')

    OCSPDASH_CONNECTION = OCSPDASH_CONNECTION


class DockerConfig(DefaultConfig):
    """Follows format from guide at https://realpython.com/blog/python/dockerizing-flask-with-compose-and-machine-from-localhost-to-the-cloud/"""
    DB_DATABASE = os.environ.get('OCSPDASH_DB_DATABASE')
    DB_USER = os.environ.get('OCSPDASH_DB_USER')
    DB_PASSWORD = os.environ.get('OCSPDASH_DB_PASSWORD')
    DB_HOST = os.environ.get('OCSPDASH_DB_HOST')

    OCSPDASH_CONNECTION = 'mysql+pymysql://{user}:{password}@{host}/{database}?charset={charset}'.format(
        user=DB_USER,
        host=DB_HOST,
        password=DB_PASSWORD,
        database=DB_DATABASE,
        charset='utf8'
    )
