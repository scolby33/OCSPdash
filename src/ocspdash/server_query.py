import base64
import logging
import platform
import subprocess
from collections import OrderedDict
from operator import itemgetter
from typing import MutableMapping, Tuple, Union

import requests
from asn1crypto.ocsp import OCSPResponse
from ocspbuilder import OCSPRequestBuilder
from oscrypto import asymmetric

from .util import RateLimitedCensysCertificates

logger = logging.getLogger(__name__)


class ServerQuery(RateLimitedCensysCertificates):
    def get_top_authorities(self, count: int = 10) -> MutableMapping[str, int]:
        """Retrieve the name and count of certificates for the top n certificate authorities by number of certs

        :param count: The number of top authorities to retrieve

        :returns: A mapping of authority name to count of certificates, sorted in descending order by certificate count
        """
        issuers_report = self.report(query='valid_nss: true', field='parsed.issuer.organization', buckets=count)
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
        ocsp_urls_report = self.report(
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
        tags_report = self.report(
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
        parameters = ['-n', '1'] if platform.system().lower() == 'windows' else ['-c', '1']
        results = subprocess.run(['ping'] + parameters + [host], stdout=subprocess.DEVNULL)
        return results.returncode == 0

    def get_certs_for_issuer_and_url(self, issuer: str, url: str) -> Union[Tuple[bytes, bytes], None]:
        """Retrieve the raw bytes for an example subject certificate and its issuing cert for a given authority and OCSP url

        :param issuer: The name of the authority from which a certificate is sought
        :param url: The OCSP URL that the certificate ought to have

        :returns: A tuple of (subject cert bytes, issuer cert bytes) or None if unsuccessful
        """
        logger.debug(f'Getting raw certificates for {issuer}: {url}')

        logger.debug(f'Getting example cert for {issuer}: {url}')
        base_query = f'valid_nss: true AND parsed.issuer.organization: "{issuer}" AND parsed.extensions.authority_info_access.ocsp_urls.raw: "{url}" AND parsed.extensions.authority_info_access.issuer_urls: /.+/'
        search = self.search(
            query=f'{base_query} AND tags: "unexpired"',
            fields=['parsed.extensions.authority_info_access.issuer_urls', 'parsed.names', 'raw']
        )
        subject_cert = next(search, None)
        if subject_cert is None:
            logger.info(f'No valid certificates remain using OCSP URL {url}')
            logger.info('Searching for an expired certificate instead')
            search = self.search(
                query=base_query,
                fields=['parsed.extensions.authority_info_access.issuer_urls', 'parsed.names', 'raw']
            )
            subject_cert = next(search, None)
            if subject_cert is None:
                return

        logger.debug(f'Getting issuer cert for {issuer}: {url}')
        issuer_urls = subject_cert['parsed.extensions.authority_info_access.issuer_urls']
        for issuer_url in issuer_urls:
            try:
                resp = requests.get(issuer_url)
                if resp.content:
                    break
            except requests.RequestException:
                logger.warning(f'Failed to download issuer cert from {issuer_url}')
        else:
            return

        return base64.b64decode(subject_cert['raw']), resp.content


def check_ocsp_response(subject_cert: bytes, issuer_cert: bytes, url: str) -> bool:
    """Create and send an OCSP request

    :param subject_cert: The certificate that information is being requested about
    :param issuer_cert: The issuer of the subject certificate
    :param url: The URL of the OCSP responder to query

    :returns: True if the request was successful, False otherwise
    """
    logger.debug(f'Checking OCSP response for {url}')
    subject = asymmetric.load_certificate(subject_cert)
    issuer = asymmetric.load_certificate(issuer_cert)

    builder = OCSPRequestBuilder(subject, issuer)
    ocsp_request = builder.build()

    try:
        ocsp_resp = requests.post(url, data=ocsp_request.dump(),
                                  headers={'Content-Type': 'application/ocsp-request'})
        parsed_ocsp_response = OCSPResponse.load(ocsp_resp.content)
    except requests.RequestException:
        logger.warning(f'Failed to make OCSP request for {issuer}: {url}')
        return False

    return parsed_ocsp_response and parsed_ocsp_response.native['response_status'] == 'successful'
