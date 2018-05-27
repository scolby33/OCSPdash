"""Test the functionality of the Manager."""

from ocspdash.manager import Manager
from .constants import TEST_KEY_ID, TEST_LOCATION_NAME, TEST_PUBLIC_KEY


def test_ensure_authority(manager_transaction: Manager):
    """Test the creation of Authority objects."""
    authority1 = manager_transaction.ensure_authority(
        name='Test Authority',
        cardinality=1234
    )
    assert authority1.name == 'Test Authority'
    assert authority1.cardinality == 1234

    authority2 = manager_transaction.ensure_authority(
        name='Test Authority',
        cardinality=2345
    )
    assert authority1 is authority2
    assert authority2.name == 'Test Authority'
    assert authority2.cardinality == 2345


def test_location_invites(manager_transaction: Manager):
    """Test the invite functionality of Location objects."""
    selector, validator = manager_transaction.create_location(TEST_LOCATION_NAME)

    location = manager_transaction.get_location_by_selector(selector)
    assert location.name == TEST_LOCATION_NAME
    assert not location.verify(b'1235lkwjal;sn')
    assert location.verify(validator)

    assert location.pubkey is None
    assert location.key_id is None

    processed_location = manager_transaction.process_location(b''.join((selector, validator)), TEST_PUBLIC_KEY)
    assert location is processed_location
    assert isinstance(processed_location.b64encoded_pubkey, str)
    assert processed_location.b64encoded_pubkey == TEST_PUBLIC_KEY
    assert processed_location.key_id == TEST_KEY_ID
