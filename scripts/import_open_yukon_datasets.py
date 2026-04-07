#!/usr/bin/env python3
# encoding: utf-8

import copy
import json
import mimetypes
import os
import tempfile
import time
from pathlib import Path
from urllib.parse import quote_plus

import click
import requests


SOURCE_CKAN_URL = "https://open.yukon.ca"
SUPPORTED_TYPES = ["data", "information", "access-requests", "pia-summaries"]
USER_AGENT = "yukon-dataset-importer/1.0"
DEFAULT_LICENSE = "OGL-Yukon-2.0"
DEFAULT_MAX_RESOURCE_BYTES = 5 * 1024 * 1024


def _session(api_token=None):
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    if api_token:
        session.headers["Authorization"] = api_token
    return session


def _ckan_action_get(session, base_url, action, **params):
    response = session.get(
        f"{base_url}/api/3/action/{action}",
        params=params,
        timeout=120,
    )
    response.raise_for_status()
    payload = response.json()
    if not payload.get("success"):
        raise click.ClickException(
            f"CKAN action {action} failed: {json.dumps(payload, indent=2)}"
        )
    return payload["result"]


def _ckan_action_post(session, base_url, action, data=None, files=None):
    response = session.post(
        f"{base_url}/api/3/action/{action}",
        data=data,
        files=files,
        timeout=300,
    )
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        if response.status_code == 409:
            raise click.ClickException(
                f"CKAN action {action} conflict: {response.text}"
            )
        raise exc
    payload = response.json()
    if not payload.get("success"):
        raise click.ClickException(
            f"CKAN action {action} failed: {json.dumps(payload, indent=2)}"
        )
    return payload["result"]


def _fetch_packages_by_type(session, dataset_type, limit):
    results = []
    start = 0
    rows = min(limit, 100)
    while len(results) < limit:
        page = _ckan_action_get(
            session,
            SOURCE_CKAN_URL,
            "package_search",
            fq=f"type:{dataset_type}",
            rows=rows,
            start=start,
        )
        items = page.get("results", [])
        if not items:
            break
        results.extend(items)
        start += len(items)
        if start >= page.get("count", 0):
            break
    return results[:limit]


def _fetch_package(session, dataset_id):
    return _ckan_action_get(
        session, SOURCE_CKAN_URL, "package_show", id=dataset_id
    )


def _safe_name(value, fallback):
    value = (value or fallback or "item").strip().lower()
    chars = []
    for char in value:
        if char.isalnum() or char in "-_":
            chars.append(char)
        elif char in " /.":
            chars.append("-")
    cleaned = "".join(chars).strip("-")
    return cleaned or fallback


def _imported_name(package):
    return f"import-{package['type']}-{_safe_name(package.get('name'), package['id'])}"[:100]


def _organization_payload(source_package, source_org):
    org_name = _safe_name(source_org.get("name"), source_org.get("id"))
    return {
        "name": org_name,
        "title": source_org.get("title") or source_org.get("display_name") or org_name,
        "description": source_org.get("description") or "",
        "image_url": source_org.get("image_display_url") or "",
    }


def _target_package_by_name(target_session, target_url, package_name):
    try:
        return _ckan_action_get(
            target_session, target_url, "package_show", id=package_name
        )
    except Exception:
        return None


def _ensure_org(target_session, target_url, source_package, source_session):
    owner_org = source_package.get("owner_org")
    if not owner_org:
        raise click.ClickException(
            f"Package {source_package['name']} has no owner_org"
        )
    source_org = _ckan_action_get(
        source_session, SOURCE_CKAN_URL, "organization_show", id=owner_org
    )
    payload = _organization_payload(source_package, source_org)
    try:
        existing = _ckan_action_get(
            target_session, target_url, "organization_show", id=payload["name"]
        )
        return existing["id"]
    except Exception:
        created = _ckan_action_post(
            target_session, target_url, "organization_create", data=payload
        )
        return created["id"]


