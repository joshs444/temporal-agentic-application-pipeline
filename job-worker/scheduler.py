"""
Discovery scheduler - runs job discovery workflows based on search_configs schedule.
"""

import asyncio
import os
from datetime import datetime, timedelta
from typing import Optional

from temporalio.client import Client as TemporalClient

from utils.database import fetch_all, execute

TEMPORAL_ADDRESS = os.getenv("TEMPORAL_ADDRESS", "localhost:7233")
CHECK_INTERVAL_SECONDS = 60  # Check every minute


def calculate_next_run(last_run: datetime, frequency: str) -> datetime:
    """Calculate next run time based on frequency."""
    if frequency == "hourly":
        return last_run + timedelta(hours=1)
    elif frequency == "daily":
        return last_run + timedelta(days=1)
    elif frequency == "weekly":
        return last_run + timedelta(weeks=1)
    else:  # manual or unknown
        return last_run + timedelta(days=365)  # Far future for manual


async def trigger_discovery_workflow(
    temporal_client: TemporalClient,
    config_id: str
) -> Optional[str]:
    """Trigger a job discovery workflow for a specific config."""
    from workflows.job_discovery import JobDiscoveryWorkflow

    workflow_id = f"scheduled-discovery-{config_id}-{datetime.utcnow().strftime('%Y%m%d%H%M')}"

    try:
        await temporal_client.start_workflow(
            JobDiscoveryWorkflow.run,
            args=[config_id],
            id=workflow_id,
            task_queue="jobhunt-worker",
        )
        print(f"[Scheduler] Started discovery workflow: {workflow_id}")
        return workflow_id
    except Exception as e:
        print(f"[Scheduler] Failed to start workflow for config {config_id}: {e}")
        return None


async def update_next_run(config_id: str, frequency: str) -> None:
    """Update next_run_at for a config after triggering."""
    next_run = calculate_next_run(datetime.utcnow(), frequency)
    await execute(
        """
        UPDATE search_configs
        SET last_run_at = NOW(), next_run_at = $1
        WHERE id = $2
        """,
        next_run, config_id
    )


async def run_scheduler(temporal_client: TemporalClient) -> None:
    """Main scheduler loop - checks for due configs and triggers workflows."""
    print("[Scheduler] Starting discovery scheduler...")

    while True:
        try:
            # Find configs due for execution
            due_configs = await fetch_all(
                """
                SELECT id, name, run_frequency
                FROM search_configs
                WHERE is_active = TRUE
                AND run_frequency != 'manual'
                AND (next_run_at IS NULL OR next_run_at <= NOW())
                """,
            )

            if due_configs:
                print(f"[Scheduler] Found {len(due_configs)} configs due for discovery")

            for config in due_configs:
                config_id = str(config["id"])
                frequency = config.get("run_frequency", "daily")

                # Trigger workflow
                workflow_id = await trigger_discovery_workflow(temporal_client, config_id)

                if workflow_id:
                    # Update next_run_at
                    await update_next_run(config_id, frequency)
                    print(f"[Scheduler] Scheduled next run for config {config['name']}")

        except Exception as e:
            print(f"[Scheduler] Error in scheduler loop: {e}")

        # Wait before next check
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)
