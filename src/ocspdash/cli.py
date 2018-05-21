# -*- coding: utf-8 -*-

"""The CLI module for OCSPdash."""

import base64
import logging
import secrets

import click
from argon2 import PasswordHasher  # TODO: use passlib for upgradability?

from ocspdash.manager import Manager
from ocspdash.models import Invite


@click.group()
def main():
    """Run OCSP Dashboard"""


@main.command()
@click.option('--host', default='0.0.0.0', help='Flask host. Defaults to localhost')
@click.option('--port', type=int, default=8000, help='Flask port.')
@click.option('--flask-debug', is_flag=True)
@click.option('-v', '--verbose', is_flag=True, help='Verbose output')
def web(host, port, flask_debug, verbose):
    """Run the Flask development server"""
    logging.basicConfig(level=(logging.DEBUG if verbose else logging.INFO))

    from ocspdash.web import create_application
    app = create_application()
    app.run(host=host, port=port, debug=flask_debug)


@main.command()
@click.option('-n', '--buckets', default=2, type=int, help='Number of top authorities')
@click.option('--connection')
@click.option('-v', '--verbose', is_flag=True, help='Verbose output')
@click.option('-u', '--username', default='test', help='Username to use')
def update(buckets, connection, verbose, username):
    """Update the local db"""
    logging.basicConfig(level=(logging.DEBUG if verbose else logging.INFO))

    m = Manager(connection=connection)
    location = m.get_or_create_location(name=username)
    m.update(location, buckets=buckets)


@main.command()
@click.option('--connection')
def nuke(connection):
    """Nukes the database"""
    if click.confirm('Nuke the database?'):
        m = Manager(connection=connection, echo=True)
        m.drop_database()


@main.command()
@click.option('--connection')
@click.argument('location_name')
def new_location(connection, location_name):
    m = Manager(connection)
    invite_id = secrets.token_bytes(16)
    invite_validator = secrets.token_bytes(16)
    ph = PasswordHasher()
    invite_validator_hash = ph.hash(invite_validator)

    new_invite = Invite(
        name=location_name,
        invite_id=invite_id,
        invite_validator=invite_validator_hash
    )
    m.session.add(new_invite)
    m.session.commit()

    click.echo(f'{new_invite.id}:{base64.urlsafe_b64encode(invite_id+invite_validator).decode("utf-8")}')


if __name__ == '__main__':
    main()
