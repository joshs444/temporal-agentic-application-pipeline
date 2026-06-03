#!/usr/bin/env python3
"""Live demo of the durable human-in-the-loop approval gate.

Runs the REAL ApplicationWorkflow (and its child FollowUpWorkflow) on Temporal's
in-memory time-skipping test server, with activities mocked so no database, LLM, or
network is required. Watch the workflow pause at the approval gate, resume on a
signal, and — in a second scene — expire on its durable 7-day timer when nobody
approves (virtual time is fast-forwarded, so the "7 days" pass instantly).

    pip install -r job-worker/requirements.txt
    python scripts/demo_approval_gate.py
"""

import asyncio
import logging
import sys
from pathlib import Path

# Keep the narration clean — silence the workflow's own framework log lines.
logging.getLogger("temporalio").setLevel(logging.ERROR)

# Make the job-worker package importable when run from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "job-worker"))

from temporalio import activity  # noqa: E402
from temporalio.testing import WorkflowEnvironment  # noqa: E402
from temporalio.worker import Worker  # noqa: E402

from workflows.application import ApplicationWorkflow  # noqa: E402
from workflows.follow_up import FollowUpWorkflow  # noqa: E402

TASK_QUEUE = "jobhunt-worker"


def say(msg=""):
    print(msg, flush=True)


def step(n, msg):
    print(f"   [{n}] {msg}", flush=True)


# --- Mock activities. Names match the real activity definitions the workflow calls. ---

@activity.defn(name="get_job_with_company")
async def get_job_with_company(job_id):
    return {
        "job": {"title": "Staff Engineer", "company_name": "Acme",
                "company_id": None, "application_email": "jobs@acme.test"},
        "company": {"name": "Acme"},
    }


@activity.defn(name="get_user_profile")
async def get_user_profile():
    return {"name": "Alex Rivera", "email": "alex@example.com"}


@activity.defn(name="generate_cover_letter")
async def generate_cover_letter(job, company, profile):
    return {"cover_letter": "Dear hiring team, ..."}


@activity.defn(name="tailor_resume_bullets")
async def tailor_resume_bullets(job, profile):
    return {"bullets": ["did a relevant thing"]}


@activity.defn(name="get_best_contact")
async def get_best_contact(job_id, company_id):
    return None


@activity.defn(name="generate_outreach_email")
async def generate_outreach_email(job, company, profile, contact, cover_letter):
    return {"subject": "Re: Staff Engineer", "body": "Hello there", "body_html": None}


@activity.defn(name="save_application_draft")
async def save_application_draft(job_id, draft):
    return "draft-1"


@activity.defn(name="log_job_event")
async def log_job_event(job_id, event_type, event_data):
    return None


@activity.defn(name="notify_user")
async def notify_user(notification_type, data):
    return None


@activity.defn(name="update_application_status")
async def update_application_status(*args):
    return None


@activity.defn(name="send_application_email")
async def send_application_email(*args):
    return {"success": True, "message_id": "msg-1"}


@activity.defn(name="create_application_record")
async def create_application_record(data):
    return "app-1"


# Child FollowUpWorkflow activities (it is started after a successful send).
@activity.defn(name="get_application")
async def get_application(application_id):
    return {"id": application_id, "job_id": "job-1"}


@activity.defn(name="get_job")
async def get_job(job_id):
    return {"title": "Staff Engineer", "company_name": "Acme"}


@activity.defn(name="check_application_replied")
async def check_application_replied(application_id):
    return False


@activity.defn(name="check_job_still_active")
async def check_job_still_active(job_id):
    return True


@activity.defn(name="generate_follow_up_email")
async def generate_follow_up_email(*args):
    return {"subject": "Re", "body": "hi", "body_html": None, "to": "x@y.test", "thread_id": None}


@activity.defn(name="send_follow_up_email")
async def send_follow_up_email(*args):
    return {"success": True, "message_id": "fu-1"}


@activity.defn(name="update_follow_up_record")
async def update_follow_up_record(*args):
    return None


ALL_ACTIVITIES = [
    get_job_with_company, get_user_profile, generate_cover_letter, tailor_resume_bullets,
    get_best_contact, generate_outreach_email, save_application_draft, log_job_event,
    notify_user, update_application_status, send_application_email, create_application_record,
    get_application, get_job, check_application_replied, check_job_still_active,
    generate_follow_up_email, send_follow_up_email, update_follow_up_record,
]


async def _await_stage(handle, stage, tries=100):
    """Poll the workflow's status query until it reaches the given stage."""
    status = {}
    for _ in range(tries):
        status = await handle.query(ApplicationWorkflow.get_status)
        if status["stage"] == stage:
            return status
        await asyncio.sleep(0.02)
    raise RuntimeError(f"workflow never reached {stage!r}; last={status}")


async def scene_approved(env):
    say("SCENE 1 — a human reviews and approves the draft")
    handle = await env.client.start_workflow(
        ApplicationWorkflow.run, args=["job-123", "email"],
        id="application-demo-approve", task_queue=TASK_QUEUE,
    )
    step(1, "Started ApplicationWorkflow: drafting outreach for 'Staff Engineer' at Acme.")
    status = await _await_stage(handle, "awaiting_approval")
    step(2, f"Paused at the approval gate. Live query -> stage={status['stage']!r}, "
            f"approved={status['approval_received']}.")
    step(3, "No process is polling a database — the workflow is durably suspended on "
            "Temporal, and would survive a worker restart while it waits.")
    await handle.signal(ApplicationWorkflow.approve_send, args=[True, None])
    step(4, "Sent signal approve_send(approved=True). The workflow resumes...")
    result = await asyncio.wait_for(handle.result(), 60)
    step(5, f"Sent + recorded: email_sent={result['email_sent']}, "
            f"message_id={result['message_id']!r}; a follow-up workflow was scheduled.")
    say()


async def scene_timeout(env):
    say("SCENE 2 — nobody approves (the durable 7-day timer fires)")
    handle = await env.client.start_workflow(
        ApplicationWorkflow.run, args=["job-456", "email"],
        id="application-demo-timeout", task_queue=TASK_QUEUE,
    )
    status = await _await_stage(handle, "awaiting_approval")
    step(1, f"Paused at the gate again (stage={status['stage']!r}). This time no one approves.")
    step(2, "Fast-forwarding virtual time by 7 days (a durable Temporal timer)...")
    result = await asyncio.wait_for(handle.result(), 60)
    step(3, f"The draft expired cleanly: success={result['success']}, "
            f"reason={result.get('error')!r}. No outreach was sent.")
    say()


async def main():
    say("=" * 72)
    say("  Durable human-in-the-loop approval gate — live demo")
    say("  Real ApplicationWorkflow on Temporal's in-memory time-skipping server.")
    say("  Activities are mocked: no database, LLM, or network required.")
    say("=" * 72)
    say()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client, task_queue=TASK_QUEUE,
            workflows=[ApplicationWorkflow, FollowUpWorkflow],
            activities=ALL_ACTIVITIES,
        ):
            await scene_approved(env)
            await scene_timeout(env)
    say("Demo complete — the gate paused, resumed on a signal, and expired on its timer.")


if __name__ == "__main__":
    asyncio.run(main())
