#!/usr/bin/env python3
"""
Airbyte Connection Migration Tool

This script allows you to export and import Airbyte connections between
different Airbyte installations.
"""

import argparse
import json
import sys
from typing import Dict, Any
import yaml
import requests


class AirbyteClient:
    """Client for interacting with Airbyte API."""
    def __init__(self, base_url: str, client_id: str, client_secret: str):
        """
        Initialize Airbyte API client.

        Args:
            base_url: Base URL for Airbyte API (e.g., https://api.airbyte.com/v1 for cloud, and https://<your-airbyte-instance>/api/public/v1 for self-hosted)
            client_id: Client ID for authentication
            client_secret: Client Secret for authentication
        """
        self.base_url = base_url.rstrip('/')
        self.client_id = client_id
        self.client_secret = client_secret
        self.session = requests.Session()
        self.access_token = None
        self._get_access_token()

    def _get_access_token(self):
        """
        Exchange client credentials for an access token.

        Raises:
            requests.HTTPError: If the token request fails
        """
        token_url = f"{self.base_url}/applications/token"
        payload = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant-type": "client_credentials"
        }

        response = requests.post(token_url, json=payload)
        response.raise_for_status()

        token_data = response.json()
        self.access_token = token_data.get('access_token')

        if not self.access_token:
            raise ValueError("No access_token in response from token endpoint")

        # Set up session with the access token
        self.session.headers.update({
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        })

    def get_connection(self, connection_id: str) -> Dict[str, Any]:
        """
        Get connection details from Airbyte.

        Args:
            connection_id: The ID of the connection to retrieve

        Returns:
            Dictionary containing connection details

        Raises:
            requests.HTTPError: If the API request fails
        """
        url = f"{self.base_url}/connections/{connection_id}"
        response = self.session.get(url)
        response.raise_for_status()
        return response.json()

    def create_connection(self, connection_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a new connection in Airbyte.

        Args:
            connection_data: Dictionary containing connection configuration

        Returns:
            Dictionary containing the created connection details

        Raises:
            requests.HTTPError: If the API request fails
        """
        url = f"{self.base_url}/connections"
        response = self.session.post(url, json=connection_data)
        response.raise_for_status()
        return response.json()


def load_config(config_path: str) -> Dict[str, Any]:
    """
    Load configuration from YAML file.

    Args:
        config_path: Path to the YAML configuration file

    Returns:
        Dictionary containing configuration

    Raises:
        FileNotFoundError: If config file doesn't exist
        yaml.YAMLError: If config file is invalid YAML
    """
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)

    # Validate required fields
    required_fields = ['source', 'destination']
    for field in required_fields:
        if field not in config:
            raise ValueError(f"Missing required field '{field}' in config")

        for subfield in ['base_url', 'client_id', 'client_secret']:
            if subfield not in config[field]:
                raise ValueError(f"Missing required field '{field}.{subfield}' in config")

    return config


def export_connection(args):
    """
    Export a connection from source Airbyte instance to JSON file.

    Args:
        args: Command line arguments containing config_path, connection_id, and output
    """
    print(f"Loading configuration from {args.config}...")
    config = load_config(args.config)

    client = AirbyteClient(
        base_url=config['source']['base_url'],
        client_id=config['source']['client_id'],
        client_secret=config['source']['client_secret']
    )

    connection_data = client.get_connection(args.connection_id)

    # Remove fields that shouldn't be included when recreating the connection
    fields_to_remove = ['connectionId', 'workspaceId', 'sourceId', 'destinationId']
    export_data = {k: v for k, v in connection_data.items() if k not in fields_to_remove}

    if 'status' in export_data:
        export_data['status'] = 'inactive'  # Set to inactive by default

    if 'configurations' not in export_data:
        print("Warning: Connection data does not contain 'configurations' field.", file=sys.stderr)
        sys.exit(1)
    
    config = export_data['configurations']
    for stream in config.get('streams', []):
        if 'selectedFields' in stream and stream['selectedFields'] is None:
            print(f"Warning: Stream {stream.get('streamName')} has 'selectedFields' set to null. Exiting.", file=sys.stderr)
            sys.exit(1)

    # Store the original IDs for reference (but not for recreation)
    export_data['_metadata'] = {
        'original_connection_id': connection_data.get('connectionId'),
        'original_source_id': connection_data.get('sourceId'),
        'original_destination_id': connection_data.get('destinationId'),
        'original_workspace_id': connection_data.get('workspaceId')
    }

    with open(args.output, 'w') as f:
        json.dump(export_data, f, indent=2)

    print(f"Successfully exported connection to {args.output}.")
    print(f"\nIMPORTANT: When importing to a new environment, you must provide:")
    print(f"  - source-id: The ID of the equivalent source in the destination instance")
    print(f"  - destination-id: The ID of the equivalent destination in the destination instance")
    print(f"  - workspace-id (optional): The workspace ID in the destination instance if different from default")


def import_connection(args):
    """
    Import a connection to destination Airbyte instance from JSON file.

    Args:
        args: Command line arguments containing config_path, input, source_id, destination_id, and workspace_id
    """
    if not args.source_id or not args.destination_id:
        print("Error: --source-id and --destination-id are required for import", file=sys.stderr)
        sys.exit(1)

    print(f"Loading configuration from {args.config}...")
    config = load_config(args.config)

    with open(args.input, 'r') as f:
        connection_data = json.load(f)

    # Remove metadata if present
    if '_metadata' in connection_data:
        del connection_data['_metadata']

    # Add required IDs for the new instance
    connection_data['sourceId'] = args.source_id
    connection_data['destinationId'] = args.destination_id

    # Add workspace ID if provided
    if args.workspace_id:
        connection_data['workspaceId'] = args.workspace_id
        print(f"\nUsing workspace ID: {args.workspace_id}")
    else:
        print(f"\nNo workspace ID specified - will use destination instance's default workspace")

    client = AirbyteClient(
        base_url=config['destination']['base_url'],
        client_id=config['destination']['client_id'],
        client_secret=config['destination']['client_secret']
    )

    result = client.create_connection(connection_data)

    print(f"\nSuccessfully created connection.")
    print(f"New connection ID: {result.get('connectionId')}")
    print(f"Workspace ID: {result.get('workspaceId', 'N/A')}")
    print(f"Connection name: {result.get('name', 'N/A')}")


def main():
    """Main entry point for the CLI."""
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Export a connection to JSON
  %(prog)s export --config config.yaml --connection-id abc-123 --output connection.json

  # Import a connection from JSON (with optional workspace ID)
  %(prog)s import --config config.yaml --input connection.json --source-id src-456 --destination-id dst-789 --workspace-id ws-123
        """
    )

    parser.add_argument(
        '--config',
        default='config.yaml',
        help='Path to YAML configuration file (default: config.yaml)'
    )

    subparsers = parser.add_subparsers(dest='command', help='Command to execute', required=True)

    # Export command
    export_parser = subparsers.add_parser(
        'export',
        help='Export a connection from source Airbyte instance'
    )
    export_parser.add_argument(
        '--connection-id',
        required=True,
        help='ID of the connection to export'
    )
    export_parser.add_argument(
        '--output',
        required=True,
        help='Output JSON file path'
    )
    export_parser.set_defaults(func=export_connection)

    # Import command
    import_parser = subparsers.add_parser(
        'import',
        help='Import a connection to destination Airbyte instance'
    )
    import_parser.add_argument(
        '--input',
        required=True,
        help='Input JSON file path (from export command)'
    )
    import_parser.add_argument(
        '--source-id',
        required=True,
        help='Source ID in the destination Airbyte instance'
    )
    import_parser.add_argument(
        '--destination-id',
        required=True,
        help='Destination ID in the destination Airbyte instance'
    )
    import_parser.add_argument(
        '--workspace-id',
        required=False,
        help='Workspace ID in the destination Airbyte instance (optional, uses default if not specified)'
    )
    import_parser.set_defaults(func=import_connection)

    args = parser.parse_args()

    try:
        args.func(args)
    except requests.HTTPError as e:
        print(f"\nAPI Error: {e}", file=sys.stderr)
        if e.response is not None:
            try:
                error_detail = e.response.json()
                print(f"Details: {json.dumps(error_detail, indent=2)}", file=sys.stderr)
            except json.JSONDecodeError:
                print(f"Response: {e.response.text}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
