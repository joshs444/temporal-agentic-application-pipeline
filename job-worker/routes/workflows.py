"""
Workflow trigger endpoints for JobHunt API.

Handles starting and managing Temporal workflows for job discovery,
enrichment, application, and interview preparation.
"""

import os
from typing import Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException
from temporalio.client import Client as TemporalClient

from models import (
    WorkflowTriggerResponse,
    ApplicationDraft,
    ApplicationApproval,
)
from utils.database import fetch_one, execute, record_to_dict

router = APIRouter()

# Temporal configuration
TEMPORAL_ADDRESS = os.getenv("TEMPORAL_ADDRESS", "localhost:7233")
TASK_QUEUE = os.getenv("TASK_QUEUE", "jobhunt-worker")

# Global Temporal client (initialized in main.py lifespan)
_temporal_client: Optional[TemporalClient] = None


async def get_temporal_client() -> TemporalClient:
    """Get the Temporal client, connecting if necessary."""
    global _temporal_client
    if _temporal_client is None:
        _temporal_client = await TemporalClient.connect(TEMPORAL_ADDRESS)
    return _temporal_client


def set_temporal_client(client: TemporalClient) -> None:
    """Set the Temporal client (called from main.py)."""
    global _temporal_client
    _temporal_client = client


@router.post("/discover", response_model=WorkflowTriggerResponse)
async def trigger_job_discovery(
    search_config_id: Optional[UUID] = None,
) -> WorkflowTriggerResponse:
    """
    Trigger a job discovery workflow.

    If search_config_id is provided, uses that saved search configuration.
    Otherwise, uses default search parameters.
    """
    try:
        client = await get_temporal_client()
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Temporal service unavailable: {str(e)}"
        )

    # Validate the search config if one was provided. Validate against the same
    # table the discovery workflow actually reads (search_configs) so any id that
    # passes here is one JobDiscoveryWorkflow can load.
    if search_config_id:
        config = await fetch_one(
            "SELECT id FROM search_configs WHERE id = $1",
            search_config_id
        )
        if not config:
            raise HTTPException(status_code=404, detail="Search config not found")

    workflow_id = f"job-discovery-{uuid4()}"

    try:
        # Start the workflow
        await client.start_workflow(
            "JobDiscoveryWorkflow",
            str(search_config_id) if search_config_id else None,
            id=workflow_id,
            task_queue=TASK_QUEUE,
        )

        # Update last_run_at if using a search config
        if search_config_id:
            await execute(
                "UPDATE search_configs SET last_run_at = NOW() WHERE id = $1",
                search_config_id
            )

        return WorkflowTriggerResponse(
            status="started",
            workflow_id=workflow_id,
            message="Job discovery workflow started successfully",
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to start workflow: {str(e)}"
        )


@router.post("/discover-from-resume", response_model=WorkflowTriggerResponse)
async def discover_jobs_from_resume(
    resume_profile_id: Optional[UUID] = None,
    salary_min: Optional[int] = None,
) -> WorkflowTriggerResponse:
    """
    Auto-discover jobs based on your resume.

    This is the simplest way to find jobs:
    1. Upload your resume (or use existing default)
    2. Optionally set minimum salary
    3. AI analyzes your resume and figures out what jobs to search for
    4. Finds and scores matching jobs

    No manual search config needed - just upload resume and go.

    Args:
        resume_profile_id: Optional specific resume to use (uses default if not provided)
        salary_min: Optional minimum salary filter (uses resume preference if not provided)
    """
    try:
        client = await get_temporal_client()
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Temporal service unavailable: {str(e)}"
        )

    # Check if a default resume exists
    resume = await fetch_one(
        """
        SELECT id, name FROM resume_profiles
        WHERE id = $1 OR (is_default = TRUE AND $1 IS NULL)
        LIMIT 1
        """,
        str(resume_profile_id) if resume_profile_id else None,
    )

    if not resume:
        raise HTTPException(
            status_code=400,
            detail="No resume found. Upload a resume first or mark one as default."
        )

    workflow_id = f"resume-discovery-{uuid4()}"

    try:
        # Start the workflow with use_resume=True
        await client.start_workflow(
            "JobDiscoveryWorkflow",
            args=[
                None,  # search_config_id
                50,    # max_results_per_config
                True,  # use_resume
                str(resume_profile_id) if resume_profile_id else None,  # resume_profile_id
                salary_min,  # salary_override
            ],
            id=workflow_id,
            task_queue=TASK_QUEUE,
        )

        return WorkflowTriggerResponse(
            status="started",
            workflow_id=workflow_id,
            message=(
                f"Resume-driven job discovery started for {resume['name']}. "
                f"AI will analyze your resume and find matching jobs."
            ),
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to start workflow: {str(e)}"
        )


