"""
Temporal activities for job discovery and processing.

These activities handle job searching, parsing, deduplication, and database operations.
"""

import json
import os
import time
from datetime import datetime
from typing import Any, Optional

from temporalio import activity

# Import will work when running in the job-worker context
try:
    from clients.serpapi import JobPosting, SerpApiClient, SerpApiError
    from utils.job_parser import (
        extract_tech_stack,
        parse_experience_level,
        parse_remote_type,
        parse_salary,
    )
except ImportError:
    # For type checking and development
    from job_worker.clients.serpapi import JobPosting, SerpApiClient, SerpApiError
    from job_worker.utils.job_parser import (
        extract_tech_stack,
        parse_experience_level,
        parse_remote_type,
        parse_salary,
    )

import asyncpg
import httpx
from openai import AsyncOpenAI


# Configuration
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://jobhunt:jobhunt_secret@localhost:5433/jobhunt_db"
)

# Provider/model config is centralized in utils.llm_config (provider-agnostic).
from utils.llm_config import LLM_MODEL, get_llm_client as _get_llm_client


async def get_db_connection() -> asyncpg.Connection:
    """Get a database connection."""
    return await asyncpg.connect(DATABASE_URL)


async def get_llm_client() -> AsyncOpenAI:
    """Get the configured OpenAI-compatible LLM client."""
    return _get_llm_client()


