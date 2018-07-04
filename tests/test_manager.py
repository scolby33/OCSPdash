# -*- coding: utf-8 -*-

"""Test the functionality of the Manager."""

from datetime import datetime

from ocspdash.manager import Manager
from ocspdash.models import Chain, Result
from .constants import TEST_KEY_ID, TEST_LOCATION_NAME, TEST_PUBLIC_KEY


def test_count_authorities(manager_function: Manager):
    """Test the counting query for authorities."""
    for i in range(10):
        manager_function.ensure_authority(
            name=f'Test Authority {i}',
            cardinality=i * 10 + 7
        )

    assert manager_function.count_authorities() == 10


def test_count_responders(manager_function: Manager):
    """Test the counting query for responders."""
    authority = manager_function.ensure_authority(
        name='Test Authority',
        cardinality=1234
    )
    for i in range(10):
        manager_function.ensure_responder(
            authority=authority,
            url=f'http://test-responder.url/{i}',
            cardinality=i * 9 - 3
        )

    assert manager_function.count_responders() == 10


def test_count_chains(manager_function: Manager):
    """Test the counting query for chains."""
    authority = manager_function.ensure_authority(
        name='Test Authority',
        cardinality=1234
    )
    responder = manager_function.ensure_responder(
        authority=authority,
        url='http://test-responder.url/',
        cardinality=123
    )

    for i in range(10):
        chain = Chain(responder=responder, subject=f'c{i}s'.encode('utf-8'), issuer=f'c{i}i'.encode('utf-8'))
        manager_function.session.add(chain)
    manager_function.session.commit()

    assert manager_function.count_chains() == 10


def test_get_authority_by_name(manager_function: Manager):
    """Test getting an authority by its name."""
    authority = manager_function.ensure_authority(
        name='Test Authority',
        cardinality=1234
    )
    assert manager_function.get_authority_by_name('Test Authority') is authority
    assert manager_function.get_authority_by_name('Nonexistent Authority') is None


def test_ensure_authority(manager_function: Manager):
    """Test the creation of Authority objects."""
    authority1 = manager_function.ensure_authority(
        name='Test Authority',
        cardinality=1234
    )
    assert authority1.name == 'Test Authority'
    assert authority1.cardinality == 1234

    authority2 = manager_function.ensure_authority(
        name='Test Authority',
        cardinality=2345
    )
    assert authority1 is authority2
    assert authority2.name == 'Test Authority'
    assert authority2.cardinality == 2345


def test_get_responder(manager_function: Manager):
    """Test getting a responder for an Authority and URL."""
    authority = manager_function.ensure_authority(
        name='Test Authority',
        cardinality=1234
    )
    responder = manager_function.ensure_responder(
        authority=authority,
        url='http://test-responder.url/',
        cardinality=123
    )

    assert manager_function.get_responder(authority, 'http://test-responder.url/') is responder
    assert manager_function.get_responder(authority, 'http://non-existent.url/') is None


def test_ensure_responder(manager_function: Manager):
    """Test the creation of Responder objects."""
    authority = manager_function.ensure_authority(
        name='Test Authority',
        cardinality=1234
    )

    responder1 = manager_function.ensure_responder(
        authority=authority,
        url='http://test-responder.url/',
        cardinality=123
    )

    assert responder1.authority is authority
    assert responder1.url == 'http://test-responder.url/'
    assert responder1.cardinality == 123

    responder2 = manager_function.ensure_responder(
        authority=authority,
        url='http://test-responder.url/',
        cardinality=234
    )

    assert responder2 is responder1
    assert responder2.url == 'http://test-responder.url/'
    assert responder2.cardinality == 234


def test_get_chain_by_certificate_hash(manager_function: Manager):
    """Test retrieving a Chain by its certificate hash."""
    authority = manager_function.ensure_authority(
        name='Test Authority',
        cardinality=1234
    )
    responder = manager_function.ensure_responder(
        authority=authority,
        url='http://test-responder.url/',
        cardinality=234
    )
    chain = Chain(
        responder=responder,
        subject=b'cs',
        issuer=b'ci'
    )
    manager_function.session.add(chain)
    manager_function.session.commit()

    certificate_hash = chain.certificate_hash

    assert manager_function.get_chain_by_certificate_hash(certificate_hash) is chain
    assert manager_function.get_chain_by_certificate_hash(b'bad hash') is None


def test_get_most_recent_chain_by_responder(manager_function: Manager):
    """Test that we get the proper Chain for a Responder."""
    authority = manager_function.ensure_authority(
        name='Test Authority',
        cardinality=1234
    )
    responder = manager_function.ensure_responder(
        authority=authority,
        url='http://test-responder.url/',
        cardinality=234
    )

    c1 = Chain(responder=responder, subject=b'c1s', issuer=b'c1i', retrieved=datetime(2018, 7, 1))
    c2 = Chain(responder=responder, subject=b'c2s', issuer=b'c2i', retrieved=datetime(2018, 7, 2))
    c3 = Chain(responder=responder, subject=b'c3s', issuer=b'c3i', retrieved=datetime(2018, 7, 3))
    c4 = Chain(responder=responder, subject=b'c4s', issuer=b'c4i', retrieved=datetime(2018, 7, 4))
    manager_function.session.add_all([c1, c2, c3, c4])
    manager_function.session.commit()

    assert manager_function.get_most_recent_chain_by_responder(responder) is c4


