# -*- coding: utf-8 -*-

"""Manager for OCSPDash."""

import logging
import os
import secrets
import uuid
from itertools import groupby
from operator import attrgetter
from typing import Iterable, List, Mapping, Optional, Tuple

from sqlalchemy import and_, create_engine, func
from sqlalchemy.engine import Engine
from sqlalchemy.orm import scoped_session, sessionmaker

from ocspdash.constants import OCSPDASH_DEFAULT_CONNECTION, OCSPDASH_USER_AGENT_IDENTIFIER
from ocspdash.models import Authority, Base, Chain, Location, Responder, Result
from ocspdash.security import pwd_context
from ocspdash.server_query import ServerQuery
from ocspdash.util import OrderedDefaultDict

__all__ = [
    'Manager',
]

logger = logging.getLogger(__name__)


def _workaround_pysqlite_transaction_bug():
    """Work around pysqlite transaction bug.

    https://groups.google.com/forum/#!topic/sqlalchemy/lmdW0Vf3z8g
    http://docs.sqlalchemy.org/en/latest/dialects/sqlite.html#serializable-isolation-savepoints-transactional-ddl
    """
    logger.debug('registering workarounds for pysqlite transactional bugs')

    from sqlite3 import Connection as _sqlite3_Connection

    from sqlalchemy import event as _event
    from sqlalchemy.engine import Engine as _Engine

    @_event.listens_for(_Engine, 'connect')
    def do_connect(dbapi_connection, connection_record):
        if isinstance(dbapi_connection, _sqlite3_Connection):
            # disable pysqlite's emitting of the BEGIN statement entirely.
            # also stops it from emitting COMMIT before any DDL.
            logger.debug('setting connection isolation level to `None` to work around pysqlite bug')
            dbapi_connection.isolation_level = None

    @_event.listens_for(_Engine, 'begin')
    def do_begin(connection):
        if isinstance(connection._Connection__connection.connection, _sqlite3_Connection):
            # emit our own BEGIN
            logger.debug('emitting our own BEGIN to work around pysqlite bug')
            connection.execute('BEGIN')


_workaround_pysqlite_transaction_bug()


