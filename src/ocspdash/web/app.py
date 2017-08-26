# -*- coding: utf-8 -*-
from collections import namedtuple, OrderedDict
from itertools import groupby
from operator import itemgetter
from pprint import pformat
from typing import List

from flask import Flask, Blueprint, render_template, jsonify, current_app, make_response, request
from flask_admin import Admin
from flask_admin.contrib.sqla import ModelView
from flask_bootstrap import Bootstrap
from flasgger import Swagger

from ..constants import OCSPDASH_DATABASE_CONNECTION, OCSPDASH_API_VERSION
from ..manager import Manager
from ..models import Authority, Responder, Chain, Result, Location
from .blueprints import api, ui


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
    Swagger(app) # Adds Swagger UI

    app.config.setdefault('OCSPDASH_CONNECTION')

    app.manager = Manager(
        connection=app.config.get('OCSPDASH_CONNECTION', OCSPDASH_DATABASE_CONNECTION),
        user=app.config.get('CENSYS_API_ID'),
        password=app.config.get('CENSYS_API_SECRET'),
    )

    app.manager.create_all()

    make_admin(app, app.manager.session)

    app.register_blueprint(api, url_prefix=f'/api/{OCSPDASH_API_VERSION}')
    app.register_blueprint(ui)

    return app

if __name__ == '__main__':
    create_application().run(debug=True)
