# -*- coding: utf-8 -*-

from flask import Flask, Blueprint, render_template, jsonify, current_app
from flask_admin import Admin
from flask_admin.contrib.sqla import ModelView
from flask_bootstrap import Bootstrap

from ocspdash.constants import OCSPDASH_DATABASE_CONNECTION
from ocspdash.web.manager import Manager
from ocspdash.web.models import Authority, Responder, Chain, User, Result

api = Blueprint('api', __name__)
ui = Blueprint('ui', __name__)


def make_admin(app: Flask, session):
    """Adds admin views to the app"""
    admin = Admin(app)

    admin.add_view(ModelView(Authority, session))
    admin.add_view(ModelView(Responder, session))

    class ChainView(ModelView):
        column_exclude_list = ['subject', 'issuer']

    admin.add_view(ChainView(Chain, session))
    admin.add_view(ModelView(User, session))
    admin.add_view(ModelView(Result, session))

    return admin


def create_application() -> Flask:
    """Creates the OCSPdash Flask application"""
    app = Flask(__name__)

    Bootstrap(app)

    app.config.setdefault('OCSPDASH_CONNECTION')

    app.manager = Manager(
        connection=app.config.get('OCSPDASH_CONNECTION', OCSPDASH_DATABASE_CONNECTION),
        user=app.config.get('CENSYS_API_ID'),
        password=app.config.get('CENSYS_API_SECRET'),
    )

    app.manager.create_all()

    make_admin(app, app.manager.session)

    app.register_blueprint(api)
    app.register_blueprint(ui)

    return app


example_payload = {
    'locations': [
        'CA, USA',
        'NY, USA',
        'NRW, DE',
    ],
    'data': [
        {
            'authority': "Let's Encrypt",
            'endpoints': [
                {
                    'url': 'http://ocsp.int-x3.letsencrypt.org',
                    'statuses': [
                        'good',
                        'questionable',
                        'bad',
                    ]
                },
                {
                    'url': 'http://ocsp.int-x2.letsencrypt.org',
                    'statuses': [
                        'unknown',
                        'unknown',
                        'unknown',
                    ]
                },
                {
                    'url': 'http://ocsp.int-x1.letsencrypt.org',
                    'statuses': [
                        'unknown',
                        'unknown',
                        'unknown',
                    ]
                }
            ]
        },
        {
            'authority': "cPanel, Inc.",
            'endpoints': [
                {
                    'url': 'http://ocsp.comodoca.com',
                    'statuses': [
                        'unknown',
                        'unknown',
                        'unknown',
                    ]
                }
            ]
        },
        {
            'authority': "COMODO CA Limited",
            'endpoints': [
                {
                    'url': 'http://ocsp.comodoca4.com',
                    'statuses': [
                        'unknown',
                        'unknown',
                        'unknown',
                    ]
                },
                {
                    'url': 'http://ocsp.comodoca2.com',
                    'statuses': [
                        'unknown',
                        'unknown',
                        'unknown',
                    ]
                },
                {
                    'url': 'http://ocsp.comodoca3.com',
                    'statuses': [
                        'unknown',
                        'unknown',
                        'unknown',
                    ]
                }
            ]
        }
    ]
}


@api.route('/status')
def get_payload():
    """Spits back the current payload"""
    return jsonify(example_payload)


@ui.route('/')
def home():
    """Shows the user the home view"""
    return render_template('index.html', payload=example_payload)


if __name__ == '__main__':
    create_application().run(debug=True)
