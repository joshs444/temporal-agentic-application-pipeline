"""
Application endpoints for JobHunt API.

Handles application tracking, status updates, and interview management.
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from models import (
    ApplicationResponse,
    ApplicationDetailResponse,
    ApplicationCreate,
    ApplicationUpdate,
    ApplicationListResponse,
    InterviewResponse,
    InterviewCreate,
    InterviewUpdate,
)
from utils.database import fetch_one, fetch_all, execute, record_to_dict, records_to_dicts

router = APIRouter()


@router.get("/", response_model=ApplicationListResponse)
async def list_applications(
    status: Optional[str] = Query(None, description="Filter by application status"),
    limit: int = Query(50, ge=1, le=100, description="Number of results to return"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
) -> ApplicationListResponse:
    """
    List all applications with optional status filter.
    """
    conditions = []
    params = []
    param_idx = 1

    if status:
        conditions.append(f"a.status = ${param_idx}")
        params.append(status)
        param_idx += 1

    where_clause = " AND ".join(conditions) if conditions else "1=1"

    # Count total
    count_query = f"SELECT COUNT(*) FROM applications a WHERE {where_clause}"
    count_result = await fetch_one(count_query, *params)
    total = count_result["count"] if count_result else 0

    # Fetch applications with job info
    query = f"""
        SELECT
            a.id, a.job_id, a.status, a.applied_at, a.resume_version,
            a.cover_letter, a.notes, a.next_action, a.next_action_date,
            a.created_at, a.updated_at,
            j.title as job_title, j.company_name
        FROM applications a
        JOIN jobs j ON a.job_id = j.id
        WHERE {where_clause}
        ORDER BY a.updated_at DESC
        LIMIT ${param_idx} OFFSET ${param_idx + 1}
    """
    params.extend([limit, offset])

    records = await fetch_all(query, *params)
    applications = [ApplicationResponse(**record_to_dict(r)) for r in records]

    return ApplicationListResponse(
        applications=applications,
        total=total,
    )


@router.get("/{application_id}", response_model=ApplicationDetailResponse)
async def get_application(application_id: UUID) -> ApplicationDetailResponse:
    """
    Get detailed application information including job and interviews.
    """
    # Fetch application
    query = """
        SELECT
            a.id, a.job_id, a.status, a.applied_at, a.resume_version,
            a.cover_letter, a.custom_answers, a.notes, a.next_action,
            a.next_action_date, a.created_at, a.updated_at
        FROM applications a
        WHERE a.id = $1
    """
    record = await fetch_one(query, application_id)

    if not record:
        raise HTTPException(status_code=404, detail="Application not found")

    app_data = record_to_dict(record)

    # Fetch associated job
    job_query = """
        SELECT
            id, external_id, source, title, company_name, company_url,
            location, remote_type, salary_min, salary_max, salary_currency,
            url, posted_at, match_score, created_at, updated_at,
            COALESCE((raw_data->>'status')::text, 'new') as status
        FROM jobs
        WHERE id = $1
    """
    job_record = await fetch_one(job_query, app_data["job_id"])
    job = record_to_dict(job_record) if job_record else None

    # Fetch interviews
    interview_query = """
        SELECT
            id, application_id, stage, scheduled_at, duration_minutes,
            location, interviewer_names, interviewer_titles, prep_notes,
            questions_to_ask, feedback, outcome, created_at, updated_at
        FROM interviews
        WHERE application_id = $1
        ORDER BY scheduled_at ASC NULLS LAST, created_at ASC
    """
    interview_records = await fetch_all(interview_query, application_id)
    interviews = [InterviewResponse(**record_to_dict(r)) for r in interview_records]

    return ApplicationDetailResponse(
        **app_data,
        job=job,
        interviews=interviews,
    )


@router.post("/", response_model=ApplicationResponse)
async def create_application(application: ApplicationCreate) -> ApplicationResponse:
    """
    Create a new application for a job.

    This creates a draft application. Use the workflows endpoint to trigger
    the full application workflow with LLM-generated materials.
    """
    # Check if job exists
    job_check = await fetch_one("SELECT id FROM jobs WHERE id = $1", application.job_id)
    if not job_check:
        raise HTTPException(status_code=404, detail="Job not found")

    # Check if application already exists for this job
    existing = await fetch_one(
        "SELECT id FROM applications WHERE job_id = $1",
        application.job_id
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail="Application already exists for this job"
        )

    # Create application
    query = """
        INSERT INTO applications (
            job_id, status, resume_version, cover_letter, notes,
            custom_answers
        ) VALUES ($1, $2, $3, $4, $5, $6)
        RETURNING
            id, job_id, status, applied_at, resume_version, cover_letter,
            notes, next_action, next_action_date, created_at, updated_at
    """
    record = await fetch_one(
        query,
        application.job_id,
        "draft",
        application.resume_version,
        application.cover_letter,
        application.notes,
        {"method": application.method},
    )

    if not record:
        raise HTTPException(status_code=500, detail="Failed to create application")

    # Update job status to "applying"
    await execute(
        """
        UPDATE jobs
        SET raw_data = jsonb_set(COALESCE(raw_data, '{}'::jsonb), '{status}', '"applying"'::jsonb),
            updated_at = NOW()
        WHERE id = $1
        """,
        application.job_id
    )

    return ApplicationResponse(**record_to_dict(record))


@router.put("/{application_id}", response_model=ApplicationResponse)
async def update_application(
    application_id: UUID,
    update: ApplicationUpdate
) -> ApplicationResponse:
    """
    Update application status, notes, or other fields.
    """
    # Build update query dynamically
    updates = []
    params = []
    param_idx = 1

    if update.status is not None:
        updates.append(f"status = ${param_idx}")
        params.append(update.status)
        param_idx += 1

        # If status is 'applied', set applied_at
        if update.status == "applied":
            updates.append("applied_at = NOW()")

    if update.notes is not None:
        updates.append(f"notes = ${param_idx}")
        params.append(update.notes)
        param_idx += 1

    if update.next_action is not None:
        updates.append(f"next_action = ${param_idx}")
        params.append(update.next_action)
        param_idx += 1

    if update.next_action_date is not None:
        updates.append(f"next_action_date = ${param_idx}")
        params.append(update.next_action_date)
        param_idx += 1

    if update.cover_letter is not None:
        updates.append(f"cover_letter = ${param_idx}")
        params.append(update.cover_letter)
        param_idx += 1

    if update.custom_answers is not None:
        updates.append(f"custom_answers = ${param_idx}")
        params.append(update.custom_answers)
        param_idx += 1

    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    params.append(application_id)
    update_clause = ", ".join(updates)

    query = f"""
        UPDATE applications
        SET {update_clause}, updated_at = NOW()
        WHERE id = ${param_idx}
        RETURNING
            id, job_id, status, applied_at, resume_version, cover_letter,
            notes, next_action, next_action_date, created_at, updated_at
    """
    record = await fetch_one(query, *params)

    if not record:
        raise HTTPException(status_code=404, detail="Application not found")

    app_data = record_to_dict(record)

    # Update job status based on application status
    if update.status:
        job_status_map = {
            "applied": "applied",
            "interviewing": "interviewing",
            "offered": "offer",
            "rejected": "rejected",
            "withdrawn": "dismissed",
        }
        if update.status in job_status_map:
            await execute(
                f"""
                UPDATE jobs
                SET raw_data = jsonb_set(
                    COALESCE(raw_data, '{{}}'::jsonb),
                    '{{status}}',
                    '"{job_status_map[update.status]}"'::jsonb
                ),
                updated_at = NOW()
                WHERE id = $1
                """,
                app_data["job_id"]
            )

    return ApplicationResponse(**app_data)


@router.delete("/{application_id}")
async def delete_application(application_id: UUID) -> dict:
    """
    Delete an application and its associated interviews.
    """
    # Get job_id before deleting
    record = await fetch_one(
        "SELECT job_id FROM applications WHERE id = $1",
        application_id
    )

    if not record:
        raise HTTPException(status_code=404, detail="Application not found")

    job_id = record["job_id"]

    # Delete application (cascade will handle interviews)
    await execute("DELETE FROM applications WHERE id = $1", application_id)

    # Reset job status back to "interested"
    await execute(
        """
        UPDATE jobs
        SET raw_data = jsonb_set(COALESCE(raw_data, '{}'::jsonb), '{status}', '"interested"'::jsonb),
            updated_at = NOW()
        WHERE id = $1
        """,
        job_id
    )

    return {"status": "deleted", "application_id": str(application_id)}


# Interview sub-routes
@router.post("/{application_id}/interview", response_model=InterviewResponse)
async def add_interview(
    application_id: UUID,
    interview: InterviewCreate
) -> InterviewResponse:
    """
    Add an interview to an application.
    """
    # Check if application exists
    app_check = await fetch_one(
        "SELECT id, job_id FROM applications WHERE id = $1",
        application_id
    )
    if not app_check:
        raise HTTPException(status_code=404, detail="Application not found")

    # Create interview
    query = """
        INSERT INTO interviews (
            application_id, stage, scheduled_at, duration_minutes,
            location, interviewer_names, interviewer_titles, prep_notes
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        RETURNING
            id, application_id, stage, scheduled_at, duration_minutes,
            location, interviewer_names, interviewer_titles, prep_notes,
            questions_to_ask, feedback, outcome, created_at, updated_at
    """
    record = await fetch_one(
        query,
        application_id,
        interview.stage,
        interview.scheduled_at,
        interview.duration_minutes,
        interview.location,
        interview.interviewer_names,
        interview.interviewer_titles,
        interview.notes,
    )

    if not record:
        raise HTTPException(status_code=500, detail="Failed to create interview")

    # Update application status to interviewing if not already
    await execute(
        """
        UPDATE applications
        SET status = 'interviewing', updated_at = NOW()
        WHERE id = $1 AND status != 'interviewing'
        """,
        application_id
    )

    # Update job status to interviewing
    await execute(
        """
        UPDATE jobs
        SET raw_data = jsonb_set(COALESCE(raw_data, '{}'::jsonb), '{status}', '"interviewing"'::jsonb),
            updated_at = NOW()
        WHERE id = $1
        """,
        app_check["job_id"]
    )

    return InterviewResponse(**record_to_dict(record))


@router.get("/{application_id}/interviews", response_model=list[InterviewResponse])
async def list_interviews(application_id: UUID) -> list[InterviewResponse]:
    """
    List all interviews for an application.
    """
    query = """
        SELECT
            id, application_id, stage, scheduled_at, duration_minutes,
            location, interviewer_names, interviewer_titles, prep_notes,
            questions_to_ask, feedback, outcome, created_at, updated_at
        FROM interviews
        WHERE application_id = $1
        ORDER BY scheduled_at ASC NULLS LAST, created_at ASC
    """
    records = await fetch_all(query, application_id)
    return [InterviewResponse(**record_to_dict(r)) for r in records]


@router.put("/{application_id}/interview/{interview_id}", response_model=InterviewResponse)
async def update_interview(
    application_id: UUID,
    interview_id: UUID,
    update: InterviewUpdate
) -> InterviewResponse:
    """
    Update an interview's details or outcome.
    """
    # Build update query dynamically
    updates = []
    params = []
    param_idx = 1

    update_fields = {
        "stage": update.stage,
        "scheduled_at": update.scheduled_at,
        "duration_minutes": update.duration_minutes,
        "location": update.location,
        "interviewer_names": update.interviewer_names,
        "interviewer_titles": update.interviewer_titles,
        "prep_notes": update.prep_notes,
        "questions_to_ask": update.questions_to_ask,
        "feedback": update.feedback,
        "outcome": update.outcome,
    }

    for field, value in update_fields.items():
        if value is not None:
            updates.append(f"{field} = ${param_idx}")
            params.append(value)
            param_idx += 1

    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    params.extend([interview_id, application_id])
    update_clause = ", ".join(updates)

    query = f"""
        UPDATE interviews
        SET {update_clause}, updated_at = NOW()
        WHERE id = ${param_idx} AND application_id = ${param_idx + 1}
        RETURNING
            id, application_id, stage, scheduled_at, duration_minutes,
            location, interviewer_names, interviewer_titles, prep_notes,
            questions_to_ask, feedback, outcome, created_at, updated_at
    """
    record = await fetch_one(query, *params)

    if not record:
        raise HTTPException(status_code=404, detail="Interview not found")

    return InterviewResponse(**record_to_dict(record))


@router.delete("/{application_id}/interview/{interview_id}")
async def delete_interview(application_id: UUID, interview_id: UUID) -> dict:
    """
    Delete an interview.
    """
    # Check if interview exists and belongs to application
    record = await fetch_one(
        "SELECT id FROM interviews WHERE id = $1 AND application_id = $2",
        interview_id,
        application_id
    )

    if not record:
        raise HTTPException(status_code=404, detail="Interview not found")

    await execute("DELETE FROM interviews WHERE id = $1", interview_id)

    return {"status": "deleted", "interview_id": str(interview_id)}
