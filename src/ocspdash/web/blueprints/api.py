# -*- coding: utf-8 -*-

"""The OCSPdash API blueprint."""

import binascii
import io
import logging
import uuid
from base64 import urlsafe_b64decode as b64decode
from datetime import datetime
from functools import partial
from http import HTTPStatus

import jsonlines
from flask import Blueprint, abort, request
from jose import jwt
from jose.exceptions import JWTError

from ocspdash.constants import OCSP_JWT_ALGORITHM, OCSP_RESULTS_JWT_CLAIM
from ocspdash.web.proxies import manager

jwt.decode = partial(jwt.decode, algorithms=OCSP_JWT_ALGORITHM)

logger = logging.getLogger(__name__)

api = Blueprint('api', __name__)


@api.route('/register', methods=['POST'])  # noqa: C901
def register_location_key():
    """Register a public key for an invited location."""
    # TODO: error handling (what if no invite, what if duplicate name, etc.)
    print(request.data)
    try:
        unverified_claims = jwt.get_unverified_claims(request.data)
    except jwt.JWTError:
        abort(HTTPStatus.BAD_REQUEST, 'malformed JWT')

    try:
        unverified_public_key = b64decode(unverified_claims['pk']).decode('utf-8')
    except KeyError:
        abort(HTTPStatus.BAD_REQUEST, "'pk' missing from claims")
    except (binascii.Error, UnicodeError):
        abort(HTTPStatus.BAD_REQUEST, "failed to decode 'pk' claim")

    try:
        claims = jwt.decode(request.data, unverified_public_key)
    except JWTError:
        abort(HTTPStatus.BAD_REQUEST, 'failed to validate JWT')

    try:
        public_key = claims['pk']
    except KeyError:
        abort(HTTPStatus.BAD_REQUEST, "'pk' misisng from claims")

    try:
        invite_token = b64decode(claims['token'])
    except KeyError:
        abort(HTTPStatus.BAD_REQUEST, "'token' missing from claims")
    except binascii.Error:
        abort(HTTPStatus.BAD_REQUEST, "failed to decode 'token' claim")

    try:
        manager.process_location(invite_token, public_key)
    except ValueError:
        abort(HTTPStatus.BAD_REQUEST, 'bad invite or public key')

    return '', HTTPStatus.NO_CONTENT


@api.route('/manifest.jsonl')
def get_manifest():
    """Return the manifest of queries an OCSPscrape client should make.

    ---
    tags:
      - ocsp
    parameters:
      - name: n
        in: query
        description: Number of top authorities
        default: 10
        required: false
        type: integer
    """
    n = request.args.get('n', type=int, default=10)  # TODO make configurable at app level
    if n > 10:
        abort(HTTPStatus.BAD_REQUEST, 'n too large, max is 10')  # TODO get the max config value here too
    manifest_lines = io.StringIO()
    with jsonlines.Writer(manifest_lines, sort_keys=True) as writer:
        writer.write_all(
            chain.get_manifest_json()
            for chain in manager.get_most_recent_chains_for_authorities(n)
        )

    return manifest_lines.getvalue(), {
        'Content-Type': 'application/json', 'Content-Disposition': 'inline; filename="manifest.jsonl"'
    }


def _prepare_result_dictionary(result_data):
    certificate_chain_uuid: uuid.UUID = uuid.UUID(result_data['certificate_chain_uuid'])

    chain = manager.get_chain_by_certificate_chain_uuid(certificate_chain_uuid)
    if not chain:
        raise ValueError(f'No chain with certificate_chain_uuid: {certificate_chain_uuid}')

    retrieved = datetime.strptime(result_data['time'], '%Y-%m-%dT%H:%M:%SZ')

    return {
        'chain': chain,
        'retrieved': retrieved,
        'ping': result_data['ping'],
        'ocsp': result_data['ocsp']
    }


@api.route('/submit', methods=['POST'])
def submit():
    """Submit scrape results.

    ---
    tags:
        - ocsp
    """
    try:
        submitted_token_header = jwt.get_unverified_header(request.data)
    except jwt.JWTError:
        abort(HTTPStatus.BAD_REQUEST, 'malformed JWT')

    try:
        key_id = uuid.UUID(submitted_token_header['kid'])
    except KeyError:
        abort(HTTPStatus.BAD_REQUEST, "'kid' missing from JWT header")

    submitting_location = manager.get_location_by_key_id(key_id)
    if not submitting_location:
        abort(HTTPStatus.BAD_REQUEST, f'no location with key id: {key_id}')

    try:
        claims = jwt.decode(request.data, submitting_location.pubkey.decode('utf-8'))
    except JWTError:
        abort(HTTPStatus.BAD_REQUEST, 'failed to validate JWT')

    try:
        results = claims[OCSP_RESULTS_JWT_CLAIM]
    except KeyError:
        abort(HTTPStatus.BAD_REQUEST, f"'{OCSP_RESULTS_JWT_CLAIM}' missing from claims")

    try:
        prepared_result_dicts = (_prepare_result_dictionary(result_data)
                                 for result_data in results)
    except (KeyError, ValueError):
        abort(HTTPStatus.BAD_REQUEST, 'invalid result data')

    # TODO: can this raise an exception? I think yes if there's a constraint broken on the DB when commit is called()
    manager.insert_payload(submitting_location, prepared_result_dicts)

    return '', HTTPStatus.NO_CONTENT
