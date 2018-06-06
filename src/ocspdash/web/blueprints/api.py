# -*- coding: utf-8 -*-

"""The OCSPdash API blueprint."""

import io
import logging
import uuid
from base64 import urlsafe_b64decode as b64decode, urlsafe_b64encode as b64encode
from datetime import datetime
from functools import partial
from http import HTTPStatus

import jsonlines
from flask import Blueprint, abort, current_app, jsonify, request
from jose import jwt
from jose.exceptions import JWTError

from ocspdash.constants import OCSP_JWT_ALGORITHM
from ocspdash.models import Result

jwt.decode = partial(jwt.decode, algorithms=OCSP_JWT_ALGORITHM)

logger = logging.getLogger(__name__)

api = Blueprint('api', __name__)


@api.route('/register', methods=['POST'])
def register_location_key():
    """Register a public key for an invited location."""
    # TODO: error handling (what if no invite, what if duplicate name, etc.)
    unverified_claims = jwt.get_unverified_claims(request.data)
    unverified_public_key = b64decode(unverified_claims['pk']).decode('utf-8')

    try:
        claims = jwt.decode(request.data, unverified_public_key)
    except JWTError:
        return abort(400)  # bad input

    public_key = claims['pk']
    invite_token = b64decode(claims['token'])

    new_location = current_app.manager.process_location(invite_token, public_key)

    if new_location is None:
        return abort(400)

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

    return manifest_lines.getvalue(), {
        'Content-Type': 'application/json', 'Content-Disposition': 'inline; filename="manifest.jsonl"'
    }


@api.route('/submit', methods=['POST'])
def submit():
    """Submit scrape results."""
    submitted_token_header = jwt.get_unverified_header(request.data)

    key_id = uuid.UUID(submitted_token_header['kid'])
    submitting_location = current_app.manager.get_location_by_key_id(key_id)

    try:
        claims = jwt.decode(request.data, submitting_location.pubkey.decode('utf-8'))
    except JWTError:
        return abort(400)

    results = []
    for result in claims['res']:  # TODO: I know this should be a function on the manager
        authority = current_app.manager.get_authority_by_name(result['authority_name'])
        responder = current_app.manager.get_responder(authority, result['responder_url'])
        chain = responder.most_recent_chain  # TODO: this is a possibly-invalid assumption about which chain the result is for
        result = Result(
            chain=chain,
            location=submitting_location,
            retrieved=datetime.strptime(result['time'], '%Y-%m-%dT%H:%M:%SZ'),
            ping=result['ping'],
            ocsp=result['ocsp']
        )
        results.append(result)
        current_app.manager.session.add(result)

    current_app.manager.session.commit()

    return ('', HTTPStatus.NO_CONTENT)


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
