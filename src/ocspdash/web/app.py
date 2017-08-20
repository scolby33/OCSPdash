# -*- coding: utf-8 -*-

from flask import Flask, Blueprint, render_template, jsonify
from flask_bootstrap import Bootstrap

api = Blueprint('api', __name__)
ui = Blueprint('ui', __name__)


def create_application():
    """Creates the OCSPdash Flask application

    :rtype: flask.Flask
    """
    app = Flask(__name__)

    Bootstrap(app)

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
