#!/usr/bin/env python3
# encoding: utf-8

import json
import random
import string
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import click


SUPPORTED_TYPES = ["data", "information", "access-requests", "pia-summaries"]
TRACKING_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
)


def _eligible_packages(dataset_refs=None, require_resources=True):
    from ckanext.yukondesign import matomo_sync

    packages = matomo_sync._active_packages(
        dataset_refs=list(dataset_refs) if dataset_refs else None
    )
    if not require_resources:
        return packages

    eligible = []
    for package in packages:
        if matomo_sync._dataset_download_urls(package):
            eligible.append(package)
    return eligible


def _normalize_site_url(site_url):
    return site_url.rstrip("/")


def _resource_urls_from_dict(site_url, package_dict):
    urls = []
    package_id = package_dict.get("id")
    dataset_type = (package_dict.get("type") or "dataset").strip("/")
    for resource in package_dict.get("resources", []):
        if resource.get("state") != "active":
            continue
        resource_url = resource.get("url")
        if not resource_url:
            continue
        if resource.get("url_type") == "upload":
            urls.append(
                "{}/{}/{}/resource/{}/download/{}".format(
                    site_url,
                    dataset_type,
                    package_id,
                    resource.get("id"),
                    resource_url.lstrip("/"),
                )
            )
        else:
            urls.append(resource_url)
    return urls


