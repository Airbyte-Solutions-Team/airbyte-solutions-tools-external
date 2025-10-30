from prefect import flow, task, get_run_logger
import httpx
import asyncio
from typing import Dict, Any, Optional
import time
import os
import argparse

BASE_URL = "https://api.airbyte.com/v1"

async def get_bearer_token(client_id: str, client_secret: str) -> str:
    """
    Fetch bearer token from Airbyte API
    """
    logger = get_run_logger()
    logger.info("Requesting bearer token from Airbyte API")
    
    payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        "grant-type": "client_credentials"
    }
    headers = {
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{BASE_URL}/applications/token",
            json=payload,
            headers=headers,
            timeout=15.0
        )
        response.raise_for_status()
        token_data = response.json()

        logger.info("Successfully retrieved bearer token from Airbyte API")

        return token_data["access_token"]

@task(retries=3, retry_delay_seconds=30)
async def trigger_airbyte_sync(
    connection_id: str,
    client_id: str,
    client_secret: str,
    job_type: str = "sync",
) -> str:
    """Trigger an Airbyte connection sync"""
    
    logger = get_run_logger()
    logger.info(f"Triggering Airbyte sync for connection: {connection_id}")
    
    bearer_token = await get_bearer_token(client_id, client_secret)
    payload = {
        "connectionId": connection_id,
        "jobType": job_type,
    }
    headers = {
        "Authorization": f"Bearer {bearer_token}",
        "Content-Type": "application/json"
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{BASE_URL}/jobs",
            json=payload,
            headers=headers,
            timeout=30.0
        )
        response.raise_for_status()
        
        job_data = response.json()
        job_id = job_data["jobId"]
        logger.info(f"Successfully triggered sync job: {job_id}")
        return job_id

@task(retries=10, retry_delay_seconds=30)
async def wait_for_sync_completion(
    job_id: str,
    client_id: str,
    client_secret: str,
    poll_interval: int = 5
) -> Dict[str, Any]:
    """Poll Airbyte for job completion"""
    
    logger = get_run_logger()
    logger.info(f"Starting to poll for job completion: {job_id}")
    logger.info(f"Poll interval: {poll_interval} seconds")
    
    bearer_token = await get_bearer_token(client_id, client_secret)
    headers = {
        "Authorization": f"Bearer {bearer_token}",
        "Content-Type": "application/json"
    }
    
    async with httpx.AsyncClient() as client:
        while True:
            logger.info(f"Checking job status for: {job_id}")
            
            response = await client.get(
                f"{BASE_URL}/jobs/{job_id}",
                headers=headers
            )
            response.raise_for_status()
            
            job_info = response.json()
            status = job_info["status"]
            logger.info(f"Job {job_id} status: {status}")
            
            if status in ["incomplete", "failed", "succeeded", "cancelled"]:
                logger.info(f"Job {job_id} completed with status: {status}")
                return job_info
            
            logger.info(f"Job still running, waiting {poll_interval} seconds before next check")
            await asyncio.sleep(poll_interval)

@flow
async def airbyte_sync_flow(
    connection_id: str,
    client_id: str,
    client_secret: str,
):
    """Main flow to trigger and monitor Airbyte sync"""
    
    logger = get_run_logger()
    logger.info("Starting Airbyte sync flow")
    logger.info(f"Using connection ID: {connection_id}")
    
    # Trigger sync
    job_id = await trigger_airbyte_sync(
        connection_id=connection_id,
        client_id=client_id,
        client_secret=client_secret
    )
    
    logger.info(f"Started Airbyte sync job: {job_id}")
    
    # Wait for completion
    job_result = await wait_for_sync_completion(
        job_id=job_id,
        client_id=client_id,
        client_secret=client_secret
    )
    
    logger.info(f"Airbyte job complete with status: {job_result['status']}")
    return job_result

def main():
    parser = argparse.ArgumentParser(description="Trigger and monitor Airbyte sync")
    parser.add_argument(
        "--connection-id", 
        required=True,
        help="The Airbyte connection ID to sync"
    )
    parser.add_argument(
        "--client-id",
        required=True,
        help="The Airbyte client ID to use"
    )
    parser.add_argument(
        "--client-secret",
        required=True,
        help="The Airbyte client secret to use"
    )
    
    args = parser.parse_args()
    
    # Run the flow with parsed arguments
    asyncio.run(airbyte_sync_flow(
        connection_id=args.connection_id,
        client_id=args.client_id,
        client_secret=args.client_secret
    ))

if __name__ == "__main__":
    main()