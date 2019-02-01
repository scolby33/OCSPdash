# -*- coding: utf-8 -*-

"""Blueprint for non-API endpoints in OCSPdash."""

from flask import Blueprint, render_template

from ocspdash.web.proxies import manager

__all__ = ['ui']

ui = Blueprint('ui', __name__)


@ui.route('/')
def home():
    """Show the user the home view."""
    payload = manager.get_payload()
    return render_template('index.html', payload=payload)
