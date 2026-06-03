"""
Job endpoints for JobHunt API.

Handles job listing, filtering, updates, and status changes.
"""

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from models import (
    JobResponse,
    JobDetailResponse,
    JobUpdate,
    JobCreate,
    JobListResponse,
)
from utils.database import fetch_one, fetch_all, execute, record_to_dict

router = APIRouter()


@router.get("/", response_model=JobListResponse)
async def list_jobs(
    status: Optional[str] = Query(None, description="Filter by job status"),
    min_fit_score: Optional[float] = Query(None, description="Minimum fit/match score"),
    source: Optional[str] = Query(None, description="Filter by source (serpapi, linkedin, etc.)"),
    search: Optional[str] = Query(None, description="Search in title and company name"),
    sort_by: str = Query("fit_score", description="Sort field: fit_score, created_at, title"),
    sort_order: str = Query("desc", description="Sort order: asc or desc"),
    limit: int = Query(50, ge=1, le=100, description="Number of results to return"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
) -> JobListResponse:
    """
    List jobs with filters and pagination.

    Returns jobs sorted by fit_score (match_score) by default.
    """
    # Build query dynamically
    conditions = []
    params = []
    param_idx = 1

    if status:
        conditions.append(f"status = ${param_idx}")
        params.append(status)
        param_idx += 1

    if min_fit_score is not None:
        conditions.append(f"match_score >= ${param_idx}")
        params.append(min_fit_score)
        param_idx += 1

    if source:
        conditions.append(f"source = ${param_idx}")
        params.append(source)
        param_idx += 1

    if search:
        conditions.append(f"(title ILIKE ${param_idx} OR company_name ILIKE ${param_idx})")
        params.append(f"%{search}%")
        param_idx += 1

    where_clause = " AND ".join(conditions) if conditions else "1=1"

    # Validate sort field
    valid_sort_fields = {
        "fit_score": "match_score",
        "match_score": "match_score",
        "created_at": "created_at",
        "title": "title",
        "company_name": "company_name",
        "posted_at": "posted_at",
    }
    sort_field = valid_sort_fields.get(sort_by, "match_score")
    sort_direction = "DESC" if sort_order.lower() == "desc" else "ASC"

    # Handle NULL values in sorting (put NULLs last for DESC, first for ASC)
    nulls_position = "NULLS LAST" if sort_direction == "DESC" else "NULLS FIRST"

    # Count total
    count_query = f"SELECT COUNT(*) FROM jobs WHERE {where_clause}"
    count_result = await fetch_one(count_query, *params)
    total = count_result["count"] if count_result else 0

    # Fetch jobs
    query = f"""
        SELECT
            id, external_id, source, title, company_name, company_url,
            location, remote_type, salary_min, salary_max, salary_currency,
            url, posted_at, match_score, created_at, updated_at,
            category, skills_matched, skills_missing, fit_score,
            COALESCE(status, 'new') as status
        FROM jobs
        WHERE {where_clause}
        ORDER BY {sort_field} {sort_direction} {nulls_position}
        LIMIT ${param_idx} OFFSET ${param_idx + 1}
    """
    params.extend([limit, offset])

    records = await fetch_all(query, *params)
    jobs = [JobResponse(**record_to_dict(r)) for r in records]

    return JobListResponse(
        jobs=jobs,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{job_id}", response_model=JobDetailResponse)
async def get_job(job_id: UUID) -> JobDetailResponse:
    """
    Get detailed job information including company and application data.
    """
    # Fetch job with company info via join
    query = """
        SELECT
            j.id, j.external_id, j.source, j.title, j.company_name, j.company_url,
            j.location, j.remote_type, j.salary_min, j.salary_max, j.salary_currency,
            j.description, j.requirements, j.url, j.posted_at, j.expires_at,
            j.match_score, j.score_breakdown, j.raw_data, j.created_at, j.updated_at,
            j.skills_matched, j.skills_missing, j.fit_score, j.category,
            COALESCE(j.status, 'new') as status,
            c.id as company_id, c.name as c_name, c.domain, c.industry, c.size_range,
            c.founded_year, c.headquarters, c.description as c_description,
            c.linkedin_url, c.glassdoor_url, c.glassdoor_rating, c.funding_stage,
            c.total_funding, c.enriched_at, c.created_at as c_created_at,
            c.updated_at as c_updated_at
        FROM jobs j
        LEFT JOIN companies c ON LOWER(j.company_name) = LOWER(c.name)
        WHERE j.id = $1
    """
    record = await fetch_one(query, job_id)

    if not record:
        raise HTTPException(status_code=404, detail="Job not found")

    job_data = record_to_dict(record)

    # Build company response if exists
    company = None
    if job_data.get("company_id"):
        company = {
            "id": job_data["company_id"],
            "name": job_data["c_name"],
            "domain": job_data["domain"],
            "industry": job_data["industry"],
            "size_range": job_data["size_range"],
            "founded_year": job_data["founded_year"],
            "headquarters": job_data["headquarters"],
            "description": job_data["c_description"],
            "linkedin_url": job_data["linkedin_url"],
            "glassdoor_url": job_data["glassdoor_url"],
            "glassdoor_rating": job_data["glassdoor_rating"],
            "funding_stage": job_data["funding_stage"],
            "total_funding": job_data["total_funding"],
            "enriched_at": job_data["enriched_at"],
            "created_at": job_data["c_created_at"],
            "updated_at": job_data["c_updated_at"],
        }

    # Check for existing application
    app_query = """
        SELECT id, job_id, status, applied_at, resume_version, cover_letter,
               notes, next_action, next_action_date, created_at, updated_at
        FROM applications
        WHERE job_id = $1
        ORDER BY created_at DESC
        LIMIT 1
    """
    app_record = await fetch_one(app_query, job_id)
    application = record_to_dict(app_record) if app_record else None

    return JobDetailResponse(
        id=job_data["id"],
        external_id=job_data["external_id"],
        source=job_data["source"],
        title=job_data["title"],
        company_name=job_data["company_name"],
        company_url=job_data["company_url"],
        location=job_data["location"],
        remote_type=job_data["remote_type"],
        salary_min=job_data["salary_min"],
        salary_max=job_data["salary_max"],
        salary_currency=job_data["salary_currency"],
        description=job_data["description"],
        requirements=job_data["requirements"],
        url=job_data["url"],
        posted_at=job_data["posted_at"],
        expires_at=job_data["expires_at"],
        fit_score=job_data.get("fit_score") or job_data.get("match_score"),
        score_breakdown=job_data["score_breakdown"],
        raw_data=job_data["raw_data"],
        status=job_data["status"],
        category=job_data.get("category"),
        skills_matched=job_data.get("skills_matched") or [],
        skills_missing=job_data.get("skills_missing") or [],
        created_at=job_data["created_at"],
        updated_at=job_data["updated_at"],
        company=company,
        application=application,
    )


@router.post("/", response_model=JobResponse)
async def create_job(job: JobCreate) -> JobResponse:
    """
    Create a new job manually.
    """
    query = """
        INSERT INTO jobs (
            source, external_id, title, company_name, location, remote_type,
            salary_min, salary_max, salary_currency, description, requirements, url,
            raw_data
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
        RETURNING
            id, external_id, source, title, company_name, company_url,
            location, remote_type, salary_min, salary_max, salary_currency,
            url, posted_at, match_score, created_at, updated_at,
            'new' as status
    """
    record = await fetch_one(
        query,
        job.source,
        job.external_id,
        job.title,
        job.company_name,
        job.location,
        job.remote_type.value if job.remote_type else None,
        job.salary_min,
        job.salary_max,
        job.salary_currency,
        job.description,
        job.requirements,
        job.url,
        {"status": "new"},
    )

    if not record:
        raise HTTPException(status_code=500, detail="Failed to create job")

    return JobResponse(**record_to_dict(record))


@router.put("/{job_id}", response_model=JobResponse)
async def update_job(job_id: UUID, update: JobUpdate) -> JobResponse:
    """
    Update job status, priority, notes, or match score.
    """
    # Build update query dynamically
    updates = []
    params = []
    param_idx = 1

    if update.status is not None:
        updates.append(f"raw_data = jsonb_set(COALESCE(raw_data, '{{}}'::jsonb), "
                      f"'{{status}}', ${param_idx}::jsonb)")
        params.append(f'"{update.status}"')
        param_idx += 1

    if update.priority is not None:
        updates.append(f"raw_data = jsonb_set(COALESCE(raw_data, '{{}}'::jsonb), "
                      f"'{{priority}}', ${param_idx}::jsonb)")
        params.append(str(update.priority))
        param_idx += 1

    if update.notes is not None:
        updates.append(f"raw_data = jsonb_set(COALESCE(raw_data, '{{}}'::jsonb), "
                      f"'{{notes}}', ${param_idx}::jsonb)")
        params.append(f'"{update.notes}"')
        param_idx += 1

    if update.match_score is not None:
        updates.append(f"match_score = ${param_idx}")
        params.append(float(update.match_score))
        param_idx += 1

    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    params.append(job_id)
    update_clause = ", ".join(updates)

    query = f"""
        UPDATE jobs
        SET {update_clause}, updated_at = NOW()
        WHERE id = ${param_idx}
        RETURNING
            id, external_id, source, title, company_name, company_url,
            location, remote_type, salary_min, salary_max, salary_currency,
            url, posted_at, match_score, created_at, updated_at,
            COALESCE((raw_data->>'status')::text, 'new') as status
    """
    record = await fetch_one(query, *params)

    if not record:
        raise HTTPException(status_code=404, detail="Job not found")

    return JobResponse(**record_to_dict(record))


@router.post("/{job_id}/interested", response_model=JobResponse)
async def mark_interested(job_id: UUID) -> JobResponse:
    """
    Mark a job as interested, moving it to the pipeline.
    """
    query = """
        UPDATE jobs
        SET raw_data = jsonb_set(COALESCE(raw_data, '{}'::jsonb), '{status}', '"interested"'::jsonb),
            updated_at = NOW()
        WHERE id = $1
        RETURNING
            id, external_id, source, title, company_name, company_url,
            location, remote_type, salary_min, salary_max, salary_currency,
            url, posted_at, match_score, created_at, updated_at,
            'interested' as status
    """
    record = await fetch_one(query, job_id)

    if not record:
        raise HTTPException(status_code=404, detail="Job not found")

    return JobResponse(**record_to_dict(record))


@router.post("/{job_id}/dismiss", response_model=JobResponse)
async def dismiss_job(job_id: UUID, reason: Optional[str] = None) -> JobResponse:
    """
    Dismiss a job from the pipeline.
    """
    # Update status and optionally add dismiss reason
    if reason:
        query = """
            UPDATE jobs
            SET raw_data = jsonb_set(
                jsonb_set(COALESCE(raw_data, '{}'::jsonb), '{status}', '"dismissed"'::jsonb),
                '{dismiss_reason}', $2::jsonb
            ),
            updated_at = NOW()
            WHERE id = $1
            RETURNING
                id, external_id, source, title, company_name, company_url,
                location, remote_type, salary_min, salary_max, salary_currency,
                url, posted_at, match_score, created_at, updated_at,
                'dismissed' as status
        """
        record = await fetch_one(query, job_id, f'"{reason}"')
    else:
        query = """
            UPDATE jobs
            SET raw_data = jsonb_set(COALESCE(raw_data, '{}'::jsonb), '{status}', '"dismissed"'::jsonb),
                updated_at = NOW()
            WHERE id = $1
            RETURNING
                id, external_id, source, title, company_name, company_url,
                location, remote_type, salary_min, salary_max, salary_currency,
                url, posted_at, match_score, created_at, updated_at,
                'dismissed' as status
        """
        record = await fetch_one(query, job_id)

    if not record:
        raise HTTPException(status_code=404, detail="Job not found")

    return JobResponse(**record_to_dict(record))


@router.delete("/{job_id}")
async def delete_job(job_id: UUID) -> dict:
    """
    Delete a job and its associated applications/interviews.
    """
    # Check if job exists first
    check_query = "SELECT id FROM jobs WHERE id = $1"
    record = await fetch_one(check_query, job_id)

    if not record:
        raise HTTPException(status_code=404, detail="Job not found")

    # Delete job (cascade will handle applications and interviews)
    await execute("DELETE FROM jobs WHERE id = $1", job_id)

    return {"status": "deleted", "job_id": str(job_id)}


@router.post("/{job_id}/star")
async def toggle_star(job_id: UUID) -> dict[str, Any]:
    """Toggle starred status for a job."""
    # Get current status
    job = await fetch_one("SELECT starred FROM jobs WHERE id = $1", job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    job_data = record_to_dict(job)
    new_status = not (job_data.get("starred") or False)
    await execute(
        "UPDATE jobs SET starred = $1, updated_at = NOW() WHERE id = $2",
        new_status, job_id
    )
    return {"id": str(job_id), "starred": new_status}


@router.post("/{job_id}/generate-cover-letter")
async def generate_cover_letter_for_job(
    job_id: UUID,
    tone: str = Query("professional", description="Tone: professional, conversational, technical")
) -> dict[str, Any]:
    """Generate a personalized cover letter for a job using LLM."""
    from activities.cover_letter import call_llm
    from prompts.cover_letter import (
        COVER_LETTER_SYSTEM_PROMPT,
        COVER_LETTER_USER_TEMPLATE,
        format_requirements_list,
        format_experience_list,
        get_tone_description,
    )
    from utils.content_formatter import format_cover_letter, validate_cover_letter, clean_text

    # Get job details
    job = await fetch_one(
        """
        SELECT j.*, c.name as company_name_full, c.description as company_desc,
               c.industry, c.employee_count
        FROM jobs j
        LEFT JOIN companies c ON j.company_id = c.id
        WHERE j.id = $1
        """,
        job_id
    )
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    job_data = record_to_dict(job)

    # Get default resume
    resume = await fetch_one(
        "SELECT * FROM resume_profiles WHERE is_default = TRUE LIMIT 1"
    )
    if not resume:
        raise HTTPException(status_code=400, detail="No default resume profile found")

    resume_data = record_to_dict(resume)

    # Build job dict for LLM
    job_for_llm = {
        "title": job_data.get("title", "Unknown Position"),
        "description": job_data.get("description", ""),
        "requirements": job_data.get("requirements", ""),
        "url": job_data.get("url", ""),
    }

    # Build company dict
    company_for_llm = {
        "name": job_data.get("company_name_full") or job_data.get("company_name", ""),
        "description": job_data.get("company_desc", ""),
        "industry": job_data.get("industry", ""),
    }

    # Build resume dict
    parsed_data = resume_data.get("parsed_data") or {}
    experiences = parsed_data.get("experiences", []) if isinstance(parsed_data, dict) else []
    if not experiences and resume_data.get("experience_summary"):
        experiences = [{"description": resume_data["experience_summary"]}]

    resume_for_llm = {
        "experiences": experiences,
        "skills": resume_data.get("skills", []),
        "achievements": resume_data.get("key_achievements", []),
    }

    # Format requirements (convert text to list if needed)
    requirements_raw = job_for_llm.get("requirements", "")
    if isinstance(requirements_raw, str) and requirements_raw:
        # Split by newlines or bullet points
        requirements_list = [
            r.strip().lstrip("•-*").strip()
            for r in requirements_raw.split("\n")
            if r.strip() and len(r.strip()) > 2
        ]
    elif isinstance(requirements_raw, list):
        requirements_list = requirements_raw
    else:
        requirements_list = []
    requirements_text = format_requirements_list(requirements_list)

    # Format relevant experience
    relevant_experience = format_experience_list(experiences[:3])
    if resume_for_llm.get("achievements"):
        relevant_experience += "\n\n**Key Achievements:**\n"
        relevant_experience += "\n".join(f"- {a}" for a in resume_for_llm["achievements"][:5])

    # Get tone description
    tone_desc = get_tone_description(tone)

    # Build company info
    company_info_parts = []
    if company_for_llm.get("description"):
        company_info_parts.append(f"About: {company_for_llm['description']}")
    if company_for_llm.get("industry"):
        company_info_parts.append(f"Industry: {company_for_llm['industry']}")
    company_info = "\n".join(company_info_parts) or "Company information not available"

    # Build the prompt
    user_prompt = COVER_LETTER_USER_TEMPLATE.format(
        job_title=job_for_llm["title"],
        company_name=company_for_llm["name"],
        job_description=job_for_llm["description"][:2000],
        company_info=company_info,
        requirements=requirements_text,
        relevant_experience=relevant_experience,
        tone=f"{tone} - {tone_desc}",
    )

    # Call LLM
    try:
        response = await call_llm(
            system_prompt=COVER_LETTER_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=0.7,
            max_tokens=800,
        )
        cover_letter_text = clean_text(response.content)

        # Validate
        is_valid, issues = validate_cover_letter(cover_letter_text)

        # Format versions
        format_versions = {
            "text": format_cover_letter(
                cover_letter_text, format="text",
                company_name=company_for_llm["name"], job_title=job_for_llm["title"]
            ),
            "markdown": format_cover_letter(
                cover_letter_text, format="markdown",
                company_name=company_for_llm["name"], job_title=job_for_llm["title"]
            ),
        }

        return {
            "job_id": str(job_id),
            "cover_letter": cover_letter_text,
            "format_versions": format_versions,
            "validation": {"is_valid": is_valid, "issues": issues},
            "metadata": {
                "model": response.model,
                "input_tokens": response.input_tokens,
                "output_tokens": response.output_tokens,
                "latency_ms": response.latency_ms,
                "tone": tone,
            },
            "generated_at": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate cover letter: {str(e)}")
