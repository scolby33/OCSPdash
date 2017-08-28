def test_ensure_authority(manager_transaction):
    authority = manager_transaction.ensure_authority(
        name='Test Authority',
        rank=0,
        cardinality=1234
    )

    assert authority.name == 'Test Authority'
    assert authority.rank == 0
    assert authority.cardinality == 1234
