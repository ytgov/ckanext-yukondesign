# encoding: utf-8

import datetime
import json
import logging
import random
import time
import calendar
from sqlalchemy import or_
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

import ckan.model as model
import ckan.plugins.toolkit as toolkit


log = logging.getLogger(__name__)

SUPPORTED_TYPES = ["data", "information", "access-requests", "pia-summaries"]
USAGE_EXTRA_KEYS = ["visits", "downloads", "visit_90_days", "download_90_days"]


class MatomoClient(object):
    def __init__(self):
        self.base_url = toolkit.config.get(
            "ckanext.yukondesign.matomo.api_url", ""
        ).strip()
        self.site_id = toolkit.config.get(
            "ckanext.yukondesign.matomo.site_id", ""
        ).strip()
        self.token_auth = toolkit.config.get(
            "ckanext.yukondesign.matomo.token_auth", ""
        ).strip()
        self.timeout = int(
            toolkit.config.get(
                "ckanext.yukondesign.matomo.timeout_seconds", 20
            )
        )
        self.start_date = toolkit.config.get(
            "ckanext.yukondesign.matomo.start_date", "2000-01-01"
        )

        if not self.base_url:
            raise toolkit.ValidationError(
                "Missing config: ckanext.yukondesign.matomo.api_url"
            )
        if not self.site_id:
            raise toolkit.ValidationError(
                "Missing config: ckanext.yukondesign.matomo.site_id"
            )
        if not self.token_auth:
            raise toolkit.ValidationError(
                "Missing config: ckanext.yukondesign.matomo.token_auth"
            )

        self.base_url = self.base_url.rstrip("/")
        self.tracking_url = "{}/matomo.php".format(self.base_url)

    def _call(self, method, extra_params):
        params = {
            "module": "API",
            "method": method,
            "idSite": self.site_id,
            "format": "JSON",
            "filter_limit": -1,
            "flat": 1,
        }
        params.update(extra_params)
        body = urlencode({"token_auth": self.token_auth}).encode("utf-8")
        query = urlencode(params, doseq=True)
        url = "{}/index.php?{}".format(self.base_url, query)
        request = Request(url, data=body)

        with urlopen(request, timeout=self.timeout) as response:
            raw = response.read().decode("utf-8")
        data = json.loads(raw)
        if isinstance(data, dict) and data.get("result") == "error":
            raise toolkit.ValidationError(
                "Matomo API error: {}".format(data.get("message"))
            )
        return data

    def _bulk_call(self, requests_payload):
        params = {
            "module": "API",
            "method": "API.getBulkRequest",
            "format": "JSON",
        }
        body = {"token_auth": self.token_auth}
        for idx, request_payload in enumerate(requests_payload):
            query = urlencode(request_payload, doseq=True)
            body["urls[{}]".format(idx)] = "?{}".format(query)

        url = "{}/index.php?{}".format(self.base_url, urlencode(params))
        request = Request(url, data=urlencode(body, doseq=True).encode("utf-8"))

        with urlopen(request, timeout=self.timeout) as response:
            raw = response.read().decode("utf-8")
        data = json.loads(raw)
        if isinstance(data, dict) and data.get("result") == "error":
            raise toolkit.ValidationError(
                "Matomo API error: {}".format(data.get("message"))
            )
        return data


