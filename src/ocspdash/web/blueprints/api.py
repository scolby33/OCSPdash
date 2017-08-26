import base64
from hmac import compare_digest

from flask import Blueprint, jsonify, current_app, request

from ...models import Authority, Responder

api = Blueprint('api', __name__)


@api.route('/status')
def get_payload():
    """Spits back the current payload"""
    payload = current_app.manager.make_payload()

    return jsonify(payload)


@api.route('/recent')
def get_recent():
    """Get the most recent result set"""
    result = current_app.manager.get_most_recent_result_for_each_location()

    return jsonify(result)


@api.route('/authority')
def get_authorities():
    return jsonify([
        authority.to_json()
        for authority in current_app.manager.session.query(Authority).all()
    ])


@api.route('/authority/<int:authority_id>')
def get_authority(authority_id):
    authority = current_app.manager.get_authority_by_id(authority_id)

    return jsonify(authority.to_json())


@api.route('/responder')
def get_responders():
    return jsonify([
        responder.to_json()
        for responder in current_app.manager.session.query(Responder).all()
    ])


@api.route('/responder/<int:responder_id>')
def get_responder(responder_id):
    responder = current_app.manager.get_responder_by_id(responder_id)

    return jsonify(responder.to_json())


@api.route('/responder/<int:responder_id>/chain')
def get_responder_chains(responder_id):
    responder = current_app.manager.get_responder_by_id(responder_id)

    return jsonify([
        chain.to_json()
        for chain in responder.chains
    ])


@api.route('/responder/<int:responder_id>/result')
def get_responder_results(responder_id):
    responder = current_app.manager.get_responder_by_id(responder_id)

    return jsonify([
        result.to_json()
        for chain in responder.chains
        for result in chain.results
    ])


@api.route('/register', methods=['POST'])
def register_location_key():
    location_id, registration_token = request.headers['authorization'].split(':', 1)
    registration_token_bytes = base64.urlsafe_b64decode(registration_token)
    if not location.activated and compare_digest(location.pubkey, registration_token_bytes):
        pubkey = request.data
        location.pubkey = pubkey
        location.activated = True
        current_app.manager.session.commit()
        return str(location.id), 200
    else:
        return '', 401
    location = current_app.manager.get_location_by_id(int(location_id))