def _fetch_packages_from_api(ckan_url, api_token=None, dataset_refs=None):
    packages = []
    headers = {"User-Agent": TRACKING_USER_AGENT}
    if api_token:
        headers["Authorization"] = api_token

    if dataset_refs:
        for dataset_ref in dataset_refs:
            req = Request(
                "{}/api/3/action/package_show?id={}".format(
                    ckan_url, dataset_ref
                ),
                headers=headers,
            )
            with urlopen(req, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
            packages.append(payload["result"])
        return packages

    start = 0
    rows = 100
    while True:
        req = Request(
            "{}/api/3/action/package_search?{}".format(
                ckan_url,
                urlencode(
                    {
                        "fq": "type:({})".format(" OR ".join(SUPPORTED_TYPES)),
                        "rows": rows,
                        "start": start,
                    }
                ),
            ),
            headers=headers,
        )
        with urlopen(req, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
        results = payload["result"]["results"]
        if not results:
            break
        packages.extend(results)
        start += len(results)
        if start >= payload["result"]["count"]:
            break
    return packages


def _eligible_package_dicts(packages, site_url, require_resources=True):
    if not require_resources:
        return packages
    return [
        package
        for package in packages
        if _resource_urls_from_dict(site_url, package)
    ]


def _random_visitor_id():
    alphabet = string.hexdigits.lower()[:16]
    return "".join(random.choice(alphabet) for _ in range(16))


def _generate_browser_traffic(
    page,
    package_dict,
    site_url,
    visits,
    downloads,
    sleep_ms,
    dry_run,
):
    dataset_type = (package_dict.get("type") or "dataset").strip("/")
    page_url = "{}/{}/{}".format(site_url, dataset_type, package_dict["name"])
    download_urls = _resource_urls_from_dict(site_url, package_dict)
    visitor_id = _random_visitor_id()

    if dry_run:
        return {
            "dataset": package_dict["name"],
            "visits_sent": 0,
            "downloads_sent": 0,
            "visitor_id": visitor_id,
            "dry_run": True,
        }

    visits_sent = 0
    downloads_sent = 0
    for _ in range(visits):
        page.goto(page_url, wait_until="domcontentloaded")
        page.wait_for_timeout(max(sleep_ms, 750))
        visits_sent += 1

    for idx in range(downloads):
        if not download_urls:
            break
        page.evaluate(
            """
            async (downloadUrl) => {
              if (!window._paq) {
                return false;
              }
              window._paq.push(['trackLink', downloadUrl, 'download']);
              await new Promise((resolve) => setTimeout(resolve, 1000));
              return true;
            }
            """,
            download_urls[idx % len(download_urls)],
        )
        page.wait_for_timeout(max(sleep_ms, 750))
        downloads_sent += 1

    return {
        "dataset": package_dict["name"],
        "visits_sent": visits_sent,
        "downloads_sent": downloads_sent,
        "visitor_id": visitor_id,
        "dry_run": False,
    }


@click.command()
@click.option(
    "-c",
    "--config",
    "config_path",
    help="Path to CKAN config file.",
)
@click.option(
    "--ckan-url",
    default=None,
    help="Standalone mode: CKAN base URL, e.g. https://ckan.yukon.dev.datopian.com",
)
@click.option(
    "--ckan-api-token",
    default=None,
    help="Optional CKAN API token for package_show/package_search.",
)
@click.option(
    "--headless/--headed",
    default=True,
    show_default=True,
    help="Standalone mode: run browser hidden or visible.",
)
@click.option(
    "--dataset-count",
    type=int,
    default=22,
    show_default=True,
    help="How many random datasets to target.",
)
@click.option(
    "--min-visits",
    type=int,
    default=3,
    show_default=True,
    help="Minimum pageviews per selected dataset.",
)
@click.option(
    "--max-visits",
    type=int,
    default=12,
    show_default=True,
    help="Maximum pageviews per selected dataset.",
)
@click.option(
    "--min-downloads",
    type=int,
    default=1,
    show_default=True,
    help="Minimum downloads per selected dataset.",
)
@click.option(
    "--max-downloads",
    type=int,
    default=4,
    show_default=True,
    help="Maximum downloads per selected dataset.",
)
@click.option(
    "--sleep-ms",
    type=int,
    default=0,
    show_default=True,
    help="Delay between events in milliseconds.",
)
@click.option(
    "--seed",
    type=int,
    default=None,
    help="Optional random seed for reproducible runs.",
)
@click.option(
    "--dataset-ref",
    "dataset_refs",
    multiple=True,
    help="Optional dataset name or id filter. Can be passed multiple times.",
)
@click.option(
    "--allow-no-resources/--require-resources",
    default=False,
    show_default=True,
    help="Include datasets without downloadable resources.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Preview selected datasets and counts without sending traffic.",
)
def main(
    config_path,
    ckan_url,
    ckan_api_token,
    headless,
    dataset_count,
    min_visits,
    max_visits,
    min_downloads,
    max_downloads,
    sleep_ms,
    seed,
    dataset_refs,
    allow_no_resources,
    dry_run,
):
    """Generate random Matomo traffic across multiple Yukon datasets."""
    if not config_path and not ckan_url:
        raise click.ClickException(
            "Pass either --config or --ckan-url for standalone browser mode"
        )
    if dataset_count < 1:
        raise click.ClickException("--dataset-count must be greater than 0")
    if min_visits < 0 or max_visits < 0 or min_downloads < 0 or max_downloads < 0:
        raise click.ClickException("Visit/download ranges must be >= 0")
    if min_visits > max_visits:
        raise click.ClickException("--min-visits cannot be greater than --max-visits")
    if min_downloads > max_downloads:
        raise click.ClickException(
            "--min-downloads cannot be greater than --max-downloads"
        )

    rng = random.Random(seed)
    totals = {
        "datasets": 0,
        "visits_sent": 0,
        "downloads_sent": 0,
    }

    if config_path:
        from ckan.cli import load_config
        from ckan.config.middleware import make_app
        from ckanext.yukondesign import matomo_sync

        config_dict = load_config(config_path)
        flask_app = make_app(config_dict)._wsgi_app

        with flask_app.app_context():
            packages = _eligible_packages(
                dataset_refs=dataset_refs,
                require_resources=not allow_no_resources,
            )

            if not packages:
                raise click.ClickException("No eligible datasets found")

            selected = (
                rng.sample(packages, min(dataset_count, len(packages)))
                if len(packages) > 1
                else packages
            )

            for package in selected:
                visits = rng.randint(min_visits, max_visits)
                downloads = rng.randint(min_downloads, max_downloads)
                if allow_no_resources and not matomo_sync._dataset_download_urls(package):
                    downloads = 0

                summary = matomo_sync.generate_test_traffic(
                    dataset_ref=package.name,
                    visits=visits,
                    downloads=downloads,
                    sleep_ms=sleep_ms,
                    dry_run=dry_run,
                )

                totals["datasets"] += 1
                totals["visits_sent"] += summary["visits_sent"]
                totals["downloads_sent"] += summary["downloads_sent"]

                click.echo(
                    "dataset={dataset} visits_sent={visits_sent} "
                    "downloads_sent={downloads_sent} visitor_id={visitor_id} "
                    "dry_run={dry_run}".format(**summary)
                )
    else:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise click.ClickException(
                "Standalone mode requires Playwright. "
                "Install it with: pip install playwright && playwright install chromium"
            )

        site_url = _normalize_site_url(ckan_url)
        packages = _eligible_package_dicts(
            _fetch_packages_from_api(
                site_url,
                api_token=ckan_api_token,
                dataset_refs=dataset_refs,
            ),
            site_url,
            require_resources=not allow_no_resources,
        )
        if not packages:
            raise click.ClickException("No eligible datasets found")

        selected = (
            rng.sample(packages, min(dataset_count, len(packages)))
            if len(packages) > 1
            else packages
        )

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=headless)
            context = browser.new_context(user_agent=TRACKING_USER_AGENT)
            page = context.new_page()
            try:
                for package in selected:
                    visits = rng.randint(min_visits, max_visits)
                    downloads = rng.randint(min_downloads, max_downloads)
                    if allow_no_resources and not _resource_urls_from_dict(site_url, package):
                        downloads = 0

                    summary = _generate_browser_traffic(
                        page,
                        package,
                        site_url=site_url,
                        visits=visits,
                        downloads=downloads,
                        sleep_ms=sleep_ms,
                        dry_run=dry_run,
                    )

                    totals["datasets"] += 1
                    totals["visits_sent"] += summary["visits_sent"]
                    totals["downloads_sent"] += summary["downloads_sent"]

                    click.echo(
                        "dataset={dataset} visits_sent={visits_sent} "
                        "downloads_sent={downloads_sent} visitor_id={visitor_id} "
                        "dry_run={dry_run}".format(**summary)
                    )
                    if sleep_ms:
                        time.sleep(float(sleep_ms) / 1000.0)
            finally:
                context.close()
                browser.close()

    click.echo(
        "random-traffic: datasets={datasets} visits_sent={visits_sent} "
        "downloads_sent={downloads_sent} dry_run={dry_run}".format(
            dry_run=dry_run, **totals
        )
    )


if __name__ == "__main__":
    main()
