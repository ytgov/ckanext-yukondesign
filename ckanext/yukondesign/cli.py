# encoding: utf-8

import click

from ckan.cli import load_config
from ckan.config.middleware import make_app

from . import matomo_sync


def get_commands():
    return [yukon_matomo]


@click.group(name="yukon-matomo")
@click.help_option("-h", "--help")
@click.pass_context
def yukon_matomo(ctx, config=None):
    config_dict = load_config(config)
    flask_app = make_app(config_dict)._wsgi_app
    ctx.obj = {"flask_app": flask_app}


@yukon_matomo.command(
    "sync-usage-data", short_help="Sync usage_data from Matomo"
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Preview updates without writing to DB.",
)
@click.option(
    "--limit",
    type=int,
    default=None,
    help="Limit number of datasets for this run.",
)
@click.option(
    "--offset",
    type=int,
    default=None,
    help="Skip this many datasets before processing the batch.",
)
@click.option(
    "--dataset-ref",
    "dataset_refs",
    multiple=True,
    help="Optional dataset name or id. Can be passed multiple times.",
)
@click.pass_context
def sync_usage_data(ctx, dry_run, limit, offset, dataset_refs):
    """Sync usage_data extras from Matomo without metadata updates."""
    flask_app = ctx.obj["flask_app"]
    with flask_app.app_context():
        summary = matomo_sync.sync_usage_data(
            dry_run=dry_run,
            limit=limit,
            offset=offset,
            dataset_refs=list(dataset_refs) if dataset_refs else None,
        )

    click.echo(
        "sync-usage-data: processed={processed} updated={updated} "
        "skipped={skipped} failed={failed} dry_run={dry_run} "
        "offset={offset} total={total} has_more={has_more} "
        "next_offset={next_offset}".format(**summary)
    )


@yukon_matomo.command(
    "generate-test-traffic",
    short_help="Generate fake Matomo visits/downloads for one dataset",
)
@click.option(
    "--dataset-ref",
    required=True,
    help="Dataset name or id to target.",
)
@click.option(
    "--visits",
    type=int,
    default=25,
    show_default=True,
    help="Number of synthetic pageviews to emit.",
)
@click.option(
    "--downloads",
    type=int,
    default=10,
    show_default=True,
    help="Number of synthetic download events to emit.",
)
@click.option(
    "--sleep-ms",
    type=int,
    default=0,
    show_default=True,
    help="Delay between events in milliseconds.",
)
@click.option(
    "--visitor-id",
    default=None,
    help="Optional 16-char visitor id; random if omitted.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Show what would be emitted without sending events.",
)
@click.pass_context
def generate_test_traffic(
    ctx,
    dataset_ref,
    visits,
    downloads,
    sleep_ms,
    visitor_id,
    dry_run,
):
    """Emit synthetic Matomo traffic for local validation."""
    flask_app = ctx.obj["flask_app"]
    with flask_app.app_context():
        summary = matomo_sync.generate_test_traffic(
            dataset_ref=dataset_ref,
            visits=visits,
            downloads=downloads,
            sleep_ms=sleep_ms,
            visitor_id=visitor_id,
            dry_run=dry_run,
        )

    click.echo(
        "generate-test-traffic: dataset={dataset} visits_sent={visits_sent} "
        "downloads_sent={downloads_sent} visitor_id={visitor_id} "
        "dry_run={dry_run}".format(**summary)
    )