def _package_payload(source_package, owner_org_id):
    dataset_type = source_package["type"]
    payload = {
        "type": dataset_type,
        "name": _imported_name(source_package),
        "title": source_package.get("title") or source_package["name"],
        "notes": source_package.get("notes") or "Imported from open.yukon.ca for local testing.",
        "owner_org": owner_org_id,
        "license_id": source_package.get("license_id") or DEFAULT_LICENSE,
        "language": source_package.get("language") or "english",
        "tag_string": ", ".join(tag["name"] for tag in source_package.get("tags", [])),
        "date_published": source_package.get("date_published") or "",
        "date_updated": source_package.get("date_updated") or "",
        "internal_notes": "Imported from open.yukon.ca for local testing.",
    }

    if dataset_type in ("data", "information"):
        payload["internal_contact_name"] = (
            source_package.get("internal_contact_name")
            or source_package.get("author")
            or "Imported Test Contact"
        )
        payload["internal_contact_email"] = (
            source_package.get("internal_contact_email")
            or source_package.get("maintainer_email")
            or "imported@example.com"
        )

    if dataset_type == "data":
        for key in [
            "methodology",
            "changelog",
            "data_dictionary",
            "data_standard",
            "author",
            "custodian",
            "custodian_email",
            "homepage_url",
            "more_info",
            "location",
        ]:
            if key in source_package and source_package.get(key) is not None:
                payload[key] = source_package.get(key)

    if dataset_type == "information":
        for key in [
            "author",
            "custodian",
            "custodian_email",
            "homepage_url",
            "publication_required_under_atipp_act",
            "publication_type_under_atipp_act",
        ]:
            if key in source_package and source_package.get(key) is not None:
                payload[key] = source_package.get(key)

    if dataset_type == "access-requests":
        payload["date_of_request"] = source_package.get("date_of_request") or source_package.get("date_published") or "2024-01-01"
        payload["file_id"] = source_package.get("file_id") or f"import-{source_package['id'][:8]}"
        payload["response_type"] = source_package.get("response_type") or "not_specified"
        if source_package.get("fees") is not None:
            payload["fees"] = source_package.get("fees")

    if dataset_type == "pia-summaries":
        payload["privacy_impact_assessment_number"] = (
            source_package.get("privacy_impact_assessment_number")
            or f"import-{source_package['id'][:8]}"
        )
        payload["date_of_approval"] = (
            source_package.get("date_of_approval")
            or source_package.get("date_published")
            or "2024-01-01"
        )

    return payload


def _uploaded_resources(source_package):
    uploaded = []
    for resource in source_package.get("resources", []):
        if resource.get("state") != "active":
            continue
        if resource.get("url_type") != "upload":
            continue
        uploaded.append(resource)
    return uploaded


def _resource_size_bytes(resource):
    for key in ("size", "resource_size", "filesize"):
        value = resource.get(key)
        if value in (None, ""):
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return None


def _resource_download_url(resource):
    resource_url = resource.get("url")
    if not resource_url:
        return None
    if resource_url.startswith("http://") or resource_url.startswith("https://"):
        return resource_url
    return f"{SOURCE_CKAN_URL}{resource_url}"


def _download_resource(session, resource, temp_dir):
    resource_url = _resource_download_url(resource)
    if not resource_url:
        return None
    filename = resource.get("url") or resource.get("name") or resource["id"]
    filename = os.path.basename(filename) or resource["id"]
    file_path = Path(temp_dir) / filename
    with session.get(resource_url, stream=True, timeout=300) as response:
        response.raise_for_status()
        with open(file_path, "wb") as output:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    output.write(chunk)
    return file_path


def _create_resource(target_session, target_url, package_id, resource, file_path):
    filename = file_path.name
    content_type = resource.get("mimetype") or mimetypes.guess_type(filename)[0] or "application/octet-stream"
    data = {
        "package_id": package_id,
        "name": resource.get("name") or filename,
        "description": resource.get("description") or "",
        "format": resource.get("format") or "",
    }
    with open(file_path, "rb") as handle:
        files = {"upload": (filename, handle, content_type)}
        return _ckan_action_post(
            target_session,
            target_url,
            "resource_create",
            data=data,
            files=files,
        )


def _resource_exists(target_package, resource):
    source_name = (resource.get("name") or "").strip().lower()
    source_description = (resource.get("description") or "").strip()
    source_format = (resource.get("format") or "").strip().lower()
    source_filename = os.path.basename(resource.get("url") or "").strip().lower()

    for existing in target_package.get("resources", []):
        existing_name = (existing.get("name") or "").strip().lower()
        existing_description = (existing.get("description") or "").strip()
        existing_format = (existing.get("format") or "").strip().lower()
        existing_filename = os.path.basename(existing.get("url") or "").strip().lower()

        if (
            source_filename
            and source_filename == existing_filename
            and source_name
            and source_name == existing_name
        ):
            return True
        if (
            source_name
            and source_name == existing_name
            and source_format
            and source_format == existing_format
            and source_description == existing_description
        ):
            return True
    return False


