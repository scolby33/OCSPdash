# -*- coding: utf-8 -*-

"""Test configuration module for OCSPdash."""

import logging

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, scoped_session, sessionmaker

from ocspdash.manager import Manager
from ocspdash.models import Base
from ocspdash.web import create_application
from .constants import TEST_CONNECTION

logger = logging.getLogger(__name__)
logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)


@pytest.fixture(scope='session')
def rfc(tmpdir_factory):
    """Create a temporary SQLite database and create the tables from the SQLAlchemy metadata.

    If the environment variable ``OCSPDASH_TEST_CONNECTION`` is set, that gets used instead of creating a temporary
    database.

    :yields: a RFC connection string to the database to use
    """
    if TEST_CONNECTION:
        db_connection = TEST_CONNECTION

    else:
        db_path = tmpdir_factory.mktemp('ocspdash').join('ocspdash.db')
        logger.warning(db_path)
        db_connection = f'sqlite:///{db_path}'

    engine = create_engine(db_connection)

    logger.debug('creating schema')
    Base.metadata.create_all(engine)

    yield db_connection


@pytest.fixture(scope='session')
def manager_session(rfc):
    """Create a Manager test fixture with a temporary SQLite database for a test session.

    All DB operations will be rolled back upon the end of the test session.
    See below for a fixture that rolls back after every test function.

    Note that a connection object is yielded as well, which is necessary for the function-scoped version, so you must unpack the actual Manager object if using this fixture directly.

    :yields: a 2-tuple of a Manager and a Connection
    """
    logger.debug('creating engine')
    engine = create_engine(rfc)

    logger.debug('creating connection')
    connection = engine.connect()

    logger.debug('creating sessionmaker')
    session_maker = sessionmaker(bind=connection)
    logger.debug('creating scoped_session')
    session: Session = scoped_session(session_maker)

    @event.listens_for(session, 'after_transaction_end')
    def restart_savepoint(session, transaction):
        logger.debug('called restart_savepoint')
        if transaction.nested and not transaction._parent.nested:
            logger.debug('restarting savepoint')
            # ensure that state is expired the way
            # session.commit() normally does
            logger.debug('expiring')
            session.expire_all()

            logger.debug('beginning nested in restart_savepoint')
            session.begin_nested()
            logger.debug('end of restart_savepoint if statement')
        logger.debug('end of restart_savepoint')

    logger.debug('beginning transaction in session')
    transaction = connection.begin()

    logger.debug('beginning nested in session')
    session.begin_nested()

    logger.debug('create Manager')
    manager = Manager(
        engine=engine,
        session=session,
        server_query=None
    )

    logger.debug('yielding from session')
    yield manager, connection

    logger.debug('closing session from session')
    session.close()
    logger.debug('rolling back transaction from session')
    transaction.rollback()

    logger.debug('closing connection')
    connection.close()


@pytest.fixture(scope='function')
def manager_function(manager_session):
    """Create a Manager test fixture with a temporary SQLite database for a test function.

    All DB operations will be rolled back upon the end of the test function.

    :yields: a Manager
    """
    logger.debug('unpacking manager and connection')
    manager: Manager = manager_session[0]
    connection = manager_session[1]

    logger.debug('beginning transaction in function')
    transaction = connection.begin()
    logger.debug('beginning nested in function')
    manager.session.begin_nested()

    logger.debug('yielding manager')
    yield manager

    logger.debug('closing session from function')
    manager.session.close()

    # rollback - everything that happened with the
    # Session above (including all calls to commit())
    # is rolled back
    logger.debug('rolling back transaction from function')
    transaction.rollback()


@pytest.fixture(scope='session')
def client_session(rfc):
    """Create a Flask test client with a temporary SQLite database for a test session.

    All DB operations will be rolled back upon the end of a test session.
    See below for a fixture that rolls back after every test function.

    Note that a connection object is yielded as well, which is necessary for the function-scoped version, so you must unpack the actual test client object if using this fixture directly.

    :yields: a 2-tuple of test client and Connection
    """
    logger.debug('creating engine for web client')
    engine = create_engine(rfc)

    logger.debug('creating connection for web client')
    connection = engine.connect()

    app = create_application(connection=rfc, db_session_options={'bind': connection})
    app.testing = True

    @event.listens_for(app.manager.session, 'after_transaction_end')
    def restart_savepoint(session, transaction):
        logger.debug('called restart_savepoint for web client')
        if transaction.nested and not transaction._parent.nested:
            logger.debug('restarting savepoint for web client')
            # ensure that state is expired the way
            # session.commit() normally does
            logger.debug('expiring for web client')
            session.expire_all()

            logger.debug('beginning nested in restart_savepoint for web client')
            session.begin_nested()
            logger.debug('end of restart_savepoint if statement for web client')
        logger.debug('end of restart_savepoint for web client')

    logger.debug('beginning transaction in session for web client')
    transaction = connection.begin()

    logger.debug('beginning nested in session for web client')
    app.manager.session.begin_nested()

    logger.debug('yielding from session for web client')
    yield app.test_client(), connection

    logger.debug('closing session from session for web client')
    app.manager.session.close()
    logger.debug('rolling back transaction from session for web client')
    transaction.rollback()

    logger.debug('closing connection for web client')
    connection.close()


@pytest.fixture(scope='function')
def client_function(client_session):
    """Create a test client fixture with a temporary SQLite database for a test function.

    All DB operations will be rolled back upon the end of the test function.

    :yields: a Flask test client
    """
    logger.debug('unpacking client and connection for web client')
    client = client_session[0]
    connection = client_session[1]

    logger.debug('beginning transaction in function for web client')
    transaction = connection.begin()
    logger.debug('beginning nested in function for web client')
    client.application.manager.session.begin_nested()

    logger.debug('yielding client for web client')
    yield client

    logger.debug('closing session from function for web client')
    client.application.manager.session.close()

    # rollback - everything that happened with the
    # Session above (including all calls to commit())
    # is rolled back
    logger.debug('rolling back transaction from function for web client')
    transaction.rollback()


# TODO: fixture to pre-fill DB with some stuff for the client to test on
