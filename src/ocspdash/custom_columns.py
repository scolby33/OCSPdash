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

        if not isinstance(value, uuid.UUID):
            return uuid.UUID(value).bytes

        if isinstance(value, uuid.UUID):
            # hex string
            return value.bytes

        raise ValueError(f'can not handle {value}')

    def process_result_value(self, value, dialect):
        if value is None:
            return

        return uuid.UUID(bytes=value)
