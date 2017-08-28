import pytest

from ocspdash.manager import Manager


@pytest.fixture(scope='session')
def app():
    pass


@pytest.fixture(scope='session')
def manager(tmpdir_factory):
    db_path = tmpdir_factory.mktemp('ocspdash').join('ocspdash.db')

    return Manager(connection=f'sqlite:///{db_path}', echo=True)


@pytest.fixture(scope='function')
def manager_transaction(manager):
    connection = manager.engine.connect()
    transaction = connection.begin()
    manager.session_maker.configure(bind=connection)

    yield manager

    manager.session_maker.configure(bind=manager.engine)
    manager.session.remove()
    transaction.rollback()
    connection.close()


@pytest.fixture(scope='session')
def manager_alt(manager):
    manager._connection = manager.engine.connect()
    manager.session_maker.configure(bind=manager._connection)

    yield manager

    manager.session_maker.configure(bind=manager.engine)
    manager._connection.close()
    del manager._connection


@pytest.fixture(scope='function')
def manager_transaction_alt(manager_alt):
    transaction = manager_alt._connection.begin()

    yield manager_alt

    manager_alt.session.remove()
    transaction.rollback()
