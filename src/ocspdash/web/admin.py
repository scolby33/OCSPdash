# -*- coding: utf-8 -*-

"""An extension of Flask-Admin to support the OCSPdash manager."""

from flask import Flask
from flask_admin import Admin
from flask_admin.contrib.sqla import ModelView

from ocspdash.models import Authority, Chain, Location, Responder, Result

__all__ = ['make_admin']


def make_admin(app: Flask, session) -> Admin:
    """Add admin views to the app."""
    admin = Admin(app)

    admin.add_view(ModelView(Authority, session))
    admin.add_view(ModelView(Responder, session))

    class ChainView(ModelView):
        column_exclude_list = ['subject', 'issuer']

    admin.add_view(ChainView(Chain, session))
    admin.add_view(ModelView(Location, session))
    admin.add_view(ModelView(Result, session))

    return admin
