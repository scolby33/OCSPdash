import base64
from hmac import compare_digest
from pprint import pformat

from flask import Blueprint, jsonify, current_app, make_response, request

from ...models import Authority, Responder, Location

api = Blueprint('api', __name__)


# @api.route('/status')
# def get_payload():
#     """Spits back the current payload"""
#     return jsonify(make_payload())  # TODO: make JSON serializable


@api.route('/recent')
def get_recent():
    """Get the most recent result set"""
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


@api.route('/responder')
def get_responders():
    return jsonify([
        responder.to_json()
        for responder in current_app.manager.session.query(Responder).all()
    ])


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


@api.route('/register', methods=['POST'])
def register_location_key():
    location_id, registration_token = request.headers['authorization'].split(':', 1)
    registration_token_bytes = base64.urlsafe_b64decode(registration_token)
    location = current_app.manager.session.query(Location).get(int(location_id))
    if not location.activated and compare_digest(location.pubkey, registration_token_bytes):
        pubkey = request.data
        location.pubkey = pubkey
        location.activated = True
        current_app.manager.session.commit()
        return str(location.id), 200
    else:
        return '', 401
