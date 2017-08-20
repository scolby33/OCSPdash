# -*- coding: utf-8 -*-

from flask import Flask, Blueprint, render_template
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


@ui.route('/')
def home():
    return render_template('index.html')


if __name__ == '__main__':
    create_application().run(debug=True)
