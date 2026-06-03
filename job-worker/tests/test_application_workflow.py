"""End-to-end tests for ApplicationWorkflow using Temporal's time-skipping test env.

These exercise the human-in-the-loop approval gate that is the centerpiece of the
project: the workflow generates a draft, blocks at the gate, and then proceeds,
rejects, cancels, or times out depending on the signal it receives. All activities
are mocked, so no database, LLM, or network access is required — only the in-memory
Temporal test server (downloaded on first run).
"""

import asyncio
import uuid

import pytest
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from workflows.application import ApplicationWorkflow
from workflows.follow_up import FollowUpWorkflow

TASK_QUEUE = "jobhunt-worker"


# --- Mock activities. Names must match the real activity definitions the workflow
# --- calls, since execute_activity resolves activities by their registered name.

@activity.defn(name="get_job_with_company")
async def mock_get_job_with_company(job_id: str) -> dict:
    return {
        "job": {
            "title": "Staff Engineer",
            "company_name": "Acme",
            "company_id": None,
            "application_email": "jobs@acme.test",
        },
        "company": {"name": "Acme"},
    }


@activity.defn(name="get_user_profile")
async def mock_get_user_profile() -> dict:
    return {"name": "Alex Rivera", "email": "alex@example.com"}


@activity.defn(name="generate_cover_letter")
async def mock_generate_cover_letter(job, company, profile) -> dict:
    return {"cover_letter": "Dear hiring team, ..."}


@activity.defn(name="tailor_resume_bullets")
async def mock_tailor_resume_bullets(job, profile) -> dict:
    return {"bullets": ["did a relevant thing"]}


@activity.defn(name="get_best_contact")
async def mock_get_best_contact(job_id, company_id):
    return None


@activity.defn(name="generate_outreach_email")
async def mock_generate_outreach_email(job, company, profile, contact, cover_letter) -> dict:
    return {"subject": "Re: Staff Engineer", "body": "Hello there", "body_html": None}


@activity.defn(name="save_application_draft")
async def mock_save_application_draft(job_id, draft) -> str:
    return "draft-1"


@activity.defn(name="log_job_event")
async def mock_log_job_event(job_id, event_type, event_data) -> None:
    return None


@activity.defn(name="notify_user")
async def mock_notify_user(notification_type, data) -> None:
    return None


@activity.defn(name="update_application_status")
async def mock_update_application_status(*args) -> None:
    return None


@activity.defn(name="send_application_email")
async def mock_send_application_email(*args) -> dict:
    return {"success": True, "message_id": "msg-1"}


@activity.defn(name="create_application_record")
async def mock_create_application_record(data) -> str:
    return "app-1"


# The child FollowUpWorkflow gets started after a successful send; register the
# handful of activities it touches so the child can start without error.
@activity.defn(name="get_application")
async def mock_get_application(application_id: str) -> dict:
    return {"id": application_id, "job_id": "job-1"}


@activity.defn(name="get_job")
async def mock_get_job(job_id: str) -> dict:
    return {"title": "Staff Engineer", "company_name": "Acme"}


@activity.defn(name="check_application_replied")
async def mock_check_application_replied(application_id: str) -> bool:
    return False


@activity.defn(name="check_job_still_active")
async def mock_check_job_still_active(job_id: str) -> bool:
    return True


@activity.defn(name="generate_follow_up_email")
async def mock_generate_follow_up_email(*args) -> dict:
    return {"subject": "Re", "body": "hi", "body_html": None, "to": "x@y.test", "thread_id": None}


@activity.defn(name="send_follow_up_email")
async def mock_send_follow_up_email(*args) -> dict:
    return {"success": True, "message_id": "fu-1"}


@activity.defn(name="update_follow_up_record")
async def mock_update_follow_up_record(*args) -> None:
    return None


ALL_ACTIVITIES = [
    mock_get_job_with_company,
    mock_get_user_profile,
    mock_generate_cover_letter,
    mock_tailor_resume_bullets,
    mock_get_best_contact,
    mock_generate_outreach_email,
    mock_save_application_draft,
    mock_log_job_event,
    mock_notify_user,
    mock_update_application_status,
    mock_send_application_email,
    mock_create_application_record,
    mock_get_application,
    mock_get_job,
    mock_check_application_replied,
    mock_check_job_still_active,
    mock_generate_follow_up_email,
    mock_send_follow_up_email,
    mock_update_follow_up_record,
]


def _worker(client) -> Worker:
    return Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[ApplicationWorkflow, FollowUpWorkflow],
        activities=ALL_ACTIVITIES,
    )


async def _await_stage(handle, stage, tries=100):
    """Poll the workflow's status query until it reaches the given stage.

    The workflow advances through several stages before the approval gate; an
    immediate query can catch an earlier one, so wait for the target stage.
    """
    status = {}
    for _ in range(tries):
        status = await handle.query(ApplicationWorkflow.get_status)
        if status["stage"] == stage:
            return status
        await asyncio.sleep(0.02)
    raise AssertionError(f"workflow never reached stage {stage!r}; last status={status}")


@pytest.mark.asyncio
async def test_approval_gate_proceeds_on_approve():
    """The workflow blocks at the gate, then sends and completes once approved."""
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with _worker(env.client):
            handle = await env.client.start_workflow(
                ApplicationWorkflow.run,
                args=["job-1", "email"],
                id=f"application-{uuid.uuid4()}",
                task_queue=TASK_QUEUE,
            )

            # It should park at the approval gate (not finish) until approved.
            status = await _await_stage(handle, "awaiting_approval")
            assert status["approval_received"] is False

            await handle.signal(ApplicationWorkflow.approve_send, args=[True, None])
            result = await asyncio.wait_for(handle.result(), timeout=60)

            assert result["success"] is True
            assert result["email_sent"] is True
            assert result["message_id"] == "msg-1"


@pytest.mark.asyncio
async def test_approval_gate_times_out_after_seven_days():
    """With no approval, the durable 7-day timer fires and the draft expires."""
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with _worker(env.client):
            handle = await env.client.start_workflow(
                ApplicationWorkflow.run,
                args=["job-1", "email"],
                id=f"application-{uuid.uuid4()}",
                task_queue=TASK_QUEUE,
            )
            # No signal: the test server skips time to the timeout.
            result = await asyncio.wait_for(handle.result(), timeout=60)

            assert result["success"] is False
            assert result["error"] == "Approval timeout"


@pytest.mark.asyncio
async def test_approval_gate_rejects_on_disapprove():
    """approve_send(False) resolves the gate as a rejection without sending."""
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with _worker(env.client):
            handle = await env.client.start_workflow(
                ApplicationWorkflow.run,
                args=["job-1", "email"],
                id=f"application-{uuid.uuid4()}",
                task_queue=TASK_QUEUE,
            )
            await handle.signal(ApplicationWorkflow.approve_send, args=[False, None])
            result = await asyncio.wait_for(handle.result(), timeout=60)

            assert result["success"] is False
            assert result.get("rejected") is True


@pytest.mark.asyncio
async def test_application_cancelled():
    """cancel_application resolves the gate as a cancellation."""
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with _worker(env.client):
            handle = await env.client.start_workflow(
                ApplicationWorkflow.run,
                args=["job-1", "email"],
                id=f"application-{uuid.uuid4()}",
                task_queue=TASK_QUEUE,
            )
            await handle.signal(ApplicationWorkflow.cancel_application)
            result = await asyncio.wait_for(handle.result(), timeout=60)

            assert result["success"] is False
            assert result.get("cancelled") is True
