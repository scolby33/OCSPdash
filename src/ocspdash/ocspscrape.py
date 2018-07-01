# -*- coding: utf-8 -*-

r"""OCSPscrape.

Description:
    ocspscrape update:
        Gets a list of responders to scrape from the OCSPdash, scrapes
        them, then uploads the results.

    ocspscrape genkey:
        Generates an EC key pair for signing submissions and registers
        with the OCSPdash server.

    ocspscrape extractkey:
        Given a JWT as output by `ocspscrape genkey`, print the details in
        a human-readable format.

Examples:
    Generate a keypair and register with the server:
        ocspscrape genkey 'my-invite-token'

    Inspect the output from ocspscrape genkey:
        ocspscrape genkey 'my-invite-token' | \
        xargs ocspscrape extractkey

"""

import json
import os
import platform
import subprocess
import sys
import urllib.parse
import uuid
from base64 import urlsafe_b64decode as b64decode, urlsafe_b64encode as b64encode
from datetime import datetime
from functools import partial
from typing import Iterable, Mapping

import click
import requests
from asn1crypto.ocsp import OCSPResponse
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from jose import jwt
from ocspbuilder import OCSPRequestBuilder
from oscrypto import asymmetric

from ocspdash.constants import NAMESPACE_OCSPDASH_KID, OCSP_RESULTS_JWT_CLAIM, OCSP_JWT_ALGORITHM

API_URL = 'api/v0/'
MANIFEST_URL = urllib.parse.urljoin(API_URL, 'manifest.jsonl')
SUBMIT_URL = urllib.parse.urljoin(API_URL, 'submit')
REGISTER_URL = urllib.parse.urljoin(API_URL, 'resigter')

config_directory = os.path.join(os.path.expanduser('~'), '.config', 'ocspdash')
if not os.path.exists(config_directory):
    os.makedirs(config_directory)

private_key_path = os.path.join(config_directory, 'private.txt')


def get_private_key() -> str:
    """Get the serialized private key to use."""
    with open(private_key_path) as f:
        return f.read()


def write_private_key(serialized_private_key: str):
    """Write the serialized private key to a configuration file.

    :param serialized_private_key: The private key to write
    """
    with open(private_key_path, 'w') as file:
        print(serialized_private_key, file=file)


@click.group()
@click.version_option('0.1.0')
def main():
    """Run the OCSPscrape tool."""


# TODO better loading of default host

@main.command()
@click.argument('invite_token')
@click.option('--host', default='http://localhost:8000')
@click.option('--no-post', is_flag=True)
def genkey(invite_token, host, no_post):
    """Generate a new public/private keypair."""
    private_key = ec.generate_private_key(ec.SECP521R1, default_backend())

    serialized_private_key = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    ).decode('utf-8')
    write_private_key(serialized_private_key)

    public_key = b64encode(private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )).decode('utf-8')

    payload = {
        'pk': public_key,
        'token': invite_token
    }
    token = jwt.encode(payload, private_key, algorithm=OCSP_JWT_ALGORITHM)

    if no_post:
        click.echo(token)

    else:
        # TODO: set useragent
        res = requests.post(
            urllib.parse.urljoin(host, REGISTER_URL),
            headers={'Content-Type': 'application/octet-stream'},
            data=token,
        )
        res.raise_for_status()


@main.command()
@click.option('--host', default='http://localhost:8000')
@click.option('--no-post', is_flag=True)
def update(host, no_post):
    """Scrape updates and post."""
    # TODO provide alternate options for loading a private key
    private_key = get_private_key()

    manifest_response = requests.get(urllib.parse.urljoin(host, MANIFEST_URL))

    if manifest_response.encoding is None:
        manifest_response.encoding = 'utf-8'

    queries = (
        json.loads(line)
        for line in manifest_response.iter_lines(decode_unicode=True)
        if line
    )

    token = scrape(key=private_key, queries=queries)

    if no_post:
        click.echo(token)

    else:
        submission_response = requests.post(
            urllib.parse.urljoin(host, SUBMIT_URL),
            headers={'Content-Type': 'application/octet-stream'},
            data=token,
        )

        submission_response.raise_for_status()


