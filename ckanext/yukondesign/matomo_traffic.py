# encoding: utf-8
"""
Fake-traffic generation for local Matomo testing.

This module is intentionally separate from matomo_sync.py (which only reads
stats from Matomo and writes them to CKAN).  Nothing here touches the CKAN DB.
"""

import calendar
import datetime
import http.client
import json
import random
from urllib.parse import urlencode, urlparse

import logging

import ckan.plugins.toolkit as toolkit

from .matomo_sync import (
    MatomoClient,
    _active_packages,
    _dataset_download_urls,
    _dataset_url,
    _get_package_by_ref,
    _shift_years,
)

log = logging.getLogger(__name__)


class MatomoTrackingClient(MatomoClient):
    """Extends MatomoClient with Matomo Bulk Tracking API support."""

    def __init__(self):
        super(MatomoTrackingClient, self).__init__()
        parsed = urlparse(self.base_url)
        self._host = parsed.hostname
        self._port = parsed.port or (443 if parsed.scheme == "https" else 80)
        self._scheme = parsed.scheme
        self._tracking_path = parsed.path.rstrip("/") + "/matomo.php"

    def _make_conn(self):
        if self._scheme == "https":
            return http.client.HTTPSConnection(
                self._host, self._port, timeout=self.timeout
            )
        return http.client.HTTPConnection(
            self._host, self._port, timeout=self.timeout
        )

    def _track_bulk(self, requests):
        """Send a list of tracking param-dicts in one POST request."""
        body = json.dumps({
            "requests": [
                "?" + urlencode(
                    dict(
                        idsite=self.site_id,
                        rec=1,
                        apiv=1,
                        rand=random.randint(1, 10 ** 9),
                        **r,
                    ),
                    doseq=True,
                )
                for r in requests
            ],
            "token_auth": self.token_auth,
        }).encode("utf-8")
        conn = self._make_conn()
        try:
            conn.request(
                "POST",
                self._tracking_path,
                body=body,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "ckan-yukon-test-traffic/1.0",
                },
            )
            resp = conn.getresponse()
            resp.read()
        finally:
            conn.close()

    def _build_pageview(self, page_url, visitor_id, at=None):
        p = {
            "url": page_url,
            "action_name": "Dataset Page View",
            "_id": visitor_id,
        }
        if at is not None:
            p["cdt"] = int(calendar.timegm(at.timetuple()))
        return p

    def _build_download(self, download_url, visitor_id, at=None):
        p = {"download": download_url, "_id": visitor_id}
        if at is not None:
            p["cdt"] = int(calendar.timegm(at.timetuple()))
        return p


def _random_visitor_id():
    return "".join(random.choice("0123456789abcdef") for _ in range(16))


def _random_datetime_in_range(start_date, end_date):
    """Return a random datetime between start_date and end_date (inclusive)."""
    delta_days = (end_date - start_date).days
    offset_days = random.randint(0, max(0, delta_days))
    offset_seconds = random.randint(0, 86399)
    return datetime.datetime.combine(
        start_date + datetime.timedelta(days=offset_days),
        datetime.time.min,
    ) + datetime.timedelta(seconds=offset_seconds)


