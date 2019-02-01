# -*- coding: utf-8 -*-

"""SQLAlchemy models for OCSPdash."""

import operator
import uuid
from base64 import urlsafe_b64decode as b64decode, urlsafe_b64encode as b64encode
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Mapping, Optional  # noqa: F401 imported for PyCharm type checking

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from oscrypto import asymmetric
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.ext.declarative import DeclarativeMeta, declarative_base
from sqlalchemy.orm import backref, relationship
from sqlalchemy.sql import functions as func

import ocspdash.util
from ocspdash.constants import (
    NAMESPACE_OCSPDASH_CERTIFICATE_CHAIN_ID,
    NAMESPACE_OCSPDASH_KID,
    OCSPSCRAPE_PRIVATE_KEY_ALGORITHMS,
)
from ocspdash.custom_columns import UUID
from ocspdash.security import pwd_context

Base: DeclarativeMeta = declarative_base()


class OCSPResponderStatus(Enum):
    """The possible statuses of an OCSP responder."""

    good = 'good'
    questionable = 'questionable'
    bad = 'bad'
    unknown = 'unknown'


class Authority(Base):
    """Represents the authority that issues certificates."""

    __tablename__ = 'authority'

    id = Column(Integer, primary_key=True)

    name = Column(
        String(255), nullable=False, index=True, doc='the name of the authority'
    )

    cardinality = Column(
        Integer,
        doc='The number of certs observed from this authority in the wild. Update this '
        'when rankings change. From the Censys crawler.',
    )

    last_updated = Column(DateTime, server_default=func.now(), onupdate=func.now())

    @property
    def old(self) -> bool:
        """Return True if the last_updated time is older than 7 days, False otherwise."""
        return self.last_updated < datetime.utcnow() - timedelta(days=7)

    def __repr__(self):
        return self.name

    def to_json(self):
        """Return a representation of the instance suitable for passing in to JSON conversion."""
        return {
            'id': self.id,
            'name': self.name,
            'cardinality': self.cardinality,
            'responders': [
                {
                    'id': responder.id,
                    'url': responder.url,
                    'cardinality': responder.cardinality,
                    'current': responder.current,
                }
                for responder in self.responders
            ],
        }


class Responder(Base):
    """Represents the unique pair of authority/endpoint."""

    __tablename__ = 'responder'

    id = Column(Integer, primary_key=True)

    authority_id = Column(
        Integer, ForeignKey('authority.id'), nullable=False, doc='the authority'
    )
    authority = relationship('Authority', backref=backref('responders'))

    url = Column(Text, nullable=False, doc='the URL of the OCSP endpoint')

    cardinality = Column(
        Integer,
        doc='The number of certs observed using this authority/endpoint pair in the '
        'wild. Update this when rankings are updated.',
    )

    last_updated = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (UniqueConstraint(authority_id, url),)

    def __repr__(self):
        return f'{self.authority} at {self.url}'

    @property
    def current(self) -> bool:
        """Calculate if this responder is current by the status of its most recent result over all chains."""
        return not all(chain.expired for chain in self.chains)

    @property
    def most_recent_chain(self) -> 'Optional[Chain]':
        """Get the most recent chain for this Responder."""
        try:
            return max(self.chains, key=operator.attrgetter('retrieved'))
        except ValueError:
            return None

    @property
    def old(self) -> bool:
        """Return True if the last_updated time is older than 7 days, False otherwise."""
        return self.last_updated < datetime.utcnow() - timedelta(days=7)

    def to_json(self):
        """Return a representation of the instance suitable for passing in to JSON conversion."""
        return {
            'id': self.id,
            'authority': {
                'id': self.authority.id,
                'name': self.authority.name,
                'cardinality': self.authority.cardinality,
            },
            'url': self.url,
            'cardinality': self.cardinality,
            'current': self.current,
        }


def _certificate_uuid_default(context) -> uuid.UUID:
    parameters = context.get_current_parameters()
    subject = parameters['subject']
    issuer = parameters['issuer']

    return ocspdash.util.uuid5(
        NAMESPACE_OCSPDASH_CERTIFICATE_CHAIN_ID, subject + issuer
    )