class MatomoTrackingClient(MatomoClient):
    def _track(self, payload):
        params = {
            "idsite": self.site_id,
            "rec": 1,
            "apiv": 1,
            "rand": random.randint(1, 10**9),
            "token_auth": self.token_auth,
        }
        params.update(payload)
        query = urlencode(params, doseq=True)
        url = "{}?{}".format(self.tracking_url, query)
        req = Request(
            url,
            headers={"User-Agent": "ckan-yukon-test-traffic/1.0"},
        )

        with urlopen(req, timeout=self.timeout) as response:
            response.read()

    def track_pageview(self, page_url, visitor_id):
        self._track(
            {
                "url": page_url,
                "action_name": "Dataset Page View",
                "_id": visitor_id,
            }
        )

    def track_download(self, page_url, download_url, visitor_id):
        self._track(
            {
                "download": download_url,
                "_id": visitor_id,
            }
        )

    def page_visits_for_periods(self, page_url, periods):
        requests_payload = []
        for period, date_value in periods:
            requests_payload.append(
                {
                    "module": "API",
                    "method": "Actions.getPageUrl",
                    "idSite": self.site_id,
                    "period": period,
                    "date": date_value,
                    "pageUrl": page_url,
                    "format": "JSON",
                }
            )

        responses = self._bulk_call(requests_payload)
        total = 0
        for response in responses:
            if isinstance(response, list) and response:
                response = response[0]
            try:
                total += int(float(response.get("nb_visits", 0)))
            except (AttributeError, TypeError, ValueError):
                continue
        return total

    def downloads_for_periods(self, package, candidate_urls, periods):
        package_prefix = "/data/{}/resource/".format(package.id)
        uploaded_urls = []
        external_urls = []

        for candidate_url in candidate_urls:
            if not candidate_url:
                continue
            if package_prefix in candidate_url:
                uploaded_urls.append(candidate_url)
            else:
                external_urls.append(candidate_url)

        requests_payload = []
        if uploaded_urls:
            for period, date_value in periods:
                requests_payload.append(
                    {
                        "module": "API",
                        "method": "API.get",
                        "idSite": self.site_id,
                        "period": period,
                        "date": date_value,
                        "segment": "actionType==downloads;actionUrl=@{}".format(
                            package_prefix
                        ),
                        "format": "JSON",
                    }
                )

        for candidate_url in external_urls:
            for period, date_value in periods:
                requests_payload.append(
                    {
                        "module": "API",
                        "method": "API.get",
                        "idSite": self.site_id,
                        "period": period,
                        "date": date_value,
                        "segment": "actionType==downloads;actionUrl=={}".format(
                            candidate_url
                        ),
                        "format": "JSON",
                    }
                )

        if not requests_payload:
            return 0

        responses = self._bulk_call(requests_payload)
        total = 0
        for response in responses:
            if isinstance(response, list) and response:
                response = response[0]
            try:
                total += int(float(response.get("nb_downloads", 0)))
            except (AttributeError, TypeError, ValueError):
                continue
        return total


def _iter_records(payload):
    if isinstance(payload, list):
        for row in payload:
            if isinstance(row, dict):
                yield row
    elif isinstance(payload, dict):
        for value in payload.values():
            if isinstance(value, list):
                for row in value:
                    if isinstance(row, dict):
                        yield row


def _normalize_url(value):
    if not value:
        return ""
    parsed = urlparse(value)
    path = parsed.path.rstrip("/") if parsed.path else ""
    if parsed.netloc:
        return "{}{}".format(parsed.netloc.lower(), path)
    return value.rstrip("/").lower()


