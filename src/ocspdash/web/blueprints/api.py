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
from flask import Blueprint, jsonify, request
from jose import jwt
from jose.exceptions import JWTError

from ocspdash.constants import OCSP_JWT_ALGORITHM, OCSP_RESULTS_JWT_CLAIM
from ocspdash.web.exceptions import InvalidUsage
from ocspdash.web.proxies import manager

jwt.decode = partial(jwt.decode, algorithms=OCSP_JWT_ALGORITHM)

logger = logging.getLogger(__name__)

api = Blueprint('api', __name__)


@api.route('/register', methods=['POST'])  # noqa: C901
def register_location_key():
    """Register a public key for an invited location."""
    # TODO: error handling (what if no invite, what if duplicate name, etc.)
    try:
        unverified_claims = jwt.get_unverified_claims(request.data)
    except jwt.JWTError as e:
        raise InvalidUsage(f'failed to decode JWT: {str(e)}')

    try:
        unverified_public_key = b64decode(unverified_claims['pk']).decode('utf-8')
    except KeyError as e:
        raise InvalidUsage(f'missing claim: {str(e)}')
    except binascii.Error as e:
        raise InvalidUsage(f"failed to decode 'pk' claim: {str(e)}")
    except UnicodeError as e:
        raise InvalidUsage(f"failed to decode 'pk' claim: {e.reason}")

    try:
        claims = jwt.decode(request.data, unverified_public_key)
    except JWTError as e:
        raise InvalidUsage(f'failed to decode JWT: {str(e)}')

    try:
        public_key = claims['pk']
    except KeyError as e:
        raise InvalidUsage(f'missing claim: {str(e)}')

    try:
        invite_token = b64decode(claims['token'])
    except KeyError as e:
        raise InvalidUsage(f'missing claim: {str(e)}')
    except binascii.Error as e:
        raise InvalidUsage(f"failed to decode 'token' claim: {str(e)}")

    try:
        manager.process_location(invite_token, public_key)
    except ValueError as e:
        raise InvalidUsage(f'failed to process invite: {str(e)}')

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
        raise InvalidUsage(f'n too large, max is 10: {n}')  # TODO get the max config value here too
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
        raise ValueError(f'no chain with certificate_chain_uuid: {certificate_chain_uuid}')

    retrieved = datetime.strptime(result_data['time'], '%Y-%m-%dT%H:%M:%SZ')

    return {
        'chain': chain,
        'retrieved': retrieved,
        'ping': result_data['ping'],
        'ocsp': result_data['ocsp']
    }


@api.route('/submit', methods=['POST'])  # noqa: C901
def submit():
    """Submit scrape results.

    ---
    tags:
        - ocsp
    """
    try:
        submitted_token_header = jwt.get_unverified_header(request.data)
    except jwt.JWTError as e:
        raise InvalidUsage(f'failed to decode JWT: {str(e)}')

    try:
        key_id = uuid.UUID(submitted_token_header['kid'])
    except KeyError as e:
        raise InvalidUsage(f'missing header claim: {str(e)}')

    submitting_location = manager.get_location_by_key_id(key_id)
    if not submitting_location:
        raise InvalidUsage(f'no location for key id', payload={'key_id': key_id})

    try:
        claims = jwt.decode(request.data, submitting_location.pubkey.decode('utf-8'))
    except JWTError as e:
        raise InvalidUsage(f'failed to decode JWT: {str(e)}')

    try:
        results = claims[OCSP_RESULTS_JWT_CLAIM]
    except KeyError as e:
        raise InvalidUsage(f'missing claim: {str(e)}')

    prepared_result_dicts = []
    for result_data in results:
        try:
            prepared_dict = _prepare_result_dictionary(result_data)
            prepared_result_dicts.append(prepared_dict)
        except (KeyError, ValueError):
            raise InvalidUsage('invalid result data', payload={'result': result_data})

    # TODO: can this raise an exception? I think yes if there's a constraint broken on the DB when commit is called()
    manager.insert_payload(submitting_location, prepared_result_dicts)

    return '', HTTPStatus.NO_CONTENT


@api.errorhandler(InvalidUsage)
def handle_invalid_usage(error: InvalidUsage):
    """Handle InvalidUsage exceptions raised by views in the blueprint.

    :param error: The exception that caused this handler to be called.
    """
    response = jsonify(error)
    response.status_code = error.status_code
    return response
