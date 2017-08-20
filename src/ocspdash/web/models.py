from datetime import datetime
from enum import Enum

from oscrypto import asymmetric


class OCSPResponderStatus(Enum):
    good = 'good'
    questionable = 'questionable'
    bad = 'bad'
    unknown = 'unknown'


class Authority(object):
    name: str = None
    number_of_certs: int = None


class OCSPResponder(object):
    # NOTE: there may be a case where one OCSP URL is used by more than one authority. URL cannot be considered unique
    url: str = None
    authority: Authority = None  # this should be a relation
    number_of_certs: int = None
    subject_cert: Certificate = None  # cached, a relation


class Certificate(object):
    subject_cert: bytes = None
    issuer_cert: bytes = None
    retrieved_on: datetime = None  # expire the cached certificate when this date is more than 7 days ago

    @property
    def expires_on(self) -> datetime:  # expire the cached certificate when this date is in the past
        certificate = asymmetric.load_certificate(self.subject_cert)
        return certificate.asn1['tbs_certificate']['validity']['not_after'].native


class TestResult(object):
    authority: Authority = None  # a relation
    url: OCSPResponder = None  # a relation, this name might not need to be "url"?
    timestamp: datetime = None  # when the test was run
    location: str = None  # where we got this result from
    current: bool = None  # whether there are any valid certs that use this URL
    ping: bool = None  # did the server respond to a ping?
    ocsp: bool = None  # did a valid OCSP request get a good response?

    @property
    def status(self) -> OCSPResponderStatus:
        if self.ocsp and self.ping:
            return OCSPResponderStatus.good
        elif self.ocsp and not self.ping:
            return OCSPResponderStatus.questionable
        elif not self.ocsp:
            return OCSPResponderStatus.bad
        else:
            return OCSPResponderStatus.unknown  # I don't think we'd ever get here
