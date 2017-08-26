"""The CLI module for OCSPdash."""
import base64
import datetime
import json
import logging
import os
import secrets
import urllib.parse
from collections import OrderedDict

import click
import nacl.encoding
import nacl.signing

from .manager import Manager
from .models import Location
from .server_query import ServerQuery, check_ocsp_response, ping
from .util import requests_session
from .web.app import create_application


@click.group()
def main():
    """Run OCSP Dashboard"""


@main.command()
@click.option('-n', default=2, type=int, help='Number of top authorities')
@click.option('-o', is_flag=True, help='Output as JSON')
@click.option('-v', is_flag=True, help='Verbose output')
def run(n, o, v):
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
        (
            issuer,
            OrderedDict(
                (url, {'current': None, 'ping': None, 'ocsp_response': None})
                for url in urls
            )
        )
        for issuer, urls in ocsp_reports.items()
    )

    for issuer, urls in test_results.items():
        for url, results in urls.items():
            results['timestamp'] = datetime.datetime.utcnow().timestamp()
            # check if current
            results['current'] = server_query.is_ocsp_url_current_for_issuer(issuer, url)
            # run ping test
            parse_result = urllib.parse.urlparse(url)
            results['ping'] = ping(parse_result.netloc)

            # run OCSP response test
            # TODO: cache this for the validity time of subject_cert or 7 days, whichever is smaller
            certs = server_query.get_certs_for_issuer_and_url(issuer, url)

            if certs is None:
                results['ocsp_response'] = False
            else:
                subject_cert, issuer_cert = certs
                results['ocsp_response'] = check_ocsp_response(subject_cert, issuer_cert, url)

    if o:
        print(json.dumps(test_results, indent=2))
    else:
        for issuer, urls in test_results.items():
            print(issuer)
            for url, results in urls.items():
                print(
                    f'>>> {url}: {"." if results["current"] else "X"}{"." if results["ping"] else "X"}{"." if results["ocsp_response"] else "X"}')


@main.command()
@click.option('--host', default='0.0.0.0', help='Flask host. Defaults to localhost')
@click.option('--port', type=int, help='Flask port. Defaults to 5000')
@click.option('--flask-debug', is_flag=True)
@click.option('-v', '--verbose', is_flag=True, help='Verbose output')
def web(host, port, flask_debug, verbose):
    """Run the Flask development server"""
    logging.basicConfig(level=(logging.DEBUG if verbose else logging.INFO))

    create_application().run(host=host, port=port, debug=flask_debug)


@main.command()
@click.option('-n', default=2, type=int, help='Number of top authorities')
@click.option('--connection')
@click.option('-v', '--verbose', is_flag=True, help='Verbose output')
@click.option('-u', '--username', default='test', help='Username to use')
def update(n, connection, verbose, username):
    """Update the local db"""
    logging.basicConfig(level=(logging.DEBUG if verbose else logging.INFO))

    m = Manager(connection=connection)
    user = m.get_or_create_location(username)
    m.update(user, n=n)


@main.command()
@click.option('--connection')
def nuke(connection):
    """Nukes the database"""
    if click.confirm('Nuke the database?'):
        m = Manager(connection=connection, echo=True)
        m.drop_database()


@main.command()
@click.option('--connection')
@click.argument('location_name')
def newloc(connection, location_name):
    m = Manager(connection)
    registration_token = secrets.token_bytes()
    new_location = Location(
        name=location_name,
        pubkey=registration_token,
        activated=False
    )
    m.session.add(new_location)
    m.session.commit()
    click.echo(f'{new_location.id}:{base64.urlsafe_b64encode(registration_token).decode("utf-8")}')


@main.command()
@click.argument('url')
@click.argument('registration_token')
def register(url, registration_token):
    """Register a new private key with the server"""
    private_key = nacl.signing.SigningKey.generate()
    public_key = private_key.verify_key.encode(encoder=nacl.encoding.URLSafeBase64Encoder)

    resp = requests_session.post(urllib.parse.urljoin(url, '/api/v0/register'),
                                 headers={'Authorization': registration_token},
                                 data=public_key)

    click.echo(resp.content)
    click.echo(private_key.encode(nacl.encoding.URLSafeBase64Encoder))


@main.command()
@click.argument('url')
@click.option('--connection')
def submit(url, connection):
    """Submit recent updates to the sever"""
    location_id, private_key_bytes = os.environ.get('OCSPDASH_PRIVATE_KEY').split(':', 1)
    private_key = nacl.signing.SigningKey(private_key_bytes, encoder=nacl.encoding.URLSafeBase64Encoder)

    m = Manager(connection)
    results = json.dumps(m.get_results())
    results_bytes = base64.urlsafe_b64encode(results.encode('utf-8'))

    signed = private_key.sign(results_bytes, nacl.encoding.URLSafeBase64Encoder)

    resp = requests_session.post(urllib.parse.urljoin(url, '/submit'), headers={'Authorization': location_id},
                                 data=signed)

    click.echo(resp.status_code)


if __name__ == '__main__':
    main()
