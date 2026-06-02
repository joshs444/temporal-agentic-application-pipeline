"""
Company endpoints for JobHunt API.

Handles company information and enrichment data.
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from models import (
    CompanyResponse,
    CompanyCreate,
    CompanyUpdate,
    CompanyListResponse,
)
from utils.database import fetch_one, fetch_all, execute, record_to_dict

router = APIRouter()


@router.get("/", response_model=CompanyListResponse)
async def list_companies(
    industry: Optional[str] = Query(None, description="Filter by industry"),
    size_range: Optional[str] = Query(None, description="Filter by company size"),
    search: Optional[str] = Query(None, description="Search in company name"),
    limit: int = Query(50, ge=1, le=100, description="Number of results to return"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
) -> CompanyListResponse:
    """
    List all companies with optional filters.
    """
    conditions = []
    params = []
    param_idx = 1

    if industry:
        conditions.append(f"industry ILIKE ${param_idx}")
        params.append(f"%{industry}%")
        param_idx += 1

    if size_range:
        conditions.append(f"size_range = ${param_idx}")
        params.append(size_range)
        param_idx += 1

    if search:
        conditions.append(f"name ILIKE ${param_idx}")
        params.append(f"%{search}%")
        param_idx += 1

    where_clause = " AND ".join(conditions) if conditions else "1=1"

    # Count total
    count_query = f"SELECT COUNT(*) FROM companies WHERE {where_clause}"
    count_result = await fetch_one(count_query, *params)
    total = count_result["count"] if count_result else 0

    # Fetch companies
    query = f"""
        SELECT
            id, name, domain, industry, size_range, founded_year,
            headquarters, description, linkedin_url, glassdoor_url,
            glassdoor_rating, funding_stage, total_funding, enriched_at,
            created_at, updated_at
        FROM companies
        WHERE {where_clause}
        ORDER BY name ASC
        LIMIT ${param_idx} OFFSET ${param_idx + 1}
    """
    params.extend([limit, offset])

    records = await fetch_all(query, *params)
    companies = [CompanyResponse(**record_to_dict(r)) for r in records]

    return CompanyListResponse(
        companies=companies,
        total=total,
    )


@router.get("/{company_id}", response_model=CompanyResponse)
async def get_company(company_id: UUID) -> CompanyResponse:
    """
    Get detailed company information.
    """
    query = """
        SELECT
            id, name, domain, industry, size_range, founded_year,
            headquarters, description, linkedin_url, glassdoor_url,
            glassdoor_rating, funding_stage, total_funding, enriched_at,
            created_at, updated_at
        FROM companies
        WHERE id = $1
    """
    record = await fetch_one(query, company_id)

    if not record:
        raise HTTPException(status_code=404, detail="Company not found")

    return CompanyResponse(**record_to_dict(record))


@router.get("/by-name/{company_name}", response_model=CompanyResponse)
async def get_company_by_name(company_name: str) -> CompanyResponse:
    """
    Get company information by name (case-insensitive).
    """
    query = """
        SELECT
            id, name, domain, industry, size_range, founded_year,
            headquarters, description, linkedin_url, glassdoor_url,
            glassdoor_rating, funding_stage, total_funding, enriched_at,
            created_at, updated_at
        FROM companies
        WHERE LOWER(name) = LOWER($1)
    """
    record = await fetch_one(query, company_name)

    if not record:
        raise HTTPException(status_code=404, detail="Company not found")

    return CompanyResponse(**record_to_dict(record))


@router.post("/", response_model=CompanyResponse)
async def create_company(company: CompanyCreate) -> CompanyResponse:
    """
    Create a new company record.
    """
    # Check if company already exists
    existing = await fetch_one(
        "SELECT id FROM companies WHERE LOWER(name) = LOWER($1)",
        company.name
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail="Company with this name already exists"
        )

    query = """
        INSERT INTO companies (
            name, domain, industry, size_range, description
        ) VALUES ($1, $2, $3, $4, $5)
        RETURNING
            id, name, domain, industry, size_range, founded_year,
            headquarters, description, linkedin_url, glassdoor_url,
            glassdoor_rating, funding_stage, total_funding, enriched_at,
            created_at, updated_at
    """
    record = await fetch_one(
        query,
        company.name,
        company.domain,
        company.industry,
        company.size_range,
        company.description,
    )

    if not record:
        raise HTTPException(status_code=500, detail="Failed to create company")

    return CompanyResponse(**record_to_dict(record))


@router.put("/{company_id}", response_model=CompanyResponse)
async def update_company(company_id: UUID, update: CompanyUpdate) -> CompanyResponse:
    """
    Update company information.
    """
    # Build update query dynamically
    updates = []
    params = []
    param_idx = 1

    update_fields = {
        "domain": update.domain,
        "industry": update.industry,
        "size_range": update.size_range,
        "founded_year": update.founded_year,
        "headquarters": update.headquarters,
        "description": update.description,
        "linkedin_url": update.linkedin_url,
    }

    for field, value in update_fields.items():
        if value is not None:
            updates.append(f"{field} = ${param_idx}")
            params.append(value)
            param_idx += 1

    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    params.append(company_id)
    update_clause = ", ".join(updates)

    query = f"""
        UPDATE companies
        SET {update_clause}, updated_at = NOW()
        WHERE id = ${param_idx}
        RETURNING
            id, name, domain, industry, size_range, founded_year,
            headquarters, description, linkedin_url, glassdoor_url,
            glassdoor_rating, funding_stage, total_funding, enriched_at,
            created_at, updated_at
    """
    record = await fetch_one(query, *params)

    if not record:
        raise HTTPException(status_code=404, detail="Company not found")

    return CompanyResponse(**record_to_dict(record))


@router.delete("/{company_id}")
async def delete_company(company_id: UUID) -> dict:
    """
    Delete a company record.

    Note: This will not delete associated jobs.
    """
    # Check if company exists
    record = await fetch_one("SELECT id FROM companies WHERE id = $1", company_id)

    if not record:
        raise HTTPException(status_code=404, detail="Company not found")

    await execute("DELETE FROM companies WHERE id = $1", company_id)

    return {"status": "deleted", "company_id": str(company_id)}


@router.get("/{company_id}/jobs")
async def get_company_jobs(
    company_id: UUID,
    limit: int = Query(50, ge=1, le=100),
) -> dict:
    """
    Get all jobs from a specific company.
    """
    # Get company name first
    company = await fetch_one("SELECT name FROM companies WHERE id = $1", company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    # Get jobs for this company
    query = """
        SELECT
            id, external_id, source, title, company_name, company_url,
            location, remote_type, salary_min, salary_max, salary_currency,
            url, posted_at, match_score, created_at, updated_at,
            COALESCE((raw_data->>'status')::text, 'new') as status
        FROM jobs
        WHERE LOWER(company_name) = LOWER($1)
        ORDER BY created_at DESC
        LIMIT $2
    """
    records = await fetch_all(query, company["name"], limit)

    return {
        "company_name": company["name"],
        "jobs": [record_to_dict(r) for r in records],
        "total": len(records),
    }
