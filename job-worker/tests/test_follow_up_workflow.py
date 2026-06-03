"""End-to-end tests for FollowUpWorkflow using Temporal's time-skipping test env.

These prove the durable follow-up sequence: the 5/12/21-day timers fire (instantly,
under time-skipping), the reply_received signal short-circuits the sequence, and the
post-timer database re-check is an always-on backstop when no signal arrives. All
activities are mocked, so no database, LLM, or network access is required.
"""

import uuid

import pytest
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from workflows.follow_up import FollowUpWorkflow

TASK_QUEUE = "jobhunt-worker"

# Mutable state toggled per-test so a single set of mocks can drive different paths.
STATE = {"db_replied": False, "job_active": True, "sends": 0}


@activity.defn(name="get_application")
async def mock_get_application(application_id: str) -> dict:
    return {"id": application_id, "job_id": "job-1"}


@activity.defn(name="get_job")
async def mock_get_job(job_id: str) -> dict:
    return {"title": "Staff Engineer", "company_name": "Acme"}


@activity.defn(name="check_application_replied")
async def mock_check_application_replied(application_id: str) -> bool:
    return STATE["db_replied"]


@activity.defn(name="check_job_still_active")
async def mock_check_job_still_active(job_id: str) -> bool:
    return STATE["job_active"]


@activity.defn(name="generate_follow_up_email")
async def mock_generate_follow_up_email(*args) -> dict:
    return {"subject": "Re", "body": "hi", "body_html": None, "to": "x@y.test", "thread_id": None}


@activity.defn(name="send_follow_up_email")
async def mock_send_follow_up_email(*args) -> dict:
    STATE["sends"] += 1
    return {"success": True, "message_id": f"fu-{STATE['sends']}"}


@activity.defn(name="update_follow_up_record")
async def mock_update_follow_up_record(*args) -> None:
    return None


@activity.defn(name="update_application_status")
async def mock_update_application_status(*args) -> None:
    return None


@activity.defn(name="log_job_event")
async def mock_log_job_event(*args) -> None:
    return None


@activity.defn(name="notify_user")
async def mock_notify_user(*args) -> None:
    return None


ALL_ACTIVITIES = [
    mock_get_application,
    mock_get_job,
    mock_check_application_replied,
    mock_check_job_still_active,
    mock_generate_follow_up_email,
    mock_send_follow_up_email,
    mock_update_follow_up_record,
    mock_update_application_status,
    mock_log_job_event,
    mock_notify_user,
]


def _worker(client) -> Worker:
    return Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[FollowUpWorkflow],
        activities=ALL_ACTIVITIES,
    )


def _reset(db_replied=False, job_active=True):
    STATE["db_replied"] = db_replied
    STATE["job_active"] = job_active
    STATE["sends"] = 0


@pytest.mark.asyncio
async def test_reply_signal_stops_sequence():
    """A reply_received signal ends the sequence before any follow-up is sent."""
    _reset()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with _worker(env.client):
            handle = await env.client.start_workflow(
                FollowUpWorkflow.run,
                args=["app-1"],
                id=f"followup-{uuid.uuid4()}",
                task_queue=TASK_QUEUE,
            )
            await handle.signal(
                FollowUpWorkflow.reply_received,
                {"sentiment": "positive", "summary": "interested"},
            )
            result = await handle.result()

            assert result["outcome"] == "replied"
            assert result["total_follow_ups"] == 0
            assert STATE["sends"] == 0


@pytest.mark.asyncio
async def test_db_recheck_stops_sequence_without_signal():
    """If the DB shows a reply (signal missed), the post-timer re-check still stops it."""
    _reset(db_replied=True)
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with _worker(env.client):
            handle = await env.client.start_workflow(
                FollowUpWorkflow.run,
                args=["app-1"],
                id=f"followup-{uuid.uuid4()}",
                task_queue=TASK_QUEUE,
            )
            result = await handle.result()

            assert result["outcome"] == "replied"
            assert result["total_follow_ups"] == 0


@pytest.mark.asyncio
async def test_full_cadence_sends_three_follow_ups():
    """No reply and an active job: all three durable timers fire and send."""
    _reset()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with _worker(env.client):
            handle = await env.client.start_workflow(
                FollowUpWorkflow.run,
                args=["app-1"],
                id=f"followup-{uuid.uuid4()}",
                task_queue=TASK_QUEUE,
            )
            result = await handle.result()

            assert result["outcome"] == "completed"
            assert result["total_follow_ups"] == 3
            assert STATE["sends"] == 3
