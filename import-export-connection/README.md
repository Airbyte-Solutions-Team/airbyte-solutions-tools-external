# Import/Export Airbyte Connection Script

A Python script to export and import Airbyte connections between different Airbyte installations.

## Installation

1. Clone or download this repository

2. (Optional) Configure a Python virtual environment (venv):

```bash 
python -m venv env
source ./env/bin/activate 
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Make the script executable (optional):
```bash
chmod +x airbyte_migrate.py
```

## Configuration

1. Copy the example configuration file:
```bash
cp config.example.yaml config.yaml
```

2. Edit `config.yaml` with your Airbyte instance credentials:

```yaml
# Source Airbyte instance (where connections will be exported from)
source:
  base_url: "https://api.airbyte.com/v1"
  client_id: "your_source_client_id"
  client_secret: "your_source_client_secret"

# Destination Airbyte instance (where connections will be imported to)
destination:
  base_url: "https://api.airbyte.com/v1"
  client_id: "your_destination_client_id"
  client_secret: "your_destination_client_secret"
```

**Note**: The `base_url` will vary slightly depending on what type of Airbyte installation you are using. 

If using Airbyte Cloud, you should use `https://api.airbyte.com/v1`. 

If using Airbyte self-hosted, you will use a variant of `https://<your-airbyte-instance>/api/public/v1`. 

### Getting Credentials

To obtain your client ID and client secret:

1. Log into your Airbyte instance
2. Navigate to **User Settings** -> **Applications**
3. Click **Create an application** or use an existing application
4. Name your application and save the generated Client ID and Client Secret

Do this for both your source and destination Airbyte instances (if they differ).

## Usage

### Export a Connection

Export a connection from the source Airbyte instance to a JSON file:

```bash
python airbyte_migrate.py export --connection-id <CONNECTION_ID> --output connection.json
```

Options:
- `--config`: Path to config file (default: `config.yaml`)
- `--connection-id`: ID of the connection to export (required)
- `--output`: Output JSON file path (required)

Example:
```bash
python airbyte_migrate.py export \
  --config config.yaml \
  --connection-id abc-123-def-456 \
  --output my_connection.json
```

### Import a Connection

Import a connection to the destination Airbyte instance from a JSON file:

```bash
python airbyte_migrate.py import \
  --input connection.json \
  --source-id <SOURCE_ID> \
  --destination-id <DESTINATION_ID> \
  --workspace-id <WORKSPACE_ID>
```

Options:
- `--config`: Path to config file (default: `config.yaml`)
- `--input`: Input JSON file path from export (required)
- `--source-id`: Source ID in the destination Airbyte instance (required)
- `--destination-id`: Destination ID in the destination Airbyte instance (required)
- `--workspace-id`: Workspace ID in the destination Airbyte instance (optional)

Example:
```bash
python airbyte_migrate.py import \
  --config config.yaml \
  --input my_connection.json \
  --source-id src-789-xyz \
  --destination-id dst-012-abc \
  --workspace-id ws-456-def
```

## Important Notes

### Source and Destination IDs

The tool exports connection configuration but does NOT migrate source and destination definitions. You must:

1. Manually create or identify the equivalent source and destination in your target Airbyte instance
2. Obtain their IDs from the destination instance
3. Provide these IDs when running the import command

The exported JSON includes metadata about the original source and destination IDs for reference.

### Workspace IDs

Workspaces can differ between Airbyte environments. The tool handles this by:

1. **During Export**: The original workspace ID is captured and displayed, then stored in the JSON metadata for reference
2. **During Import**: You can optionally specify a `--workspace-id` parameter to target a specific workspace in the destination instance
3. **If Not Specified**: The connection will be created in the destination instance's default workspace

To find workspace IDs in your Airbyte instance, you can use the List Workspaces API endpoint or check the Airbyte UI settings.

### What Gets Migrated

The tool migrates a given connection's configuration, minus the following:

- Source definitions
- Destination definitions
- Connection history, sync logs, or state