class Manager(object):
    """Manager for interacting with the database."""

    def __init__(self, engine: Engine, session: scoped_session, server_query: Optional[ServerQuery] = None) -> None:
        """Instantiate a Manager with instances of the objects it needs.

        :param engine: The database engine.
        :param session: The database session.
        :param server_query: The server_query instance. If None, using server_query-related functionality will raise an error.
        """
        self.engine = engine
        self.session = session
        self.server_query = server_query

        self.create_all()

    @classmethod
    def from_args(cls, connection: Optional[str] = None, echo: bool = False, api_id: Optional[str] = None, api_secret: Optional[str] = None) -> 'Manager':
        """Instantiate a Manager along with the objects it needs.

        :param connection: An SQLAlchemy-compatible connection string.
        :param echo: True to echo SQL emitted by SQLAlchemy.
        :param api_id: The Censys API id. If None, the value will be obtained from configuration or the environment.
        :param api_secret: The Censys API secret. If none, the value will be obtained from configuration or the environment.

        :returns: An instance of Manager configured according to the arguments provided.
        """
        engine, session = cls._get_engine_from_connection(connection=connection, echo=echo)

        server_query = cls._get_server_query(api_id=api_id, api_secret=api_secret)

        return cls(engine, session, server_query)

    @staticmethod
    def _get_connection(connection: Optional[str] = None):
        """Get a connection from one of the various configuration locations.

        Prioritizing a passed-in value, followed by a value from an environment variable, and finally the default.
        """
        if connection is not None:
            logger.info('using passed-in connection: %s', connection)
            return connection

        connection = os.environ.get('OCSPDASH_CONNECTION')

        if connection is not None:
            logger.info('using connection from environment: %s', connection)
            return connection

        logger.info('using default connection: %s', OCSPDASH_DEFAULT_CONNECTION)
        return OCSPDASH_DEFAULT_CONNECTION

    @staticmethod
    def _get_credentials(user: Optional[str] = None, password: Optional[str] = None) -> Tuple[Optional[str], Optional[str]]:
        if user is None:
            user = os.environ.get('CENSYS_API_ID')

        if password is None:
            password = os.environ.get('CENSYS_API_SECRET')

        return user, password

    @classmethod
    def _get_engine_from_connection(cls, connection: Optional[str] = None, echo: bool = False) -> Tuple[Engine, scoped_session]:
        connection = cls._get_connection(connection)
        engine = create_engine(connection, echo=echo)

        session_maker = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

        session = scoped_session(session_maker)

        return engine, session

    @classmethod
    def _get_server_query(cls, api_id: Optional[str] = None, api_secret: Optional[str] = None) -> Optional[ServerQuery]:
        api_id, api_secret = cls._get_credentials(user=api_id, password=api_secret)
        if api_id is not None and api_secret is not None:
            return ServerQuery(
                api_id=api_id,
                api_secret=api_secret,
                user_agent_identifier=OCSPDASH_USER_AGENT_IDENTIFIER
            )

    def create_all(self, checkfirst=True):
        """Issue appropriate CREATE statements via SQLalchemy to create the database tables.

        :param checkfirst: Don't issue CREATEs for tables already present in the target database if True.
        """
        Base.metadata.create_all(self.engine, checkfirst=checkfirst)

    def drop_database(self):
        """Drop all tables from the connected database."""
        Base.metadata.drop_all(self.engine)

    def count_authorities(self) -> int:
        """Count the number of authorities in the local database."""
        return self.session.query(Authority).count()

    def count_responders(self) -> int:
        """Count the number of responders in the local database."""
        return self.session.query(Responder).count()

    def count_chains(self) -> int:
        """Count the number of chains in the local database."""
        return self.session.query(Chain).count()

    def get_authority_by_name(self, name: str) -> Optional[Authority]:
        """Get an Authority from the DB by name if it exists.

        :param name: the name of the authority

        :returns: The Authority or None
        """
        return self.session.query(Authority).filter(Authority.name == name).one_or_none()

    def ensure_authority(self, name: str, cardinality: int) -> Authority:
        """Create or update an Authority in the DB.

        If an Authority with the given name exists, the cardinality is updated.
        Otherwise, a new Authority is created with the given name and cardinality.

        :param name: the name of the authority
        :param cardinality: the number of certificates observed from the authority in the wild

        :returns: the new or updated Authority
        """
        authority = self.get_authority_by_name(name)

        if authority is None:
            authority = Authority(
                name=name,
                cardinality=cardinality,
            )
            self.session.add(authority)

        else:
            authority.cardinality = cardinality

        self.session.commit()

        return authority

    def get_responder(self, authority: Authority, url: str) -> Optional[Responder]:
        """Get a responder by the authority and URL.

        :param authority: the Authority from the DB
        :param url: the URL of the responder

        :returns: the Responder or None
        """
        f = and_(Responder.authority_id == authority.id, Responder.url == url)
        return self.session.query(Responder).filter(f).one_or_none()

    def ensure_responder(self, authority: Authority, url: str, cardinality: int) -> Responder:
        """Create or update a responder in the DB.

        If a responder with the given Authority and URL exists, the cardinality is updated.
        Otherwise, a new Responder is created with the given information.

        :param authority: the corresponding Authority for the responder
        :param url: the URL of the responder
        :param cardinality: the number of certificates observed using the responder in the wild

        :returns: the new or updated Responder
        """
        responder = self.get_responder(authority=authority, url=url)

        if responder is None:
            responder = Responder(
                authority=authority,
                url=url,
                cardinality=cardinality
            )
            self.session.add(responder)

        else:
            responder.cardinality = cardinality

        self.session.commit()

        return responder

    def get_chain_by_certificate_hash(self, certificate_hash: bytes) -> Optional[Chain]:
        """Get a chain by its certificate hash.

        :param certificate_hash: the bytes of the certificate_hash

        :returns: the Chain or None
        """
        return self.session.query(Chain).filter(Chain.certificate_hash == certificate_hash).one_or_none()

    def get_most_recent_chain_by_responder(self, responder: Responder) -> Optional[Chain]:
        """Get the newest chain for a Responder.

        :param responder: the Responder whose chain we're seeking

        :returns: the Chain or None
        """
        return self.session.query(Chain).filter(Chain.responder_id == responder.id).order_by(
            Chain.retrieved.desc()).first()

    def ensure_chain(self, responder: Responder) -> Optional[Chain]:
        """Get or create a chain for a Responder.

        If a Chain exists in the database and is not "old" as specified in the Chain model and the certificates it
        contains are unexpired, returns that Chain.
        If a Chain exists, is not "old", but its contents are expired, return the Chain if the responder has no
        unexpired certificates in the wild.
        If a Chain exists, is not "old", and its contents are unexpired, returns that Chain.
        Otherwise, retrieves a new chain from Censys, adds it to the database, and returns the new Chain.

        :param responder: the Responder whose chain we're seeking

        :returns: the Chain or None
        """
        if self.server_query is None:
            raise RuntimeError('Missing sensys server query')

        most_recent_chain = self.get_most_recent_chain_by_responder(responder)

        if most_recent_chain and not most_recent_chain.old:
            if not most_recent_chain.expired:
                return most_recent_chain

            if not responder.current:
                return most_recent_chain

        subject, issuer = self.server_query.get_certs_for_issuer_and_url(responder.authority.name, responder.url)

        if subject is None or issuer is None:
            return None

        chain = Chain(
            responder=responder,
            subject=subject,
            issuer=issuer,
        )

        self.session.add(chain)
        self.session.commit()

        return chain

    def get_location_by_name(self, name: str) -> Optional[Location]:
        """Get a Location from the database by its name.

        :param name: the name of the Location

        :returns: the Location or None
        """
        return self.session.query(Location).filter(Location.name == name).one_or_none()

    def update(self, n: int = 10):
        """Update the database of Authorities, Responders, and Chains from Censys.

        If there are no Authorities in the DB or if any of the top n Authorities are "old" as defined by that property,
        retrieves an all-new set of Authorities, Responders, and Chains from Censys.

        If any Responder is "old", update all the Responders for the old Responder's Authority.

        If any Chain is "old", update the Chain for the corresponding Responder.

        Otherwise, it's a no-op.

        :param n: the number of top authorities to get information on
        """
        if self.server_query is None:
            raise RuntimeError('No username and password for Censys supplied')

        authorities = self.get_top_authorities(n)
        if (not authorities or  # probably a first run with a clean DB
                any(authority.old for authority in authorities)):
            issuers = self.server_query.get_top_authorities(buckets=n)
            for issuer_name, issuer_cardinality in issuers.items():
                authority = self.ensure_authority(issuer_name, issuer_cardinality)

                ocsp_urls = self.server_query.get_ocsp_urls_for_issuer(authority.name)

                for url, responder_cardinality in ocsp_urls.items():
                    responder = self.ensure_responder(authority, url, responder_cardinality)
                    self.ensure_chain(responder)

        authorities = self.get_top_authorities(n)
        for authority in authorities:
            if any(responder.old for responder in authority.responders):
                ocsp_urls = self.server_query.get_ocsp_urls_for_issuer(authority.name)
                for url, responder_cardinality in ocsp_urls.items():
                    self.ensure_responder(authority, url, responder_cardinality)
            for responder in authority.responders:
                self.ensure_chain(responder)

    def get_top_authorities(self, n: int = 10) -> List[Authority]:
        """Retrieve the top authorities (as measured by cardinality) from the database.

        Will retrieve up to n, but if there are fewer entries in the DB, it will not create more.

        :param n: the number of top authorities to retrieve

        :returns: a list of up to n Authorities
        """
        return self.session.query(Authority).order_by(Authority.cardinality.desc()).limit(n).all()

    def get_most_recent_result_for_each_location(self) -> List[Result]:
        """Get the most recent results for each location."""
        # TODO better docstring
        subquery = (
            self.session.query(
                Responder.id.label('resp_id'),
                Location.id.label('loc_id'),
                func.max(Result.retrieved).label('most_recent'),
            )
            .select_from(Result)
            .join(Chain)
            .join(Responder)
            .join(Location)
            .group_by(Responder.id, Location.id)
            .subquery()
        )
        query = (
            self.session.query(Result)
            .select_from(subquery)
            .join(Result, Result.retrieved == subquery.c.most_recent)
            .join(Chain)
            .join(
                Responder,
                and_(
                    Responder.id == Chain.responder_id,
                    Responder.id == subquery.c.resp_id,
                ),
            )
            .join(
                Location,
                and_(
                    Location.id == Result.location_id,
                    Location.id == subquery.c.loc_id
                ),
            )
        )
        return query.all()

    def get_all_locations_with_test_results(self) -> List[Location]:
        """Return all the Location objects that have at least one associated Result."""
        return (
            self.session.query(Location)
                .join(Location.results)
                .group_by(Location.id)
                .having(func.count(Result.location_id) > 0)
                .all()
        )

    def get_payload(self):
        """Get the current status payload for the index."""
        # TODO better docstring and type checking
        locations = self.get_all_locations_with_test_results()

        authorities = OrderedDefaultDict(list)

        for authority, results_by_authority in groupby(self.get_most_recent_result_for_each_location(), attrgetter('chain.responder.authority')):
            for responder, results_by_authority_and_location in groupby(results_by_authority, attrgetter('chain.responder')):
                row = (responder.url, responder.current)
                row = row + tuple(results_by_authority_and_location)
                authorities[authority.name].append(row)

        return {
            'locations': locations,
            'sections': authorities
        }

    def get_location_by_key_id(self, key_id: uuid.UUID) -> Optional[Location]:
        """Get a location by its key id."""
        return self.session.query(Location).filter(Location.key_id == key_id).one_or_none()

    def create_location(self, location_name: str) -> Tuple[bytes, bytes]:
        """Create a new Location with an invite.

        :param location_name: The name to be associated with the Location.

        :returns: A 2-tuple containing a 16-byte string of the "selector" and a 16-byte string of the "validator".
        """
        selector = secrets.token_bytes(16)
        validator = secrets.token_bytes(16)
        invite_validator_hash = pwd_context.hash(validator)

        new_location = Location(
            name=location_name,
            selector=selector,
            validator_hash=invite_validator_hash
        )

        self.session.add(new_location)
        self.session.commit()
        return selector, validator

    def get_location_by_selector(self, selector: bytes) -> Optional[Location]:
        """Get an invite by its binary selector."""
        return self.session.query(Location).filter(Location.selector == selector).one_or_none()

    def process_location(self, invite_token: bytes, public_key: str) -> Optional[Location]:
        """Given an invite token and public key, check for a valid invite and associate the public key with the corresponding location.

        :parameter invite_token: a 32-byte string corresponding to an invited Location.
        :parameter public_key: The public key to be associated with the Location.

        :returns: The Location if a valid invite was provided, otherwise None.
        """
        if len(invite_token) != 32:
            raise ValueError('invite_token of wrong length')
        selector = invite_token[:16]
        validator = invite_token[16:]

        location = self.get_location_by_selector(selector)
        if location is None:
            raise Exception(f'location not found for selector: {selector}')
        if location.pubkey:  # this invite has already been used
            return None
        if not location.verify(validator):
            return None

        # TODO: verify that the public key is an algorithm we want to support
        location.set_public_key(public_key)

        self.session.commit()
        return location

    def get_most_recent_chains_for_authorities(self, n: Optional[int] = 10) -> List[Chain]:
        """Get the most recently updated chain for each of the top n authorities.

        :param n: The number of Authorities/Chains to retrieve. Pass None for no limit.

        :returns: A list of chains.
        """
        top_authorities = (
            self.session.query(Authority.id.label('auth_id'))
            .order_by(Authority.cardinality.desc())
        )
        if n is not None:
            top_authorities = top_authorities.limit(n)
        top_authorities = top_authorities.subquery('top_authorities')

        top_authorities_responders = (
            self.session.query(Responder.id.label('resp_id'))
            .select_from(top_authorities)
            .join(Responder, Responder.authority_id == top_authorities.c.auth_id)
            .subquery('top_authorities_responders')
        )

        most_recent_chain_timestamps = (
            self.session.query(func.max(Chain.retrieved).label('most_recent'), Chain.responder_id.label('resp_id'))
            .select_from(top_authorities_responders)
            .join(Chain, Chain.responder_id == top_authorities_responders.c.resp_id)
            .group_by(Chain.responder_id)
            .subquery('most_recent_chain_timestamps')
        )

        query = (
            self.session.query(Chain)
            .select_from(most_recent_chain_timestamps)
            .join(Chain, and_(
                Chain.responder_id == most_recent_chain_timestamps.c.resp_id,
                Chain.retrieved == most_recent_chain_timestamps.c.most_recent
            ))
        )

        return query.all()

    def insert_payload(self, location: Location, results: Iterable[Mapping]):
        """Take the submitted payload and insert its results into the database."""
        for prepared_result_dict in results:
            result = Result(**prepared_result_dict)
            result.location = location
            self.session.add(result)

        self.session.commit()
