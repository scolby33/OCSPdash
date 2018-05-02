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
from base64 import urlsafe_b64decode as b64decode, urlsafe_b64encode as b64encode
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

NAMESPACE_OCSPDASH_KID = uuid.UUID('c81dcfc6-2131-4d05-8ea4-4e5ad8123696')
RESULTS_JWT_CLAIM = 'res'
JWT_ALGORITHM = 'ES512'


def main():
    arguments = docopt(__doc__, version='OCSPscrape 0.1.0')
    if arguments['genkey']:
        genkey(arguments['<invite-token>'], arguments['--fish'])
    elif arguments['extractkey']:
        extractkey(arguments['<token>'], arguments['--notrunc'])
    else:
        scrape()


def genkey(invite_token: str, fish: bool = False):
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
    key_id = str(uuid.uuid5(NAMESPACE_OCSPDASH_KID, public_key))

    payload = {
        'pk': public_key,
        'kid': key_id,
        'token': invite_token
    }
    token = jwt.encode(payload, private_key, algorithm=JWT_ALGORITHM)

    if not fish:
        print(f"export OCSPSCRAPE_KEY_ID='{key_id}'", file=sys.stderr)
        print(f"export OCSPSCRAPE_PRIVATE_KEY='{serialized_private_key}'", file=sys.stderr)
    else:
        print(f"set -gx OCSPSCRAPE_KEY_ID '{key_id}'", file=sys.stderr)
        print(f"set -gx OCSPSCRAPE_PRIVATE_KEY '{serialized_private_key}'", file=sys.stderr)
    print(token)


def extractkey(token: str, notrunc: bool = False):
    unverified_claims = jwt.get_unverified_claims(token)
    public_key = b64decode(unverified_claims['pk']).decode('utf-8')
    claims = jwt.decode(token, public_key, algorithms=[JWT_ALGORITHM])
    if notrunc:
        print(f'public key:\t{claims["pk"]}'.expandtabs(7))
    else:
        print(f'public key:\t{claims["pk"]}'.expandtabs(7)[:78] + '..')
    print(f'key id:\t{claims["kid"]}'.expandtabs(7))
    print(f'invite token:\t{claims["token"]}'.expandtabs(7))


def scrape():
    requests_session = requests.Session()
    requests_session.headers.update({'User-Agent': ' '.join([requests.utils.default_user_agent(), 'OCSPscrape 0.1.0'])})

    payload = {RESULTS_JWT_CLAIM: []}

    for line in tqdm(sys.stdin):
        query = json.loads(line)

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
    key_id = os.environ['OCSPSCRAPE_KEY_ID']
    payload['iat'] = datetime.utcnow()
    token = jwt.encode(payload, key, headers={'kid': key_id}, algorithm=JWT_ALGORITHM)
    print(token)


def ping(host: str) -> bool:
    """Returns True if host responds to ping request.

        :param host: The hostname to ping

        :returns: True if an ICMP echo is received, False otherwise
    """
    parameters = ['-n', '1'] if platform.system().lower() == 'windows' else ['-c', '1']
    results = subprocess.run(['ping'] + parameters + [host], stdout=subprocess.DEVNULL)
    return results.returncode == 0


def check_ocsp_response(subject_cert: bytes, issuer_cert: bytes, url: str, session) -> bool:
    """Create and send an OCSP request

        :param subject_cert: The certificate that information is being requested about
        :param issuer_cert: The issuer of the subject certificate
        :param url: The URL of the OCSP responder to query
        :param session: A requests session

        :returns: True if the request was successful, False otherwise
    """
    # TODO better documentation/type hinting for the session parameter
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