# -*- coding: utf-8 -*-

import logging
import uuid
from base64 import urlsafe_b64decode as b64decode

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from flask import Blueprint, jsonify, current_app, request
from jose import jwt
from jose.exceptions import JWTError

from ocspdash.constants import NAMESPACE_OCSPDASH_KID
# from ocspdash.models import Authority, Responder
from ocspdash.models import Location

logger = logging.getLogger(__name__)

api = Blueprint('api', __name__)


@api.route('/register', methods=['POST'])
def register_location_key():
    # TODO: error handling (what if no invite, what if duplicate name, etc.)
    # TODO: what type do I really want pubkey to be? Binary, bytes but including ----BEGIN----, etc?)
    unverified_claims = jwt.get_unverified_claims(request.data)

    unverified_public_key = b64decode(unverified_claims['pk']).decode('utf-8')
    try:
        claims = jwt.decode(request.data, unverified_public_key, 'ES512')  # todo move the algorithm into a constant
    except JWTError:
        return 400  # bad input

    # todo get this in a form for cryptography to use?--bytes for jwt?
    public_key = claims['pk']

    invite_token = b64decode(claims['token'])
    if len(invite_token) != 32:
        return 400  # bad input

    invite_id = invite_token[:16]
    invite_validator = invite_token[16:]

    # select the token with invite_id
    invite = current_app.manager.get_invite_by_selector(invite_id)

    ph = PasswordHasher()
    try:
        ph.verify(invite.invite_validator, invite_validator)
    except VerifyMismatchError:
        return 400  # todo better response

    # now that we know the invite is valid, verify keyid
    key_id = uuid.uuid5(NAMESPACE_OCSPDASH_KID, public_key)
    if str(key_id) != claims['kid']:
        return 400

    new_location = Location(
        name=invite.name,
        pubkey=b64decode(public_key),
        key_id=key_id
    )
    current_app.manager.session.add(new_location)
    current_app.manager.session.delete(invite)
    current_app.manager.session.commit()

    logger.debug(new_location.to_json())

    return jsonify(new_location.to_json())

# @api.route('/status')
# def get_payload():
#     """Spits back the current payload"""
#     payload = current_app.manager.make_payload()
#
#     return jsonify(payload)


# @api.route('/recent')
# def get_recent():
#     """Get the most recent result set"""
#     result = current_app.manager.get_most_recent_result_for_each_location()
#
#     return jsonify(result)


# @api.route('/authority')
# def get_authorities():
#     return jsonify([
#         authority.to_json()
#         for authority in current_app.manager.session.query(Authority).all()
#     ])


# @api.route('/authority/<int:authority_id>')
# def get_authority(authority_id):
#     authority = current_app.manager.get_authority_by_id(authority_id)
#
#     return jsonify(authority.to_json())


# @api.route('/responder')
# def get_responders():
#     return jsonify([
#         responder.to_json()
#         for responder in current_app.manager.session.query(Responder).all()
#     ])


# @api.route('/responder/<int:responder_id>')
# def get_responder(responder_id):
#     responder = current_app.manager.get_responder_by_id(responder_id)
#
#     return jsonify(responder.to_json())


# @api.route('/responder/<int:responder_id>/chain')
# def get_responder_chains(responder_id):
#     responder = current_app.manager.get_responder_by_id(responder_id)
#
#     return jsonify([
#         chain.to_json()
#         for chain in responder.chains
#     ])


# @api.route('/responder/<int:responder_id>/result')
# def get_responder_results(responder_id):
#     responder = current_app.manager.get_responder_by_id(responder_id)
#
#     return jsonify([
#         result.to_json()
#         for chain in responder.chains
#         for result in chain.results
#     ])