def generate_test_traffic(
    dataset_ref,
    visits_3y=25,
    visits_90d=10,
    downloads_3y=10,
    downloads_90d=5,
    dry_run=False,
):
    """Send synthetic pageviews and download events to Matomo.

    All events for a dataset are sent in a single bulk POST so the number
    of HTTP round-trips equals the number of datasets, not the number of
    individual events.  Events are backdated with Matomo's ``cdt`` parameter
    so the 3-year and 90-day windows are populated independently.  Every
    pageview uses a unique visitor ID so Matomo counts each as a distinct visit.
    """
    if visits_3y < 0 or visits_90d < 0 or downloads_3y < 0 or downloads_90d < 0:
        raise toolkit.ValidationError("All visit/download counts must be >= 0")

    total_downloads = downloads_3y + downloads_90d
    package = _get_package_by_ref(dataset_ref)
    page_url = _dataset_url(package)
    download_urls = _dataset_download_urls(package)

    if total_downloads > 0 and not download_urls:
        raise toolkit.ValidationError(
            "Dataset has no active resource URLs to count as downloads"
        )

    today = datetime.date.today()
    end_date = today - datetime.timedelta(days=1)
    last_90_start = end_date - datetime.timedelta(days=89)
    pre_90_end = last_90_start - datetime.timedelta(days=1)
    three_year_start = _shift_years(end_date, -3) + datetime.timedelta(days=1)

    if dry_run:
        return {
            "dataset": package.name,
            "page_url": page_url,
            "visits_3y_targeted": visits_3y,
            "visits_90d_targeted": visits_90d,
            "downloads_3y_targeted": downloads_3y,
            "downloads_90d_targeted": downloads_90d,
            "visits_3y_sent": 0,
            "visits_90d_sent": 0,
            "downloads_3y_sent": 0,
            "downloads_90d_sent": 0,
            "dry_run": True,
        }

    client = MatomoTrackingClient()
    requests = []

    for _ in range(visits_3y):
        at = _random_datetime_in_range(three_year_start, pre_90_end)
        requests.append(client._build_pageview(page_url, _random_visitor_id(), at=at))

    for _ in range(visits_90d):
        at = _random_datetime_in_range(last_90_start, end_date)
        requests.append(client._build_pageview(page_url, _random_visitor_id(), at=at))

    for idx in range(downloads_3y):
        at = _random_datetime_in_range(three_year_start, pre_90_end)
        download_url = download_urls[idx % len(download_urls)]
        requests.append(client._build_download(download_url, _random_visitor_id(), at=at))

    for idx in range(downloads_90d):
        at = _random_datetime_in_range(last_90_start, end_date)
        download_url = download_urls[idx % len(download_urls)]
        requests.append(client._build_download(download_url, _random_visitor_id(), at=at))

    if requests:
        client._track_bulk(requests)

    return {
        "dataset": package.name,
        "page_url": page_url,
        "visits_3y_targeted": visits_3y,
        "visits_90d_targeted": visits_90d,
        "downloads_3y_targeted": downloads_3y,
        "downloads_90d_targeted": downloads_90d,
        "visits_3y_sent": visits_3y,
        "visits_90d_sent": visits_90d,
        "downloads_3y_sent": downloads_3y if download_urls else 0,
        "downloads_90d_sent": downloads_90d if download_urls else 0,
        "dry_run": False,
    }


def generate_bulk_traffic(
    visits_3y=25,
    visits_90d=10,
    downloads_3y=10,
    downloads_90d=5,
    dataset_refs=None,
    limit=None,
    offset=None,
    dry_run=False,
):
    """Generate fake traffic for every active dataset of every supported type.

    ``dataset_refs`` can be a list of names/ids to restrict which datasets are
    targeted.  Omit it (or pass ``None``) to target all supported datasets.
    ``limit`` / ``offset`` work the same way as in sync_usage_data.
    """
    packages = _active_packages(
        dataset_refs=dataset_refs,
        limit=limit,
        offset=offset,
    )
    log.info(
        "generate_bulk_traffic: starting for %s package(s) dry_run=%s",
        len(packages),
        dry_run,
    )

    succeeded = 0
    failed = 0
    skipped = 0
    totals = {
        "visits_3y_sent": 0,
        "visits_90d_sent": 0,
        "downloads_3y_sent": 0,
        "downloads_90d_sent": 0,
    }

    for package in packages:
        download_urls = _dataset_download_urls(package)
        effective_dl_3y = downloads_3y if download_urls else 0
        effective_dl_90d = downloads_90d if download_urls else 0

        if not download_urls and (downloads_3y or downloads_90d):
            log.info(
                "generate_bulk_traffic: package=%s has no resource URLs, "
                "skipping downloads",
                package.name,
            )

        try:
            result = generate_test_traffic(
                dataset_ref=package.name,
                visits_3y=visits_3y,
                visits_90d=visits_90d,
                downloads_3y=effective_dl_3y,
                downloads_90d=effective_dl_90d,
                dry_run=dry_run,
            )
            if effective_dl_3y == 0 and effective_dl_90d == 0 and visits_3y == 0 and visits_90d == 0:
                skipped += 1
            else:
                succeeded += 1
            for key in totals:
                totals[key] += result.get(key, 0)
            log.info(
                "generate_bulk_traffic: package=%s v3y=%s v90d=%s dl3y=%s dl90d=%s",
                package.name,
                result["visits_3y_sent"],
                result["visits_90d_sent"],
                result["downloads_3y_sent"],
                result["downloads_90d_sent"],
            )
        except Exception as exc:
            failed += 1
            log.exception(
                "generate_bulk_traffic: failed for package=%s: %s",
                package.name,
                exc,
            )

    return {
        "total_packages": len(packages),
        "succeeded": succeeded,
        "failed": failed,
        "skipped": skipped,
        "dry_run": dry_run,
        **totals,
    }
