# -*- coding: utf-8 -*-

import logging
import os

from flasgger import Swagger
from flask import Flask
from flask_admin import Admin
from flask_admin.contrib.sqla import ModelView
from flask_bootstrap import Bootstrap
from flask_sqlalchemy import SQLAlchemy

from ocspdash.constants import OCSPDASH_API_VERSION, OCSPDASH_CONNECTION
from ocspdash.manager import BaseManager, Manager
from ocspdash.models import (Authority, Chain, Invite, Location, Responder,
                             Result)
from ocspdash.web.blueprints import api, ui

logger = logging.getLogger('web')


def make_admin(app: Flask, session) -> Admin:
    """Adds admin views to the app"""
    admin = Admin(app)

    admin.add_view(ModelView(Authority, session))
    admin.add_view(ModelView(Responder, session))

    class ChainView(ModelView):
        column_exclude_list = ['subject', 'issuer']

    admin.add_view(ChainView(Chain, session))
    admin.add_view(ModelView(Location, session))
    admin.add_view(ModelView(Result, session))
    admin.add_view(ModelView(Invite, session))

    return admin


def create_application() -> Flask:
    """Creates the OCSPdash Flask application"""
    app = Flask(__name__)

    if 'OCSPDASH_CONFIG' in os.environ:
        app.config.from_object(os.environ['OCSPDASH_CONFIG'])
    else:
        app.config.from_object('ocspdash.web.config.DefaultConfig')

    app.config.setdefault('OCSPDASH_CONNECTION', OCSPDASH_CONNECTION)
    app.config['SQLALCHEMY_DATABASE_URI'] = app.config['OCSPDASH_CONNECTION']
    app.config.setdefault('SQLALCHEMY_TRACK_MODIFICATIONS', False)

    db = SQLAlchemy(app=app)
    Bootstrap(app)
    Swagger(app)  # Adds Swagger UI

    class WebBaseManager(BaseManager):
        def __init__(self, *args, **kwargs):
            self.session = db.session
            self.engine = db.engine

    class WebManager(WebBaseManager, Manager):
        """Killin it with the MRO"""

    app.manager = WebManager(
        user=app.config['CENSYS_API_ID'],
        password=app.config['CENSYS_API_SECRET'],
    )

    app.manager.create_all()

    make_admin(app, app.manager.session)

    app.register_blueprint(api, url_prefix=f'/api/{OCSPDASH_API_VERSION}')
    app.register_blueprint(ui)

    logger.info('created wsgi app')

    return app


if __name__ == '__main__':
    create_application().run(debug=True)
