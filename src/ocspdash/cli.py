"""The CLI module for OCSPdash."""
from collections import OrderedDict
import datetime
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

    issuers = server_query.get_top_authorities(n)  # TODO: cache this result for 24 hours

    ocsp_reports = OrderedDict(  # TODO: cache this result for 24 hours
        (issuer, server_query.get_ocsp_urls_for_issuer(issuer))
        for issuer in issuers.keys()
    )

    test_results = OrderedDict(
        (issuer, OrderedDict((url, {'current': None, 'ping': None, 'ocsp_response': None}) for url in urls))
        for issuer, urls in ocsp_reports.items()
    )

    for issuer, urls in test_results.items():
        for url, results in urls.items():
            results['timestamp'] = datetime.datetime.utcnow().timestamp()
            # check if current
            current = server_query.is_ocsp_url_current_for_issuer(issuer, url)
            results['current'] = current
            # run ping test
            host = urllib.parse.urlparse(url)[1]
            results['ping'] = server_query.ping(host)
            # run OCSP response test
            certs = server_query.get_certs_for_issuer_and_url(issuer, url)  # TODO: cache this for the validity time of subject_cert or 7 days, whichever is smaller

            results['ocsp_response'] = server_query.check_ocsp_response(*certs, url) if certs else False

    if o:
        print(json.dumps(test_results, indent=2))
    else:
        for issuer, urls in test_results.items():
            print(issuer)
            for url, results in urls.items():
                print(f'>>> {url}: {"." if results["current"] else "X"}{"." if results["ping"] else "X"}{"." if results["ocsp_response"] else "X"}')


if __name__ == '__main__':
    main()
