# Airbyte Connection State Migration

> [!NOTE]
> This tool is experimental code that is not supported like other [Airbyte](https://airbyte.com) projects, and is provided for reference purposes only. For assistance with this project, please use this repository's [Issues tab](https://github.com/Airbyte-Solutions-Team/airbyte-solutions-tools-external/issues) to report any faults or feature requests.

A simple Python tool to migrate Airbyte connection state from one workspace to another after Terraform has created equivalent target connections. The migration runs in two steps:

1. `export` — pulls source state and writes it to a JSON file keyed by connection name
2. `apply` — reads the generated JSON file and writes state to the matching target connections

## Setup

```bash
cd state-migration
python -m venv .venv # or python3, depending on OS
source .venv/bin/activate # or equivalent for your operating system
pip install -r requirements.txt
```

Then copy the example config and fill it in:

```bash
cp config.example.yaml config.yaml
# edit config.yaml
```

## Configuration

All configuration lives in `config.yaml`. The CLI is just two subcommands — `export` and `apply` — each accepting `--config / -c` (default `./config.yaml`).

`export` only reads the `source` section of the config; `apply` only reads the `target` section. Both read `options`.

Each environment supplies its own client ID + secret. The script manages the exchange of client ID + secret for the necessary token.

<details>
<summary>Overriding target URLs</summary>
The default target is Airbyte Cloud. `target.public_api_root` and `target.config_api_root` are optional and default to `https://api.airbyte.com/v1` and `https://cloud.airbyte.com/api` respectively.

Override them only if migrating to a non-Cloud destination.
</details>

The source's `public_api_root` and `config_api_root` are required because the source is typically a self-hosted instance and varies as a result. 

Example config (migrating from self-hosted to Airbyte Cloud):

```yaml
# Source is where we are pulling state from
source:
  # <source_webapp_url> is the domain of your self-hosted environment; for example: airbyte.contoso.com 
  public_api_root: https://<source_webapp_url>/api/public/v1
  config_api_root: https://<source_webapp_url>/api 
  workspace_id: 00000000-0000-0000-0000-000000000000 
  client_id: <source_client_id>
  client_secret: <source_client_secret>

# Target is where state will be applied to
target:
  workspace_id: 00000000-0000-0000-0000-000000000000
  client_id: <target_client_id>
  client_secret: <target_client_secret>

options:
  connection_names_file: connections.txt   # required for `export`
  output_dir: ./migration-output
  # export_file: ./migration-output/state_export.json   # optional override
  dry_run: false
  allow_overwrite: false
  log_level: INFO
```

See `config.example.yaml` for an example config file, which you can use as a start point.

### Connection names file

Plain newline-separated text — one connection name per line. Blank lines and lines starting with `#` are skipped, and surrounding whitespace is trimmed. Names must be unique; duplicates fail with the offending line numbers before any API calls are made.

See `connections.example.txt`.

## Important Safeguards

This tool will:

- Fail on duplicate names in the source workspace, the target workspace, or the input file
- Fail on missing names in either workspace
- Fail on non-empty target state unless `options.allow_overwrite: true`
- Skip writes when the source `stateType` is `not_set`
- Fail any target connection whose `status` is `active` — disable or pause the connection in Airbyte (or Terraform) before applying
- Use the safe `create_or_update_safe` endpoint, which refuses to write while a sync is running

You are responsible for everything outside the script — in particular:

- Disable / pause source syncs before fetching source state
- Block target syncs until state has been restored
- Verify connector versions match between source and target. Major-version jumps may render source state incompatible

## Usage

```bash
# 1. Pull source state to a JSON file
python migrate_airbyte_state.py export --config config.yaml

# 2. (Apply Terraform to create equivalent target connections)

# 3. Write the exported state to the target workspace
#    (set options.dry_run: true in config.yaml first to preview)
python migrate_airbyte_state.py apply --config config.yaml
```

## Output files

Everything is written to `options.output_dir`:

`export` writes:
- `state_export.json` (or whatever `options.export_file` points to). Each entry in the JSON contains the source connection ID, state type, the raw `/v1/state/get` payload, and an export timestamp. The file also includes a `schema_version` and a `metadata` block describing where it came from for future proofing.

`apply` writes:
- `state_write_audit.csv` — one row per connection with columns:
  - `connection_name`
  - `source_connection_id`
  - `target_connection_id`
  - `source_state_type`
  - `write_status` (`written` / `dry_run` / `skipped` / `failed`)
  - `error`, if any
