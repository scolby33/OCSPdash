"""Test configuration module for OCSPdash."""

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import scoped_session, sessionmaker

from ocspdash.manager import Manager


@pytest.fixture(scope='session')
def manager_session(tmpdir_factory):
    """Create a Manager test fixture with a temporary SQLite database for a test session.

    All DB operations will be rolled back upon the end of the test session.
    See below for a fixture that rolls back after every test function.

    Note that a connection object is yielded as well, which is necessary for the function-scoped version, so you must unpack the actual Manager object if using this fixture directly.

    :yields: a 2-tuple of a Manager and a Connection
    """
    db_path = tmpdir_factory.mktemp('ocspdash').join('ocspdash.db')

    engine = create_engine(f'sqlite:///{db_path}')
    connection = engine.connect()

    session_maker = sessionmaker(bind=connection)
    session = scoped_session(session_maker)

    @event.listens_for(session, 'after_transaction_end')
    def restart_savepoint(session, transaction):
        if transaction.nested and not transaction._parent.nested:
            # ensure that state is expired the way
            # session.commit() normally does
            session.expire_all()

            session.begin_nested()

    transaction = connection.begin()
    session.begin_nested()

    manager = Manager(
        engine=engine,
        session=session,
        server_query=None
    )

    yield manager, connection

    session.close()
    transaction.rollback()

    connection.close()


@pytest.fixture(scope='function')
def manager_function(manager_session):
    """Create a Manager test fixture with a temporary SQLite database for a test function.

    All DB operations will be rolled back upon the end of the test function.

    :yields: a Manager
    """
    manager: Manager = manager_session[0]
    connection = manager_session[1]

    transaction = connection.begin()
    manager.session.begin_nested()

    yield manager

    manager.session.close()

    # rollback - everything that happened with the
    # Session above (including all calls to commit())
    # is rolled back
    transaction.rollback()
