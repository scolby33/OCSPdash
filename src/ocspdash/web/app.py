# -*- coding: utf-8 -*-

"""Factories for creating the OCSPdash web UI Flask app."""

import logging
import os

from flasgger import Swagger
from flask import Flask
from flask_admin import Admin
from flask_admin.contrib.sqla import ModelView
from flask_bootstrap import Bootstrap
from flask_sqlalchemy import SQLAlchemy

from ocspdash.constants import OCSPDASH_API_VERSION, OCSPDASH_DEFAULT_CONNECTION
from ocspdash.manager import Manager
from ocspdash.models import (
    Authority, Chain, Location, Responder,
    Result,
)
from ocspdash.util import ToJSONCustomEncoder
from ocspdash.web.blueprints import api, ui

logger = logging.getLogger('web')

OCSPDASH_CONFIG = 'OCSPDASH_CONFIG'
OCSPDASH_CONNECTION = 'OCSPDASH_CONNECTION'


def make_admin(app: Flask, session) -> Admin:
    """Adds admin views to the app."""
    admin = Admin(app)

    admin.add_view(ModelView(Authority, session))
    admin.add_view(ModelView(Responder, session))

    class ChainView(ModelView):
        column_exclude_list = ['subject', 'issuer']

    admin.add_view(ChainView(Chain, session))
    admin.add_view(ModelView(Location, session))
    admin.add_view(ModelView(Result, session))

    return admin


def create_application() -> Flask:
    """Creates the OCSPdash Flask application."""
    app = Flask(__name__)

    ocspdash_config = os.environ.get(OCSPDASH_CONFIG)
    if ocspdash_config is not None:
        app.config.from_object(ocspdash_config)
    else:
        app.config.from_object('ocspdash.web.config.DefaultConfig')

    app.config.setdefault(OCSPDASH_CONNECTION, OCSPDASH_DEFAULT_CONNECTION)
    app.config['SQLALCHEMY_DATABASE_URI'] = app.config[OCSPDASH_CONNECTION]
    app.config.setdefault('SQLALCHEMY_TRACK_MODIFICATIONS', False)

    db = SQLAlchemy(app=app)
    Bootstrap(app)
    Swagger(app)  # Adds Swagger UI

    app.manager = Manager(engine=db.engine, session=db.session, server_query=None)

    app.json_encoder = ToJSONCustomEncoder

    make_admin(app, app.manager.session)

    app.register_blueprint(api, url_prefix=f'/api/{OCSPDASH_API_VERSION}')
    app.register_blueprint(ui)

    logger.info('created wsgi app')

    return app


if __name__ == '__main__':
    create_application().run(debug=True)