def test_get_location_by_name(manager_function: Manager):
    """Test getting a location by its name."""
    selector, validator = manager_function.create_location(TEST_LOCATION_NAME)

    location = manager_function.get_location_by_selector(selector)
    assert location

    assert manager_function.get_location_by_name(TEST_LOCATION_NAME) is location
    assert manager_function.get_location_by_name('Nonexistent Location') is None


def test_location_invites(manager_function: Manager):
    """Test the invite functionality of Location objects."""
    selector, validator = manager_function.create_location(TEST_LOCATION_NAME)

    location = manager_function.get_location_by_selector(selector)
    assert location.name == TEST_LOCATION_NAME
    assert not location.verify(b'random wrong value')
    assert location.verify(validator)

    assert location.pubkey is None
    assert location.key_id is None

    processed_location = manager_function.process_location(b''.join((selector, validator)), TEST_PUBLIC_KEY)
    assert location is processed_location
    assert isinstance(processed_location.b64encoded_pubkey, str)
    assert processed_location.b64encoded_pubkey == TEST_PUBLIC_KEY
    assert processed_location.key_id == TEST_KEY_ID


def test_get_all_locations(manager_function: Manager):
    """Test the retrieval of all locations (that have test results)."""
    manager_function.create_location('l1')
    manager_function.create_location('l2')
    manager_function.create_location('l3')

    l1 = manager_function.get_location_by_name('l1')
    assert l1 is not None
    l2 = manager_function.get_location_by_name('l2')
    assert l2 is not None
    l3 = manager_function.get_location_by_name('l3')
    assert l3 is not None

    r1 = Result(location=l1, ping=True, ocsp=True)  # bool values don't matter here
    r2 = Result(location=l1, ping=True, ocsp=True)  # but need to be set to satisfy
    r3 = Result(location=l1, ping=True, ocsp=True)  # db not null constraint
    r4 = Result(location=l2, ping=True, ocsp=True)

    manager_function.session.add_all([r1, r2, r3, r4])
    manager_function.session.commit()

    locations = manager_function.get_all_locations_with_test_results()

    assert l1 in locations
    assert l2 in locations
    assert l3 not in locations


def test_get_most_recent_chains_for_authorities(manager_function: Manager):
    """Test getting the most recent chain for each top authority. This becomes the manifest."""
    a1 = manager_function.ensure_authority('a1', 5)
    assert a1 is not None
    a2 = manager_function.ensure_authority('a2', 5)
    assert a2 is not None
    a3 = manager_function.ensure_authority('a3', 5)
    assert a3 is not None

    assert 3 == manager_function.count_authorities()

    r1 = manager_function.ensure_responder(a1, 'url1', 5)
    r2 = manager_function.ensure_responder(a1, 'url2', 5)
    r3 = manager_function.ensure_responder(a2, 'url3', 5)
    r4 = manager_function.ensure_responder(a2, 'url4', 5)

    assert 4 == manager_function.count_responders()

    c1 = Chain(responder=r1, subject=b'c1s', issuer=b'c1i')
    c2 = Chain(responder=r2, subject=b'c2s', issuer=b'c2i')
    c3 = Chain(responder=r3, subject=b'c3s', issuer=b'c3i')
    c4 = Chain(responder=r4, subject=b'c4s', issuer=b'c4i')

    manager_function.session.add_all([c1, c2, c3, c4])
    manager_function.session.commit()

    assert 4 == manager_function.count_chains()

    chains = manager_function.get_most_recent_chains_for_authorities()
    assert 4 == len(chains)
    assert c1 in chains
    assert c2 in chains
    assert c3 in chains
    assert c4 in chains

    c5 = Chain(responder=r1, subject=b'c5s', issuer=b'c5i')
    c6 = Chain(responder=r3, subject=b'c6s', issuer=b'c6i')

    manager_function.session.add_all([c5, c6])
    manager_function.session.commit()

    assert 6 == manager_function.count_chains()

    chains = manager_function.get_most_recent_chains_for_authorities()
    assert 4 == len(chains)
    assert c5 in chains
    assert c2 in chains
    assert c6 in chains
    assert c4 in chains


def test_recent_results(manager_function: Manager):
    """Test that nothing crashes if you try and get the recent results."""
    manager_function.get_most_recent_result_for_each_location()


def test_get_payload(manager_function: Manager):
    """Test that nothing crashes if you try and get the payload."""
    manager_function.get_payload()
