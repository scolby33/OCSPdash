# -*- coding: utf-8 -*-

import base64
import json

from nacl.encoding import URLSafeBase64Encoder
import nacl.exceptions
import nacl.signing
from flask import Blueprint, abort, current_app, render_template, request
from nacl.signing import VerifyKey

__all__ = [
    'ui',
]

ui = Blueprint('ui', __name__)


@ui.route('/')
def home():
    """Show the user the home view."""
    payload = current_app.manager.make_payload()
    return render_template('index.html', payload=payload)


@ui.route('/submit', methods=['POST'])
def submit():
    """Show the submit view."""
    location_id = int(request.headers['authorization'])

    location = current_app.manager.get_location_by_id(location_id)

    if not location.activated:
        return abort(403, f'Not activated: {location}')

    key = location.pubkey

    try:
        verify_key = VerifyKey(key=key, encoder=URLSafeBase64Encoder)
        payload = verify_key.verify(request.data, encoder=URLSafeBase64Encoder)

    except nacl.exceptions.BadSignatureError as e:
        return abort(403, f'Bad Signature: {e}')

    decoded_payload = json.loads(base64.urlsafe_b64decode(payload).decode('utf-8'))
    current_app.manager.insert_payload(decoded_payload)

    return '', 204
