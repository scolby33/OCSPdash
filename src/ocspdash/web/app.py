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



def make_admin(app: Flask, session) -> Admin:
    """Add admin views to the app."""
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
    """Create the OCSPdash Flask application."""
    app = Flask(__name__)
    app.config.update(dict(
        SQLALCHEMY_DATABASE_URI=os.environ.get('OCSPDASH_CONNECTION', OCSPDASH_DEFAULT_CONNECTION),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SECRET_KEY=os.environ.get('OCSPDASH_SECRET_KEY', 'test key'),
        DEBUG=os.environ.get('OCSPDASH_DEBUG', False),
        CENSYS_API_ID=os.environ.get('CENSYS_API_ID'),
        CENSYS_API_SECRET=os.environ.get('CENSYS_API_SECRET'),
    ))



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
