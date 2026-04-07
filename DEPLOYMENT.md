Deployment documentation
=======================

## Requirements

1. `ckanext-scheming` must be installed and configured. This extension is used to create custom datasets and resource schemas.
2. `ckanext-downloadall` must be installed and enabled. Yukon Design templates call `downloadall` helpers to render the dataset download-all UI, and the extension also provides the background zip-generation workflow.

## Install `ckanext-downloadall`

> **Important:** Deploy `ckanext-downloadall` from the `yukon-2.11.0` branch, not from PyPI. The Yukon-specific branch contains fixes and customisations required by this extension.

Activate the CKAN virtual environment and install the extension from the correct branch:

```bash
. /usr/lib/ckan/default/bin/activate
pip install git+https://github.com/datopian/ckanext-downloadall.git@yukon-2.11.0
```

If you are deploying from a checked-out source tree, check out the correct branch and install in development mode:

```bash
git clone https://github.com/datopian/ckanext-downloadall.git
cd ckanext-downloadall
git checkout yukon-2.11.0
pip install -e .
```

## Configuration settings

We need to setup the following configuration settings in the CKAN configuration file (`/etc/ckan/default/ckan.ini`), or in the environment variables:

```env
# Plugin order is very important
ckan.plugins = downloadall yukondesign activity scheming_datasets envvars
ckan.auth.anon_create_dataset = false
ckan.auth.create_unowned_dataset = false
ckan.auth.allow_dataset_collaborators = true
ckan.auth.allow_admin_collaborators = true
ckan.licenses_group_url = file:///srv/app/src/ckanext-yukondesign/licenses-yukon.json
ckan.dataset.create_on_ui_requires_resources = false
# Put Matomo siteid here (4 is used for the Datopian test environment)
ckan.locale_default = en
ckan.locales_offered = en fr
ckan.scheming.dataset_schemas = ckanext.yukondesign:data_schema.yaml ckanext.yukondesign:information_schema.yaml ckanext.yukondesign:access-requests_schema.yaml ckanext.yukondesign:pia-summaries_schema.yaml

# Matomo usage-data sync settings
ckanext.yukondesign.matomo.api_url = http://matomo:80
ckanext.yukondesign.matomo.site_id = 1
ckanext.yukondesign.matomo.token_auth = <matomo-api-token>
ckanext.yukondesign.matomo.timeout_seconds = 20
# Maximum `limit` allowed via the API action. Set to 0 (or omit) for no limit.
ckanext.yukondesign.matomo.api_sync_max_limit = 0

# Download-all settings
ckanext.downloadall.max_resource_size = 104857600
ckanext.downloadall.include_external_resources = false
```

Optional `downloadall` setting:

```env
# Include extra dataset fields in datapackage.json
ckanext.downloadall.dataset_fields_to_add_to_datapackage = field_a field_b
```

License file is provided in the `licenses-yukon.json` file in the repository. You can change the path to the file if needed.

`ckanext-downloadall` also requires the CKAN background jobs worker to be running, because zip files are generated asynchronously whenever datasets or resources change.

## Restart after enabling `downloadall`

After installation or configuration changes:

1. Restart the CKAN worker process.
2. Restart the CKAN web process.
3. Confirm the background jobs worker is running.

Without the worker, the "Download all" button may appear but the zip file will not be generated or refreshed.

## `downloadall` CLI commands

The extension provides a CLI for manual zip generation and backfilling:

```bash
downloadall --help
```

Generate or refresh the zip for a single dataset:

```bash
downloadall -c /etc/ckan/default/ckan.ini update-zip <dataset-name-or-id>
```

Generate or refresh zips for all datasets:

```bash
downloadall -c /etc/ckan/default/ckan.ini update-all-zips
```

If you need to run the job synchronously from the command line, use:

```bash
downloadall -c /etc/ckan/default/ckan.ini update-all-zips --synchronous
```

When running synchronous updates against uploaded files, run the command as the same OS user that owns the CKAN file storage if required by your deployment permissions.

## Views sync command

This extension provides a CLI group to sync Matomo analytics into the schema
fields under the `usage_data` group.

```bash
ckan -c /etc/ckan/default/ckan.ini yukon-matomo sync-usage-data
```

Useful flags:

- `--dry-run`: fetch and calculate values but rollback DB changes
- `--limit N`: process only N datasets
- `--offset N`: skip the first N matching datasets before processing
- `--dataset-ref <name-or-id>`: sync only specific datasets (repeatable)

Low-impact operation guidance:

- Prefer scheduled syncs over on-demand refreshes from the web UI.
- Run the sync nightly or a few times per day, not continuously.
- Prefer `--dataset-ref` for one-off backfills or targeted fixes.
- If you run broader syncs, keep `--limit` small and batch them.
- Use `--offset` with `--limit` to page through the catalog in multiple calls.
- Avoid parallel sync jobs against the same Matomo instance.
- If Matomo becomes slow or returns errors, let the run fail and retry later instead of aggressively retrying.
- The current windows are:
  - `Visits` / `Downloads`: last 3 years
  - `Visits (last 90 days)` / `Downloads (last 90 days)`: last 90 days
- Windows end at yesterday, not today, to avoid partial-day counts.
- Long-range queries are split into month/year/range chunks and sent via Matomo Bulk API requests to reduce API overhead.

The sync writes values directly to `PackageExtra` records for:

- `visits`
- `downloads`
- `visit_90_days`
- `download_90_days`

It intentionally avoids `package_update` and `package_patch` so dataset
`metadata_modified` is not changed by analytics refreshes.

## Views sync API action

The same sync can also be triggered through the CKAN Action API:

