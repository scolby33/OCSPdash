# -*- coding: utf-8 -*-

"""Factories for creating the OCSPdash web UI Flask app."""

import logging
import os
from typing import Optional

#from flasgger import Swagger
from flask import Flask
from flask_bootstrap import Bootstrap

from ocspdash.constants import OCSPDASH_API_VERSION, OCSPDASH_CONNECTION
from ocspdash.util import ToJSONCustomEncoder
from ocspdash.web.admin import make_admin
from ocspdash.web.blueprints import api, ui
from ocspdash.web.extension import OCSPSQLAlchemy

__all__ = ['create_application']

logger = logging.getLogger('web')


def create_application(
    connection: Optional[str] = None, flask_debug: bool = False
) -> Flask:
    """Create the OCSPdash Flask application.

    :param connection: Database connection string
    :param flask_debug: Enable Flask debug mode, overridden by env $DEBUG
    """
    app = Flask(__name__)
    app.config.update(
        dict(
            SQLALCHEMY_DATABASE_URI=connection or OCSPDASH_CONNECTION,
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
            SECRET_KEY=os.environ.get('SECRET_KEY', 'test key'),
            DEBUG=os.environ.get('DEBUG', flask_debug),
            CENSYS_API_ID=os.environ.get('CENSYS_API_ID'),
            CENSYS_API_SECRET=os.environ.get('CENSYS_API_SECRET'),
        )
    )
    db = OCSPSQLAlchemy(app=app)

    Bootstrap(app)
    #Swagger(app)  # Adds Swagger UI

    app.manager = db.manager
    app.json_encoder = ToJSONCustomEncoder

    if app.debug:
        make_admin(app, db.session)

    app.register_blueprint(api, url_prefix=f'/api/{OCSPDASH_API_VERSION}')
    app.register_blueprint(ui)

    logger.info('created wsgi app')

    return app


if __name__ == '__main__':
    create_application().run(debug=True)
