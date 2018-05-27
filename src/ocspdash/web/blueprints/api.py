# -*- coding: utf-8 -*-

"""The OCSPdash API blueprint."""

import io
import logging
from base64 import urlsafe_b64decode as b64decode
from base64 import urlsafe_b64encode as b64encode

import jsonlines
from flask import Blueprint, current_app, jsonify, request
from jose import jwt
from jose.exceptions import JWTError

logger = logging.getLogger(__name__)

api = Blueprint('api', __name__)


@api.route('/register', methods=['POST'])
def register_location_key():
    """Register a public key for an invited location."""
    # TODO: error handling (what if no invite, what if duplicate name, etc.)
    unverified_claims = jwt.get_unverified_claims(request.data)
    unverified_public_key = b64decode(unverified_claims['pk']).decode('utf-8')
    try:
        claims = jwt.decode(request.data, unverified_public_key, 'ES512')  # todo move the algorithm into a constant
    except JWTError:
        return 400  # bad input

    public_key = claims['pk']

    invite_token = b64decode(claims['token'])

    new_location = current_app.manager.process_location(invite_token, public_key)

    if new_location is None:
        return 400
    else:
        return jsonify(new_location)


@api.route('/manifest.jsonl')
def get_manifest():
    """Return the manifest of queries an OCSPscrape client should make."""
    manifest_data = current_app.manager.get_manifest()

    manifest_lines = io.StringIO()
    with jsonlines.Writer(manifest_lines, sort_keys=True) as writer:
        writer.write_all(
            {
                'authority_name': authority_name,
                'responder_url': responder_url,
                'subject_certificate': b64encode(subject_certificate).decode('utf-8'),
                'issuer_certificate': b64encode(issuer_certificate).decode('utf-8')
            }
            for authority_name, responder_url, subject_certificate, issuer_certificate in manifest_data
        )

    return manifest_lines.getvalue(), {'Content-Type': 'application/json', 'Content-Disposition': 'inline; filename="manifest.jsonl"'}

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
