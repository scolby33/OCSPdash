# -*- coding: utf-8 -*-

"""Test the functionality of the Manager."""

from ocspdash.manager import Manager
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
