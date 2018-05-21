# -*- coding: utf-8 -*-

"""Manager for OCSPDash."""

import logging
import os
import uuid
from base64 import urlsafe_b64decode as b64decode
from collections import OrderedDict, namedtuple
from itertools import groupby
from operator import itemgetter
from typing import List, Optional, Tuple

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from sqlalchemy import and_, create_engine, func
from sqlalchemy.orm import scoped_session, sessionmaker

from ocspdash.constants import NAMESPACE_OCSPDASH_KID, OCSPDASH_CONNECTION
from ocspdash.models import (Authority, Base, Chain, Invite, Location,
                             Responder, Result)
from ocspdash.server_query import ServerQuery

__all__ = [
    'BaseManager',
    'Manager',
]

logger = logging.getLogger(__name__)


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

    logger.info('using default connection: %s', OCSPDASH_CONNECTION)
    return OCSPDASH_CONNECTION


class BaseManager(object):
    def __init__(self, connection=None, echo=False):
        self.connection = _get_connection(connection=connection)

        self.engine = create_engine(self.connection, echo=echo)

        #: A SQLAlchemy session maker
        self.session_maker = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False)

        #: A SQLAlchemy session object
        self.session = scoped_session(self.session_maker)

        self.create_all()

    def create_all(self, checkfirst=True):
        Base.metadata.create_all(self.engine, checkfirst=checkfirst)

    def drop_database(self):
        Base.metadata.drop_all(self.engine)


class Manager(BaseManager):
    def __init__(self, connection=None, echo: bool = None, user: str = None, password: str = None):
        """All the operations required to find the OCSP servers of the top certificate authorities and test them.

        :param user: A valid `Censys <https://censys.io>`_ API ID
        :param password: The matching `Censys <https://censys.io>`_ API secret
        """
        super().__init__(connection=connection, echo=echo)

        if user is None:
            user = os.environ.get('CENSYS_API_ID')

        if password is None:
            password = os.environ.get('CENSYS_API_SECRET')

        if user is None or password is None:
            self.server_query = None
        else:
            self.server_query = ServerQuery(user, password)

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

    def get_or_create_location(self, name: str) -> Location:
        """Get a Location from the database by name, or create a new one if none with that name exists.

        :param name: the name of the Location

        :returns: the Location
        """
        location = self.get_location_by_name(name)

        if location is None:
            location = Location(name=name)
            self.session.add(location)
            self.session.commit()

        return location

    def update(self, n: int = 10):
        """Update the database of Authorities, Responders, and Chains from Censys.

        If there are no Authorities in the DB or if any of the top n Authorities haven't been updated in the past
        7 days, retrieves an all-new set of Authorities, Responders, and Chains from Censys.

        Otherwise, it's a no-op.

        :param n: the number of top authorities to get information on
        """
        if self.server_query is None:
            raise RuntimeError('No username and password for Censys supplied')

        authorities = self.get_top_authorities(n)
        if (not authorities  # probably a first run with a clean DB
                or any(authority.old for authority in authorities)):
            issuers = self.server_query.get_top_authorities(buckets=n)
            for issuer_name, issuer_cardinality in issuers.items():
                authority = self.ensure_authority(issuer_name, issuer_cardinality)

                ocsp_urls = self.server_query.get_ocsp_urls_for_issuer(authority.name)

                for url, responder_cardinality in ocsp_urls.items():
                    responder = self.ensure_responder(authority, url, responder_cardinality)
                    self.ensure_chain(responder)

    def get_top_authorities(self, n: int = 10) -> List[Authority]:
        """Retrieve the top authorities (as measured by cardinality) from the database.
        Will retrieve up to n, but if there are fewer entries in the DB, it will not create more.

        :param n: the number of top authorities to retrieve

        :returns: a list of up to n Authorities
        """
        return self.session.query(Authority).order_by(Authority.cardinality.desc()).limit(n).all()

    def get_most_recent_result_for_each_location(self) -> List[Tuple[Authority, Responder, Result, Location]]:
        """Gets the most recent results for each location"""
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
        """Return all the Location objects that have at least one associated Result"""
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

    def get_invite_by_id(self, invite_id: int) -> Invite:
        """Get an invite."""
        return self.session.query(Invite).get(invite_id)

    def get_invite_by_selector(self, selector: bytes) -> Invite:
        """Get an invite by its binary selector."""
        return self.session.query(Invite).filter_by(invite_id=selector).one_or_none()

    def process_invite(self, invite_token: bytes, public_key: str) -> Optional[Location]:
        _password_hasher = PasswordHasher()  # todo move this to be an instance or class variable once the manager inheritence/init situation is figured out

        if len(invite_token) != 32:
            return
        invite_id = invite_token[:16]
        invite_validator = invite_token[16:]

        invite = self.get_invite_by_selector(invite_id)
        try:
            _password_hasher.verify(invite.invite_validator, invite_validator)
        except VerifyMismatchError:
            return

        key_id = uuid.uuid5(NAMESPACE_OCSPDASH_KID, public_key)

        new_location = Location(
            name=invite.name,
            pubkey=b64decode(public_key),
            key_id=key_id
        )
        self.session.add(new_location)
        self.session.delete(invite)
        self.session.commit()
        return new_location

    def get_results(self):
        logger.warning('Get results method is not actually implemented')
        return {'test': 12345}

    def insert_payload(self, payload):
        """Takes the payload submitted and returns it"""
        logger.info('Submitted payload: %s', payload)
        logger.warning('Submit method is not actually implemented')
