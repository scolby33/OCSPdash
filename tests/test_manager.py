# -*- coding: utf-8 -*-

"""Test the functionality of the Manager."""

from ocspdash.manager import Manager
from ocspdash.models import Chain, Result
from .constants import TEST_KEY_ID, TEST_LOCATION_NAME, TEST_PUBLIC_KEY


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

    r1 = Result(location=l1)
    r2 = Result(location=l1)
    r3 = Result(location=l1)
    r4 = Result(location=l2)

    manager_function.session.add_all([r1, r2, r3, r4])
    manager_function.session.commit()

    locations = manager_function.get_all_locations_with_test_results()

    assert l1 in locations
    assert l2 in locations
    assert l3 not in locations


def test_get_manifest(manager_function: Manager):
    """Test the generation of the manifest."""
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

    chains = manager_function._get_manifest_chains()
    assert 4 == len(chains)
    assert c1 in chains
    assert c2 in chains
    assert c3 in chains
    assert c4 in chains

    c5 = Chain(responder=r1, subject=b'c5s', issuer=b'c5i')
    c6 = Chain(responder=r3, subject=b'c5s', issuer=b'c5i')

    manager_function.session.add_all([c5, c6])
    manager_function.session.commit()

    assert 6 == manager_function.count_chains()

    chains = manager_function._get_manifest_chains()
    assert 4 == len(chains)
    assert c5 in chains
    assert c2 in chains
    assert c6 in chains
    assert c4 in chains


def test_get_payload(manager_function: Manager):
    """Test that nothing crashes if you try and get the payload."""
    manager_function.get_payload()
