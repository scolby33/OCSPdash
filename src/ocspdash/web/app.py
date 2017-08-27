# -*- coding: utf-8 -*-

import os

from flasgger import Swagger
from flask import Flask
from flask_admin import Admin
from flask_admin.contrib.sqla import ModelView
from flask_bootstrap import Bootstrap

from ocspdash.constants import OCSPDASH_DATABASE_CONNECTION, OCSPDASH_API_VERSION
from ocspdash.manager import Manager
from ocspdash.models import Authority, Responder, Chain, Result, Location
from ocspdash.web.blueprints import api, ui


def make_admin(app: Flask, session):
    """Adds admin views to the app"""
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
    """Creates the OCSPdash Flask application"""
    app = Flask(__name__)

    Bootstrap(app)
    Swagger(app)  # Adds Swagger UI

    if 'OCSPDASH_BUILD_DOCKER' in os.environ:
        app.config.from_object('ocspdash.web.config.DockerConfig')

    app.config.setdefault('OCSPDASH_CONNECTION', OCSPDASH_DATABASE_CONNECTION)

    app.manager = Manager(
        connection=app.config['OCSPDASH_CONNECTION'],
        user=app.config['CENSYS_API_ID'],
        password=app.config['CENSYS_API_SECRET'],
    )

    app.manager.create_all()

    make_admin(app, app.manager.session)

    app.register_blueprint(api, url_prefix=f'/api/{OCSPDASH_API_VERSION}')
    app.register_blueprint(ui)

    return app


if __name__ == '__main__':
    create_application().run(debug=True)
