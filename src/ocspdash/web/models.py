# -*- coding: utf-8 -*-

from datetime import datetime
from enum import Enum

from oscrypto import asymmetric
from sqlalchemy import (
    Binary,
    Column,
    ForeignKey,
    Boolean,
    UniqueConstraint,
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

    name = Column(String(255), nullable=False, index=True, doc='The name of the authority')

    number_of_certs = Column(Integer)  # TODO document this

    rank = Column(Integer, doc=("Update this when rankings change. Don't delete formerly-high-ranked "
                                "authorities as that would mess up relations to old test results"))

    endpoints = relationship(
        'Endpoint',
        secondary=Responder,
        primaryjoin=(id == Responder.authority_id),
        secondaryjoin=(id == Responder.endpoint_id),
        backref=backref('authorities')
    )


class Endpoint(Base):
    """Represents the URL at which an OCSP is present"""
    __tablename__ = 'endpoint'

    id = Column(Integer, primary_key=True)

    url = Column(Text, nullable=False, doc='The URL of the OCSP endpoint')


class Responder(Base):
    """Represents the unique pair of authority/endpoint"""
    __tablename__ = 'responder'

    id = Column(Integer, primary_key=True)

    authority_id = Column(Integer, ForeignKey('authority.id'), nullable=False, doc='The authority')
    endpoint_id = Column(Integer, ForeignKey('endpoint.id'), nullable=False, doc='The endpoint')

    __table_args__ = (
        UniqueConstraint(authority_id, endpoint_id),
    )


class Certificate(Base):
    """Represents a certificate and its origin"""
    __tablename__ = 'certificate'

    id = Column(Integer, primary_key=True)

    responder_id = Column(Integer, ForeignKey('responder.id'))
    responder = relationship('Responder')

    subject = Column(Binary, nullable=False, doc="")
    issuer = Column(Binary, nullable=False, doc="")
    retrieved = Column(DateTime, nullable=False,
                       doc="expire the cached certificate when this date is more than 7 days ago")

    @property
    def expires_on(self) -> datetime:  # expire the cached certificate when this date is in the past
        certificate = asymmetric.load_certificate(self.subject_cert)
        return certificate.asn1['tbs_certificate']['validity']['not_after'].native


class User(Base):
    """References a user"""
    __tablename__ = 'user'

    id = Column(Integer, primary_key=True)

    location = Column(Text, doc='The location to be displayed')


class Result(Base):
    """The information about the result from a ping"""
    __tablename__ = 'result'

    id = Column(Integer, primary_key=True)

    certificate_id = Column(Integer, ForeignKey('certificate.id'))
    certificate = relationship('Certificate', backref=backref('results'))

    user_id = Column(Integer, ForeignKey('user.id'), nullable=False, doc='The user that ran the test')
    user = relationship('User', backref=backref('results', lazy='dynamic'))

    retrieved = Column(DateTime, default=datetime.utcnow, doc="When was the test run")
    ping = Column(Boolean, default=False, nullable=False, doc='did the server respond to a ping?')
    ocsp = Column(Boolean, default=False, nullable=False, doc='did a valid OCSP request get a good response?')

    @property
    def status(self) -> OCSPResponderStatus:  # relates to the glyphicon displayed
        """Gets the status

        :rtype: OCSPResponderStatus
        """
        if not self.ocsp:
            return OCSPResponderStatus.bad

        if self.ping:
            return OCSPResponderStatus.good

        return OCSPResponderStatus.questionable
