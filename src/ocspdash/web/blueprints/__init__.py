# -*- coding: utf-8 -*-

"""Flask blueprints for the OCSPdash web UI and REST API."""

from .api import api
from .ui import ui

__all__ = [
    'api',
    'ui'
]
