# -*- coding: utf-8 -*-

"""Manager for OCSPDash."""

import logging
import os
import secrets
from collections import OrderedDict, namedtuple
from itertools import groupby
from operator import itemgetter
from typing import List, Optional, Tuple

from sqlalchemy import and_, create_engine, func
from sqlalchemy.engine import Engine
from sqlalchemy.orm import scoped_session, sessionmaker

from ocspdash.constants import OCSPDASH_DEFAULT_CONNECTION
from ocspdash.models import (Authority, Base, Chain, Location,
                             Responder, Result)
from ocspdash.security import pwd_context
from ocspdash.server_query import ServerQuery

__all__ = [
    'Manager',
]

logger = logging.getLogger(__name__)


class Manager(object):
    def __init__(self, engine: Engine, session: scoped_session, server_query: ServerQuery):
        self.engine = engine
        self.session = session
        self.server_query = server_query

        self.create_all()

    @classmethod
    def from_args(cls, connection: Optional[str] = None, echo: bool = False, api_id: Optional[str] = None, api_secret: Optional[str] = None):
        engine, session = cls._get_engine_from_connection(connection=connection, echo=echo)

        server_query = cls._get_server_query(api_id=api_id, api_secret=api_secret)

        return cls(engine, session, server_query)

    @staticmethod
    def _get_connection(connection=None):
        """Get a connection from one of the various configuration locations, prioritizing a passed-in value,
        followed by a value from an environment variable, and finally the default.
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
    def _get_credentials(user: Optional[str] = None, password: Optional[str] = None) -> Tuple[str, str]:
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
            return ServerQuery(api_id, api_secret)

    def create_all(self, checkfirst=True):
        Base.metadata.create_all(self.engine, checkfirst=checkfirst)

    def drop_database(self):
        Base.metadata.drop_all(self.engine)

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

        returns: the Chain or None
        """
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

    def get_most_recent_result_for_each_location(self) -> List[Tuple[Authority, Responder, Result, Location]]:
        """Gets the most recent results for each location."""
        return self.session.query(Authority, Responder, Result, Location) \
            .join(Responder) \
            .join(Chain) \
            .join(Result) \
            .join(Location) \
            .group_by(Responder, Location) \
            .having(func.max(Result.retrieved)) \
            .order_by(Authority.cardinality.desc()) \
            .order_by(Authority.name) \
            .order_by(Responder.cardinality.desc()) \
            .order_by(Responder.url) \
            .order_by(Location.name) \
            .all()

    def get_all_locations_with_test_results(self) -> List[Location]:
        """Return all the Location objects that have at least one associated Result."""
        # TODO @cthoyt
        return [
            location
            for location in self.session.query(Location).all()
            if location.results
        ]

    def make_payload(self):
        locations = self.get_all_locations_with_test_results()
        Row = namedtuple('Row', f'url current {" ".join(location.name for location in locations)}')
        Row.__new__.__defaults__ = (None,) * (len(Row._fields) - 2)

        sections = OrderedDict()
        for authority, group in groupby(self.get_most_recent_result_for_each_location(), itemgetter(0)):
            sections[authority.name] = []
            for responder, group2 in groupby(group, itemgetter(1)):
                results = {
                    location.name: result
                    for _, _, result, location in group2
                }
                row = Row(url=responder.url, current=responder.current, **results)
                sections[authority.name].append(row)

        return {
            'locations': locations,
            'sections': sections
        }

    def get_location_by_id(self, location_id: int) -> Location:
        """Get a location."""
        return self.session.query(Location).get(location_id)

    def get_responder_by_id(self, responder_id: int) -> Responder:
        """Get a responder."""
        return self.session.query(Responder).get(responder_id)

    def get_authority_by_id(self, authority_id: int) -> Authority:
        """Get an authority."""
        return self.session.query(Authority).get(authority_id)

    def create_location(self, location_name: str) -> Tuple[bytes, bytes]:
        selector = secrets.token_bytes(16)
        validator = secrets.token_bytes(16)
        invite_validator_hash = pwd_context.hash(validator)

        new_invite = Location(
            name=location_name,
            selector=selector,
            validator_hash=invite_validator_hash
        )

        self.session.add(new_invite)
        self.session.commit()
        return selector, validator

    def get_location_by_selector(self, selector: bytes) -> Optional[Location]:
        """Get an invite by its binary selector."""
        return self.session.query(Location).filter(Location.selector == selector).one_or_none()

    def process_location(self, invite_token: bytes, public_key: str) -> Optional[Location]:
        if len(invite_token) != 32:
            raise ValueError('invite_token of wrong length')
        selector = invite_token[:16]
        validator = invite_token[16:]

        location = self.get_location_by_selector(selector)
        if not location.verify(validator):
            return

        location.set_public_key(public_key)

        self.session.commit()
        return location

    def get_manifest(self):
        authorities = self.get_top_authorities()
        responders = []
        for authority in authorities:
            responders.extend(authority.responders)

        # TODO @cthoyt SQL
        chains = [responder.most_recent_chain for responder in responders]

        assert len(responders) == len(chains)

        ManifestEntry = namedtuple('ManifestEntry', 'authority_name responder_url subject_certificate issuer_certificate')
        return [
            ManifestEntry(
                authority_name=chain.responder.authority.name,
                responder_url=chain.responder.url,
                subject_certificate=chain.subject,
                issuer_certificate=chain.issuer
            )
            for chain in chains if chain is not None
        ]

    def get_results(self):
        logger.warning('Get results method is not actually implemented')
        return {'test': 12345}

    def insert_payload(self, payload):
        """Takes the payload submitted and returns it."""
        logger.info('Submitted payload: %s', payload)
        logger.warning('Submit method is not actually implemented')
