from collections import namedtuple, OrderedDict
from itertools import groupby
from operator import itemgetter
from typing import List

from flask import Blueprint, render_template, request, current_app

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
    headers = request.headers

    print(data)
    print(headers)
    return ('', 204)


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
