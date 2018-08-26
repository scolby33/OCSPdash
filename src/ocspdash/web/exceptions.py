# -*- coding: utf-8 -*-

"""Exceptions and Errors for the OCSPdash web package."""

from http import HTTPStatus
from typing import Mapping


class InvalidUsage(Exception):
    """An Exception to be raised by a view for invalid usage of the endpoint."""

    status_code = HTTPStatus.BAD_REQUEST

    def __init__(self, message: str, status_code: HTTPStatus=None, payload: Mapping=None) -> None:
        """Create an InvalidUsage exception.

        :param message: The message for the exception; will be placed in the `message` key of the JSON returned in the response.
        :param status_code: An HTTP status code for the response; default is 400 BAD REQUEST. It will also be placed in the `status` key of the returned JSON.
        :param payload: A mapping that can be jsonified by Flask; will be returned as JSON in the response alongside the message.
        """
        super().__init__(self)
        self.message = message
        if status_code is not None:
            self.status_code = status_code
        self.payload = payload

    def to_json(self) -> Mapping:
        """Return a representation of the exception suitable to passed for JSON conversion."""
        rv = dict(self.payload or ())
        rv['message'] = self.message
        rv['status'] = self.status_code
        return rv