@router.post("/enrich/{job_id}", response_model=WorkflowTriggerResponse)
async def trigger_enrichment(job_id: UUID) -> WorkflowTriggerResponse:
    """
    Trigger a job enrichment workflow for a specific job.

    This will enrich the job with additional details like company info,
    salary estimates, and match scoring.
    """
    # Verify job exists
    job = await fetch_one("SELECT id, title, company_name FROM jobs WHERE id = $1", job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    try:
        client = await get_temporal_client()
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Temporal service unavailable: {str(e)}"
        )

    workflow_id = f"job-enrichment-{job_id}"

    try:
        await client.start_workflow(
            "JobEnrichmentWorkflow",
            str(job_id),
            id=workflow_id,
            task_queue=TASK_QUEUE,
        )

        return WorkflowTriggerResponse(
            status="started",
            workflow_id=workflow_id,
            message=f"Enrichment workflow started for {job['title']} at {job['company_name']}",
        )
    except Exception as e:
        # Check if workflow already running
        if "already started" in str(e).lower():
            return WorkflowTriggerResponse(
                status="already_running",
                workflow_id=workflow_id,
                message="Enrichment workflow is already running for this job",
            )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to start workflow: {str(e)}"
        )


@router.post("/apply/{job_id}", response_model=WorkflowTriggerResponse)
async def trigger_application(
    job_id: UUID,
    method: str = "email",
) -> WorkflowTriggerResponse:
    """
    Start application workflow for a job.

    This generates application materials (cover letter, resume tweaks)
    and returns a draft for approval. The draft will be stored and can
    be retrieved via GET /apply/{job_id}/draft.

    Methods: 'email', 'portal', 'referral'
    """
    # Verify job exists and get details
    job = await fetch_one(
        """
        SELECT id, title, company_name, description, requirements,
               COALESCE((raw_data->>'status')::text, 'new') as status
        FROM jobs WHERE id = $1
        """,
        job_id
    )
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Check if application already exists
    existing_app = await fetch_one(
        "SELECT id, status FROM applications WHERE job_id = $1",
        job_id
    )
    if existing_app and existing_app["status"] not in ("draft", "withdrawn"):
        raise HTTPException(
            status_code=409,
            detail=f"Application already exists with status: {existing_app['status']}"
        )

    try:
        client = await get_temporal_client()
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Temporal service unavailable: {str(e)}"
        )

    workflow_id = f"application-{job_id}"

    try:
        await client.start_workflow(
            "ApplicationWorkflow",
            args=[str(job_id), method],
            id=workflow_id,
            task_queue=TASK_QUEUE,
        )

        # Create or update application record with draft status
        if existing_app:
            await execute(
                """
                UPDATE applications
                SET status = 'draft',
                    custom_answers = jsonb_set(
                        COALESCE(custom_answers, '{}'::jsonb),
                        '{method}', $2::jsonb
                    ),
                    updated_at = NOW()
                WHERE id = $1
                """,
                existing_app["id"],
                f'"{method}"'
            )
        else:
            await execute(
                """
                INSERT INTO applications (job_id, status, custom_answers)
                VALUES ($1, 'draft', $2)
                """,
                job_id,
                {"method": method, "workflow_id": workflow_id}
            )

        # Update job status
        await execute(
            """
            UPDATE jobs
            SET raw_data = jsonb_set(COALESCE(raw_data, '{}'::jsonb), '{status}', '"applying"'::jsonb),
                updated_at = NOW()
            WHERE id = $1
            """,
            job_id
        )

        return WorkflowTriggerResponse(
            status="started",
            workflow_id=workflow_id,
            message=(
                f"Application workflow started for {job['title']} at {job['company_name']}. "
                "Draft will be available shortly at GET /api/workflows/apply/{job_id}/draft"
            ),
        )
    except Exception as e:
        if "already started" in str(e).lower():
            return WorkflowTriggerResponse(
                status="already_running",
                workflow_id=workflow_id,
                message="Application workflow is already running for this job",
            )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to start workflow: {str(e)}"
        )


