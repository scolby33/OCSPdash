# -*- coding: utf-8 -*-

"""Local proxies for OCSPdash."""

from flask import current_app
from werkzeug.local import LocalProxy

from ocspdash.manager import Manager
from ocspdash.web.extension import OCSPSQLAlchemy

__all__ = ['manager']


def get_manager_proxy():
    """Get a proxy for the manager in the current app.

    Why make this its own function? It tricks type assertion tools into knowing that the LocalProxy object represents
    a Manager.
    """
    return LocalProxy(lambda: OCSPSQLAlchemy.get_manager(current_app))


manager: Manager = get_manager_proxy()
