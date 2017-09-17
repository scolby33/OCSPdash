# -*- coding: utf-8 -*-

import base64
import json

import nacl.encoding
import nacl.exceptions
import nacl.signing
from flask import Blueprint, render_template, request, current_app, abort

ui = Blueprint('ui', __name__)


@ui.route('/')
def home():
    """Shows the user the home view"""
    payload = current_app.manager.make_payload()
    return render_template('index.html', payload=payload)


@ui.route('/submit', methods=['POST'])
def submit():
    data = request.data
    location_id = int(request.headers['authorization'])

    location = current_app.manager.get_location_by_id(location_id)

    if not location.activated:
        abort(403, f'Not activated: {location}')

    pubkey = location.pubkey

    try:
        verify_key = nacl.signing.VerifyKey(pubkey, encoder=nacl.encoding.URLSafeBase64Encoder)
        payload = verify_key.verify(data, encoder=nacl.encoding.URLSafeBase64Encoder)
    except nacl.exceptions.BadSignatureError as e:
        abort(403, f'Bad Signature: {e}')

    decoded_payload = json.loads(base64.urlsafe_b64decode(payload).decode('utf-8'))

    current_app.manager.insert_payload(decoded_payload)

    return '', 204
