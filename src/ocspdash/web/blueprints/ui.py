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
    payload = make_payload()
    return render_template('index.html', payload=payload)


@ui.route('/submit', methods=['POST'])
def submit():
    data = request.data
    location_id = int(request.headers['authorization'])

    location = current_app.manager.session.query(Location).get(location_id)
    if not location.activated:
        return '', 403

    try:
        pubkey = location.pubkey
        verify_key = nacl.signing.VerifyKey(pubkey, encoder=nacl.encoding.URLSafeBase64Encoder)
        payload = verify_key.verify(data, encoder=nacl.encoding.URLSafeBase64Encoder)
    except nacl.exceptions.BadSignatureError:
        return '', '403'
    print(json.loads(base64.urlsafe_b64decode(payload).decode('utf-8')))
    return '', 204


def make_payload():
    locations: List[Location] = current_app.manager.get_all_locations_with_test_results()
    Row = namedtuple('Row', f'url current {" ".join(location.name for location in locations)}')
    Row.__new__.__defaults__ = (None,) * (len(Row._fields) - 2)

    sections = OrderedDict()
    for authority, group in groupby(current_app.manager.get_most_recent_result_for_each_location(), itemgetter(0)):
        sections[authority.name] = []
        for responder, group2 in groupby(group, itemgetter(1)):
            results = {
                location.name: result
                for _, _, result, location in group2
            }
            row = Row(url=responder.url, current=responder.current, **results)
            sections[authority.name].append(row)

    return {
        'locations': locations,
        'sections': sections
    }
