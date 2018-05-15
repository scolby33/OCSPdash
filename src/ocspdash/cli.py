# -*- coding: utf-8 -*-

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
from argon2 import PasswordHasher  # TODO: use passlib for upgradability?
from requests import Response

from ocspdash.manager import Manager
from ocspdash.models import Invite
from ocspdash.server_query import ServerQuery, check_ocsp_response, ping
from ocspdash.util import requests_session


@click.group()
def main():
    """Run OCSP Dashboard"""


@main.command()
@click.option('-n', '--buckets', default=2, type=int, help='Number of top authorities')
@click.option('-o', is_flag=True, help='Output as JSON')
@click.option('-v', '--verbose', is_flag=True, help='Verbose output')
def run(buckets, o, verbose):
    logging.basicConfig(level=(logging.DEBUG if verbose else logging.INFO))

    server_query = ServerQuery(os.environ.get('UID'), os.environ.get('SECRET'))

    issuers = server_query.get_top_authorities(buckets=buckets)  # TODO: cache this result for 24 hours

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
            subject_cert, issuer_cert = server_query.get_certs_for_issuer_and_url(issuer, url)

            if subject_cert is None or issuer_cert is None:
                results['ocsp_response'] = False
            else:
                results['ocsp_response'] = check_ocsp_response(subject_cert, issuer_cert, url)

    if o:
        click.echo(json.dumps(test_results, indent=2))
    else:
        for issuer, urls in test_results.items():
            click.echo(issuer)
            for url, results in urls.items():
                click.echo(
                    f'>>> {url}: {"." if results["current"] else "X"}{"." if results["ping"] else "X"}{"." if results["ocsp_response"] else "X"}')


@main.command()
@click.option('--host', default='0.0.0.0', help='Flask host. Defaults to localhost')
@click.option('--port', type=int, default=8000, help='Flask port.')
@click.option('--flask-debug', is_flag=True)
@click.option('-v', '--verbose', is_flag=True, help='Verbose output')
def web(host, port, flask_debug, verbose):
    """Run the Flask development server"""
    logging.basicConfig(level=(logging.DEBUG if verbose else logging.INFO))

    from ocspdash.web import create_application
    app = create_application()
    app.run(host=host, port=port, debug=flask_debug)


@main.command()
@click.option('-n', '--buckets', default=2, type=int, help='Number of top authorities')
@click.option('--connection')
@click.option('-v', '--verbose', is_flag=True, help='Verbose output')
@click.option('-u', '--username', default='test', help='Username to use')
def update(buckets, connection, verbose, username):
    """Update the local db"""
    logging.basicConfig(level=(logging.DEBUG if verbose else logging.INFO))

    m = Manager(connection=connection)
    location = m.get_or_create_location(name=username)
    m.update(location, buckets=buckets)


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
    invite_id = secrets.token_bytes(16)
    invite_validator = secrets.token_bytes(16)
    ph = PasswordHasher()
    invite_validator_hash = ph.hash(invite_validator)

    new_invite = Invite(
        name=location_name,
        invite_id=invite_id,
        invite_validator=invite_validator_hash
    )
    m.session.add(new_invite)
    m.session.commit()

    click.echo(f'{new_invite.id}:{base64.urlsafe_b64encode(invite_id+invite_validator).decode("utf-8")}')


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


def make_submission(url: str, location_id, private_key_bytes, results) -> Response:
    private_key = nacl.signing.SigningKey(private_key_bytes, encoder=nacl.encoding.URLSafeBase64Encoder)

    results_bytes = base64.urlsafe_b64encode(json.dumps(results).encode('utf-8'))

    signed = private_key.sign(results_bytes, nacl.encoding.URLSafeBase64Encoder)

    return requests_session.post(
        urllib.parse.urljoin(url, '/submit'),
        headers={'Authorization': location_id},
        data=signed
    )


@main.command()
@click.argument('url')
@click.option('--connection')
def submit(url, connection):
    """Submit recent updates to the sever"""
    location_id, private_key_bytes = os.environ.get('OCSPDASH_PRIVATE_KEY').split(':', 1)
    manager = Manager(connection)
    results = manager.get_results()
    resp = make_submission(url, location_id, private_key_bytes, results)
    click.echo(resp.status_code)


if __name__ == '__main__':
    main()
