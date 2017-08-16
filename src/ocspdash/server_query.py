import base64
from collections import OrderedDict
import enum
import logging
from operator import itemgetter
import os
import platform
import subprocess
from typing import List, MutableMapping, Union

from asn1crypto.ocsp import OCSPResponse
from ocspbuilder import OCSPRequestBuilder
from oscrypto import asymmetric
import requests

from .util import RateLimitedCensysCertificates

UID = os.environ.get('UID')
SECRET = os.environ.get('SECRET')

logger = logging.getLogger(__name__)


class OCSPVerificationResponses(enum.Enum):
    no_url = 'No Issuer URL'
    no_cert_download = 'Failed to Download Issuer Cert'


class ServerQuery(object):
    def __init__(self, api_id: str, api_secret: str) -> None:
        """All the operations required to find the OCSP servers of the top certificate authorities and test them.

        :param api_id: A valid `Censys <https://censys.io>`_ API ID
        :param api_secret: The matching `Censys <https://censys.io>`_ API secret
        """
        self.censys_api = RateLimitedCensysCertificates(api_id, api_secret)

    def get_top_authorities(self, n: int=10) -> MutableMapping[str, int]:
        """Retrieve the name and count of certificates for the top n certificate authorities by number of certs

        :param n: The number of top authorities to retrieve

        :returns: A mapping of authority name to count of certificates, sorted in descending order by certificate count
        """
        issuers_report = self.censys_api.report(query='valid_nss: true', field='parsed.issuer.organization', buckets=n)
        issuers_and_counts = OrderedDict(sorted(
            ((result['key'], result['doc_count']) for result in issuers_report['results']),
            key=itemgetter(1),
            reverse=True
        ))
        return issuers_and_counts

    def get_ocsp_urls_for_issuer(self, issuer: str) -> MutableMapping[str, int]:
        """Retrieve all the OCSP URLs used by the authority in the wild

        :param issuer: The name of the authority to get OCSP URLs for

        :returns: A mapping of OCSP URLs to count of certificates, sorted in descending order by certificate count
        """
        ocsp_urls_report = self.censys_api.report(
            query=f'valid_nss: true AND parsed.issuer.organization: "{issuer}"',
            field='parsed.extensions.authority_info_access.ocsp_urls'
        )
        ocsp_urls_and_counts = OrderedDict(sorted(
            ((result['key'], result['doc_count']) for result in ocsp_urls_report['results']),
            key=itemgetter(1),
            reverse=True
        ))
        return ocsp_urls_and_counts

    def is_ocsp_url_current_for_issuer(self, issuer: str, url: str) -> bool:
        """Determine if an issuer is currently using a particular OCSP URL.
        A URL is deemed "current" if there is at least one non-expired, valid certificate that lists it.

        :param issuer: The name of the authority
        :param url: the OCSP URL to check

        :returns: True if the URL appears to be in use, False otherwise
        """
        tags_report = self.censys_api.report(
            query=f'valid_nss: true AND parsed.issuer.organization: "{issuer}" AND parsed.extensions.authority_info_access.ocsp_urls.raw: "{url}" AND (tags: "unexpired" OR tags: "expired")',
            field='tags'
        )
        results = {result['key']: result['doc_count'] for result in tags_report['results']}
        if results.get('unexpired', 0) > 0:
            return True
        return False

    @staticmethod
    def ping(host: str) -> bool:
        """Returns True if host responds to ping request.

        :param host: The hostname to ping

        :returns: True if an ICMP echo is received, False otherwise
        """
        logger.debug(f'Pinging {host}')
        parameters = '-n 1' if platform.system().lower() == 'windows' else '-c 1'
        return subprocess.run(f'ping {parameters} {host}', stdout=subprocess.DEVNULL).returncode == 0

    def get_example_cert_for_issuer_and_ocsp_url(self, issuer: str, url: str, accept_expired: bool=False, n: int=0) -> Union[dict, None]:
        """Retrieve a certificate issued by the authority and with a given OCSP URL, if possible.

        :param issuer: The name of the authority who issued the certificate
        :param url: The OCSP URL the certificate ought to have
        :param accept_expired: Whether an expired certificate is acceptable
        :param n: Return the nth certificate from the search. Useful if the zeroth certificate is inappropriate in some way.

        :returns: A dictionary containing the issuer urls, parsed names, and raw certificate in base64-encoded bytes or None if an error occurs
        """
        logger.debug(f'Getting example cert for {issuer}: {url}')
        base_query = f'valid_nss: true AND parsed.issuer.organization: "{issuer}" AND parsed.extensions.authority_info_access.ocsp_urls.raw: "{url}"'

        search = self.censys_api.search(
            query=f'{base_query} AND tags: "unexpired"',
            fields=['parsed.extensions.authority_info_access.issuer_urls', 'parsed.names', 'raw']
        )

        for _ in range(n):
            next(search, None)
        cert = next(search, None)

        if cert is None:
            logger.info(f'No valid certificates remain using OCSP URL {url}')
            if accept_expired:
                logger.info('Searching for an expired certificate instead')
                search = self.censys_api.search(  # willing to take an expired one? Here you go!
                    query=base_query,
                    fields=['parsed.extensions.authority_info_access.issuer_urls', 'parsed.names', 'raw']
                )

                for _ in range(n):
                    next(search, None)
                cert = next(search, None)

        return cert

    @staticmethod
    def load_issuer_cert(issuer_urls: List[str]) -> Union[asymmetric.Certificate, None]:
        """Given a list of URLs where the issuer certificate may reside, attempt to download it

        :param issuer_urls: A list of possible URLs

        :returns: A Certificate object or None if an error occurred
        """
        issuer_cert = None
        for issuer_url in issuer_urls:  # try to obtain the issuer certificate
            try:
                resp = requests.get(issuer_url)
                issuer_cert = asymmetric.load_certificate(resp.content)
                break
            except requests.RequestException:
                logger.warning(f'Failed to download issuer cert from {issuer_url}')
            except ValueError:
                logger.warning(f'Failed to load issuer cert from {issuer_url}')
        return issuer_cert

    @staticmethod
    def send_ocsp_request(subject_cert: asymmetric.Certificate, issuer_cert: asymmetric.Certificate, url: str) -> OCSPResponse:
        """Create and send an OCSP request, returning the OCSP response

        :param subject_cert: The certificate information is being requested about
        :param issuer_cert: The issuer of the subject certificate
        :param url: The URL of the OCSP responder to query

        :returns: An OCSPResponse object
        """
        builder = OCSPRequestBuilder(subject_cert, issuer_cert)
        ocsp_request = builder.build()

        parsed_ocsp_response = None
        try:
            ocsp_resp = requests.post(url, data=ocsp_request.dump(), headers={'Content-Type': 'application/ocsp-request'})
            parsed_ocsp_response = OCSPResponse.load(ocsp_resp.content)
        except requests.RequestException:
            logger.warning('Failed to make OCSP request')

        return parsed_ocsp_response

    def ocsp(self, issuer: str, url: str) -> Union[bool, OCSPVerificationResponses]:
        """Test if an OCSP server responds to requests

        :param issuer: The certificate authority under test
        :param url: The URL of the OCSP server under test

        :returns: True if the server appears to be operating, False if it is not. A value from OCSPVerficationResponses if a non-OCSP error is encountered.
        """
        logger.debug(f'Checking OCSP response for {issuer}: {url}')
        example_cert = self.get_example_cert_for_issuer_and_ocsp_url(issuer, url, accept_expired=True)

        try:
            issuer_urls = example_cert['parsed.extensions.authority_info_access.issuer_urls']
        except KeyError:  # the cert we got didn't have an issuer url, so let's try another one!
            example_cert = self.get_example_cert_for_issuer_and_ocsp_url(issuer, url, accept_expired=True, n=1)
            if not example_cert:
                return OCSPVerificationResponses.no_url
            try:
                issuer_urls = example_cert['parsed.extensions.authority_info_access.issuer_urls']
            except KeyError:  # if we don't get one here, give up
                return OCSPVerificationResponses.no_url

        issuer_cert = self.load_issuer_cert(issuer_urls)
        if not issuer_cert:
            return OCSPVerificationResponses.no_cert_download

        example_cert_bytes = base64.b64decode(example_cert['raw'])
        subject_cert = asymmetric.load_certificate(example_cert_bytes)

        parsed_ocsp_response = self.send_ocsp_request(subject_cert, issuer_cert, url)
        return parsed_ocsp_response and parsed_ocsp_response.native['response_status'] == 'successful'
