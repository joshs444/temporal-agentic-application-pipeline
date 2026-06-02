"""
Dashboard and analytics endpoints for JobHunt API.

Provides statistics, pipeline views, activity feeds, and search configuration
management.
"""

from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from models import (
    DashboardStats,
    PipelineResponse,
    PipelineStage,
    ActivityEvent,
    ActivityFeed,
    SearchConfigResponse,
    SearchConfigCreate,
    SearchConfigUpdate,
    JobResponse,
)
from utils.database import fetch_one, fetch_all, execute, record_to_dict, records_to_dicts

router = APIRouter()


@router.get("/stats", response_model=DashboardStats)
async def get_stats() -> DashboardStats:
    """
    Get overall dashboard statistics.

    Returns counts, rates, and averages for jobs, applications, and interviews.
    """
    # Get current time bounds
    now = datetime.utcnow()
    week_ago = now - timedelta(days=7)

    # Total jobs
    total_jobs_result = await fetch_one("SELECT COUNT(*) as count FROM jobs")
    jobs_total = total_jobs_result["count"] if total_jobs_result else 0

    # Jobs this week
    jobs_week_result = await fetch_one(
        "SELECT COUNT(*) as count FROM jobs WHERE created_at >= $1",
        week_ago
    )
    jobs_this_week = jobs_week_result["count"] if jobs_week_result else 0

    # Total applications
    total_apps_result = await fetch_one("SELECT COUNT(*) as count FROM applications")
    applications_total = total_apps_result["count"] if total_apps_result else 0

    # Applications this week
    apps_week_result = await fetch_one(
        "SELECT COUNT(*) as count FROM applications WHERE created_at >= $1",
        week_ago
    )
    applications_this_week = apps_week_result["count"] if apps_week_result else 0

    # Interviews scheduled (future interviews)
    interviews_result = await fetch_one(
        """
        SELECT COUNT(*) as count FROM interviews
        WHERE scheduled_at >= $1 AND outcome IS NULL
        """,
        now
    )
    interviews_scheduled = interviews_result["count"] if interviews_result else 0

    # Response rate (applications that got interviews / total applications)
    response_result = await fetch_one(
        """
        SELECT
            COUNT(DISTINCT a.id) as total_apps,
            COUNT(DISTINCT CASE WHEN i.id IS NOT NULL THEN a.id END) as apps_with_interviews
        FROM applications a
        LEFT JOIN interviews i ON a.id = i.application_id
        WHERE a.status != 'draft'
        """
    )
    if response_result and response_result["total_apps"] > 0:
        response_rate = (
            response_result["apps_with_interviews"] / response_result["total_apps"]
        ) * 100
    else:
        response_rate = 0.0

    # Average fit score
    avg_score_result = await fetch_one(
        "SELECT AVG(match_score) as avg_score FROM jobs WHERE match_score IS NOT NULL"
    )
    avg_fit_score = (
        float(avg_score_result["avg_score"])
        if avg_score_result and avg_score_result["avg_score"]
        else None
    )

    return DashboardStats(
        jobs_total=jobs_total,
        jobs_this_week=jobs_this_week,
        applications_total=applications_total,
        applications_this_week=applications_this_week,
        interviews_scheduled=interviews_scheduled,
        response_rate=round(response_rate, 1),
        avg_fit_score=round(avg_fit_score, 1) if avg_fit_score else None,
    )


@router.get("/pipeline", response_model=PipelineResponse)
async def get_pipeline(
    limit_per_stage: int = Query(20, ge=1, le=50, description="Max jobs per stage"),
) -> PipelineResponse:
    """
    Get jobs grouped by status for Kanban-style pipeline view.

    Stages: new, interested, applying, applied, interviewing, offer, rejected, dismissed
    """
    # Define pipeline stages in order
    stages = [
        "new",
        "interested",
        "applying",
        "applied",
        "interviewing",
        "offer",
        "rejected",
        "dismissed",
    ]

    pipeline_stages = []
    total = 0

    for stage in stages:
        # Get count for this stage
        count_result = await fetch_one(
            """
            SELECT COUNT(*) as count FROM jobs
            WHERE COALESCE((raw_data->>'status')::text, 'new') = $1
            """,
            stage
        )
        count = count_result["count"] if count_result else 0
        total += count

        # Get jobs for this stage
        records = await fetch_all(
            """
            SELECT
                id, external_id, source, title, company_name, company_url,
                location, remote_type, salary_min, salary_max, salary_currency,
                url, posted_at, match_score, created_at, updated_at,
                COALESCE((raw_data->>'status')::text, 'new') as status
            FROM jobs
            WHERE COALESCE((raw_data->>'status')::text, 'new') = $1
            ORDER BY match_score DESC NULLS LAST, created_at DESC
            LIMIT $2
            """,
            stage,
            limit_per_stage
        )
        jobs = [JobResponse(**record_to_dict(r)) for r in records]

        pipeline_stages.append(PipelineStage(
            status=stage,
            count=count,
            jobs=jobs,
        ))

    return PipelineResponse(
        stages=pipeline_stages,
        total=total,
    )


