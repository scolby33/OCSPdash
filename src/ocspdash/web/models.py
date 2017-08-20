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

    name = Column(String(255), nullable=False, index=True, doc='the name of the authority')

    cardinality = Column(Integer, doc="The number of certs observed from this authority in the wild. Update this "
                                      "when rankings change. From the Censys crawler.")

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
    """Represents the URL at which an OCSP responder is present"""
    __tablename__ = 'endpoint'

    id = Column(Integer, primary_key=True)

    url = Column(Text, nullable=False, doc='the URL of the OCSP endpoint')


class Responder(Base):
    """Represents the unique pair of authority/endpoint"""
    __tablename__ = 'responder'

    id = Column(Integer, primary_key=True)

    authority_id = Column(Integer, ForeignKey('authority.id'), nullable=False, doc='the authority')
    endpoint_id = Column(Integer, ForeignKey('endpoint.id'), nullable=False, doc='the endpoint')

    cardinality = Column(Integer, doc="The number of certs observed using this authority/endpoint pair in the "
                                      "wild. Update this when rankings are updated.")

    __table_args__ = (
        UniqueConstraint(authority_id, endpoint_id),
    )


class Chain(Base):
    """Represents a certificate and its issuing certificate"""
    __tablename__ = 'chain'

    id = Column(Integer, primary_key=True)

    responder_id = Column(Integer, ForeignKey('responder.id'))
    responder = relationship('Responder')

    subject = Column(Binary, nullable=False, doc='raw bytes of the subject certificate')
    issuer = Column(Binary, nullable=False, doc="raw bytes of the subject's issuer certificate")
    retrieved = Column(DateTime, nullable=False,
                       doc='expire the cached chain when this date is more than 7 days ago')

    @property
    def expires_on(self) -> datetime:  # expire the cached certificate when this date is in the past
        certificate = asymmetric.load_certificate(self.subject_cert)
        return certificate.asn1['tbs_certificate']['validity']['not_after'].native

    @property
    def expired(self) -> bool:
        """Has this certificate expired?"""
        return self.expires_on < datetime.now()


class User(Base):
    """References a user"""
    __tablename__ = 'user'

    id = Column(Integer, primary_key=True)

    location = Column(Text, doc='the location to be displayed')


class Result(Base):
    """The information about the result from a ping"""
    __tablename__ = 'result'

    id = Column(Integer, primary_key=True)

    responder_id = Column(Integer, ForeignKey('responder.id'), doc='the authority/endpoint pair that was tested')
    responder = relationship('Responder', backref=backref('results'))

    chain_id = Column(Integer, ForeignKey('chain.id'), doc='the certificate chain that was used for the OCSP '
                                                           'test')
    chain = relationship('Chain', backref=backref('results'))

    user_id = Column(Integer, ForeignKey('user.id'), nullable=False, doc='the user that ran the test')
    user = relationship('User', backref=backref('results', lazy='dynamic'))

    retrieved = Column(DateTime, default=datetime.utcnow, doc='when the test was run')
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
