# -*- coding: utf-8 -*-

"""OCSPscrape.

Usage:
    ocspscrape
    ocspscrape genkey [--fish] <invite-token>
    ocspscrape extractkey [--notrunc] <token>

Options:
    --fish      output an environment file suitable for
                the fish shell instead of POSIX
    --notrunc   do not truncate public key output

Description:
    ocspscrape:
        Reads JSON Lines indicating responders to be scraped from STDIN
        and writes a JWT of results suitable for POSTing to STDOUT.
        Progress information is printed to STDERR.

    ocspscrape genkey:
        Generates an EC key pair for signing submissions.
        Environment variable declarations suitable for sourcing from a file
        are written to STDERR and a JWT suitable for POSTing to the server
        are written to STDOUT.

    ocspscrape extractkey:
        Given a JWT as output by `ocspscrape genkey`, print the details in
        a human-readable format.

Examples:
    Scrape OCSP responders and submit results:
        source ocspscrape.env ; \\
        curl http://ocsp.dash/queries.jsonl | ocspscrape | \\
        curl -d @- http://ocsp.dash/results

    Generate a keypair and register with the server:
        ocspscrape genkey 'my-invite-token' 2>ocspscrape.env | \\
        curl -d @- http://ocsp.dash/register

    Inspect the output from ocspscrape genkey:
        ocspscrape genkey 'my-invite-token' | \\
        xargs ocspscrape extractkey

"""
# TODO docstrings for new functions
import json
import os
import platform
import subprocess
import sys
import urllib.parse
import uuid
from base64 import urlsafe_b64decode as b64decode
from base64 import urlsafe_b64encode as b64encode
from datetime import datetime

import requests
from asn1crypto.ocsp import OCSPResponse
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from docopt import docopt
from jose import jwt
from ocspbuilder import OCSPRequestBuilder
from oscrypto import asymmetric
from tqdm import tqdm

# TODO: should this be from constants.py or kept separate to have this module be freestanding/a separate package?
NAMESPACE_OCSPDASH_KID = uuid.UUID('c81dcfc6-2131-4d05-8ea4-4e5ad8123696')
RESULTS_JWT_CLAIM = 'res'
JWT_ALGORITHM = 'ES512'


def main():
    arguments = docopt(__doc__, version='OCSPscrape 0.1.0')
    if arguments['genkey']:
        token, private_key = genkey(arguments['<invite-token>'])
        if not arguments['--fish']:
            print(f"export OCSPSCRAPE_PRIVATE_KEY='{private_key}'", file=sys.stderr)
        else:
            print(f"set -gx OCSPSCRAPE_PRIVATE_KEY '{private_key}'", file=sys.stderr)
        print(token)
    elif arguments['extractkey']:
        claims = extract_claims(arguments['<token>'])
        if arguments['--notrunc']:
            print(f'public key:\t{claims["pk"]}'.expandtabs(7))
        else:
            print(f'public key:\t{claims["pk"]}'.expandtabs(7)[:78] + '..')
        print(f'invite token:\t{claims["token"]}'.expandtabs(7))
    else:
        token = scrape(
            json.loads(line)
            for line in tqdm(sys.stdin)
        )
        print(token)


def genkey(invite_token: str):
    private_key = ec.generate_private_key(ec.SECP521R1, default_backend())
    serialized_private_key = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    ).decode('utf-8')
    public_key = b64encode(private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )).decode('utf-8')

    payload = {
        'pk': public_key,
        'token': invite_token
    }
    token = jwt.encode(payload, private_key, algorithm=JWT_ALGORITHM)

    return token, serialized_private_key


def extract_claims(token: str):
    unverified_claims = jwt.get_unverified_claims(token)
    public_key = b64decode(unverified_claims['pk']).decode('utf-8')
    claims = jwt.decode(token, public_key, algorithms=[JWT_ALGORITHM])
    return claims


def scrape(queries):
    # TODO needs type hint for return
    requests_session = requests.Session()
    requests_session.headers.update({'User-Agent': ' '.join([requests.utils.default_user_agent(), 'OCSPscrape 0.1.0'])})

    payload = {RESULTS_JWT_CLAIM: []}

    for query in queries:
        query_id = query['id']

        url = query['url']
        netloc = urllib.parse.urlparse(url).netloc

        subject_bytes = b64decode(query['subject'])
        issuer_bytes = b64decode(query['issuer'])

        time = datetime.utcnow().strftime('%FT%TZ')
        ping_result = ping(netloc)
        ocsp_result = check_ocsp_response(subject_bytes, issuer_bytes, url, requests_session)

        payload[RESULTS_JWT_CLAIM].append({
            'id': query_id,
            'time': time,
            'ping': ping_result,
            'ocsp': ocsp_result
        })

    # TODO handle missing env vars more gracefully
    key = os.environ['OCSPSCRAPE_PRIVATE_KEY']
    key_id = str(_keyid_from_private_key(key))
    payload['iat'] = datetime.utcnow()
    token = jwt.encode(payload, key, headers={'kid': key_id}, algorithm=JWT_ALGORITHM)
    return token


def _keyid_from_private_key(private_key_data: str) -> uuid.UUID:
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
    """Returns True if host responds to ping request.

    :param host: The hostname to ping

    :returns: True if an ICMP echo is received, False otherwise
    """
    parameters = ['-n', '1'] if platform.system().lower() == 'windows' else ['-c', '1']
    results = subprocess.run(['ping'] + parameters + [host], stdout=subprocess.DEVNULL)
    return results.returncode == 0


def check_ocsp_response(subject_cert: bytes, issuer_cert: bytes, url: str, session: requests.Session) -> bool:
    """Create and send an OCSP request

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


if __name__ == '__main__':
    sys.exit(main())
