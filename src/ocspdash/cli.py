"""The CLI module for OCSPdash."""
from collections import OrderedDict
import logging
import json
import os
import urllib.parse

import click

from .server_query import ServerQuery


@click.command()
@click.option('-n', default=2, help='Number of top authorities')
@click.option('-o', is_flag=True, help='Output as JSON')
@click.option('-v', is_flag=True, help='Verbose output')
def main(n, o, v):
    if v:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    server_query = ServerQuery(os.environ.get('UID'), os.environ.get('SECRET'))

    issuers = server_query.get_top_authorities(n)

    ocsp_reports = OrderedDict(
        (issuer, server_query.get_ocsp_urls_for_issuer(issuer))
        for issuer in issuers.keys()
    )

    test_results = OrderedDict(
        (issuer, OrderedDict((url, {'current': None, 'ping': None, 'ocsp_response': None}) for url in urls))
        for issuer, urls in ocsp_reports.items()
    )

    for issuer, urls in test_results.items():
        for url, results in urls.items():
            # check if current
            current = server_query.is_ocsp_url_current_for_issuer(issuer, url)
            results['current'] = current
            # run ping test
            host = urllib.parse.urlparse(url)[1]
            results['ping'] = server_query.ping(host)
            # run OCSP response test
            results['ocsp_response'] = server_query.ocsp(issuer, url)

    if o:
        print(json.dumps(test_results, indent=2))
    else:
        for issuer, urls in test_results.items():
            print(issuer)
            for url, results in urls.items():
                if results['ocsp_response'] is True:
                    ocsp_status = '.'
                elif results['ocsp_response'] == 'No Issuer Url':
                    ocsp_status = 'I'
                elif results['ocsp_response'] == 'Failed to Download Issuer Cert':
                    ocsp_status = 'D'
                else:
                    ocsp_status = 'X'

                print(f'>>> {url}: {"." if results["current"] else "X"}{"." if results["ping"] else "X"}{ocsp_status}')


if __name__ == '__main__':
    main()