@activity.defn
async def discover_jobs(search_config: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Run a job search based on the provided configuration and return new jobs.

    This activity:
    1. Executes the search via SerpApi
    2. Deduplicates against existing jobs in the database
    3. Returns only jobs not already in the system

    Args:
        search_config: Configuration dict with:
            - query: Search query string
            - locations: List of locations to search
            - companies: Optional list of target companies
            - max_results: Optional max results per location (default 50)
            - chips: Optional SerpApi filter chips

    Returns:
        List of new job postings as dictionaries.
    """
    activity.logger.info(f"Starting job discovery with config: {search_config}")

    query = search_config.get("query", "")
    locations = search_config.get("locations", ["Remote"])
    max_results = search_config.get("max_results", 50)
    chips = search_config.get("chips")
    target_companies = search_config.get("companies", [])

    if not query:
        activity.logger.warning("Empty query provided, skipping search")
        return []

    client = SerpApiClient()
    all_jobs: list[JobPosting] = []

    # Search each location
    for location in locations:
        activity.heartbeat(f"Searching {location}...")

        try:
            jobs = await client.search_jobs_all_pages(
                query=query,
                location=location,
                max_pages=(max_results + 9) // 10,
                chips=chips,
            )
            activity.logger.info(f"Found {len(jobs)} jobs in {location}")
            all_jobs.extend(jobs)

        except SerpApiError as e:
            activity.logger.error(f"SerpApi error for {location}: {e}")
            continue

    # Filter by target companies if specified
    if target_companies:
        target_companies_lower = [c.lower() for c in target_companies]
        all_jobs = [
            job for job in all_jobs
            if any(tc in job.company_name.lower() for tc in target_companies_lower)
        ]
        activity.logger.info(f"Filtered to {len(all_jobs)} jobs from target companies")

    # Deduplicate against database
    new_jobs = await _dedupe_jobs(all_jobs)
    activity.logger.info(f"After deduplication: {len(new_jobs)} new jobs")

    return [job.to_dict() for job in new_jobs]


async def _dedupe_jobs(jobs: list[JobPosting]) -> list[JobPosting]:
    """
    Remove jobs that already exist in the database.

    Args:
        jobs: List of job postings to check.

    Returns:
        List of jobs not already in the database.
    """
    if not jobs:
        return []

    try:
        conn = await get_db_connection()
        try:
            # Get existing external IDs
            external_ids = [job.external_id for job in jobs]
            existing = await conn.fetch(
                """
                SELECT external_id FROM jobs
                WHERE external_id = ANY($1::text[])
                """,
                external_ids,
            )
            existing_ids = {row["external_id"] for row in existing}

            # Filter out existing jobs
            new_jobs = [
                job for job in jobs
                if job.external_id not in existing_ids
            ]
            return new_jobs

        finally:
            await conn.close()

    except Exception as e:
        activity.logger.warning(f"Database check failed, returning all jobs: {e}")
        return jobs


@activity.defn
async def parse_job_requirements(job_id: str) -> dict[str, Any]:
    """
    Use LLM to extract structured requirements from a job description.

    Args:
        job_id: The database ID of the job to parse.

    Returns:
        Dictionary containing:
            - required_skills: List of required skills
            - preferred_skills: List of preferred/nice-to-have skills
            - years_experience_min: Minimum years required
            - years_experience_max: Maximum years mentioned
            - education: Required education level
            - certifications: Any required certifications
            - experience_level: Inferred level (entry, mid, senior, etc.)
            - tech_stack: Extracted technologies
    """
    activity.logger.info(f"Parsing requirements for job {job_id}")

    conn = await get_db_connection()
    try:
        # Fetch job details
        job = await conn.fetchrow(
            """
            SELECT id, title, description, company_name
            FROM jobs WHERE id = $1
            """,
            job_id,
        )

        if not job:
            activity.logger.error(f"Job {job_id} not found")
            return {"error": "Job not found"}

        title = job["title"]
        description = job["description"]
        company_name = job["company_name"]

        # Use LLM to parse requirements
        llm_client = await get_llm_client()

        prompt = f"""Analyze this job posting and extract structured requirements.

Job Title: {title}
Company: {company_name}

Job Description:
{description[:8000]}

Extract and return a JSON object with these fields:
- required_skills: array of explicitly required skills/technologies
- preferred_skills: array of nice-to-have or preferred skills
- years_experience_min: minimum years of experience required (integer or null)
- years_experience_max: maximum years mentioned (integer or null)
- education: required education level (e.g., "Bachelor's", "Master's", "PhD", or null)
- certifications: array of any required certifications
- key_responsibilities: array of main job responsibilities

Return ONLY the JSON object, no other text."""

        start_time = time.time()
        response = await llm_client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": "You are a job requirements parser. Return only valid JSON."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=2000,
        )
        latency_ms = int((time.time() - start_time) * 1000)

        # Parse LLM response
        content = response.choices[0].message.content.strip()

        # Handle potential markdown code blocks
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
            content = content.strip()

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            activity.logger.error(f"Failed to parse LLM response as JSON: {content[:200]}")
            parsed = {}

        # Add computed fields
        parsed["experience_level"] = parse_experience_level(title, description)
        parsed["tech_stack"] = extract_tech_stack(description)

        # Log LLM call (would use utils.llm_logging in production)
        activity.logger.info(
            f"LLM call completed in {latency_ms}ms, "
            f"found {len(parsed.get('required_skills', []))} required skills"
        )

        # Update job in database with parsed requirements
        await conn.execute(
            """
            UPDATE jobs
            SET parsed_requirements = $2,
                experience_level = $3,
                updated_at = NOW()
            WHERE id = $1
            """,
            job_id,
            json.dumps(parsed),
            parsed.get("experience_level"),
        )

        return parsed

    finally:
        await conn.close()


@activity.defn
async def check_job_still_active(job_id: str) -> bool:
    """
    Re-fetch a job to verify it's still posted.

    Args:
        job_id: The database ID of the job to check.

    Returns:
        True if job is still active, False otherwise.
    """
    activity.logger.info(f"Checking if job {job_id} is still active")

    conn = await get_db_connection()
    try:
        job = await conn.fetchrow(
            """
            SELECT external_id, url FROM jobs WHERE id = $1
            """,
            job_id,
        )

        if not job:
            return False

        external_id = job["external_id"]
        url = job["url"]

        # Try to fetch via SerpApi first
        if external_id:
            client = SerpApiClient()
            job_details = await client.get_job_details(external_id)
            if job_details:
                activity.logger.info(f"Job {job_id} is still active (via SerpApi)")
                return True

        # Fall back to checking URL directly
        if url:
            try:
                async with httpx.AsyncClient(timeout=10.0) as http_client:
                    response = await http_client.head(
                        url,
                        follow_redirects=True,
                        headers={"User-Agent": "Mozilla/5.0 (compatible; JobHunt/1.0)"},
                    )

                    # 404 or 410 means job is gone
                    if response.status_code in (404, 410):
                        activity.logger.info(f"Job {job_id} is no longer active (404/410)")
                        await _mark_job_inactive(conn, job_id)
                        return False

                    # 200 means likely still active
                    if response.status_code == 200:
                        activity.logger.info(f"Job {job_id} appears active (200 from URL)")
                        return True

            except httpx.RequestError as e:
                activity.logger.warning(f"Failed to check URL for job {job_id}: {e}")

        # Default to active if we can't verify
        return True

    finally:
        await conn.close()


async def _mark_job_inactive(conn: asyncpg.Connection, job_id: str) -> None:
    """Mark a job as inactive in the database."""
    await conn.execute(
        """
        UPDATE jobs
        SET status = 'inactive',
            inactive_at = NOW(),
            updated_at = NOW()
        WHERE id = $1
        """,
        job_id,
    )


@activity.defn
async def save_jobs_to_db(jobs: list[dict[str, Any]]) -> int:
    """
    Bulk insert jobs to the database.

    Args:
        jobs: List of job dictionaries (from JobPosting.to_dict()).

    Returns:
        Number of jobs successfully inserted.
    """
    if not jobs:
        return 0

    activity.logger.info(f"Saving {len(jobs)} jobs to database")

    conn = await get_db_connection()
    try:
        inserted = 0

        for job_data in jobs:
            try:
                # Convert posted_at string to datetime if needed
                posted_at = job_data.get("posted_at")
                if isinstance(posted_at, str):
                    posted_at = datetime.fromisoformat(posted_at.replace("Z", "+00:00"))

                await conn.execute(
                    """
                    INSERT INTO jobs (
                        external_id,
                        title,
                        company_name,
                        location,
                        description,
                        salary_min,
                        salary_max,
                        job_type,
                        remote_type,
                        posted_at,
                        url,
                        source,
                        requirements,
                        benefits,
                        company_logo_url,
                        company_rating,
                        company_reviews_count,
                        status,
                        created_at,
                        updated_at
                    ) VALUES (
                        $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                        $11, $12, $13, $14, $15, $16, $17, 'new', NOW(), NOW()
                    )
                    ON CONFLICT (external_id) DO NOTHING
                    """,
                    job_data.get("external_id"),
                    job_data.get("title"),
                    job_data.get("company_name"),
                    job_data.get("location"),
                    job_data.get("description"),
                    job_data.get("salary_min"),
                    job_data.get("salary_max"),
                    job_data.get("job_type"),
                    job_data.get("remote_type"),
                    posted_at,
                    job_data.get("url"),
                    job_data.get("source"),
                    json.dumps(job_data.get("requirements", [])),
                    json.dumps(job_data.get("benefits", [])),
                    job_data.get("company_logo_url"),
                    job_data.get("company_rating"),
                    job_data.get("company_reviews_count"),
                )
                inserted += 1

            except Exception as e:
                activity.logger.warning(
                    f"Failed to insert job {job_data.get('external_id')}: {e}"
                )

        activity.logger.info(f"Successfully inserted {inserted} jobs")
        return inserted

    finally:
        await conn.close()


def _serialize_config(row) -> dict[str, Any]:
    """Convert a database row to a JSON-serializable dict."""
    result = dict(row)
    # Convert datetime fields to ISO strings for Temporal serialization
    for key, value in result.items():
        if isinstance(value, datetime):
            result[key] = value.isoformat()
        elif hasattr(value, 'isoformat'):  # Other date types
            result[key] = value.isoformat()
    # Convert UUID to string
    if 'id' in result and result['id'] is not None:
        result['id'] = str(result['id'])
    return result


@activity.defn
async def get_search_configs(config_id: Optional[str] = None) -> list[dict[str, Any]]:
    """
    Load search configurations from the database.

    Args:
        config_id: Optional specific config ID to fetch, or None for all active configs.

    Returns:
        List of search configuration dictionaries.
    """
    from utils.database import get_pool

    pool = await get_pool()
    async with pool.acquire() as conn:
        if config_id:
            # Fetch specific config
            row = await conn.fetchrow(
                "SELECT * FROM search_configs WHERE id = $1",
                config_id if isinstance(config_id, str) else str(config_id)
            )
            if row:
                configs = [_serialize_config(row)]
                activity.logger.info(f"Loaded search config: {row['name']}")
                return configs
            else:
                activity.logger.warning(f"Search config not found: {config_id}")
                return []
        else:
            # Fetch all active configs
            rows = await conn.fetch(
                """
                SELECT * FROM search_configs
                WHERE is_active = TRUE
                ORDER BY name ASC
                """
            )
            configs = [_serialize_config(row) for row in rows]
            activity.logger.info(f"Loaded {len(configs)} active search configs")
            return configs


@activity.defn
async def enrich_job_company_info(job_id: str) -> dict[str, Any]:
    """
    Enrich job with additional company information.

    Args:
        job_id: The database ID of the job.

    Returns:
        Dictionary with company enrichment data.
    """
    activity.logger.info(f"Enriching company info for job {job_id}")

    conn = await get_db_connection()
    try:
        job = await conn.fetchrow(
            """
            SELECT company_name, description FROM jobs WHERE id = $1
            """,
            job_id,
        )

        if not job:
            return {"error": "Job not found"}

        company_name = job["company_name"]

        # Use LLM to extract company context from job description
        llm_client = await get_llm_client()

        prompt = f"""Based on this job posting, extract any mentioned information about the company.

Company Name: {company_name}
Job Description:
{job["description"][:4000]}

Extract and return a JSON object with:
- company_description: brief description of what the company does
- industry: the company's industry
- company_size: if mentioned (startup, small, medium, large, enterprise)
- funding_stage: if mentioned (seed, series A/B/C, public, etc.)
- tech_culture: any hints about engineering culture
- notable_facts: any notable facts mentioned

Return ONLY the JSON object."""

        start_time = time.time()
        response = await llm_client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": "You are a company information extractor. Return only valid JSON."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=1000,
        )
        latency_ms = int((time.time() - start_time) * 1000)

        content = response.choices[0].message.content.strip()

        # Handle markdown code blocks
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
            content = content.strip()

        try:
            enrichment = json.loads(content)
        except json.JSONDecodeError:
            enrichment = {"raw_response": content[:500]}

        # Update job with enrichment
        await conn.execute(
            """
            UPDATE jobs
            SET company_info = $2,
                updated_at = NOW()
            WHERE id = $1
            """,
            job_id,
            json.dumps(enrichment),
        )

        activity.logger.info(f"Company enrichment completed in {latency_ms}ms for job {job_id}")
        return enrichment

    finally:
        await conn.close()


@activity.defn
async def score_job_fit(job_id: str, user_profile: dict[str, Any]) -> dict[str, Any]:
    """
    Score how well a job matches the user's profile.

    Args:
        job_id: The database ID of the job.
        user_profile: User's profile with skills, experience, preferences.

    Returns:
        Dictionary with fit score and reasoning.
    """
    activity.logger.info(f"Scoring job fit for {job_id}")

    conn = await get_db_connection()
    try:
        job = await conn.fetchrow(
            """
            SELECT title, company_name, description, location, remote_type,
                   salary_min, salary_max, parsed_requirements, experience_level
            FROM jobs WHERE id = $1
            """,
            job_id,
        )

        if not job:
            return {"error": "Job not found", "score": 0}

        llm_client = await get_llm_client()

        prompt = f"""Score how well this job matches the candidate profile.

JOB:
Title: {job["title"]}
Company: {job["company_name"]}
Location: {job["location"]} ({job["remote_type"]})
Salary: ${job["salary_min"] or "?"} - ${job["salary_max"] or "?"}
Experience Level: {job["experience_level"] or "Unknown"}
Requirements: {job["parsed_requirements"] or "Not parsed"}

CANDIDATE PROFILE:
{json.dumps(user_profile, indent=2)}

Score the job fit from 0-100 and provide reasoning.

Return a JSON object with:
- score: integer 0-100
- skill_match: percentage of required skills the candidate has
- experience_match: how well experience level matches
- location_match: whether location/remote preferences align
- salary_match: whether salary range meets expectations
- pros: list of positive match factors
- cons: list of concerns or gaps
- recommendation: "strong_apply", "apply", "maybe", or "skip"

Return ONLY the JSON object."""

        start_time = time.time()
        response = await llm_client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": "You are a job fit scoring expert. Return only valid JSON."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=1500,
        )
        latency_ms = int((time.time() - start_time) * 1000)

        content = response.choices[0].message.content.strip()

        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
            content = content.strip()

        try:
            scoring = json.loads(content)
        except json.JSONDecodeError:
            scoring = {"score": 50, "error": "Failed to parse scoring"}

        # Update job with score
        await conn.execute(
            """
            UPDATE jobs
            SET fit_score = $2,
                fit_analysis = $3,
                updated_at = NOW()
            WHERE id = $1
            """,
            job_id,
            scoring.get("score", 0),
            json.dumps(scoring),
        )

        activity.logger.info(
            f"Job {job_id} scored {scoring.get('score', 0)} in {latency_ms}ms"
        )
        return scoring

    finally:
        await conn.close()
