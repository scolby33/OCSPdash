import base64
from collections import OrderedDict
import logging
from operator import itemgetter
import os
import platform
import subprocess

from asn1crypto.ocsp import OCSPResponse
from ocspbuilder import OCSPRequestBuilder
from oscrypto import asymmetric
import requests

from .util import RateLimitedCensysCertificates

UID = os.environ.get('UID')
SECRET = os.environ.get('SECRET')

logger = logging.getLogger(__name__)


class ServerQuery(object):
    def __init__(self, api_id, api_secret):
        self.censys_api = RateLimitedCensysCertificates(api_id, api_secret)

    def get_top_authorities(self, n=10):
        issuers_report = self.censys_api.report(query='valid_nss: true', field='parsed.issuer.organization', buckets=n)
        issuers_and_counts = OrderedDict(sorted(
            ((result['key'], result['doc_count']) for result in issuers_report['results']),
            key=itemgetter(1),
            reverse=True
        ))
        return issuers_and_counts

    def get_ocsp_urls_for_issuer(self, issuer):
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

    def is_ocsp_url_current_for_issuer(self, issuer, url):
        tags_report = self.censys_api.report(
            query=f'valid_nss: true AND parsed.issuer.organization: "{issuer}" AND parsed.extensions.authority_info_access.ocsp_urls.raw: "{url}" AND (tags: "unexpired" OR tags: "expired")',
            field='tags'
        )
        results = {result['key']: result['doc_count'] for result in tags_report['results']}
        if results.get('unexpired', 0) > 0:
            return True
        return False

    @staticmethod
    def ping(host):
        """Returns True if host responds to ping request."""
        logger.debug(f'Pinging {host}')
        parameters = '-n 1' if platform.system().lower() == 'windows' else '-c 1'
        return subprocess.run(f'ping {parameters} {host}', stdout=subprocess.DEVNULL).returncode == 0

    def get_example_cert_for_issuer_and_ocsp_url(self, issuer, url, accept_expired=False, n=0):
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
    def load_issuer_cert(issuer_urls):
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
    def send_ocsp_request(subject_cert, issuer_cert, url):
        builder = OCSPRequestBuilder(subject_cert, issuer_cert)
        ocsp_request = builder.build()

        parsed_ocsp_response = None
        try:
            ocsp_resp = requests.post(url, data=ocsp_request.dump(), headers={'Content-Type': 'application/ocsp-request'})
            parsed_ocsp_response = OCSPResponse.load(ocsp_resp.content)
        except requests.RequestException:
            logger.warning('Failed to make OCSP request')

        return parsed_ocsp_response


    def ocsp(self, issuer, url):
        logger.debug(f'Checking OCSP response for {issuer}: {url}')
        example_cert = self.get_example_cert_for_issuer_and_ocsp_url(issuer, url, accept_expired=True)

        try:
            issuer_urls = example_cert['parsed.extensions.authority_info_access.issuer_urls']
        except KeyError:  # the cert we got didn't have an issuer url, so let's try another one!
            example_cert = self.get_example_cert_for_issuer_and_ocsp_url(issuer, url, accept_expired=True, n=1)
            if not example_cert:
                return 'No Issuer Url'
            try:
                issuer_urls = example_cert['parsed.extensions.authority_info_access.issuer_urls']
            except KeyError:  # if we don't get one here, give up
                return 'No Issuer Url'

        issuer_cert = self.load_issuer_cert(issuer_urls)
        if not issuer_cert:
            return 'Failed to Download Issuer Cert'

        example_cert_bytes = base64.b64decode(example_cert['raw'])
        subject_cert = asymmetric.load_certificate(example_cert_bytes)

        parsed_ocsp_response = self.send_ocsp_request(subject_cert, issuer_cert, url)
        if parsed_ocsp_response and parsed_ocsp_response.native['response_status'] == 'successful':
            return True
        else:
            return False
