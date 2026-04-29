# encoding: utf-8

import calendar
import datetime
import json
import logging
from sqlalchemy import or_
import http.client
from urllib.parse import urlencode, urlparse

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

    def _http_conn(self):
        parsed = urlparse(self.base_url)
        host = parsed.hostname
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        if parsed.scheme == "https":
            return http.client.HTTPSConnection(host, port, timeout=self.timeout)
        return http.client.HTTPConnection(host, port, timeout=self.timeout)

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
        query = urlencode(params, doseq=True)
        body = urlencode({"token_auth": self.token_auth}).encode("utf-8")
        parsed = urlparse(self.base_url)
        path = parsed.path.rstrip("/") + "/index.php?" + query
        conn = self._http_conn()
        try:
            conn.request(
                "POST", path, body=body,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            resp = conn.getresponse()
            raw = resp.read().decode("utf-8")
        finally:
            conn.close()
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
        parsed = urlparse(self.base_url)
        path = parsed.path.rstrip("/") + "/index.php?" + urlencode(params)
        encoded_body = urlencode(body, doseq=True).encode("utf-8")
        log.debug("Matomo _bulk_call path=%s body_len=%s num_urls=%s", path, len(encoded_body), len(requests_payload))
        conn = self._http_conn()
        try:
            conn.request(
                "POST", path, body=encoded_body,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            resp = conn.getresponse()
            raw = resp.read().decode("utf-8")
        finally:
            conn.close()
        data = json.loads(raw)
        if isinstance(data, dict) and data.get("result") == "error":
            raise toolkit.ValidationError(
                "Matomo API error: {}".format(data.get("message"))
            )
        return data

    def _visits_payload(self, page_url, periods):
        """Build sub-request entries for page visit counts (per dataset URL)."""
        return [
            {
                "module": "API",
                "method": "Actions.getPageUrl",
                "idSite": self.site_id,
                "period": period,
                "date": date_value,
                "pageUrl": page_url,
                "format": "JSON",
            }
            for period, date_value in periods
        ]

    def _downloads_site_payload(self, periods):
        """Build sub-request entries for site-wide download counts (archive-backed)."""
        return [
            {
                "module": "API",
                "method": "Actions.getDownloads",
                "idSite": self.site_id,
                "period": period,
                "date": date_value,
                "format": "JSON",
                "filter_limit": "-1",
                "flat": "1",
            }
            for period, date_value in periods
        ]

    @staticmethod
    def _sum_visits(responses):
        total = 0
        for response in responses:
            if isinstance(response, list) and response:
                response = response[0]
            try:
                total += int(float(response.get("nb_visits", 0)))
            except (AttributeError, TypeError, ValueError):
                continue
        return total

    @staticmethod
    def _build_download_map(responses):
        """Aggregate nb_hits by normalised download URL across all period responses."""
        url_hits = {}
        for response in responses:
            rows = response if isinstance(response, list) else []
            for row in rows:
                if not isinstance(row, dict):
                    continue
                raw_url = row.get("Actions_DownloadUrl") or row.get("label") or ""
                if not raw_url or row.get("is_summary"):
                    continue
                # Normalise: strip scheme, lowercase, no trailing slash
                parsed = urlparse(raw_url if "://" in raw_url else "http://" + raw_url)
                key = (parsed.netloc.lower() + parsed.path).rstrip("/")
                hits = 0
                try:
                    hits = int(float(row.get("nb_hits", 0)))
                except (TypeError, ValueError):
                    pass
                url_hits[key] = url_hits.get(key, 0) + hits
        return url_hits

    def prefetch_downloads(self, periods):
        """Fetch site-wide download counts for all periods in one bulk request.
        Returns a dict mapping normalised URL path to total hit count."""
        payload = self._downloads_site_payload(periods)
        if not payload:
            return {}
        responses = self._bulk_call(payload)
        return self._build_download_map(responses)

    def fetch_page_visits(self, page_url, periods_3y, periods_90d):
        """Fetch page visit counts for both time windows in one request."""
        v3y = self._visits_payload(page_url, periods_3y)
        v90 = self._visits_payload(page_url, periods_90d)
        split = len(v3y)
        combined = v3y + v90
        if not combined:
            return 0, 0
        responses = self._bulk_call(combined)
        visits_3y = self._sum_visits(responses[:split])
        visits_90d = self._sum_visits(responses[split:])
        return visits_3y, visits_90d

    def fetch_page_visits_multilang(self, page_urls, periods_3y, periods_90d):
        """Fetch page visit counts for multiple language URLs combined.

        Args:
            page_urls: List of URLs (e.g., English and French versions)
            periods_3y: Period chunks for 3-year window
            periods_90d: Period chunks for 90-day window

        Returns:
            Tuple of (visits_3y, visits_90d) summed across all URLs
        """
        if not page_urls:
            return 0, 0

        all_payloads_3y = []
        all_payloads_90d = []

        for url in page_urls:
            all_payloads_3y.extend(self._visits_payload(url, periods_3y))
            all_payloads_90d.extend(self._visits_payload(url, periods_90d))

        split = len(all_payloads_3y)
        combined = all_payloads_3y + all_payloads_90d

        if not combined:
            return 0, 0

        responses = self._bulk_call(combined)
        visits_3y = self._sum_visits(responses[:split])
        visits_90d = self._sum_visits(responses[split:])
        return visits_3y, visits_90d


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


def _sum_downloads_from_map(download_map, candidate_urls, package_id):
    """Sum download hits for a dataset's resource URLs from a pre-fetched site-wide map.

    Uploaded files: match any map key that contains the package resource path prefix.
    External URLs: match by normalised URL.
    """
    package_prefix = "/data/{}/resource/".format(package_id)
    total = 0
    for url in candidate_urls:
        if not url:
            continue
        if package_prefix in url:
            # Uploaded file — sum all download URLs that belong to this package
            for key, hits in download_map.items():
                if package_prefix in key:
                    total += hits
            # Only count prefix once even if multiple resources share the package path
            break
        else:
            parsed = urlparse(url if "://" in url else "http://" + url)
            key = (parsed.netloc.lower() + parsed.path).rstrip("/")
            total += download_map.get(key, 0)
    return total


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
    """Get the primary (English) dataset URL using the correct package type."""
    site_url = toolkit.config.get("ckan.site_url", "").rstrip("/")
    dataset_type = (package.type or "dataset").strip("/")
    if site_url:
        return "{}/{}/{}".format(site_url, dataset_type, package.name)
    return "/{}/{}".format(dataset_type, package.name)


def _dataset_urls_multilang(package):
    """Get all language-variant URLs for a dataset (English + French).

    Returns a list of URLs to query for visit statistics, combining:
    - English URL: /{type}/{name}
    - French URL: /fr/{type}/{name}
    """
    site_url = toolkit.config.get("ckan.site_url", "").rstrip("/")
    dataset_type = (package.type or "dataset").strip("/")

    urls = []

    # English URL
    if site_url:
        urls.append("{}/{}/{}".format(site_url, dataset_type, package.name))
    else:
        urls.append("/{}/{}".format(dataset_type, package.name))

    # French URL
    if site_url:
        url_fr = "{}/fr/{}/{}".format(site_url, dataset_type, package.name)
        urls.append(url_fr)
    else:
        urls.append("/fr/{}/{}".format(dataset_type, package.name))

    return urls


def _dataset_download_urls(package):
    site_url = toolkit.config.get("ckan.site_url", "").rstrip("/")
    urls = []
    for resource in package.resources:
        if resource.state != "active":
            continue
        if not resource.url:
            continue
        extras = getattr(resource, "extras", None) or {}
        if isinstance(extras, dict) and "downloadall_datapackage_hash" in extras:
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

    client = MatomoClient()

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

    # Pre-fetch site-wide download counts once for each time window.
    # Actions.getDownloads reads from Matomo archives (fast) instead of
    # scanning raw logs per dataset (slow segment queries).
    periods_3y = _period_chunks(three_year_start, end_date)
    periods_90d = _period_chunks(last_90_start, end_date)
    log.info("Matomo sync prefetching downloads: 3y=%s periods, 90d=%s periods",
             len(periods_3y), len(periods_90d))
    download_map_3y = client.prefetch_downloads(periods_3y)
    download_map_90d = client.prefetch_downloads(periods_90d)
    log.info("Matomo sync download maps: 3y=%s urls, 90d=%s urls",
             len(download_map_3y), len(download_map_90d))

    for package in packages:
        processed += 1
        try:
            with model.Session.begin_nested():
                page_urls = _dataset_urls_multilang(package)
                download_urls = _dataset_download_urls(package)

                visits, visit_90_days = client.fetch_page_visits_multilang(
                    page_urls, periods_3y, periods_90d
                )
                downloads = _sum_downloads_from_map(
                    download_map_3y, download_urls, package.id
                )
                download_90_days = _sum_downloads_from_map(
                    download_map_90d, download_urls, package.id
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
