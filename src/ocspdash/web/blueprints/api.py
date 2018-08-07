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
        return 'malformed JWT', HTTPStatus.BAD_REQUEST

    try:
        unverified_public_key = b64decode(unverified_claims['pk']).decode('utf-8')
    except KeyError:
        return "'pk' missing from unverified claims", HTTPStatus.BAD_REQUEST
    except (binascii.Error, UnicodeError):
        abort(400)  # bad data in 'pk' claim
        return "failed to decode 'pk' claim", HTTPStatus.BAD_REQUEST

    try:
        claims = jwt.decode(request.data, unverified_public_key)
    except JWTError:
        return 'failed to validate JWT', HTTPStatus.BAD_REQUEST

    try:
        public_key = claims['pk']
    except KeyError:
        return "'pk' misisng from verified claims", HTTPStatus.BAD_REQUEST

    try:
        invite_token = b64decode(claims['token'])
    except KeyError:
        return "'token' missing from verified claims", HTTPStatus.BAD_REQUEST
    except binascii.Error:
        return "failed to decode 'token' claim", HTTPStatus.BAD_REQUEST

    try:
        manager.process_location(invite_token, public_key)
    except ValueError:
        return 'bad invite or public key', HTTPStatus.BAD_REQUEST

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
        abort(400, 'n too large, max is 10')  # TODO get the max config value here too
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
    submitted_token_header = jwt.get_unverified_header(request.data)

    key_id = uuid.UUID(submitted_token_header['kid'])
    submitting_location = manager.get_location_by_key_id(key_id)

    try:
        claims = jwt.decode(request.data, submitting_location.pubkey.decode('utf-8'))
    except JWTError:
        return abort(400)

    prepared_result_dicts = (_prepare_result_dictionary(result_data)
                             for result_data in claims[OCSP_RESULTS_JWT_CLAIM])
    manager.insert_payload(submitting_location, prepared_result_dicts)

    return ('', HTTPStatus.NO_CONTENT)