@router.get("/activity", response_model=ActivityFeed)
async def get_activity(
    days: int = Query(7, ge=1, le=30, description="Number of days to look back"),
) -> ActivityFeed:
    """
    Get recent activity feed.

    Includes job discoveries, applications, interviews, and status changes.
    """
    since = datetime.utcnow() - timedelta(days=days)
    events = []

    # Recent jobs discovered
    job_records = await fetch_all(
        """
        SELECT id, title, company_name, created_at
        FROM jobs
        WHERE created_at >= $1
        ORDER BY created_at DESC
        LIMIT 50
        """,
        since
    )
    for job in job_records:
        events.append(ActivityEvent(
            id=job["id"],
            event_type="job_discovered",
            title=f"New job: {job['title']}",
            description=f"at {job['company_name']}",
            entity_type="job",
            entity_id=job["id"],
            occurred_at=job["created_at"],
        ))

    # Recent applications
    app_records = await fetch_all(
        """
        SELECT a.id, a.status, a.created_at, a.applied_at, j.title, j.company_name
        FROM applications a
        JOIN jobs j ON a.job_id = j.id
        WHERE a.created_at >= $1 OR a.applied_at >= $1
        ORDER BY COALESCE(a.applied_at, a.created_at) DESC
        LIMIT 50
        """,
        since
    )
    for app in app_records:
        if app["applied_at"] and app["applied_at"] >= since:
            events.append(ActivityEvent(
                id=app["id"],
                event_type="application_sent",
                title=f"Applied to {app['title']}",
                description=f"at {app['company_name']}",
                entity_type="application",
                entity_id=app["id"],
                occurred_at=app["applied_at"],
            ))
        elif app["created_at"] >= since and app["status"] == "draft":
            events.append(ActivityEvent(
                id=app["id"],
                event_type="application_drafted",
                title=f"Draft created for {app['title']}",
                description=f"at {app['company_name']}",
                entity_type="application",
                entity_id=app["id"],
                occurred_at=app["created_at"],
            ))

    # Recent interviews scheduled
    interview_records = await fetch_all(
        """
        SELECT i.id, i.stage, i.scheduled_at, i.created_at, j.title, j.company_name
        FROM interviews i
        JOIN applications a ON i.application_id = a.id
        JOIN jobs j ON a.job_id = j.id
        WHERE i.created_at >= $1
        ORDER BY i.created_at DESC
        LIMIT 50
        """,
        since
    )
    for interview in interview_records:
        events.append(ActivityEvent(
            id=interview["id"],
            event_type="interview_scheduled",
            title=f"{interview['stage'].replace('_', ' ').title()} interview scheduled",
            description=f"for {interview['title']} at {interview['company_name']}",
            entity_type="interview",
            entity_id=interview["id"],
            occurred_at=interview["created_at"],
        ))

    # Sort all events by time
    events.sort(key=lambda e: e.occurred_at, reverse=True)

    return ActivityFeed(
        events=events[:100],  # Limit total events
        days=days,
    )


@router.get("/upcoming-interviews")
async def get_upcoming_interviews(
    days: int = Query(14, ge=1, le=30, description="Days to look ahead"),
) -> dict:
    """
    Get upcoming interviews in the next N days.
    """
    now = datetime.utcnow()
    future = now + timedelta(days=days)

    records = await fetch_all(
        """
        SELECT
            i.id, i.stage, i.scheduled_at, i.duration_minutes, i.location,
            i.interviewer_names, i.prep_notes,
            j.title, j.company_name, j.url as job_url
        FROM interviews i
        JOIN applications a ON i.application_id = a.id
        JOIN jobs j ON a.job_id = j.id
        WHERE i.scheduled_at >= $1 AND i.scheduled_at <= $2
        AND i.outcome IS NULL
        ORDER BY i.scheduled_at ASC
        """,
        now,
        future
    )

    return {
        "interviews": records_to_dicts(records),
        "total": len(records),
        "period_days": days,
    }


# Search configuration endpoints
@router.get("/search-configs", response_model=list[SearchConfigResponse])
async def get_search_configs() -> list[SearchConfigResponse]:
    """
    Get all saved search configurations.
    """
    records = await fetch_all(
        """
        SELECT
            id, name, query_params, is_active, last_run_at,
            run_frequency_hours, created_at, updated_at
        FROM search_queries
        ORDER BY name ASC
        """
    )
    return [SearchConfigResponse(**record_to_dict(r)) for r in records]


