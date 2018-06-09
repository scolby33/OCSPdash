# -*- coding: utf-8 -*-


from flask import Flask
from flask_sqlalchemy import SQLAlchemy, get_state

from ocspdash.manager import Manager


class OCSPSQLAlchemy(SQLAlchemy):
    """An extension of Flask-SQLAlchemy to support the OCSPdash manager."""

    manager: Manager

    def init_app(self, app: Flask):
        """
        :param app: A Flask app
        """
        super().init_app(app)

        self.manager = Manager(engine=self.engine, session=self.session)

    @staticmethod
    def get_manager(app: Flask) -> Manager:
        """
        :param app: A Flask app
        """
        return get_state(app).db.manager
