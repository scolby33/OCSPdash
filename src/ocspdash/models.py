# -*- coding: utf-8 -*-

"""SQLAlchemy models for OCSPdash."""

import operator
from base64 import urlsafe_b64encode as b64encode
from datetime import datetime, timedelta, timezone
from enum import Enum

from oscrypto import asymmetric
from sqlalchemy import Binary, Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import backref, relationship
from sqlalchemy.sql import functions as func

from ocspdash.custom_columns import UUID

Base = declarative_base()


class OCSPResponderStatus(Enum):
    good = 'good'
    questionable = 'questionable'
    bad = 'bad'
    unknown = 'unknown'


class Authority(Base):
    """Represents the authority that issues certificates."""
    __tablename__ = 'authority'

    id = Column(Integer, primary_key=True)

    name = Column(String(255), nullable=False, index=True, doc='the name of the authority')

    cardinality = Column(Integer, doc="The number of certs observed from this authority in the wild. Update this "
                                      "when rankings change. From the Censys crawler.")

    last_updated = Column(DateTime, server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return self.name

    def to_json(self):
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
            ]
        }


class Responder(Base):
    """Represents the unique pair of authority/endpoint."""
    __tablename__ = 'responder'

    id = Column(Integer, primary_key=True)

    authority_id = Column(Integer, ForeignKey('authority.id'), nullable=False, doc='the authority')
    authority = relationship('Authority', backref=backref('responders'))

    url = Column(Text, nullable=False, doc='the URL of the OCSP endpoint')

    cardinality = Column(Integer, doc="The number of certs observed using this authority/endpoint pair in the "
                                      "wild. Update this when rankings are updated.")

    def __repr__(self):
        return f'{self.authority} at {self.url}'

    @property
    def current(self) -> bool:
        """Calculates if this responder is current by the status of its most recent result over all chains."""
        return max(
            (
                result
                for chain in self.chains
                for result in chain.results
            ),
            key=operator.attrgetter('retrieved')
        ).current

    def to_json(self):
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


class Chain(Base):
    """Represents a certificate and its issuing certificate."""
    __tablename__ = 'chain'

    id = Column(Integer, primary_key=True)

    responder_id = Column(Integer, ForeignKey('responder.id'))
    responder = relationship('Responder', backref=backref('chains'))

    subject = Column(Binary, nullable=False, doc='raw bytes of the subject certificate')
    issuer = Column(Binary, nullable=False, doc="raw bytes of the subject's issuer certificate")
    retrieved = Column(DateTime, default=datetime.utcnow, nullable=False,
                       doc='expire the cached chain when this date is more than 7 days ago')

    @property
    def expired(self) -> bool:
        """Has this certificate expired?"""
        certificate = asymmetric.load_certificate(self.subject)
        expires_on = certificate.asn1['tbs_certificate']['validity']['not_after'].native
        return expires_on < datetime.utcnow().replace(tzinfo=timezone.utc)

    @property
    def old(self) -> bool:
        return self.retrieved < datetime.utcnow() - timedelta(days=7)

    def __repr__(self):
        return f'{self.responder} at {self.retrieved}'

    def to_json(self):
        return {
            'id': self.id,
            'retrieved': str(self.retrieved),
            'expired': self.expired,
            'old': self.old,
        }


class Location(Base):
    """References a testing location."""
    __tablename__ = 'location'

    id = Column(Integer, primary_key=True)

    name = Column(String(255), index=True, doc='the name of the location', unique=True)
    pubkey = Column(Binary, doc="the location's public signing key")
    key_id = Column(UUID, doc="the UUID of the location's public key")

    def __repr__(self):
        return self.name

    def to_json(self):
        return {
            'id': self.id,
            'name': self.name,
            'pubkey': b64encode(self.pubkey).decode('utf-8'),
            'key_id': self.key_id,
            'results': [
                result.id for result in self.results
            ]
        }


class Invite(Base):
    """An invite for a new testing location."""
    __tablename__ = 'invite'

    id = Column(Integer, primary_key=True)
    name = Column(String(255), doc='the name of the invited location')
    invite_id = Column(Binary(16), nullable=False, unique=True, index=True, doc='')
    invite_validator = Column(String(255), nullable=False, doc='')

    def __repr__(self):
        return f'Invite for {self.name}'

    def to_json(self):
        return {
            'id': self.id,
            'name': self.name,
            'invite_id': self.invite_id,
            'invite_token': self.invite_validator
        }


class Result(Base):
    """The information about the result from a ping."""
    __tablename__ = 'result'

    id = Column(Integer, primary_key=True)

    chain_id = Column(Integer, ForeignKey('chain.id'), doc='the certificate chain that was used for the OCSP test')
    chain = relationship('Chain', backref=backref('results'))

    location_id = Column(Integer, ForeignKey('location.id'), nullable=False, doc='the location that ran the test')
    location = relationship('Location', backref=backref('results', lazy='dynamic'))

    retrieved = Column(DateTime, default=datetime.utcnow, doc='when the test was run')

    created = Column(Boolean, default=False, nullable=False, doc="able to create chain")
    current = Column(Boolean, default=False, nullable=False, doc='is this responder specified by any currently '
                                                                 'valid certificates?')
    ping = Column(Boolean, default=False, nullable=False, doc='did the server respond to a ping?')
    ocsp = Column(Boolean, default=False, nullable=False, doc='did a valid OCSP request get a good response?')

    @property
    def status(self) -> OCSPResponderStatus:  # relates to the glyphicon displayed
        """Gets the status."""
        if not self.ocsp:
            return OCSPResponderStatus.bad

        if self.ping:
            return OCSPResponderStatus.good

        return OCSPResponderStatus.questionable

    def __repr__(self):
        return f'<{self.__class__.__name__} created={self.created}, current={self.current}, ping={self.ping}, ocsp={self.ocsp}>'

    def to_json(self):
        return {
            'id': self.id,
            'location': {
                'id': self.location.id,
                'location': self.location.name
            },
            'chain': {
                'id': self.chain.id,
                'retrieved': str(self.chain.retrieved),
                'expired': self.chain.expired,
                'old': self.chain.old,
            },
            'retrieved': str(self.retrieved),
            'created': self.created,
            'current': self.current,
            'ping': self.ping,
            'ocsp': self.ocsp,
        }
