# Connector Manifest CLI

> [!NOTE]
> This tool is experimental code that is not supported like other [Airbyte](https://airbyte.com) projects, and is provided for reference purposes only. For assistance with this project, please use this repository's [Issues tab](https://github.com/Airbyte-Solutions-Team/airbyte-solutions-tools-external/issues) to report any faults or feature requests.

A small Python CLI for validating a connector manifest, running a read against one stream, and converting YAML and JSON files for use with tools such as Terraform. It is useful for testing a manifest before packaging it as a connector or pasting it into Connector Builder.

The included fixture at `fixtures/test.yaml` requires no credentials and can be used as a smoke test.

## Setup

```bash
cd connector-manifest-cli
python -m venv .venv # or python3, depending on OS
source .venv/bin/activate # or equivalent for your operating system
pip install -r requirements.txt
```

## Configuration

The CLI accepts connector configuration as JSON. Treat credentials as regular connector input fields rather than special CLI flags.

Use inline JSON:

```bash
python connector-manifest-cli test --manifest fixtures/test.yaml --stream debug_company --config-json '{}'
```

Or use a JSON file:

```bash
python connector-manifest-cli test --manifest path/to/manifest.yaml --stream stream_name --config-file config.json
```

Example `config.json`:

```json
{
  "api_key": "example-api-key",
  "start_date": "2024-01-01T00:00:00Z"
}
```

The tool injects the manifest into the connector config under Airbyte CDK's `__injected_declarative_manifest` key, so you do not need to include that field yourself.

## Usage

Validate the provided fixture:

```bash
python connector-manifest-cli test --manifest fixtures/test.yaml --stream debug_company --config-json '{}'
```

The stream argument is required and matches the UI flow of testing one stream at a time.

Run a read after validation:

```bash
python connector-manifest-cli test --manifest fixtures/test.yaml --stream debug_company --config-json '{}' --read
```

`--read` may call external APIs. Omit it when you only want to validate that the manifest can be loaded by the CDK.

After a read, the CLI runs schema inference against the records it received. This mirrors the Connector Builder test flow and surfaces cases where the inferred record shape does not contain the configured primary key or cursor field. To run a read without schema inference, add `--skip-schema-inference`.

By default, read output is formatted for humans. To print raw messages from the CDK library as JSON instead, add `--json-output`:

```bash
python connector-manifest-cli test --manifest fixtures/test.yaml --stream debug_company --config-json '{}' --read --json-output
```

Manifest validation errors are summarized by default so that schema mistakes are easier to read. Add `--show-traceback` to print the full Python traceback when debugging.

Convert a manifest from YAML to JSON for Terraform:

```bash
python connector-manifest-cli convert fixtures/test.yaml --output fixtures/test.json
```

Convert JSON back to YAML:

```bash
python connector-manifest-cli convert fixtures/test.json --output fixtures/test.yaml
```

If `--output` is omitted, converted content is written to stdout. The converter infers formats from file extensions by default. Use `--from-format` or `--to-format` when an extension is ambiguous.

## Options

### test

- `--manifest / -m`: Path to the declarative manifest **YAML** file. Defaults to `fixtures/test.yaml`.
- `--stream / -s`: Stream to include in the configured catalog. Required.
- `--config-json`: Connector config as a JSON object. Defaults to `{}`.
- `--config-file`: Path to a JSON file containing connector config.
- `--state-file`: Optional JSON file containing Airbyte state.
- `--read`: Run `source.read` after validation.
- `--json-output`: Print raw Airbyte messages as JSON during `--read`.
- `--skip-schema-inference`: Do not infer and validate the stream schema after `--read`.
- `--log-level`: Python logging level. Defaults to `INFO`.
- `--show-traceback`: Print full Python tracebacks for debugging.

### convert

- `input`: Input YAML or JSON file.
- `--output / -o`: Output file. Defaults to stdout.
- `--from-format`: Input format. One of `auto`, `yaml`, or `json`. Defaults to `auto`.
- `--to-format`: Output format. One of `auto`, `json`, or `yaml`. Defaults to the output extension or the opposite input format.
- `--indent`: JSON indentation when writing JSON. Defaults to `2`.
- `--show-traceback`: Print full Python tracebacks for debugging.

## Testing

Use the included fixture for a local validation check:

```bash
python connector-manifest-cli test --manifest fixtures/test.yaml --stream debug_company --config-json '{}'
```

Expected output:

```text
Manifest validated OK: fixtures/test.yaml (debug_company)
```