@router.get("/search-configs/{config_id}", response_model=SearchConfigResponse)
async def get_search_config(config_id: UUID) -> SearchConfigResponse:
    """
    Get a specific search configuration.
    """
    record = await fetch_one(
        """
        SELECT
            id, name, query_params, is_active, last_run_at,
            run_frequency_hours, created_at, updated_at
        FROM search_queries
        WHERE id = $1
        """,
        config_id
    )

    if not record:
        raise HTTPException(status_code=404, detail="Search config not found")

    return SearchConfigResponse(**record_to_dict(record))


@router.post("/search-configs", response_model=SearchConfigResponse)
async def create_search_config(config: SearchConfigCreate) -> SearchConfigResponse:
    """
    Create a new search configuration.
    """
    # Check for duplicate name
    existing = await fetch_one(
        "SELECT id FROM search_queries WHERE LOWER(name) = LOWER($1)",
        config.name
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail="Search config with this name already exists"
        )

    record = await fetch_one(
        """
        INSERT INTO search_queries (
            name, query_params, is_active, run_frequency_hours
        ) VALUES ($1, $2, $3, $4)
        RETURNING
            id, name, query_params, is_active, last_run_at,
            run_frequency_hours, created_at, updated_at
        """,
        config.name,
        config.query_params,
        config.is_active,
        config.run_frequency_hours,
    )

    if not record:
        raise HTTPException(status_code=500, detail="Failed to create search config")

    return SearchConfigResponse(**record_to_dict(record))


@router.put("/search-configs/{config_id}", response_model=SearchConfigResponse)
async def update_search_config(
    config_id: UUID,
    update: SearchConfigUpdate
) -> SearchConfigResponse:
    """
    Update a search configuration.
    """
    # Build update query dynamically
    updates = []
    params = []
    param_idx = 1

    if update.name is not None:
        updates.append(f"name = ${param_idx}")
        params.append(update.name)
        param_idx += 1

    if update.query_params is not None:
        updates.append(f"query_params = ${param_idx}")
        params.append(update.query_params)
        param_idx += 1

    if update.is_active is not None:
        updates.append(f"is_active = ${param_idx}")
        params.append(update.is_active)
        param_idx += 1

    if update.run_frequency_hours is not None:
        updates.append(f"run_frequency_hours = ${param_idx}")
        params.append(update.run_frequency_hours)
        param_idx += 1

    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    params.append(config_id)
    update_clause = ", ".join(updates)

    record = await fetch_one(
        f"""
        UPDATE search_queries
        SET {update_clause}, updated_at = NOW()
        WHERE id = ${param_idx}
        RETURNING
            id, name, query_params, is_active, last_run_at,
            run_frequency_hours, created_at, updated_at
        """,
        *params
    )

    if not record:
        raise HTTPException(status_code=404, detail="Search config not found")

    return SearchConfigResponse(**record_to_dict(record))


@router.delete("/search-configs/{config_id}")
async def delete_search_config(config_id: UUID) -> dict:
    """
    Delete a search configuration.
    """
    record = await fetch_one(
        "SELECT id FROM search_queries WHERE id = $1",
        config_id
    )

    if not record:
        raise HTTPException(status_code=404, detail="Search config not found")

    await execute("DELETE FROM search_queries WHERE id = $1", config_id)

    return {"status": "deleted", "config_id": str(config_id)}


@router.get("/job-sources")
async def get_job_sources() -> dict:
    """
    Get breakdown of jobs by source.
    """
    records = await fetch_all(
        """
        SELECT source, COUNT(*) as count
        FROM jobs
        GROUP BY source
        ORDER BY count DESC
        """
    )

    return {
        "sources": records_to_dicts(records),
        "total": sum(r["count"] for r in records),
    }


@router.get("/application-funnel")
async def get_application_funnel() -> dict:
    """
    Get application funnel metrics.

    Shows conversion rates at each stage of the application process.
    """
    # Get counts at each stage
    stages = ["draft", "applied", "interviewing", "offered", "rejected", "withdrawn"]

    funnel = []
    for stage in stages:
        result = await fetch_one(
            "SELECT COUNT(*) as count FROM applications WHERE status = $1",
            stage
        )
        funnel.append({
            "stage": stage,
            "count": result["count"] if result else 0,
        })

    # Calculate conversion rates
    total_apps = sum(s["count"] for s in funnel if s["stage"] != "draft")
    applied = next((s["count"] for s in funnel if s["stage"] == "applied"), 0)
    interviewing = next((s["count"] for s in funnel if s["stage"] == "interviewing"), 0)
    offered = next((s["count"] for s in funnel if s["stage"] == "offered"), 0)

    # Active applications (applied + interviewing)
    active = applied + interviewing

    return {
        "funnel": funnel,
        "metrics": {
            "total_applications": total_apps,
            "active_applications": active,
            "interview_rate": round((interviewing / total_apps * 100), 1) if total_apps > 0 else 0,
            "offer_rate": round((offered / total_apps * 100), 1) if total_apps > 0 else 0,
        },
    }
