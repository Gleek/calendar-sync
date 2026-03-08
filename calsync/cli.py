import click

from . import db
from .auth import get_credentials, build_service
from .config import load_config
from .export import export_org
from .sync import sync_all


@click.group()
@click.option("--db-path", default="calendar.db", help="Path to SQLite database")
@click.option("--config", default=None, help="Path to config file")
@click.pass_context
def main(ctx, db_path, config):
    ctx.ensure_object(dict)
    ctx.obj["db_path"] = db_path
    ctx.obj["config"] = load_config(config)


@main.command()
@click.option("--full", is_flag=True, help="Ignore sync tokens, do full sync")
@click.option("--config-dir", default=None, help="Path to auth config directory")
@click.pass_context
def sync(ctx, full, config_dir):
    """Sync Google Calendar events to SQLite."""
    conn = db.get_db(ctx.obj["db_path"])
    db.init_db(conn)

    click.echo("Authenticating...")
    creds = get_credentials(config_dir)
    service = build_service(creds)

    click.echo("Syncing calendars...")
    num_cals, num_events = sync_all(service, conn, ctx.obj["config"], full=full)
    conn.close()

    click.echo(f"Done. Synced {num_cals} calendars, {num_events} events.")


@main.command()
@click.option("--output", "-o", default="calendar.org", help="Output org file path")
@click.pass_context
def export(ctx, output):
    """Export SQLite events to org-mode file."""
    conn = db.get_db(ctx.obj["db_path"])
    num_events = export_org(conn, output, ctx.obj["config"])
    conn.close()

    click.echo(f"Wrote {num_events} events to {output}")