@router.get("/apply/{job_id}/draft", response_model=ApplicationDraft)
async def get_application_draft(job_id: UUID) -> ApplicationDraft:
    """
    Get the current application draft for a job.

    Returns the generated cover letter, resume version, and any
    custom answers that the workflow has produced.
    """
    # Get application with draft data
    record = await fetch_one(
        """
        SELECT
            a.id, a.job_id, a.status, a.cover_letter, a.resume_version,
            a.custom_answers, a.created_at
        FROM applications a
        WHERE a.job_id = $1
        ORDER BY a.created_at DESC
        LIMIT 1
        """,
        job_id
    )

    if not record:
        raise HTTPException(status_code=404, detail="No application draft found for this job")

    data = record_to_dict(record)

    # Determine draft status
    draft_status = "pending_approval"
    if data["status"] == "applied":
        draft_status = "approved"
    elif data["status"] == "withdrawn":
        draft_status = "rejected"

    return ApplicationDraft(
        job_id=data["job_id"],
        cover_letter=data["cover_letter"],
        resume_version=data["resume_version"],
        custom_answers=data["custom_answers"],
        method=data["custom_answers"].get("method", "email") if data["custom_answers"] else "email",
        status=draft_status,
        created_at=data["created_at"],
    )


@router.post("/apply/{job_id}/approve", response_model=WorkflowTriggerResponse)
async def approve_application(
    job_id: UUID,
    approval: ApplicationApproval,
) -> WorkflowTriggerResponse:
    """
    Approve or reject an application draft.

    If approved, the application will be submitted via the specified method.
    If edits are provided, they will be applied before submission.
    """
    # Get application
    app_record = await fetch_one(
        "SELECT id, status, custom_answers FROM applications WHERE job_id = $1",
        job_id
    )

    if not app_record:
        raise HTTPException(status_code=404, detail="No application found for this job")

    if app_record["status"] != "draft":
        raise HTTPException(
            status_code=409,
            detail=f"Application is not in draft status (current: {app_record['status']})"
        )

    if not approval.approved:
        # Tell the running workflow to stop waiting at the approval gate (best-effort)
        # so it resolves immediately instead of sitting until the 7-day timeout.
        try:
            client = await get_temporal_client()
            handle = client.get_workflow_handle(f"application-{job_id}")
            await handle.signal("approve_send", args=[False, None])
        except Exception:
            pass

        # Mark as withdrawn/rejected
        await execute(
            """
            UPDATE applications
            SET status = 'withdrawn', updated_at = NOW()
            WHERE job_id = $1
            """,
            job_id
        )
        await execute(
            """
            UPDATE jobs
            SET raw_data = jsonb_set(COALESCE(raw_data, '{}'::jsonb), '{status}', '"interested"'::jsonb),
                updated_at = NOW()
            WHERE id = $1
            """,
            job_id
        )
        return WorkflowTriggerResponse(
            status="rejected",
            workflow_id="",
            message="Application draft rejected and withdrawn",
        )

    # Apply edits if provided
    if approval.edits:
        updates = []
        params = []
        param_idx = 1

        if "cover_letter" in approval.edits:
            updates.append(f"cover_letter = ${param_idx}")
            params.append(approval.edits["cover_letter"])
            param_idx += 1

        if "resume_version" in approval.edits:
            updates.append(f"resume_version = ${param_idx}")
            params.append(approval.edits["resume_version"])
            param_idx += 1

        if "custom_answers" in approval.edits:
            updates.append(f"custom_answers = custom_answers || ${param_idx}::jsonb")
            params.append(approval.edits["custom_answers"])
            param_idx += 1

        if updates:
            params.append(job_id)
            update_clause = ", ".join(updates)
            await execute(
                f"""
                UPDATE applications
                SET {update_clause}, updated_at = NOW()
                WHERE job_id = ${param_idx}
                """,
                *params
            )

    # Signal the workflow to proceed with submission
    try:
        client = await get_temporal_client()
        workflow_id = f"application-{job_id}"

        # Signal the running workflow's approve_send(approved, edits) handler.
        # The signal name and positional args must match ApplicationWorkflow.approve_send.
        handle = client.get_workflow_handle(workflow_id)
        await handle.signal("approve_send", args=[True, approval.edits])

        return WorkflowTriggerResponse(
            status="approved",
            workflow_id=workflow_id,
            message="Application approved and submission in progress",
        )
    except Exception:
        # If workflow not running, update directly
        await execute(
            """
            UPDATE applications
            SET status = 'applied', applied_at = NOW(), updated_at = NOW()
            WHERE job_id = $1
            """,
            job_id
        )
        await execute(
            """
            UPDATE jobs
            SET raw_data = jsonb_set(COALESCE(raw_data, '{}'::jsonb), '{status}', '"applied"'::jsonb),
                updated_at = NOW()
            WHERE id = $1
            """,
            job_id
        )

        return WorkflowTriggerResponse(
            status="approved",
            workflow_id="",
            message="Application approved and marked as applied (workflow not active)",
        )


