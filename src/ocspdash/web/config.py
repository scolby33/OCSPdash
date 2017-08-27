# -*- coding: utf-8 -*-

import os


class DockerConfig(object):
    """Follows format from guide at https://realpython.com/blog/python/dockerizing-flask-with-compose-and-machine-from-localhost-to-the-cloud/"""
    SECRET_KEY = os.environ['OCSPDASH_SECRET_KEY']
    DEBUG = os.environ['OCSPDASH_DEBUG']

    DB_NAME = os.environ['OCSPDASH_DB_NAME']
    DB_USER = os.environ['OCSPDASH_DB_USER']
    DB_PASS = os.environ['OCSPDASH_DB_PASS']
    DB_SERVICE = os.environ['OCSPDASH_DB_SERVICE']
    DB_PORT = os.environ['OCSPDASH_DB_PORT']

    OCSPDASH_CONNECTION = 'postgresql://{0}:{1}@{2}:{3}/{4}'.format(
        DB_USER, DB_PASS, DB_SERVICE, DB_PORT, DB_NAME
    )