def _build_claim(session: requests.Session, query: Mapping) -> Mapping:
    """Build a result dictionary.

    :param session: A requests Session
    :param query: The data from a responder
    """
    responder_url = query['responder_url']
    netloc = urllib.parse.urlparse(responder_url).netloc

    subject_bytes = b64decode(query['subject_certificate'])
    issuer_bytes = b64decode(query['issuer_certificate'])

    time = datetime.utcnow().strftime('%FT%TZ')
    ping_result = ping(netloc)
    ocsp_result = check_ocsp_response(subject_bytes, issuer_bytes, responder_url, session)

    return {
        'chain_certificate_hash': query['chain_certificate_hash'],
        'time': time,
        'ping': ping_result,
        'ocsp': ocsp_result
    }


def scrape(key: str, queries: Iterable[Mapping]) -> str:
    """Scrape the OCSP responders provided.

    :param key: The private key
    :param queries: An iterator over JSON dictionaries representing the manifest from OCSPdash
    """
    session = requests.Session()
    session.headers.update({'User-Agent': ' '.join([requests.utils.default_user_agent(), 'OCSPscrape 0.1.0'])})
    build_claim = partial(_build_claim, session)

    claims = {
        'iat': datetime.utcnow(),
        OCSP_RESULTS_JWT_CLAIM: [build_claim(query) for query in queries]
    }

    key_id = str(_keyid_from_private_key(key))

    return jwt.encode(
        claims=claims,
        key=key,
        headers={'kid': key_id},
        algorithm=OCSP_JWT_ALGORITHM
    )


def _keyid_from_private_key(private_key_data: str) -> uuid.UUID:
    """Get a UUID for a private key.

    :param private_key_data: The data for a private key
    """
    loaded_private_key = serialization.load_pem_private_key(
        data=private_key_data.encode('utf-8'),
        password=None,
        backend=default_backend()
    )
    public_key = b64encode(loaded_private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )).decode('utf-8')
    key_id = uuid.uuid5(NAMESPACE_OCSPDASH_KID, public_key)
    return key_id


def ping(host: str) -> bool:
    """Return if the host responds to a ping request.

    :param host: The hostname to ping

    :returns: True if an ICMP echo is received, False otherwise
    """
    parameters = ['-n', '1'] if platform.system().lower() == 'windows' else ['-c', '1']
    results = subprocess.run(['ping'] + parameters + [host], stdout=subprocess.DEVNULL)
    return results.returncode == 0


def check_ocsp_response(subject_cert: bytes, issuer_cert: bytes, url: str, session: requests.Session) -> bool:
    """Create and send an OCSP request.

    :param subject_cert: The certificate that information is being requested about
    :param issuer_cert: The issuer of the subject certificate
    :param url: The URL of the OCSP responder to query
    :param session: A requests session

    :returns: True if the request was successful, False otherwise
    """
    try:
        subject = asymmetric.load_certificate(subject_cert)
        issuer = asymmetric.load_certificate(issuer_cert)
    except TypeError:
        return False

    builder = OCSPRequestBuilder(subject, issuer)
    ocsp_request = builder.build()

    try:
        ocsp_resp = session.post(url, data=ocsp_request.dump(), headers={'Content-Type': 'application/ocsp-request'})
    except requests.RequestException:
        return False

    try:
        parsed_ocsp_response = OCSPResponse.load(ocsp_resp.content)
    except ValueError:
        return False

    return parsed_ocsp_response and parsed_ocsp_response.native['response_status'] == 'successful'


@main.command()
@click.argument('token')
@click.option('--notrunc', is_flag=True)
def extractkey(token: str, notrunc: bool):
    """Extract the claims from a generate JWT and print them nicely."""
    # FIXME its not obvious what to put in as the token here...
    unverified_claims = jwt.get_unverified_claims(token)
    public_key = b64decode(unverified_claims['pk']).decode('utf-8')
    claims = jwt.decode(token, public_key, algorithms=[OCSP_JWT_ALGORITHM])

    if notrunc:
        click.echo(f'public key:\t{claims["pk"]}'.expandtabs(7))
    else:
        click.echo(f'public key:\t{claims["pk"]}'.expandtabs(7)[:78] + '..')

    click.echo(f'invite token:\t{claims["token"]}'.expandtabs(7))


if __name__ == '__main__':
    sys.exit(main())
