# Airbyte Prefect Integration Sample

This sample demonstrates how to trigger and monitor Airbyte connection syncs using Prefect workflows.

## Overview

The `prefect_airbyte_sample.py` script provides a Prefect flow that:
1. Authenticates with the Airbyte API using OAuth client credentials
2. Triggers a sync job for a specified Airbyte connection
3. Polls the job status until completion
4. Returns the final job result

## Prerequisites

- Python 3.8 or higher
- An Airbyte account with API access
- Airbyte API credentials (client ID and client secret)
- An existing Airbyte connection to sync

## Installation

1. Install the required dependencies:
```bash
pip install -r requirements.txt
```

## Obtaining Airbyte API Credentials

To use this script, you'll need to obtain API credentials from Airbyte:

1. Log in to your Airbyte Cloud account
2. Navigate to User Settings -> Applications
3. Create a new application or use an existing one
4. Note your **Client ID** and **Client Secret**

## Usage

### Command Line

Run the script from the command line with the required arguments:

```bash
python prefect_airbyte_sample.py \
  --connection-id <YOUR_CONNECTION_ID> \
  --client-id <YOUR_CLIENT_ID> \
  --client-secret <YOUR_CLIENT_SECRET>
```

### Example

```bash
python prefect_airbyte_sample.py \
  --connection-id "a1b2c3d4-e5f6-7890-abcd-ef1234567890" \
  --client-id "your-client-id" \
  --client-secret "your-client-secret"
```

## Script Components

### Tasks

- **`trigger_airbyte_sync`**: Triggers a sync job for the specified connection
  - Retries: 3 times with 30-second delay between attempts
  - Returns the job ID

- **`wait_for_sync_completion`**: Polls the job status until completion
  - Retries: 10 times with 30-second delay between attempts
  - Default poll interval: 5 seconds
  - Returns the final job information

### Flow

- **`airbyte_sync_flow`**: Main workflow that orchestrates the sync process
  - Triggers the sync
  - Waits for completion
  - Returns the final job result

### Helper Functions

- **`get_bearer_token`**: Authenticates with the Airbyte API and retrieves an access token

## Job Status Values

The script monitors for the following terminal job statuses:
- `succeeded`: Job completed successfully
- `failed`: Job failed
- `incomplete`: Job completed but with issues
- `cancelled`: Job was cancelled

## Logging

The script uses Prefect's built-in logging system. All important events are logged, including:
- Authentication attempts
- Job trigger events
- Status checks
- Job completion

## Error Handling

- Both tasks implement retry logic with exponential backoff
- HTTP errors will raise exceptions and trigger retries
- Failed jobs will complete the workflow but return a failed status

## Customization

### Adjusting Poll Interval

To change how often the script checks job status, modify the `poll_interval` parameter in the `wait_for_sync_completion` task call within the flow:

```python
job_result = await wait_for_sync_completion(
    job_id=job_id,
    client_id=client_id,
    client_secret=client_secret,
    poll_interval=10  # Check every 10 seconds instead of 5
)
```

## API Documentation

For more information about the Airbyte API, visit:
- [Airbyte API Documentation](https://reference.airbyte.com/reference/getting-started)

## Troubleshooting

### Authentication Errors

If you receive authentication errors:
- Verify your client ID and client secret are correct
- Ensure your API credentials have the necessary permissions
- Check that your credentials haven't expired

### Connection Not Found

If you receive a 404 error:
- Verify the connection ID is correct
- Ensure the connection exists in your Airbyte workspace
- Check that your API credentials have access to the workspace containing the connection

### Timeout Errors

If jobs are timing out:
- Increase the `poll_interval` to reduce API call frequency
- Check the Airbyte UI to see if the job is still running
- Consider increasing the timeout values in the HTTP client calls

## License

This is a sample script provided for demonstration purposes under the ELv2 license.