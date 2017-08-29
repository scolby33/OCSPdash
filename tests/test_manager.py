def test_ensure_authority(manager_transaction):
    authority1 = manager_transaction.ensure_authority(
        name='Test Authority',
        rank=0,
        cardinality=1234
    )
    assert authority1.name == 'Test Authority'
    assert authority1.rank == 0
    assert authority1.cardinality == 1234

    authority2 = manager_transaction.ensure_authority(
        name='Test Authority',
        rank=1,
        cardinality=2345
    )
    assert authority1 is authority2
    assert authority2.name == 'Test Authority'
    assert authority2.rank == 1
    assert authority2.cardinality == 2345
