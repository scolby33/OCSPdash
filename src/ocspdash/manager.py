# -*- coding: utf-8 -*-

import logging
import os
import urllib.parse
from collections import namedtuple, OrderedDict
from itertools import groupby
from operator import itemgetter
from typing import Optional, List, Tuple

from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker, scoped_session

from ocspdash.constants import OCSPDASH_DATABASE_CONNECTION
from ocspdash.models import (
    Base,
    Authority,
    Responder,
    Chain,
    Location,
    Result
)
from ocspdash.server_query import ServerQuery, check_ocsp_response, ping

logger = logging.getLogger(__name__)


class BaseCacheManager(object):
    def __init__(self, connection=None, echo=False):
        if connection:
            self.connection = connection
        elif 'OCSPDASH_CONNECTION' in os.environ:
            logger.info('using connection from environment: %s', os.environ['OCSPDASH_CONNECTION'])
            self.connection = os.environ['OCSPDASH_CONNECTION']
        else:
            logger.info('using default connection: %s', OCSPDASH_DATABASE_CONNECTION)
            self.connection = OCSPDASH_DATABASE_CONNECTION

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


class Manager(BaseCacheManager):
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

        if user is None and password is None:
            self.server_query = None
        else:
            self.server_query = ServerQuery(user, password)

    def ensure_authority(self, name: str, rank: int, cardinality: int) -> Authority:
        authority = self.session.query(Authority).filter(Authority.name == name).one_or_none()

        if authority is None:
            authority = Authority(
                name=name,
                cardinality=cardinality,
                rank=rank
            )
            self.session.add(authority)

        else:
            authority.rank = rank
            authority.cardinality = cardinality

        self.session.commit()

        return authority

    def ensure_responder(self, authority: Authority, url: str, cardinality: int) -> Responder:
        responder = self.session.query(Responder).filter(Responder.authority_id == authority.id,
                                                         Responder.url == url).one_or_none()

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

    def ensure_chain(self, responder: Responder) -> Optional[Chain]:
        most_recent = self.session.query(Chain).filter(Chain.responder_id == responder.id).order_by(
            Chain.retrieved.desc()).first()

        if most_recent and not most_recent.old:
            if not most_recent.expired:
                return most_recent

            if not responder.current:
                return most_recent

        subject, issuer = self.server_query.get_certs_for_issuer_and_url(responder.authority.name, responder.url)

        if subject is None or issuer is None:
            return None

        chain = Chain(
            responder=responder,
            subject=subject,
            issuer=issuer,
        )

        self.session.add(chain)

        return chain

    def get_or_create_location(self, name: str) -> Location:
        location = self.session.query(Location).filter(Location.name == name).one_or_none()

        if location is None:
            location = Location(name=name)
            self.session.add(location)

        return location

    def update(self, location: Location, n: int = 10):
        """Runs the update

        :param location: The location from which the update function is run
        :param n: The number of top authorities to query
        """
        if self.server_query is None:
            raise RuntimeError('No username and password for Censys supplied')

        issuers = self.server_query.get_top_authorities(n)

        for rank, (issuer_name, issuer_cardinality) in enumerate(issuers.items()):
            authority = self.ensure_authority(issuer_name, rank, issuer_cardinality)

            ocsp_urls = self.server_query.get_ocsp_urls_for_issuer(authority.name)

            for url, responder_cardinality in ocsp_urls.items():
                responder = self.ensure_responder(authority, url, responder_cardinality)

                chain = self.ensure_chain(responder)

                result = Result(
                    chain=chain,
                    location=location
                )

                if chain is not None:
                    result.created = True
                    result.current = self.server_query.is_ocsp_url_current_for_issuer(authority.name, url)
                    parse_result = urllib.parse.urlparse(url)
                    result.ping = ping(parse_result.netloc)
                    result.ocsp = check_ocsp_response(chain.subject, chain.issuer, url)

                self.session.add(result)
                self.session.commit()

            self.session.commit()

        self.session.commit()

    def get_top_authorities(self, n: int = 10) -> List[Authority]:
        """Retrieve the top (by cardinality) authorities from the database.
        Will get up to n, but if there are fewer entries in the db, it will not create more.
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
        """Gets a location"""
        return self.session.query(Location).get(location_id)

    def get_responder_by_id(self, responder_id: int) -> Responder:
        """Gets a responder"""
        return self.session.query(Responder).get(responder_id)

    def get_authority_by_id(self, authority_id: int) -> Authority:
        return self.session.query(Authority).get(authority_id)

    def get_results(self):
        logger.warning('Get results method is not actually implemented')
        return {'test': 12345}

    def insert_payload(self, payload):
        """Takes the payload submitted and returns it"""
        logger.info('Submitted payload: %s', payload)
        logger.warning('Submit method is not actually implemented')