@click.command()
@click.option(
    "--target-url",
    required=True,
    help="Local CKAN base URL, e.g. http://localhost:5000",
)
@click.option(
    "--target-api-token",
    required=True,
    help="API token for the local target CKAN sysadmin.",
)
@click.option(
    "--per-type",
    type=int,
    default=50,
    show_default=True,
    help="How many datasets to import for each Yukon dataset type.",
)
@click.option(
    "--dataset-type",
    "dataset_types",
    multiple=True,
    type=click.Choice(SUPPORTED_TYPES),
    help="Restrict import to specific dataset types.",
)
@click.option(
    "--sleep-seconds",
    type=float,
    default=0.0,
    show_default=True,
    help="Optional delay between dataset imports.",
)
@click.option(
    "--max-resource-mb",
    type=float,
    default=5.0,
    show_default=True,
    help="Skip uploaded resources larger than this size in megabytes.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Show what would be imported without creating datasets.",
)
def main(
    target_url,
    target_api_token,
    per_type,
    dataset_types,
    sleep_seconds,
    max_resource_mb,
    dry_run,
):
    """Import Yukon datasets with uploaded resources into a local CKAN."""
    target_url = target_url.rstrip("/")
    source_session = _session()
    target_session = _session(target_api_token)
    selected_types = list(dataset_types) or SUPPORTED_TYPES

    totals = {
        "datasets_created": 0,
        "resources_uploaded": 0,
        "datasets_skipped": 0,
    }
    max_resource_bytes = int(max_resource_mb * 1024 * 1024)

    with tempfile.TemporaryDirectory(prefix="yukon-import-") as temp_dir:
        for dataset_type in selected_types:
            packages = _fetch_packages_by_type(source_session, dataset_type, per_type)
            click.echo(f"type={dataset_type} selected={len(packages)}")
            for package_stub in packages:
                source_package = _fetch_package(source_session, package_stub["id"])
                resources = _uploaded_resources(source_package)

                owner_org_id = _ensure_org(
                    target_session, target_url, source_package, source_session
                )
                package_payload = _package_payload(source_package, owner_org_id)

                if dry_run:
                    click.echo(
                        f"dry-run dataset={package_payload['name']} "
                        f"type={dataset_type} resources={len(resources)}"
                    )
                    continue

                existing_package = _target_package_by_name(
                    target_session, target_url, package_payload["name"]
                )
                if existing_package:
                    created = existing_package
                    click.echo(
                        f"reuse dataset={created['name']} type={dataset_type}"
                    )
                else:
                    created = _ckan_action_post(
                        target_session,
                        target_url,
                        "package_create",
                        data=package_payload,
                    )
                    totals["datasets_created"] += 1

                uploaded_count = 0
                for resource in resources:
                    resource_size = _resource_size_bytes(resource)
                    if resource_size is not None and resource_size > max_resource_bytes:
                        click.echo(
                            f"skip resource dataset={created['name']} "
                            f"resource={resource.get('name') or resource.get('id')} "
                            f"reason=size_limit "
                            f"size_bytes={resource_size}"
                        )
                        continue
                    if _resource_exists(created, resource):
                        click.echo(
                            f"skip resource dataset={created['name']} "
                            f"resource={resource.get('name') or resource.get('id')} "
                            f"reason=already_exists"
                        )
                        continue
                    file_path = _download_resource(source_session, resource, temp_dir)
                    if not file_path:
                        continue
                    try:
                        _create_resource(
                            target_session,
                            target_url,
                            created["id"],
                            resource,
                            file_path,
                        )
                    except click.ClickException as exc:
                        if "conflict" in str(exc).lower():
                            click.echo(
                                f"skip resource dataset={created['name']} "
                                f"resource={resource.get('name') or resource.get('id')} "
                                f"reason=conflict"
                            )
                            created = _ckan_action_get(
                                target_session, target_url, "package_show", id=created["id"]
                            )
                            continue
                        raise
                    uploaded_count += 1
                    totals["resources_uploaded"] += 1
                    created = _ckan_action_get(
                        target_session, target_url, "package_show", id=created["id"]
                    )

                click.echo(
                    f"created dataset={created['name']} type={dataset_type} "
                    f"resources_uploaded={uploaded_count}"
                )
                if not resources:
                    click.echo(
                        f"note dataset={created['name']} reason=no_uploaded_resources"
                    )
                if sleep_seconds:
                    time.sleep(sleep_seconds)

    click.echo(
        "import-complete datasets_created={datasets_created} "
        "resources_uploaded={resources_uploaded} datasets_skipped={datasets_skipped}".format(
            **totals
        )
    )


if __name__ == "__main__":
    main()
