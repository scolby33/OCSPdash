# -*- coding: utf-8 -*-

import operator
from datetime import datetime, timedelta, timezone
from enum import Enum

from oscrypto import asymmetric
from sqlalchemy import (
    Binary,
    Column,
    ForeignKey,
    Boolean,
    Integer,
    String,
    DateTime,
    Text
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, backref

Base = declarative_base()


class OCSPResponderStatus(Enum):
    good = 'good'
    questionable = 'questionable'
    bad = 'bad'
    unknown = 'unknown'


class Authority(Base):
    """Represents the authority that issues certificates"""
    __tablename__ = 'authority'

    id = Column(Integer, primary_key=True)

    name = Column(String(255), nullable=False, index=True, doc='the name of the authority')

    cardinality = Column(Integer, doc="The number of certs observed from this authority in the wild. Update this "
                                      "when rankings change. From the Censys crawler.")

    rank = Column(Integer, doc=("Update this when rankings change. Don't delete formerly-high-ranked "
                                "authorities as that would mess up relations to old test results"))

    def __repr__(self):
        return self.name


class Responder(Base):
    """Represents the unique pair of authority/endpoint"""
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
            'authority_id': self.authority_id,
            'url': self.url,
            'cardinality': self.cardinality,
            'current': self.current,
        }


class Chain(Base):
    """Represents a certificate and its issuing certificate"""
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


class User(Base):
    """References a user"""
    __tablename__ = 'user'

    id = Column(Integer, primary_key=True)

    location = Column(String(255), index=True, doc='the location to be displayed')

    def __repr__(self):
        return self.location


class Result(Base):
    """The information about the result from a ping"""
    __tablename__ = 'result'

    id = Column(Integer, primary_key=True)

    chain_id = Column(Integer, ForeignKey('chain.id'), doc='the certificate chain that was used for the OCSP test')
    chain = relationship('Chain', backref=backref('results'))

    user_id = Column(Integer, ForeignKey('user.id'), nullable=False, doc='the user that ran the test')
    user = relationship('User', backref=backref('results', lazy='dynamic'))

    retrieved = Column(DateTime, default=datetime.utcnow, doc='when the test was run')

    created = Column(Boolean, default=False, nullable=False, doc="able to create chain")
    current = Column(Boolean, default=False, nullable=False, doc='is this responder specified by any currently '
                                                                 'valid certificates?')
    ping = Column(Boolean, default=False, nullable=False, doc='did the server respond to a ping?')
    ocsp = Column(Boolean, default=False, nullable=False, doc='did a valid OCSP request get a good response?')

    @property
    def status(self) -> OCSPResponderStatus:  # relates to the glyphicon displayed
        """Gets the status"""
        if not self.ocsp:
            return OCSPResponderStatus.bad

        if self.ping:
            return OCSPResponderStatus.good

        return OCSPResponderStatus.questionable

    def __repr__(self):
        return f'<{self.__class__.__name__} created={self.created}, current={self.current}, ping={self.ping}, ocsp={self.ocsp})>'
