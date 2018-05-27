"""Test configuration module for OCSPdash."""

import pytest

from ocspdash.manager import Manager


@pytest.fixture(scope='session')
def app():
    """Create a Flask app test fixture."""
    pass


@pytest.fixture(scope='session')
def manager(tmpdir_factory):
    """Create a Manager test fixture with a temporary SQLite database."""
    db_path = tmpdir_factory.mktemp('ocspdash').join('ocspdash.db')

    return Manager.from_args(connection=f'sqlite:///{db_path}', echo=True)


@pytest.fixture(scope='function')
def manager_transaction(manager):
    """Create a Manager test fixture that rolls back the database state after each test function."""
    connection = manager.engine.connect()
    transaction = connection.begin()
    manager.session.configure(bind=connection)

    yield manager

    manager.session.configure(bind=manager.engine)
    manager.session.remove()
    transaction.rollback()
    connection.close()


@pytest.fixture(scope='session')
def manager_alt(manager):
    """Create a Manager test fixture that rolls back the database state after each test session."""
    manager._connection = manager.engine.connect()
    manager.session.configure(bind=manager._connection)

    yield manager

    manager.session.configure(bind=manager.engine)
    manager._connection.close()
    del manager._connection


@pytest.fixture(scope='function')
def manager_transaction_alt(manager_alt):
    """Create an alternative Manager test fixture that rolls back the database state after each test function."""
    transaction = manager_alt._connection.begin()

    yield manager_alt

    manager_alt.session.remove()
    transaction.rollback()
