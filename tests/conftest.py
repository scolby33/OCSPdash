# -*- coding: utf-8 -*-

"""Test configuration module for OCSPdash."""

import logging

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import scoped_session, sessionmaker

from ocspdash.manager import Manager
from ocspdash.models import Base
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
    session = scoped_session(session_maker)

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
    manager = Manager(engine=engine, session=session, server_query=None)

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
