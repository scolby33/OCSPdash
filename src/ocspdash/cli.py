# -*- coding: utf-8 -*-

"""The CLI module for OCSPdash."""

import base64
import logging

import click

from ocspdash.constants import OCSPDASH_CONNECTION
from ocspdash.manager import Manager


@click.group()
def main():
    """Run OCSPdash."""


@main.command()
@click.option('--host', default='0.0.0.0', help='Flask host. Defaults to localhost')
@click.option('--port', type=int, default=8000, help='Flask port.')
@click.option(
    '--connection', help=f'SQLAlchemy connection. Defaults to {OCSPDASH_CONNECTION}'
)
@click.option('--flask-debug', is_flag=True)
@click.option('-v', '--verbose', is_flag=True, help='Verbose output')
def web(host, port, connection, flask_debug, verbose):
    """Run the Flask development server."""
    logging.basicConfig(level=(logging.DEBUG if verbose else logging.INFO))

    from ocspdash.web import create_application

    app = create_application(connection=connection, flask_debug=flask_debug)
    app.run(host=host, port=port, debug=flask_debug)


@main.command()
@click.option('-n', '--buckets', default=2, type=int, help='Number of top authorities')
@click.option(
    '--connection', help=f'SQLAlchemy connection. Defaults to {OCSPDASH_CONNECTION}'
)
@click.option('-v', '--verbose', is_flag=True, help='Verbose output')
def update(buckets, connection, verbose):
    """Update the local database."""
    logging.basicConfig(level=(logging.DEBUG if verbose else logging.INFO))

    m = Manager.from_args(connection=connection)
    m.update(n=buckets)


@main.command()
@click.option(
    '--connection', help=f'SQLAlchemy connection. Defaults to {OCSPDASH_CONNECTION}'
)
@click.option('-y', '--yes', is_flag=True)
def nuke(connection, yes):
    """Nuke the database."""
    if yes or click.confirm('Nuke the database?'):
        m = Manager.from_args(connection=connection, echo=True)
        m.drop_database()


@main.command()
@click.option(
    '--connection', help=f'SQLAlchemy connection. Defaults to {OCSPDASH_CONNECTION}'
)
@click.argument('location_name')
def new_location(connection, location_name):
    """Register a new location."""
    m = Manager.from_args(connection=connection)

    invite_id, invite_validator = m.create_location(location_name)

    click.echo(
        base64.urlsafe_b64encode(b''.join((invite_id, invite_validator))).decode(
            'utf-8'
        )
    )


if __name__ == '__main__':
    main()
