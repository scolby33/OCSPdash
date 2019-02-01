# -*- coding: utf-8 -*-

"""The OCSPdash API blueprint."""

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

    new_location = manager.process_location(invite_token, public_key)

    if new_location is None:
        return abort(400)

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
    n = request.args.get(  # TODO make configurable at app level
        'n', type=int, default=10
    )
    if n > 10:
        abort(400, 'n too large, max is 10')  # TODO get the max config value here too
    manifest_lines = io.StringIO()
    with jsonlines.Writer(manifest_lines, sort_keys=True) as writer:
        writer.write_all(
            chain.get_manifest_json()
            for chain in manager.get_most_recent_chains_for_authorities(n)
        )

    return (
        manifest_lines.getvalue(),
        {
            'Content-Type': 'application/json',
            'Content-Disposition': 'inline; filename="manifest.jsonl"',
        },
    )


def _prepare_result_dictionary(result_data):
    certificate_chain_uuid: uuid.UUID = uuid.UUID(result_data['certificate_chain_uuid'])
    chain = manager.get_chain_by_certificate_chain_uuid(certificate_chain_uuid)

    retrieved = datetime.strptime(result_data['time'], '%Y-%m-%dT%H:%M:%SZ')

    return {
        'chain': chain,
        'retrieved': retrieved,
        'ping': result_data['ping'],
        'ocsp': result_data['ocsp'],
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

    prepared_result_dicts = (
        _prepare_result_dictionary(result_data)
        for result_data in claims[OCSP_RESULTS_JWT_CLAIM]
    )
    manager.insert_payload(submitting_location, prepared_result_dicts)

    return ('', HTTPStatus.NO_CONTENT)
