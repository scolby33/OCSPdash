from sqlalchemy.types import TypeDecorator, BINARY
from sqlalchemy.dialects.postgresql import UUID
import uuid


class UUID(TypeDecorator):
    """Platform-independent UUID type.

    Uses Postgresql's UUID type, otherwise uses
    BINARY(16).
    Based on http://docs.sqlalchemy.org/en/rel_0_9/core/custom_types.html?highlight=guid#backend-agnostic-guid-type
    """
    impl = BINARY

    def load_dialect_impl(self, dialect):
        if dialect.name == 'postgresql':
            return dialect.type_descriptor(UUID())
        else:
            return dialect.type_descriptor(BINARY)

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        elif dialect.name == 'postgresql':
            return str(value)
        else:
            if not isinstance(value, uuid.UUID):
                return uuid.UUID(value).bytes
            else:
                # hex string
                return value.bytes

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        else:
            return uuid.UUID(bytes=value)
