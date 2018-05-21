# -*- coding: utf-8 -*-

"""Implements custom SQLAlchemy TypeDecorators."""

import uuid

import sqlalchemy.dialects.postgresql
from sqlalchemy.types import BINARY, TypeDecorator

__all__ = [
    'UUID',
]


class UUID(TypeDecorator):
    """Platform-independent UUID type.

    Uses Postgresql's UUID type, otherwise uses
    BINARY(16).
    Based on http://docs.sqlalchemy.org/en/rel_0_9/core/custom_types.html?highlight=guid#backend-agnostic-guid-type
    """

    impl = BINARY

    def load_dialect_impl(self, dialect):
        if dialect.name == 'postgresql':
            return dialect.type_descriptor(sqlalchemy.dialects.postgresql.UUID())

        return dialect.type_descriptor(BINARY)

    def process_bind_param(self, value, dialect):
        if value is None:
            return

        if dialect.name == 'postgresql':
            return str(value)

        if isinstance(value, uuid.UUID):
            # raw UUID bytes
            return value.bytes

        value_uuid = uuid.UUID(value)
        return value_uuid.bytes

    def process_result_value(self, value, dialect):
        if value is None:
            return

        if dialect.name == 'postgresql':
            return uuid.UUID(value)

        return uuid.UUID(bytes=value)