@router.post("/interview-prep/{interview_id}", response_model=WorkflowTriggerResponse)
async def trigger_interview_prep(interview_id: UUID) -> WorkflowTriggerResponse:
    """
    Start interview preparation workflow.

    Generates interview preparation materials including:
    - Company research summary
    - Common questions for this role/stage
    - Questions to ask the interviewer
    - Technical preparation topics (if applicable)
    """
    # Get interview details
    interview = await fetch_one(
        """
        SELECT
            i.id, i.application_id, i.stage, i.scheduled_at,
            i.interviewer_names, i.interviewer_titles,
            j.title, j.company_name, j.description, j.requirements
        FROM interviews i
        JOIN applications a ON i.application_id = a.id
        JOIN jobs j ON a.job_id = j.id
        WHERE i.id = $1
        """,
        interview_id
    )

    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found")

    try:
        client = await get_temporal_client()
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Temporal service unavailable: {str(e)}"
        )

    workflow_id = f"interview-prep-{interview_id}"

    try:
        # The workflow re-fetches interview/company details via activities, so it
        # only needs the interview_id (matching InterviewPrepWorkflow.run's signature).
        await client.start_workflow(
            "InterviewPrepWorkflow",
            args=[str(interview_id)],
            id=workflow_id,
            task_queue=TASK_QUEUE,
        )

        return WorkflowTriggerResponse(
            status="started",
            workflow_id=workflow_id,
            message=(
                f"Interview prep workflow started for {interview['stage']} "
                f"at {interview['company_name']}"
            ),
        )
    except Exception as e:
        if "already started" in str(e).lower():
            return WorkflowTriggerResponse(
                status="already_running",
                workflow_id=workflow_id,
                message="Interview prep workflow is already running",
            )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to start workflow: {str(e)}"
        )


@router.get("/status/{workflow_id}")
async def get_workflow_status(workflow_id: str) -> dict:
    """
    Get the status of a running workflow.
    """
    try:
        client = await get_temporal_client()
        handle = client.get_workflow_handle(workflow_id)
        description = await handle.describe()

        return {
            "workflow_id": workflow_id,
            "status": description.status.name,
            "start_time": description.start_time.isoformat() if description.start_time else None,
            "close_time": description.close_time.isoformat() if description.close_time else None,
            "workflow_type": description.workflow_type,
        }
    except Exception as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=404, detail="Workflow not found")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get workflow status: {str(e)}"
        )


@router.post("/cancel/{workflow_id}")
async def cancel_workflow(workflow_id: str) -> dict:
    """
    Cancel a running workflow.
    """
    try:
        client = await get_temporal_client()
        handle = client.get_workflow_handle(workflow_id)
        await handle.cancel()

        return {
            "workflow_id": workflow_id,
            "status": "cancelled",
            "message": "Workflow cancellation requested",
        }
    except Exception as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=404, detail="Workflow not found")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to cancel workflow: {str(e)}"
        )