```bash
curl -X POST "https://<ckan-host>/api/3/action/yukon_matomo_sync_usage_data" \
  -H "Authorization: <sysadmin-api-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "limit": 25,
    "offset": 0,
    "dry_run": false
  }'
```

Useful request fields:

- `dry_run`: same meaning as the CLI flag
- `limit`: maximum number of datasets to process in this call
- `offset`: number of matching datasets to skip before processing
- `dataset_refs`: optional list of dataset names or ids to sync

Important API behavior:

- Only sysadmins can call this action.
- If you do not pass `dataset_refs` or `limit`, the API defaults to `limit=25`.
- The API rejects `limit > 100` to keep calls conservative.
- Responses include `total`, `offset`, `has_more`, and `next_offset` so callers can page through the whole catalog.
- For frequent automation, prefer small batches from a scheduler rather than large ad hoc API calls.

## Generate synthetic traffic for local testing

You can emit fake Matomo events for one dataset and then run the sync command.

```bash
# Send synthetic traffic to Matomo for one dataset
ckan -c /etc/ckan/default/ckan.ini yukon-matomo generate-test-traffic \
	--dataset-ref <dataset-name-or-id> \
	--visits 50 \
	--downloads 20

# Pull those values back into CKAN extras
ckan -c /etc/ckan/default/ckan.ini yukon-matomo sync-usage-data \
	--dataset-ref <dataset-name-or-id>
```

Options for `generate-test-traffic`:

- `--sleep-ms`: small delay between events (useful for low-resource Matomo)
- `--visitor-id`: provide a stable visitor id across runs
- `--dry-run`: preview without sending events

## Generate random synthetic traffic across many datasets

For broader testing, you can run the helper script below to randomly select
multiple active datasets and emit synthetic visits/downloads for each.

```bash
python /srv/app/src/ckanext-yukondesign/scripts/generate_random_matomo_traffic.py \
  -c /etc/ckan/default/ckan.ini \
  --dataset-count 22 \
  --min-visits 3 \
  --max-visits 12 \
  --min-downloads 1 \
  --max-downloads 4
```

Useful flags:

- `--dataset-ref <name-or-id>`: restrict selection to a subset (repeatable)
- `--allow-no-resources`: include datasets without downloadable resources
- `--sleep-ms`: add delay between emitted events
- `--seed`: make a random run reproducible
- `--dry-run`: preview selected datasets without sending events

The same script can also run from a local machine without CKAN internals by
using Playwright to open CKAN pages in a real browser session:

```bash
python src/ckanext-yukondesign/scripts/generate_random_matomo_traffic.py \
  --ckan-url https://ckan.yukon.dev.datopian.com \
  --dataset-count 22 \
  --min-visits 3 \
  --max-visits 12 \
  --min-downloads 1 \
  --max-downloads 4
```

Prerequisites for standalone mode:

```bash
pip install playwright
playwright install chromium
```

## Import Yukon datasets into a local instance

To seed a local CKAN with Yukon datasets copied from `open.yukon.ca`, including
downloading uploaded resources from the source instance and re-uploading them
to your local instance, use:

```bash
python src/ckanext-yukondesign/scripts/import_open_yukon_datasets.py \
  --target-url http://localhost:5000 \
  --target-api-token <local-sysadmin-token> \
  --per-type 50
```

Notes:

- Only resources with `url_type=upload` are imported.
- Linked/external resources are skipped.
- Missing organizations are created automatically on the target instance.
- Use `--dataset-type data --dataset-type information` etc. to limit the types.
- Use `--dry-run` to preview what would be imported.

## One-shot local smoke test

Use this script to run a full local test cycle: capture metadata timestamp,
emit synthetic traffic, sync usage fields, and verify metadata timestamp is
unchanged.

```bash
#!/usr/bin/env bash
set -euo pipefail

CKAN_INI="${CKAN_INI:-/etc/ckan/default/ckan.ini}"
DATASET_REF="${DATASET_REF:-replace-with-dataset-name-or-id}"
VISITS="${VISITS:-50}"
DOWNLOADS="${DOWNLOADS:-20}"

if [[ "$DATASET_REF" == "replace-with-dataset-name-or-id" ]]; then
	echo "Set DATASET_REF first, for example:"
	echo "  DATASET_REF=my-dataset-name bash ./test-matomo-sync.sh"
	exit 1
fi

get_metadata_modified() {
	ckan -c "$CKAN_INI" action package_show id="$DATASET_REF" | python -c '
import json,sys
data=json.load(sys.stdin)
result=data.get("result", data)
print(result.get("metadata_modified", ""))
'
}

echo "[1/5] Capturing metadata_modified before sync"
before="$(get_metadata_modified)"
echo "Before: $before"

echo "[2/5] Sending synthetic Matomo traffic"
ckan -c "$CKAN_INI" yukon-matomo generate-test-traffic \
	--dataset-ref "$DATASET_REF" \
	--visits "$VISITS" \
	--downloads "$DOWNLOADS" \
	--sleep-ms 50

echo "[3/5] Dry-run sync"
ckan -c "$CKAN_INI" yukon-matomo sync-usage-data \
	--dataset-ref "$DATASET_REF" \
	--dry-run

echo "[4/5] Real sync"
ckan -c "$CKAN_INI" yukon-matomo sync-usage-data \
	--dataset-ref "$DATASET_REF"

echo "[5/5] Capturing metadata_modified after sync"
after="$(get_metadata_modified)"
echo "After:  $after"

if [[ "$before" == "$after" ]]; then
	echo "PASS: metadata_modified unchanged"
else
	echo "FAIL: metadata_modified changed"
	exit 2
fi
```
