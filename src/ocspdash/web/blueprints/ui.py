import base64
from collections import namedtuple, OrderedDict
from itertools import groupby
import json
from operator import itemgetter
from typing import List

from flask import Blueprint, render_template, request, current_app
import nacl.signing
import nacl.encoding
import nacl.exceptions

from ...models import Location

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
    except nacl.exceptions.BadSignatureError:
        return '', '403'
    print(json.loads(base64.urlsafe_b64decode(payload).decode('utf-8')))
    return '', 204



