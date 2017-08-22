# -*- coding: utf-8 -*-
from collections import namedtuple, OrderedDict
from itertools import groupby
from pprint import pformat
from operator import itemgetter
from typing import List

from flask import Flask, Blueprint, render_template, jsonify, current_app, make_response
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


@api.route('/status')
def get_payload():
    """Spits back the current payload"""
    return jsonify(make_payload())  # TODO: make JSON serializable


@api.route('/recent')
def get_recent():
    result = current_app.manager.get_most_recent_result_for_each_location()
    f = pformat(result)
    return make_response(f, {'Content-Type': 'text/plain'})
    # return render_template('recent.html', payload=result)


@api.route('/authority')
def get_authorities():
    return jsonify([
        authority.to_json()
        for authority in current_app.manager.session.query(Authority).all()
    ])


@api.route('/authority/<int:authority_id>')
def get_authority(authority_id):
    return jsonify(current_app.manager.session.query(Authority).get(authority_id).to_json())


@api.route('/responder/<int:responder_id>')
def get_responder(responder_id):
    return jsonify(current_app.manager.session.query(Responder).get(responder_id).to_json())


@api.route('/responder/<int:responder_id>/chain')
def get_responder_chains(responder_id):
    return jsonify([
        chain.to_json()
        for chain in current_app.manager.session.query(Responder).get(responder_id).chains
    ])


@api.route('/responder/<int:responder_id>/result')
def get_responder_results(responder_id):
    return jsonify([
        result.to_json()
        for chain in current_app.manager.session.query(Responder).get(responder_id).chains
        for result in chain.results
    ])


@api.route('/responder')
def get_responders():
    return jsonify([
        responder.to_json()
        for responder in current_app.manager.session.query(Responder).all()
    ])


@ui.route('/')
def home():
    """Shows the user the home view"""
    payload = make_payload()
    return render_template('index.html', payload=payload)


def make_payload():
    locations: List[User] = current_app.manager.get_all_locations_with_test_results()
    Row = namedtuple('Row', f'url current {" ".join(user.location for user in locations)}')
    Row.__new__.__defaults__ = (None,) * (len(Row._fields) - 2)

    sections = OrderedDict()
    for authority, group in groupby(current_app.manager.get_most_recent_result_for_each_location(), itemgetter(0)):
        sections[authority.name] = []
        for responder, group2 in groupby(group, itemgetter(1)):
            results = {
                user.location: result
                for _, _, result, user in group2
            }
            row = Row(url=responder.url, current=responder.current, **results)
            sections[authority.name].append(row)

    return {
        'locations': locations,
        'sections': sections
    }


if __name__ == '__main__':
    create_application().run(debug=True)
