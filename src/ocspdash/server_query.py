# -*- coding: utf-8 -*-

"""Classes for querying Censys.io data on certificates."""

import base64
import logging
from collections import OrderedDict
from operator import itemgetter
from typing import MutableMapping, Tuple, Union

import requests

from ocspdash.util import RateLimitedCensysCertificates, requests_session

logger = logging.getLogger(__name__)


def _get_results(report):
    return sorted(
        report['results'],
        key=itemgetter('doc_count'),
        reverse=True
    )


def _get_results_as_dict(report):
    results = _get_results(report)

    return OrderedDict([
        (result['key'], result['doc_count'])
        for result in results
    ])


class ServerQuery(RateLimitedCensysCertificates):
    """An interface to Censys.io's REST API."""

    def get_top_authorities(self, buckets: int = 10) -> MutableMapping[str, int]:
        """Retrieve the name and count of certificates for the top n certificate authorities by number of certs.

        :param buckets: The number of top authorities to retrieve

        :returns: A mapping of authority name to count of certificates, sorted in descending order by certificate count
        """
        report = self.report(
            query='validation.nss.valid: true',
            field='parsed.issuer.organization',
            buckets=buckets
        )

        return _get_results_as_dict(report)

    def get_ocsp_urls_for_issuer(self, issuer: str) -> MutableMapping[str, int]:
        """Retrieve all the OCSP URLs used by the authority in the wild.

        :param issuer: The name of the authority to get OCSP URLs for

        :returns: A mapping of OCSP URLs to count of certificates, sorted in descending order by certificate count
        """
        report = self.report(
            query=f'validation.nss.valid: true AND parsed.issuer.organization: "{issuer}"',
            field='parsed.extensions.authority_info_access.ocsp_urls'
        )

        return _get_results_as_dict(report)

    @staticmethod
    def _url_not_expired(results):
        return results.get('unexpired', 0) > 0

    def is_ocsp_url_current_for_issuer(self, issuer: str, url: str) -> bool:
        """Determine if an issuer is currently using a particular OCSP URL.

        A URL is deemed "current" if there is at least one non-expired, valid certificate that lists it.

        :param issuer: The name of the authority
        :param url: the OCSP URL to check

        :returns: True if the URL appears to be in use, False otherwise
        """
        tags_report = self.report(
            query=f'validation.nss.valid: true AND parsed.issuer.organization: "{issuer}" AND parsed.extensions.authority_info_access.ocsp_urls.raw: "{url}" AND (tags: "unexpired" OR tags: "expired")',
            field='tags'
        )

        results = {
            result['key']: result['doc_count']
            for result in tags_report['results']
        }

        return self._url_not_expired(results)

    def get_certs_for_issuer_and_url(self, issuer: str, url: str) -> Union[Tuple[bytes, bytes], Tuple[None, None]]:
        """Retrieve the raw bytes for an example subject certificate and its issuing cert for a given authority and OCSP url.

        :param issuer: The name of the authority from which a certificate is sought
        :param url: The OCSP URL that the certificate ought to have

        :returns: A tuple of (subject cert bytes, issuer cert bytes) or None if unsuccessful
        """
        logger.debug(f'Getting raw certificates for {issuer}: {url}')

        logger.debug(f'Getting example cert for {issuer}: {url}')
        base_query = f'validation.nss.valid: true AND parsed.issuer.organization: "{issuer}" AND parsed.extensions.authority_info_access.ocsp_urls.raw: "{url}" AND parsed.extensions.authority_info_access.issuer_urls: /.+/'
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
                return None, None

        logger.debug(f'Getting issuer cert for {issuer}: {url}')
        issuer_urls = subject_cert['parsed.extensions.authority_info_access.issuer_urls']
        for issuer_url in issuer_urls:
            try:
                resp = requests_session.get(issuer_url)
                resp.raise_for_status()
                if resp.content:
                    break
            except requests.RequestException:
                logger.warning(f'Failed to download issuer cert from {issuer_url}')
        else:
            return None, None

        return base64.b64decode(subject_cert['raw']), resp.content