def _shift_months(value, months):
    month_index = (value.month - 1) + months
    year = value.year + (month_index // 12)
    month = (month_index % 12) + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return datetime.date(year, month, day)


def _shift_years(value, years):
    year = value.year + years
    day = min(value.day, calendar.monthrange(year, value.month)[1])
    return datetime.date(year, value.month, day)


def _period_chunks(start_date, end_date):
    chunks = []
    current = start_date

    while current <= end_date:
        if (
            current.day == 1
            and current.month == 1
            and datetime.date(current.year, 12, 31) <= end_date
        ):
            chunks.append(("year", str(current.year)))
            current = datetime.date(current.year + 1, 1, 1)
            continue

        last_day_of_month = calendar.monthrange(current.year, current.month)[1]
        month_end = datetime.date(current.year, current.month, last_day_of_month)
        if current.day == 1 and month_end <= end_date:
            chunks.append(("month", "{:04d}-{:02d}".format(current.year, current.month)))
            if current.month == 12:
                current = datetime.date(current.year + 1, 1, 1)
            else:
                current = datetime.date(current.year, current.month + 1, 1)
            continue

        range_end = min(month_end, end_date)
        chunks.append(
            (
                "range",
                "{},{}".format(current.isoformat(), range_end.isoformat()),
            )
        )
        current = range_end + datetime.timedelta(days=1)
    return chunks


def _sum_metric_for_urls(records, candidate_urls, metric_keys):
    candidates = set()
    for url in candidate_urls:
        if not url:
            continue
        normalized = _normalize_url(url)
        if normalized:
            candidates.add(normalized)

    total = 0
    for row in _iter_records(records):
        row_urls = []
        for value in (row.get("label"), row.get("url")):
            normalized_value = _normalize_url(value)
            if normalized_value:
                row_urls.append(normalized_value)

        if not row_urls:
            continue

        if any(
            row_url in candidates
            or any(c in row_url or row_url in c for c in candidates)
            for row_url in row_urls
        ):
            for metric_key in metric_keys:
                value = row.get(metric_key)
                if value is None:
                    continue
                try:
                    total += int(float(value))
                except (TypeError, ValueError):
                    continue
                break
    return total


def _dataset_url(package):
    site_url = toolkit.config.get("ckan.site_url", "").rstrip("/")
    if site_url:
        return "{}/dataset/{}".format(site_url, package.name)
    return "/dataset/{}".format(package.name)


def _dataset_download_urls(package):
    site_url = toolkit.config.get("ckan.site_url", "").rstrip("/")
    urls = []
    for resource in package.resources:
        if resource.state != "active":
            continue
        if not resource.url:
            continue

        resource_url = resource.url
        parsed = urlparse(resource_url)
        if parsed.scheme and parsed.netloc:
            urls.append(resource_url)
            continue

        if getattr(resource, "url_type", "") == "upload" and site_url:
            urls.append(
                "{}/data/{}/resource/{}/download/{}".format(
                    site_url,
                    package.id,
                    resource.id,
                    resource_url.lstrip("/"),
                )
            )
            continue

        urls.append(resource_url)
    return urls


def _get_package_by_ref(dataset_ref):
    package = model.Package.get(dataset_ref)
    if package and package.state == "active":
        return package

    package = (
        model.Session.query(model.Package)
        .filter_by(name=dataset_ref, state="active")
        .first()
    )
    if package:
        return package

    raise toolkit.ObjectNotFound("Dataset not found: {}".format(dataset_ref))


def _random_visitor_id():
    alphabet = "0123456789abcdef"
    return "".join(random.choice(alphabet) for _ in range(16))


def generate_test_traffic(
    dataset_ref,
    visits=25,
    downloads=10,
    sleep_ms=0,
    visitor_id=None,
    dry_run=False,
):
    if visits < 0 or downloads < 0:
        raise toolkit.ValidationError("visits/downloads must be >= 0")
    if sleep_ms < 0:
        raise toolkit.ValidationError("sleep_ms must be >= 0")

    package = _get_package_by_ref(dataset_ref)
    page_url = _dataset_url(package)
    download_urls = _dataset_download_urls(package)

    if downloads > 0 and not download_urls:
        raise toolkit.ValidationError(
            "Dataset has no active resource URLs to count as downloads"
        )

    visitor_id = visitor_id or _random_visitor_id()

    if dry_run:
        return {
            "dataset": package.name,
            "visitor_id": visitor_id,
            "page_url": page_url,
            "downloads_targeted": downloads,
            "visits_targeted": visits,
            "downloads_sent": 0,
            "visits_sent": 0,
            "dry_run": True,
        }

    client = MatomoTrackingClient()

    visits_sent = 0
    downloads_sent = 0

    for _ in range(visits):
        client.track_pageview(page_url, visitor_id)
        visits_sent += 1
        if sleep_ms:
            time.sleep(float(sleep_ms) / 1000.0)

    for idx in range(downloads):
        download_url = download_urls[idx % len(download_urls)]
        client.track_download(page_url, download_url, visitor_id)
        downloads_sent += 1
        if sleep_ms:
            time.sleep(float(sleep_ms) / 1000.0)

    return {
        "dataset": package.name,
        "visitor_id": visitor_id,
        "page_url": page_url,
        "downloads_targeted": downloads,
        "visits_targeted": visits,
        "downloads_sent": downloads_sent,
        "visits_sent": visits_sent,
        "dry_run": False,
    }


def _upsert_extra(package_id, key, value):
    existing = (
        model.Session.query(model.PackageExtra)
        .filter_by(package_id=package_id, key=key)
        .first()
    )
    value = str(value)
    if existing:
        if existing.value != value:
            existing.value = value
            return True
        return False

    model.Session.add(
        model.PackageExtra(package_id=package_id, key=key, value=value)
    )
    return True


def _active_packages_query(dataset_refs=None):
    query = model.Session.query(model.Package).filter(
        model.Package.state == "active",
        model.Package.type.in_(SUPPORTED_TYPES),
    )
    if dataset_refs:
        query = query.filter(
            or_(
                model.Package.name.in_(dataset_refs),
                model.Package.id.in_(dataset_refs),
            )
        )
    query = query.order_by(model.Package.metadata_created.desc())
    return query


def _active_packages(dataset_refs=None, limit=None, offset=None):
    query = _active_packages_query(dataset_refs=dataset_refs)
    if offset:
        query = query.offset(offset)
    if limit:
        query = query.limit(limit)
    return query.all()


def sync_usage_data(dry_run=False, limit=None, offset=None, dataset_refs=None):
    if limit is not None and limit < 1:
        raise toolkit.ValidationError("--limit must be greater than 0")
    if offset is not None and offset < 0:
        raise toolkit.ValidationError("--offset must be greater than or equal to 0")

    client = MatomoTrackingClient()

    today = datetime.date.today()
    end_date = today - datetime.timedelta(days=1)
    last_90_start = end_date - datetime.timedelta(days=89)
    three_year_start = _shift_years(end_date, -3) + datetime.timedelta(days=1)

    processed = 0
    updated = 0
    skipped = 0
    failed = 0

    base_query = _active_packages_query(dataset_refs=dataset_refs)
    total = base_query.count()
    packages = _active_packages(
        dataset_refs=dataset_refs,
        limit=limit,
        offset=offset,
    )
    log.info("Matomo sync starting for %s package(s)", len(packages))

    for package in packages:
        processed += 1
        try:
            with model.Session.begin_nested():
                page_url = _dataset_url(package)
                download_urls = _dataset_download_urls(package)

                visits = client.page_visits_for_periods(
                    page_url, _period_chunks(three_year_start, end_date)
                )
                downloads = client.downloads_for_periods(
                    package,
                    download_urls,
                    _period_chunks(three_year_start, end_date),
                )
                visit_90_days = client.page_visits_for_periods(
                    page_url, _period_chunks(last_90_start, end_date)
                )
                download_90_days = client.downloads_for_periods(
                    package,
                    download_urls,
                    _period_chunks(last_90_start, end_date),
                )

                payload = {
                    "visits": visits,
                    "downloads": downloads,
                    "visit_90_days": visit_90_days,
                    "download_90_days": download_90_days,
                }

                package_changed = False
                for key in USAGE_EXTRA_KEYS:
                    if _upsert_extra(package.id, key, payload[key]):
                        package_changed = True

            if package_changed:
                updated += 1
            else:
                skipped += 1

            log.info(
                "Matomo sync package=%s changed=%s payload=%s",
                package.name,
                package_changed,
                payload,
            )
        except Exception as exc:
            failed += 1
            # Ensure any in-flight statement state is cleared before next pkg.
            model.Session.rollback()
            log.exception(
                "Matomo sync failed for package=%s: %s", package.name, exc
            )

    if dry_run:
        model.Session.rollback()
    else:
        model.repo.commit()

    offset = offset or 0
    next_offset = offset + processed
    has_more = next_offset < total

    return {
        "processed": processed,
        "updated": updated,
        "skipped": skipped,
        "failed": failed,
        "dry_run": dry_run,
        "offset": offset,
        "total": total,
        "has_more": has_more,
        "next_offset": next_offset if has_more else None,
    }