class Chain(Base):
    """Represents a certificate and its issuing certificate."""

    __tablename__ = 'chain'

    id = Column(Integer, primary_key=True)

    responder_id = Column(Integer, ForeignKey('responder.id'))
    responder = relationship('Responder', backref=backref('chains'))

    subject = Column(LargeBinary, nullable=False, doc='raw bytes of the subject certificate')
    issuer = Column(
        LargeBinary, nullable=False, doc="raw bytes of the subject's issuer certificate"
    )
    retrieved = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
        doc='expire the cached chain when this date is more than 7 days ago',
    )

    certificate_chain_uuid = Column(
        UUID,
        nullable=False,
        unique=True,
        default=_certificate_uuid_default,
        onupdate=_certificate_uuid_default,
        index=True,
        doc='',
    )

    @property
    def expired(self) -> bool:
        """Return True if the subject certificate has expired, False otherwise."""
        certificate = asymmetric.load_certificate(self.subject)
        expires_on = certificate.asn1['tbs_certificate']['validity']['not_after'].native
        return expires_on < datetime.utcnow().replace(tzinfo=timezone.utc)

    @property
    def old(self) -> bool:
        """Return True if the last_updated time is older than 7 days, False otherwise."""
        return self.retrieved < datetime.utcnow() - timedelta(days=7)

    def get_manifest_json(self) -> Mapping:
        """Get a mapping suitable for creating a manifest line in the API."""
        return {
            'responder_url': self.responder.url,
            'subject_certificate': b64encode(self.subject).decode('utf-8'),
            'issuer_certificate': b64encode(self.issuer).decode('utf-8'),
            'certificate_chain_uuid': str(self.certificate_chain_uuid),
        }

    def __repr__(self):
        return f'{self.responder} at {self.retrieved}'

    def to_json(self):
        """Return a representation of the instance suitable for passing in to JSON conversion."""
        return {
            'id': self.id,
            'retrieved': str(self.retrieved),
            'expired': self.expired,
            'old': self.old,
        }


class Location(Base):
    """An invite for a new testing location."""

    __tablename__ = 'location'

    id = Column(Integer, primary_key=True)
    name = Column(String(255), doc='the name of the invited location')

    selector = Column(LargeBinary(16), nullable=False, unique=True, index=True, doc='')
    validator_hash = Column(String(255), nullable=False, doc='')

    pubkey = Column(LargeBinary, doc="the location's public signing key")
    key_id = Column(UUID, doc="the UUID of the location's public key", index=True)

    @property
    def accepted(self) -> bool:
        """Check if this location has a public key and key identifier pair."""
        return self.pubkey is not None and self.key_id is not None

    def verify(self, validator: bytes) -> bool:
        """Verify a validator against the Location's validator_hash.

        :param validator: The validator to be verified.

        :returns: True if the validator is valid, False otherwise.
        """
        return pwd_context.verify(validator, self.validator_hash)

    def set_public_key(self, public_key: str):
        """Set the pubkey and key_id for the Location based on an input public key.

        :param public_key: The public key for the Location.
        """
        pubkey = b64decode(public_key)
        loaded_pubkey = serialization.load_pem_public_key(pubkey, default_backend())
        if not any(
            isinstance(getattr(loaded_pubkey, 'curve', None), algorithm)
            for algorithm in OCSPSCRAPE_PRIVATE_KEY_ALGORITHMS
        ):
            raise ValueError('Key type not in accepted algorithms')
        self.pubkey = b64decode(public_key)
        self.key_id = uuid.uuid5(NAMESPACE_OCSPDASH_KID, public_key)

    @property
    def b64encoded_pubkey(self) -> str:  # noqa: D401
        """A URL-safe Base64 string encoding of the Location's public key.

        :returns: The encoded public key.
        """
        return b64encode(self.pubkey).decode('utf-8')

    def __repr__(self):
        if self.accepted:
            return f'Location {self.name}'

        return f'Invite for {self.name}'

    def to_json(self):
        """Return a representation of the instance suitable for passing in to JSON conversion."""
        return {
            'id': self.id,
            'name': self.name,
            'selector': str(self.selector),
            'validator_hash': self.validator_hash,
            'pubkey': str(self.pubkey),
            'key_id': str(self.key_id),
            'results': [result.id for result in self.results],
        }


class Result(Base):
    """The information about the result from a ping."""

    __tablename__ = 'result'

    id = Column(Integer, primary_key=True)

    chain_id = Column(
        Integer,
        ForeignKey('chain.id'),
        doc='the certificate chain that was used for the OCSP test',
    )
    chain = relationship('Chain', backref=backref('results'))

    location_id = Column(
        Integer,
        ForeignKey('location.id'),
        nullable=False,
        doc='the location that ran the test',
    )
    location = relationship('Location', backref=backref('results', lazy='dynamic'))

    retrieved = Column(DateTime, default=datetime.utcnow, doc='when the test was run')

    ping = Column(Boolean, nullable=False, doc='did the server respond to a ping?')
    ocsp = Column(
        Boolean, nullable=False, doc='did a valid OCSP request get a good response?'
    )

    @property
    def status(self) -> OCSPResponderStatus:  # relates to the glyphicon displayed
        """Get the status of the responder.

        Relates to the icon displayed in the web UI.
        """
        if not self.ocsp:
            return OCSPResponderStatus.bad

        if self.ping:
            return OCSPResponderStatus.good

        return OCSPResponderStatus.questionable

    def __repr__(self):
        return f'<{self.__class__.__name__}, ping={self.ping}, ocsp={self.ocsp}>'

    def to_json(self):
        """Return a representation of the instance suitable for passing in to JSON conversion."""
        return {
            'id': self.id,
            'location': {'id': self.location.id, 'location': self.location.name},
            'chain': {
                'id': self.chain.id,
                'retrieved': str(self.chain.retrieved),
                'expired': self.chain.expired,
                'old': self.chain.old,
            },
            'retrieved': str(self.retrieved),
            'ping': self.ping,
            'ocsp': self.ocsp,
        }
