"""
Workflow Activities for JobHunt

Aggregate activities used across the workflows (job discovery, enrichment,
application, follow-up, interview prep) that don't live in a more specialized
activity module.

Most activities here are fully implemented (DB reads/writes, LLM calls, Apollo
enrichment). A few are explicit placeholders pending external integration and
are clearly marked with a comment and a structured "pending_integration"-style
return so the orchestration still runs end to end:

  - send_application_email / send_follow_up_email
        thin wrappers; real sending goes through activities.email.send_outreach_email
  - research_company_recent / research_interviewer
        interview-prep research stubs
        (see also activities.company.research_company_culture)
"""

import os
from datetime import datetime, timezone
from typing import Optional

import asyncpg
from temporalio import activity

from utils.llm import extract_json
from utils.llm_config import LLM_MODEL
from utils.profile import candidate_first_name

# Configuration
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://jobhunt:jobhunt_secret@localhost:5433/jobhunt_db"
)

# Real outbound email is OFF by default so the pipeline runs end-to-end safely in
# demo mode. Set EMAIL_SENDING_ENABLED=true (with Gmail OAuth configured) to send
# for real via activities.email.send_outreach_email.
EMAIL_SENDING_ENABLED = os.getenv("EMAIL_SENDING_ENABLED", "false").lower() in ("1", "true", "yes")


async def get_db_connection() -> asyncpg.Connection:
    """Get a database connection."""
    return await asyncpg.connect(DATABASE_URL)


# =============================================================================
# JOB DISCOVERY ACTIVITIES
# =============================================================================

@activity.defn
async def search_jobs_searchapi(
    query: str,
    location: Optional[str] = None,
    max_results: int = 50,
) -> dict:
    """Search for jobs using SearchAPI.io Google Jobs."""
    activity.logger.info(f"[SearchAPI] Searching: query='{query}', location={location}")

    try:
        from clients.searchapi import SearchApiClient
        client = SearchApiClient()
        jobs = await client.search_jobs(
            query=query,
            location=location or "Remote",
            max_results=max_results,
        )
        activity.logger.info(f"[SearchAPI] Found {len(jobs)} jobs")
        return {"jobs": [j.to_dict() for j in jobs], "total": len(jobs)}
    except Exception as e:
        activity.logger.error(f"SearchAPI search failed: {e}")
        return {"jobs": [], "total": 0, "error": str(e)}


@activity.defn
async def search_jobs_serpapi(
    query: str,
    location: Optional[str] = None,
    job_type: Optional[str] = None,
    date_posted: Optional[str] = None,
    max_results: int = 50,
) -> dict:
    """Search for jobs using SerpApi Google Jobs API (legacy)."""
    activity.logger.info(f"Searching jobs: query='{query}', location={location}")

    try:
        from clients.serpapi import SerpApiClient
        client = SerpApiClient()
        jobs = await client.search_jobs_all_pages(
            query=query,
            location=location or "Remote",
            max_pages=(max_results + 9) // 10,
        )
        return {"jobs": [j.to_dict() for j in jobs], "total": len(jobs)}
    except Exception as e:
        activity.logger.error(f"SerpApi search failed: {e}")
        return {"jobs": [], "total": 0, "error": str(e)}


@activity.defn
async def search_jobs_grok(
    keywords: list[str],
    locations: list[str],
    remote_ok: bool = True,
    experience_years: Optional[int] = None,
    salary_min: Optional[int] = None,
    max_results: int = 20,
    exclude_companies: Optional[list[str]] = None,
    target_companies: Optional[list[str]] = None,
    posted_within_days: int = 7,
) -> dict:
    """
    Search for jobs using Grok agentic web search.

    This is the preferred method - tools are FREE, only tokens cost.
    Searches LinkedIn, Indeed, Glassdoor, and company career pages.
    """
    activity.logger.info(
        f"[GrokSearch] Searching: keywords={keywords}, locations={locations}, "
        f"remote_ok={remote_ok}, max_results={max_results}"
    )

    try:
        from clients.grok_search import search_jobs_with_grok

        result = await search_jobs_with_grok(
            keywords=keywords,
            locations=locations,
            remote_ok=remote_ok,
            experience_years=experience_years,
            salary_min=salary_min,
            max_results=max_results,
            exclude_companies=exclude_companies,
            target_companies=target_companies,
            posted_within_days=posted_within_days,
        )

        # Convert JobListing objects to dicts for Temporal serialization
        jobs_dicts = [j.to_dict() for j in result.get("jobs", [])]

        activity.logger.info(
            f"[GrokSearch] Found {len(jobs_dicts)} jobs, "
            f"latency={result.get('latency_ms')}ms, "
            f"tokens={result.get('tokens_used')}"
        )

        return {
            "jobs": jobs_dicts,
            "total": result.get("total_found", len(jobs_dicts)),
            "sites_searched": result.get("sites_searched", []),
            "search_query": result.get("search_query", ""),
            "latency_ms": result.get("latency_ms", 0),
            "tokens_used": result.get("tokens_used", {}),
            "error": result.get("error"),
        }

    except Exception as e:
        activity.logger.error(f"[GrokSearch] Failed: {e}")
        return {
            "jobs": [],
            "total": 0,
            "error": str(e),
        }


@activity.defn
async def analyze_resume_for_job_search(resume_profile_id: Optional[str] = None) -> dict:
    """
    Analyze a resume and suggest job titles to search for.

    Uses LLM to understand the candidate's background and suggest
    appropriate job titles, seniority levels, and search terms.

    Args:
        resume_profile_id: Optional ID of resume to analyze. Uses default if None.

    Returns:
        dict with:
            - job_titles: List of job titles to search for
            - keywords: Additional search keywords
            - seniority_level: suggested level (junior/mid/senior/staff/lead)
            - industries: Relevant industries
            - locations: Preferred locations from resume
            - remote_preference: remote/hybrid/onsite preference
            - salary_range: {min, max} from resume
            - reasoning: Why these suggestions were made
    """
    activity.logger.info(f"Analyzing resume for job search: {resume_profile_id or 'default'}")

    conn = await get_db_connection()
    try:
        # Get resume from database
        if resume_profile_id:
            resume = await conn.fetchrow(
                "SELECT * FROM resume_profiles WHERE id = $1",
                resume_profile_id,
            )
        else:
            resume = await conn.fetchrow(
                "SELECT * FROM resume_profiles WHERE is_default = TRUE LIMIT 1"
            )

        if not resume:
            return {"error": "No resume found", "job_titles": []}

        # Build resume context for LLM
        skills = resume.get("skills") or []
        target_titles = resume.get("target_titles") or []
        experience_years = resume.get("experience_years") or 0
        experience_summary = resume.get("experience_summary") or ""
        raw_text = resume.get("raw_text") or ""
        preferred_locations = resume.get("preferred_locations") or []
        salary_min = resume.get("salary_expectation_min")
        salary_max = resume.get("salary_expectation_max")
        preferred_remote = resume.get("preferred_remote") or "remote"

        # If resume already has target_titles, use those as a starting point
        if target_titles:
            activity.logger.info(f"Resume has target_titles: {target_titles}")

        # Call LLM to analyze and suggest job titles
        from utils.llm import get_xai_client
        client = get_xai_client()

        # Build resume section - use raw_text if available, else fall back to summary
        resume_content = ""
        if raw_text:
            resume_content = f"FULL RESUME TEXT:\n{raw_text[:4000]}"
        elif experience_summary:
            resume_content = f"Experience Summary: {experience_summary[:1000]}"

        prompt = f"""Analyze this candidate's resume and suggest the best job titles to search for.

{resume_content}

STRUCTURED DATA:
- Years of Experience: {experience_years}
- Preferred Locations: {', '.join(preferred_locations) if preferred_locations else 'Remote'}
- Skills: {', '.join(skills[:30]) if skills else 'Not specified'}
- Current Target Titles: {', '.join(target_titles) if target_titles else 'Not specified'}
- Salary Range: ${salary_min or 0:,} - ${salary_max or 0:,}
- Remote Preference: {preferred_remote}

Based on this resume, suggest 5-7 specific job titles this person should search for.
Consider: their actual job history, seniority level, and technical stack.
Use exact titles that appear on LinkedIn/Indeed job postings.

Return JSON only:
{{
    "job_titles": ["Title 1", "Title 2", ...],
    "keywords": ["keyword1", "keyword2", ...],
    "seniority_level": "senior|staff|lead|principal|mid|junior",
    "reasoning": "Brief explanation of why these titles fit"
}}
"""

        response = await client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a job search expert. Analyze the candidate's actual "
                        "work history and technical experience. Suggest job titles that "
                        "match their seniority level and tech stack. Focus on titles that "
                        "actually appear on LinkedIn and Indeed job postings."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=800,
        )

        content = response.choices[0].message.content or "{}"

        # Parse JSON from response
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]

        import json
        try:
            suggestions = json.loads(content.strip())
        except json.JSONDecodeError:
            # Fallback to resume's target_titles if parsing fails
            suggestions = {
                "job_titles": target_titles or ["Software Engineer"],
                "keywords": skills[:5] if skills else [],
                "seniority_level": "senior" if experience_years >= 5 else "mid",
                "reasoning": "Fallback to resume target titles",
            }

        # Combine with resume preferences
        result = {
            "job_titles": suggestions.get("job_titles", target_titles or []),
            "keywords": suggestions.get("keywords", []),
            "seniority_level": suggestions.get("seniority_level", "mid"),
            "industries": resume.get("target_industries") or [],
            "locations": preferred_locations if preferred_locations else ["Remote"],
            "remote_preference": preferred_remote,
            "salary_range": {
                "min": salary_min,
                "max": salary_max,
            },
            "reasoning": suggestions.get("reasoning", ""),
            "resume_profile_id": str(resume["id"]),
            "resume_name": resume.get("full_name"),
        }

        activity.logger.info(f"Suggested job titles: {result['job_titles']}")
        return result

    except Exception as e:
        activity.logger.error(f"Resume analysis failed: {e}")
        return {"error": str(e), "job_titles": []}
    finally:
        await conn.close()


@activity.defn
async def enrich_job_contacts(job_id: str, company_name: str) -> dict:
    """
    Find recruiter/hiring manager contacts for a high-priority job.

    Uses Grok agentic search to find LinkedIn profiles and emails.
    """
    activity.logger.info(f"[GrokSearch] Enriching contacts for job {job_id} at {company_name}")

    try:
        # Get job details from database
        conn = await get_db_connection()
        try:
            job = await conn.fetchrow(
                "SELECT * FROM jobs WHERE id = $1",
                job_id if isinstance(job_id, str) else str(job_id),
            )
            if not job:
                return {"error": "Job not found"}

            from clients.grok_search import enrich_job_contacts as grok_enrich, JobListing

            # Create a minimal JobListing for the enrichment call
            job_listing = JobListing(
                external_id=job["external_id"] or "",
                title=job["title"],
                company_name=job["company_name"],
                company_url=job.get("company_url"),
                location=job.get("location", ""),
                remote_type=job.get("remote_type", "unknown"),
                salary_min=job.get("salary_min"),
                salary_max=job.get("salary_max"),
                salary_currency=job.get("salary_currency", "USD"),
                description=job.get("description", ""),
                requirements=[],
                url=job.get("url", ""),
                source=job.get("source", "unknown"),
                posted_at=job.get("posted_at"),
            )

            contacts = await grok_enrich(job_listing, company_name)

            # Update job record with contact info
            if contacts.get("recruiter"):
                import json
                await conn.execute(
                    """
                    UPDATE jobs SET
                        raw_data = raw_data || $1::jsonb,
                        updated_at = NOW()
                    WHERE id = $2
                    """,
                    json.dumps({"recruiter_info": contacts.get("recruiter")}),
                    job_id,
                )

            return contacts

        finally:
            await conn.close()

    except Exception as e:
        activity.logger.error(f"[GrokSearch] Contact enrichment failed: {e}")
        return {"error": str(e)}


@activity.defn
async def dedupe_jobs(raw_jobs: list[dict]) -> dict:
    """Deduplicate jobs against existing database records."""
    activity.logger.info(f"Deduplicating {len(raw_jobs)} jobs")

    if not raw_jobs:
        return {"new_jobs": [], "duplicate_count": 0}

    try:
        conn = await get_db_connection()
        try:
            # Get existing external IDs
            external_ids = [j.get("external_id") for j in raw_jobs if j.get("external_id")]
            if not external_ids:
                return {"new_jobs": raw_jobs, "duplicate_count": 0}

            existing = await conn.fetch(
                "SELECT external_id FROM jobs WHERE external_id = ANY($1::text[])",
                external_ids,
            )
            existing_ids = {row["external_id"] for row in existing}

            new_jobs = [j for j in raw_jobs if j.get("external_id") not in existing_ids]
            duplicate_count = len(raw_jobs) - len(new_jobs)

            return {"new_jobs": new_jobs, "duplicate_count": duplicate_count}
        finally:
            await conn.close()
    except Exception as e:
        activity.logger.warning(f"Dedupe failed, returning all: {e}")
        return {"new_jobs": raw_jobs, "duplicate_count": 0}


@activity.defn
async def parse_job_listing(job_listing: dict) -> dict:
    """
    Parse raw job listing and analyze fit using LLM.

    Uses Grok LLM to:
    - Analyze skills match against user's resume
    - Identify skills_matched and skills_missing
    - Calculate fit_score

    Also determines job category for filtering.
    """
    activity.logger.info(f"Parsing job with LLM: {job_listing.get('title', 'unknown')}")

    title = job_listing.get("title", "")
    description = job_listing.get("description", "")

    # Determine job category (simple, doesn't need LLM)
    try:
        from utils.job_parser import determine_job_category
        category = determine_job_category(title, description)
        job_listing["category"] = category
    except Exception as e:
        activity.logger.warning(f"Category determination failed: {e}")
        job_listing["category"] = "other"

    # Skip LLM analysis if no description
    if not description or len(description.strip()) < 50:
        activity.logger.info(f"Skipping LLM analysis for {title}: no description")
        job_listing["skills_matched"] = []
        job_listing["skills_missing"] = []
        job_listing["fit_score"] = None
        return job_listing

    try:
        from utils.llm import analyze_job_fit

        # Get the full resume profile from database
        conn = await get_db_connection()
        try:
            resume_row = await conn.fetchrow("""
                SELECT name, skills, experience_years, experience_summary,
                       key_achievements, target_titles, preferred_locations, education
                FROM resume_profiles
                WHERE is_default = TRUE
                LIMIT 1
            """)

            if not resume_row:
                activity.logger.warning("No default resume profile found")
                job_listing["skills_matched"] = []
                job_listing["skills_missing"] = []
                job_listing["fit_score"] = None
                return job_listing

            # Build resume dict for LLM
            import json
            education = resume_row["education"] or []
            # Ensure education is a list of dicts
            if isinstance(education, str):
                try:
                    education = json.loads(education)
                except (json.JSONDecodeError, ValueError):
                    education = []
            elif not isinstance(education, list):
                education = []

            resume = {
                "name": resume_row["name"],
                "skills": {"all": resume_row["skills"] or []},
                "years_of_experience": resume_row["experience_years"],
                "titles": resume_row["target_titles"] or [],
                "location": (resume_row["preferred_locations"] or ["Unknown"])[0],
                "achievements": resume_row["key_achievements"] or [],
                "education": education,
                "experience": [],  # Simplified - just use skills
            }

        finally:
            await conn.close()

        # Call LLM to analyze job fit
        activity.logger.info(f"Calling LLM to analyze: {title}")
        result = await analyze_job_fit(description, resume)

        # Ensure result is a dict
        if not isinstance(result, dict):
            raise ValueError(f"analyze_job_fit returned {type(result)}, expected dict")

        # Extract results from LLM response
        job_listing["skills_matched"] = result.get("skills_matched", [])
        job_listing["skills_missing"] = result.get("skills_missing", [])
        job_listing["fit_score"] = result.get("fit_score")

        # Store additional LLM insights in raw_data
        if "raw_data" not in job_listing:
            job_listing["raw_data"] = {}
        job_listing["raw_data"]["llm_analysis"] = {
            "experience_match": result.get("experience_match"),
            "title_alignment": result.get("title_alignment"),
            "reasoning": result.get("reasoning"),
            "strengths": result.get("strengths", []),
            "concerns": result.get("concerns", []),
        }

        activity.logger.info(
            f"LLM analysis for {title}: score={result.get('fit_score')}, "
            f"matched={len(job_listing['skills_matched'])}, "
            f"missing={len(job_listing['skills_missing'])}"
        )

    except Exception as e:
        import traceback
        activity.logger.warning(
            f"LLM analysis failed for {title}: {e}\n{traceback.format_exc()}"
        )
        # Don't fail the whole job, just return without LLM enrichment
        job_listing["skills_matched"] = []
        job_listing["skills_missing"] = []
        job_listing["fit_score"] = None

    return job_listing


@activity.defn
async def calculate_initial_fit_score(job: dict, config: dict) -> dict:
    """Calculate initial fit score based on search config criteria."""
    activity.logger.info("Calculating initial fit score")

    score = 0.5
    signals = []

    # Check for keyword matches - keywords can be list or string
    keywords_raw = config.get("keywords", [])
    if isinstance(keywords_raw, str):
        keywords = keywords_raw.lower().split()
    elif isinstance(keywords_raw, list):
        keywords = [k.lower() for k in keywords_raw if isinstance(k, str)]
    else:
        keywords = []

    title_lower = job.get("title", "").lower()
    desc_lower = job.get("description", "").lower()

    for kw in keywords:
        if kw in title_lower:
            score += 0.1
            signals.append(f"Title contains '{kw}'")
        elif kw in desc_lower:
            score += 0.05
            signals.append(f"Description contains '{kw}'")

    # Cap score
    score = min(1.0, score)

    return {"score": score, "signals": signals}


@activity.defn
async def save_job(job_data: dict) -> str:
    """Save job to database with all available fields, return job_id."""
    activity.logger.info(f"Saving job: {job_data.get('title', 'unknown')} at {job_data.get('company_name')}")

    conn = await get_db_connection()
    try:
        import uuid
        import json
        job_id = str(uuid.uuid4())

        # Prepare raw_data JSONB with extra fields
        raw_data = {
            "recruiter_name": job_data.get("recruiter_name"),
            "recruiter_email": job_data.get("recruiter_email"),
            "recruiter_linkedin": job_data.get("recruiter_linkedin"),
            "hiring_manager_name": job_data.get("hiring_manager_name"),
            "hiring_manager_linkedin": job_data.get("hiring_manager_linkedin"),
            "careers_email": job_data.get("careers_email"),
            "apply_email": job_data.get("apply_email"),  # Email extracted from posting
            "company_industry": job_data.get("company_industry"),
            "company_size": job_data.get("company_size"),
            "company_funding": job_data.get("company_funding"),
            "tech_stack": job_data.get("tech_stack", []),
            "apply_method": job_data.get("apply_method"),
            "fit_signals": job_data.get("fit_signals", []),
        }
        # Merge in any existing raw_data (e.g., llm_analysis from parse_job_listing)
        existing_raw_data = job_data.get("raw_data", {})
        if isinstance(existing_raw_data, dict):
            raw_data.update(existing_raw_data)
        # Remove None values
        raw_data = {k: v for k, v in raw_data.items() if v is not None}

        # Convert requirements list to text if needed
        requirements = job_data.get("requirements")
        if isinstance(requirements, list):
            requirements = "\n".join(f"• {r}" for r in requirements)

        # Convert posted_at from ISO string to datetime if needed
        posted_at = job_data.get("posted_at")
        if isinstance(posted_at, str):
            from datetime import datetime
            try:
                posted_at = datetime.fromisoformat(posted_at.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                posted_at = None

        # Get skills arrays
        skills_matched = job_data.get("skills_matched", [])
        skills_missing = job_data.get("skills_missing", [])
        category = job_data.get("category")

        await conn.execute(
            """
            INSERT INTO jobs (
                id, external_id, title, company_name, company_url, location, remote_type,
                salary_min, salary_max, salary_currency, description, requirements,
                url, source, posted_at, match_score, raw_data, status,
                category, skills_matched, skills_missing,
                created_at, updated_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16,
                    $17, 'new', $18, $19, $20, NOW(), NOW())
            ON CONFLICT (source, external_id) DO UPDATE SET
                title = EXCLUDED.title,
                salary_min = COALESCE(EXCLUDED.salary_min, jobs.salary_min),
                salary_max = COALESCE(EXCLUDED.salary_max, jobs.salary_max),
                match_score = COALESCE(EXCLUDED.match_score, jobs.match_score),
                raw_data = jobs.raw_data || EXCLUDED.raw_data,
                category = COALESCE(EXCLUDED.category, jobs.category),
                skills_matched = COALESCE(EXCLUDED.skills_matched, jobs.skills_matched),
                skills_missing = COALESCE(EXCLUDED.skills_missing, jobs.skills_missing),
                updated_at = NOW()
            """,
            uuid.UUID(job_id),
            job_data.get("external_id"),
            job_data.get("title"),
            job_data.get("company_name"),
            job_data.get("company_url"),
            job_data.get("location"),
            job_data.get("remote_type"),
            job_data.get("salary_min"),
            job_data.get("salary_max"),
            job_data.get("salary_currency", "USD"),
            job_data.get("description"),
            requirements,
            job_data.get("url"),
            job_data.get("source", "grok_search"),
            posted_at,
            job_data.get("fit_score"),
            json.dumps(raw_data),
            category,
            skills_matched if skills_matched else None,
            skills_missing if skills_missing else None,
        )

        activity.logger.info(f"Saved job {job_id}: {job_data.get('title')}")
        return job_id
    finally:
        await conn.close()


@activity.defn
async def get_job_by_url(url: str) -> Optional[dict]:
    """Get job by URL (for deduplication)."""
    conn = await get_db_connection()
    try:
        row = await conn.fetchrow("SELECT * FROM jobs WHERE url = $1", url)
        return dict(row) if row else None
    finally:
        await conn.close()


@activity.defn
async def update_search_config_last_run(
    config_id: str,
    jobs_found: int,
    jobs_new: int,
) -> None:
    """Update search config with last run statistics."""
    activity.logger.info(f"Updating config {config_id}: found={jobs_found}, new={jobs_new}")
    # Config is stored in JSON file, not database - log only for now


@activity.defn
async def log_job_event(job_id: str, event_type: str, event_data: dict) -> None:
    """Log a job-related event."""
    activity.logger.info(f"Job event: {event_type} for job {job_id}")
    # Can be enhanced to store in database event log


# =============================================================================
# JOB ENRICHMENT ACTIVITIES
# =============================================================================

@activity.defn
async def get_job(job_id: str) -> Optional[dict]:
    """Get job by ID."""
    activity.logger.info(f"Getting job {job_id}")

    conn = await get_db_connection()
    try:
        import uuid
        row = await conn.fetchrow("SELECT * FROM jobs WHERE id = $1", uuid.UUID(job_id))
        return dict(row) if row else None
    finally:
        await conn.close()


@activity.defn
async def get_company_by_domain(domain: str) -> Optional[dict]:
    """Get company by domain."""
    conn = await get_db_connection()
    try:
        row = await conn.fetchrow("SELECT * FROM companies WHERE domain = $1", domain)
        return dict(row) if row else None
    finally:
        await conn.close()


@activity.defn
async def apollo_enrich_company(company_name: str, domain: Optional[str]) -> dict:
    """Enrich company via Apollo API."""
    activity.logger.info(f"Apollo enriching: {company_name}")

    try:
        from clients.apollo import ApolloClient
        client = ApolloClient()

        if domain:
            company = await client.enrich_company(domain)
        else:
            company = await client.search_company_by_name(company_name)

        if not company:
            return {"found": False}

        return {
            "found": True,
            "id": company.apollo_id,
            "name": company.name,
            "domain": company.domain,
            "description": company.description,
            "industry": company.industry,
            "employees": company.employee_count,
            "employee_range": company.employee_range,
            "city": company.headquarters.get("city") if company.headquarters else None,
            "state": company.headquarters.get("state") if company.headquarters else None,
            "country": company.headquarters.get("country") if company.headquarters else None,
            "linkedin_url": company.linkedin_url,
            "website_url": company.website_url,
            "founded_year": company.founded_year,
            "funding_stage": company.funding_stage,
            "total_funding": company.total_funding,
            "technologies": company.tech_stack,
            "keywords": company.keywords,
        }
    except Exception as e:
        activity.logger.error(f"Apollo enrichment failed: {e}")
        return {"found": False, "error": str(e)}


@activity.defn
async def apollo_search_contacts(domain: str, titles: list[str]) -> dict:
    """Search for contacts at a company via Apollo."""
    activity.logger.info(f"Apollo searching contacts at {domain}")

    try:
        from clients.apollo import ApolloClient
        client = ApolloClient()

        contacts = await client.search_contacts(
            domain=domain,
            titles=titles,
            per_page=20,
        )

        return {
            "contacts": [
                {
                    "id": c.apollo_id,
                    "name": c.name,
                    "email": c.email,
                    "title": c.title,
                    "linkedin_url": c.linkedin_url,
                    "seniority": c.seniority,
                }
                for c in contacts
            ]
        }
    except Exception as e:
        activity.logger.error(f"Apollo contact search failed: {e}")
        return {"contacts": [], "error": str(e)}


@activity.defn
async def calculate_detailed_fit_score(
    job: dict,
    company: Optional[dict],
    contacts: list[dict],
    culture_data: dict,
) -> dict:
    """Calculate detailed fit score with reasoning using LLM."""
    activity.logger.info("Calculating detailed fit score")

    try:
        from utils.llm import get_xai_client, DEFAULT_MODEL
        import json
        import time

        client = get_xai_client()

        # Get user profile for comparison
        user_profile = await get_user_profile()

        # Build context for LLM
        job_context = f"""
Job Title: {job.get('title', 'Unknown')}
Company: {job.get('company_name', 'Unknown')}
Location: {job.get('location', 'Unknown')}
Description: {(job.get('description') or '')[:2000]}
Requirements: {(job.get('requirements') or '')[:1000]}
"""

        company_context = ""
        if company:
            company_context = f"""
Company Details:
- Industry: {company.get('industry', 'Unknown')}
- Size: {company.get('employee_count', 'Unknown')} employees
- Domain: {company.get('domain', 'Unknown')}
- Description: {(company.get('description') or '')[:500]}
"""

        culture_context = ""
        if culture_data:
            culture_context = f"""
Culture Signals:
- Glassdoor Rating: {culture_data.get('glassdoor_rating', 'Unknown')}
- Values: {', '.join(culture_data.get('values', []))}
- Keywords: {', '.join(culture_data.get('culture_keywords', []))}
"""

        candidate_context = f"""
Candidate Profile:
- Name: {user_profile.get('name', 'Unknown')}
- Title: {user_profile.get('title', 'Unknown')}
- Years Experience: {user_profile.get('years_experience', 'Unknown')}
- Skills: {', '.join(user_profile.get('skills', []))}
- Summary: {user_profile.get('summary', '')}
"""

        prompt = f"""Analyze the fit between this job opportunity and the candidate.

{job_context}
{company_context}
{culture_context}
{candidate_context}

Contacts Available: {len(contacts)} relevant contacts found at this company.

Provide a comprehensive fit analysis. Respond ONLY with valid JSON (no markdown):
{{
    "score": <0.0-1.0 float representing fit score>,
    "reasoning": "<2-3 sentence explanation of the overall fit>",
    "signals": ["<positive signal 1>", "<positive signal 2>", ...],
    "concerns": ["<concern 1>", "<concern 2>", ...],
    "skills_matched": ["<skill1>", "<skill2>", ...],
    "skills_missing": ["<skill1>", "<skill2>", ...],
    "recommendation": "strong_apply" | "apply" | "review" | "skip"
}}

Scoring guide:
- 0.85-1.0: Excellent match, meets/exceeds all requirements
- 0.70-0.84: Strong match, meets most requirements with minor gaps
- 0.50-0.69: Moderate match, meets core requirements but has gaps
- 0.30-0.49: Weak match, meets some requirements but significant gaps
- 0.0-0.29: Poor match, does not meet core requirements

Be specific and actionable in your analysis."""

        start_time = time.time()

        response = await client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "You are a career advisor analyzing job fit for a candidate. "
                               "Be honest and specific. Respond only with valid JSON."
                },
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=800,
        )

        latency_ms = int((time.time() - start_time) * 1000)
        activity.logger.info(f"LLM fit score call completed in {latency_ms}ms")

        # Parse response
        content = response.choices[0].message.content or "{}"

        # Clean up potential markdown formatting
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        content = content.strip()

        result = extract_json(content)

        # Ensure required fields with defaults
        return {
            "score": float(result.get("score", 0.5)),
            "reasoning": result.get("reasoning", "Analysis complete"),
            "signals": result.get("signals", []),
            "concerns": result.get("concerns", []),
            "skills_matched": result.get("skills_matched", []),
            "skills_missing": result.get("skills_missing", []),
            "recommendation": result.get("recommendation", "review"),
            "_metadata": {
                "model": DEFAULT_MODEL,
                "latency_ms": latency_ms,
            }
        }

    except Exception as e:
        activity.logger.error(f"LLM fit scoring failed: {e}")
        # Fallback to basic scoring
        score = 0.5
        signals = []

        if company:
            score += 0.1
            signals.append("Company data available")
        if contacts:
            score += 0.1
            signals.append(f"{len(contacts)} contacts found")
        if culture_data.get("glassdoor_rating"):
            rating = culture_data["glassdoor_rating"]
            if rating >= 4.0:
                score += 0.1
                signals.append(f"Good Glassdoor rating: {rating}")

        recommendation = "review"
        if score >= 0.8:
            recommendation = "strong_apply"
        elif score >= 0.6:
            recommendation = "apply"
        elif score < 0.4:
            recommendation = "skip"

        return {
            "score": min(1.0, score),
            "reasoning": f"Fallback scoring (LLM error: {str(e)[:100]})",
            "signals": signals,
            "concerns": [],
            "skills_matched": [],
            "skills_missing": [],
            "recommendation": recommendation,
        }


@activity.defn
async def save_company(company_data: dict) -> str:
    """Save company to database, return company_id."""
    activity.logger.info(f"Saving company: {company_data.get('name', 'unknown')}")

    conn = await get_db_connection()
    try:
        import uuid
        import json
        company_id = str(uuid.uuid4())

        await conn.execute(
            """
            INSERT INTO companies (id, name, domain, description, industry, employee_count,
                                 linkedin_url, website, tech_stack, created_at, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, NOW(), NOW())
            ON CONFLICT (domain) DO UPDATE SET
                name = EXCLUDED.name,
                description = EXCLUDED.description,
                industry = EXCLUDED.industry,
                employee_count = EXCLUDED.employee_count,
                updated_at = NOW()
            RETURNING id
            """,
            uuid.UUID(company_id),
            company_data.get("name"),
            company_data.get("domain"),
            company_data.get("description"),
            company_data.get("industry"),
            company_data.get("employee_count"),
            company_data.get("linkedin_url"),
            company_data.get("website"),
            json.dumps(company_data.get("technologies", [])),
        )

        return company_id
    finally:
        await conn.close()


@activity.defn
async def update_company(company_id: str, company_data: dict) -> None:
    """Update existing company record."""
    activity.logger.info(f"Updating company {company_id}")

    conn = await get_db_connection()
    try:
        import uuid
        import json
        await conn.execute(
            """
            UPDATE companies SET
                name = COALESCE($2, name),
                description = COALESCE($3, description),
                industry = COALESCE($4, industry),
                employee_count = COALESCE($5, employee_count),
                tech_stack = COALESCE($6, tech_stack),
                updated_at = NOW()
            WHERE id = $1
            """,
            uuid.UUID(company_id),
            company_data.get("name"),
            company_data.get("description"),
            company_data.get("industry"),
            company_data.get("employee_count"),
            json.dumps(company_data.get("technologies", [])) if company_data.get("technologies") else None,
        )
    finally:
        await conn.close()


@activity.defn
async def update_job_enrichment(job_id: str, enrichment_data: dict) -> None:
    """Update job with enrichment data including skills analysis."""
    activity.logger.info(f"Updating job enrichment for {job_id}")

    conn = await get_db_connection()
    try:
        import uuid
        import json

        # Extract fit result which contains skills data
        fit_result = enrichment_data.get("fit_result", {})
        fit_score = fit_result.get("score") or enrichment_data.get("fit_score")
        skills_matched = fit_result.get("skills_matched", [])
        skills_missing = fit_result.get("skills_missing", [])

        await conn.execute(
            """
            UPDATE jobs SET
                company_id = COALESCE($2, company_id),
                fit_score = COALESCE($3, fit_score),
                match_score = COALESCE($3 * 100, match_score),
                skills_matched = COALESCE($4, skills_matched),
                skills_missing = COALESCE($5, skills_missing),
                fit_analysis = COALESCE($6, fit_analysis),
                enriched_at = $7,
                updated_at = NOW()
            WHERE id = $1
            """,
            uuid.UUID(job_id),
            uuid.UUID(enrichment_data["company_id"]) if enrichment_data.get("company_id") else None,
            fit_score,
            skills_matched if skills_matched else None,
            skills_missing if skills_missing else None,
            json.dumps(enrichment_data) if enrichment_data else None,
            datetime.now(timezone.utc),
        )
    finally:
        await conn.close()


@activity.defn
async def link_job_to_company(job_id: str, company_id: str) -> None:
    """Link job to company record."""
    activity.logger.info(f"Linking job {job_id} to company {company_id}")

    conn = await get_db_connection()
    try:
        import uuid
        await conn.execute(
            "UPDATE jobs SET company_id = $2, updated_at = NOW() WHERE id = $1",
            uuid.UUID(job_id),
            uuid.UUID(company_id),
        )
    finally:
        await conn.close()


@activity.defn
async def save_contacts(job_id: str, company_id: Optional[str], contacts: list[dict]) -> None:
    """Save contacts to database."""
    activity.logger.info(f"Saving {len(contacts)} contacts")

    conn = await get_db_connection()
    try:
        import uuid
        for contact in contacts:
            # Upsert the contact (deduped by email), then link it to the job
            # through the contact_jobs join table.
            row = await conn.fetchrow(
                """
                INSERT INTO contacts (id, company_id, name, email, title,
                                    linkedin_url, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, NOW(), NOW())
                ON CONFLICT (email) DO UPDATE SET
                    title = EXCLUDED.title,
                    linkedin_url = EXCLUDED.linkedin_url,
                    updated_at = NOW()
                RETURNING id
                """,
                uuid.uuid4(),
                uuid.UUID(company_id) if company_id else None,
                contact.get("name"),
                contact.get("email"),
                contact.get("title"),
                contact.get("linkedin_url"),
            )
            if row:
                await conn.execute(
                    """
                    INSERT INTO contact_jobs (contact_id, job_id)
                    VALUES ($1, $2)
                    ON CONFLICT (contact_id, job_id) DO NOTHING
                    """,
                    row["id"],
                    uuid.UUID(job_id),
                )
    finally:
        await conn.close()


# =============================================================================
# APPLICATION ACTIVITIES
# =============================================================================

@activity.defn
async def get_job_with_company(job_id: str) -> Optional[dict]:
    """Get job with associated company data."""
    activity.logger.info(f"Getting job with company: {job_id}")

    conn = await get_db_connection()
    try:
        import uuid
        job = await conn.fetchrow(
            """
            SELECT j.*, c.name as company_name_enriched, c.domain, c.industry,
                   c.description as company_description, c.employee_count
            FROM jobs j
            LEFT JOIN companies c ON c.id = j.company_id
            WHERE j.id = $1
            """,
            uuid.UUID(job_id),
        )

        if not job:
            return None

        job_dict = dict(job)
        company = {
            "id": str(job_dict.get("company_id")) if job_dict.get("company_id") else None,
            "name": job_dict.get("company_name_enriched") or job_dict.get("company_name"),
            "domain": job_dict.get("domain"),
            "industry": job_dict.get("industry"),
            "description": job_dict.get("company_description"),
            "employee_count": job_dict.get("employee_count"),
        }

        return {"job": job_dict, "company": company}
    finally:
        await conn.close()


@activity.defn
async def get_user_profile(resume_profile_id: Optional[str] = None) -> Optional[dict]:
    """
    Get user profile for personalization from resume_profiles table.

    Args:
        resume_profile_id: Optional UUID of a specific resume profile.
                          If not provided, returns the default profile.

    Returns:
        User profile dict with name, skills, title, experience info.
    """
    import uuid as uuid_module
    conn = await get_db_connection()
    try:
        if resume_profile_id:
            row = await conn.fetchrow(
                """
                SELECT name, skills, target_titles, experience_years,
                       experience_summary, key_achievements, parsed_data
                FROM resume_profiles WHERE id = $1
                """,
                uuid_module.UUID(resume_profile_id),
            )
        else:
            row = await conn.fetchrow(
                """
                SELECT name, skills, target_titles, experience_years,
                       experience_summary, key_achievements, parsed_data
                FROM resume_profiles WHERE is_default = TRUE LIMIT 1
                """,
            )

        if not row:
            activity.logger.warning("No resume profile found, returning minimal fallback")
            return {
                "name": "Applicant",
                "skills": [],
                "title": "Professional",
                "years_experience": None,
                "summary": None,
            }

        # Extract name - prefer parsed_data.name if available, else use profile name
        parsed_data = row.get("parsed_data") or {}
        name = parsed_data.get("name") or row.get("name") or "Applicant"

        # Get title from target_titles
        target_titles = row.get("target_titles") or []
        title = target_titles[0] if target_titles else "Professional"

        return {
            "name": name,
            "skills": row.get("skills") or [],
            "title": title,
            "years_experience": row.get("experience_years"),
            "summary": row.get("experience_summary"),
            "key_achievements": row.get("key_achievements") or [],
        }
    except Exception as e:
        activity.logger.error(f"Error fetching user profile: {e}")
        return {
            "name": "Applicant",
            "skills": [],
            "title": "Professional",
            "years_experience": None,
            "summary": None,
        }
    finally:
        await conn.close()


@activity.defn
async def get_best_contact(job_id: str, company_id: Optional[str]) -> Optional[dict]:
    """Get best contact for reaching out about a job."""
    activity.logger.info(f"Getting best contact for job {job_id}")

    conn = await get_db_connection()
    try:
        import uuid
        # First try contacts linked to job
        contact = await conn.fetchrow(
            """
            SELECT * FROM contacts
            WHERE job_id = $1
            ORDER BY
                CASE WHEN title ILIKE '%recruiter%' THEN 1
                     WHEN title ILIKE '%talent%' THEN 2
                     WHEN title ILIKE '%hr%' THEN 3
                     ELSE 4 END,
                created_at DESC
            LIMIT 1
            """,
            uuid.UUID(job_id),
        )

        if contact:
            return dict(contact)

        # Fall back to company contacts
        if company_id:
            contact = await conn.fetchrow(
                """
                SELECT * FROM contacts
                WHERE company_id = $1
                ORDER BY
                    CASE WHEN title ILIKE '%recruiter%' THEN 1
                         WHEN title ILIKE '%talent%' THEN 2
                         WHEN title ILIKE '%hr%' THEN 3
                         ELSE 4 END,
                    created_at DESC
                LIMIT 1
                """,
                uuid.UUID(company_id),
            )
            if contact:
                return dict(contact)

        return None
    finally:
        await conn.close()


@activity.defn
async def save_application_draft(job_id: str, draft_data: dict) -> str:
    """Save application draft to database."""
    activity.logger.info(f"Saving application draft for job {job_id}")

    conn = await get_db_connection()
    try:
        import uuid
        import json
        draft_id = str(uuid.uuid4())

        await conn.execute(
            """
            INSERT INTO application_drafts (id, job_id, draft_data, status, created_at, updated_at)
            VALUES ($1, $2, $3, 'draft', NOW(), NOW())
            """,
            uuid.UUID(draft_id),
            uuid.UUID(job_id),
            json.dumps(draft_data),
        )

        return draft_id
    finally:
        await conn.close()


@activity.defn
async def update_application_status(draft_id: str, status: str, reason: str) -> None:
    """Update application/draft status."""
    activity.logger.info(f"Updating draft {draft_id} status to {status}")

    conn = await get_db_connection()
    try:
        import uuid
        await conn.execute(
            """
            UPDATE application_drafts
            SET status = $2, status_reason = $3, updated_at = NOW()
            WHERE id = $1
            """,
            uuid.UUID(draft_id),
            status,
            reason,
        )
    finally:
        await conn.close()


@activity.defn
async def send_application_email(
    to: str,
    to_name: str,
    subject: str,
    body: str,
    body_html: Optional[str],
    job_id: str,
) -> dict:
    """Send the application email.

    Delegates to activities.email.send_outreach_email (real Gmail send) when
    EMAIL_SENDING_ENABLED is set. Otherwise returns a stubbed success so the
    orchestration completes end-to-end in demo mode without sending anything.
    """
    activity.logger.info(f"Sending application email to {to} (sending_enabled={EMAIL_SENDING_ENABLED})")

    if not EMAIL_SENDING_ENABLED:
        import uuid
        return {"success": True, "message_id": f"stub-{uuid.uuid4()}", "stubbed": True}

    from .email import send_outreach_email
    return await send_outreach_email(
        to_email=to,
        to_name=to_name or to,
        subject=subject,
        body=body,
        job_id=job_id,
        email_type="initial",
        html_body=body_html,
    )


@activity.defn
async def create_application_record(application_data: dict) -> str:
    """Create application record in database."""
    activity.logger.info("Creating application record")

    conn = await get_db_connection()
    try:
        import uuid
        app_id = str(uuid.uuid4())

        await conn.execute(
            """
            INSERT INTO applications (id, job_id, status, applied_at, method, notes, created_at, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, NOW(), NOW())
            """,
            uuid.UUID(app_id),
            uuid.UUID(application_data["job_id"]),
            application_data.get("status", "applied"),
            datetime.fromisoformat(application_data["applied_at"]) if application_data.get("applied_at") else datetime.now(timezone.utc),
            application_data.get("method", "email"),
            application_data.get("notes"),
        )

        return app_id
    finally:
        await conn.close()


# =============================================================================
# FOLLOW-UP ACTIVITIES
# =============================================================================

@activity.defn
async def get_application(application_id: str) -> Optional[dict]:
    """Get application by ID."""
    conn = await get_db_connection()
    try:
        import uuid
        row = await conn.fetchrow(
            "SELECT * FROM applications WHERE id = $1",
            uuid.UUID(application_id),
        )
        return dict(row) if row else None
    finally:
        await conn.close()


@activity.defn
async def check_application_replied(application_id: str) -> bool:
    """Check if application has received a reply."""
    conn = await get_db_connection()
    try:
        import uuid
        row = await conn.fetchrow(
            """
            SELECT 1 FROM outreach_emails
            WHERE job_id = (SELECT job_id FROM applications WHERE id = $1)
            AND replied_at IS NOT NULL
            LIMIT 1
            """,
            uuid.UUID(application_id),
        )
        return row is not None
    finally:
        await conn.close()


@activity.defn
async def generate_follow_up_email(
    application_id: str,
    step: int,
    follow_up_type: str,
) -> dict:
    """Generate follow-up email content."""
    activity.logger.info(f"Generating follow-up email step {step} ({follow_up_type})")

    conn = await get_db_connection()
    try:
        import uuid
        # Get application and job details
        app = await conn.fetchrow(
            """
            SELECT a.*, j.title, j.company_name, oe.recipient_email AS to_email, oe.gmail_thread_id
            FROM applications a
            JOIN jobs j ON j.id = a.job_id
            LEFT JOIN outreach_emails oe ON oe.job_id = a.job_id AND oe.status = 'sent'
            WHERE a.id = $1
            ORDER BY oe.sent_at DESC
            LIMIT 1
            """,
            uuid.UUID(application_id),
        )

        if not app:
            return {"error": "Application not found"}

        # Generate follow-up based on type
        first_name = "there"  # Would need contact lookup
        company = app["company_name"]
        title = app["title"]

        if follow_up_type == "gentle_bump":
            subject = f"Re: {title} opportunity"
            body = f"""Hi {first_name},

I wanted to follow up on my application for the {title} role at {company}. I'm still very interested in the opportunity and would love to discuss how my experience could contribute to your team.

Would you have 15 minutes this week to chat?

Best,
{candidate_first_name()}"""
        elif follow_up_type == "value_add":
            subject = f"Re: {title} - additional context"
            body = f"""Hi {first_name},

I've been thinking more about the {title} role and wanted to share a quick thought about how I could help with [specific challenge].

In my previous role, I [relevant accomplishment]. I'd love to discuss how this experience could apply to {company}.

Let me know if you have time for a brief conversation.

Best,
{candidate_first_name()}"""
        else:  # graceful_close
            subject = f"Re: {title} - checking in one last time"
            body = f"""Hi {first_name},

I wanted to reach out one more time about the {title} position. I understand you may have moved forward with other candidates, but if the role is still open, I'd love to connect.

Either way, thank you for your consideration. I hope we can connect in the future.

Best,
{candidate_first_name()}"""

        return {
            "to": app["to_email"],
            "subject": subject,
            "body": body,
            "body_html": None,
            "thread_id": app["gmail_thread_id"],
        }
    finally:
        await conn.close()


@activity.defn
async def send_follow_up_email(
    application_id: str,
    to: str,
    subject: str,
    body: str,
    body_html: Optional[str],
    thread_id: Optional[str],
) -> dict:
    """Send the follow-up email.

    Delegates to activities.email.send_outreach_email (real Gmail send, threaded to
    the original) when EMAIL_SENDING_ENABLED is set; otherwise returns a stubbed
    success so the durable follow-up sequence completes in demo mode.
    """
    activity.logger.info(f"Sending follow-up to {to} (sending_enabled={EMAIL_SENDING_ENABLED})")

    if not EMAIL_SENDING_ENABLED:
        import uuid
        return {"success": True, "message_id": f"stub-{uuid.uuid4()}", "stubbed": True}

    import uuid
    # Resolve the job_id for this application (required by send_outreach_email).
    conn = await get_db_connection()
    try:
        row = await conn.fetchrow(
            "SELECT job_id FROM applications WHERE id = $1", uuid.UUID(application_id)
        )
    finally:
        await conn.close()
    if not row:
        return {"success": False, "error": "Application not found"}

    from .email import send_outreach_email
    return await send_outreach_email(
        to_email=to,
        to_name=to,
        subject=subject,
        body=body,
        job_id=str(row["job_id"]),
        email_type="follow_up",
        html_body=body_html,
        thread_id=thread_id,
    )


@activity.defn
async def update_follow_up_record(application_id: str, follow_up_data: dict) -> None:
    """Record follow-up in database."""
    activity.logger.info(f"Recording follow-up for application {application_id}")

    conn = await get_db_connection()
    try:
        import uuid
        import json
        # Update application with follow-up info
        await conn.execute(
            """
            UPDATE applications
            SET follow_ups = COALESCE(follow_ups, '[]'::jsonb) || $2::jsonb,
                updated_at = NOW()
            WHERE id = $1
            """,
            uuid.UUID(application_id),
            json.dumps([follow_up_data]),
        )
    finally:
        await conn.close()


# =============================================================================
# INTERVIEW PREP ACTIVITIES
# =============================================================================

@activity.defn
async def get_interview(interview_id: str) -> Optional[dict]:
    """Get interview by ID."""
    conn = await get_db_connection()
    try:
        import uuid
        row = await conn.fetchrow(
            "SELECT * FROM interviews WHERE id = $1",
            uuid.UUID(interview_id),
        )
        return dict(row) if row else None
    finally:
        await conn.close()


@activity.defn
async def get_application_with_job(application_id: str) -> Optional[dict]:
    """Get application with associated job data."""
    conn = await get_db_connection()
    try:
        import uuid
        app = await conn.fetchrow(
            """
            SELECT a.*, j.title, j.company_name, j.description, j.requirements,
                   j.company_id, c.domain, c.industry as company_industry
            FROM applications a
            JOIN jobs j ON j.id = a.job_id
            LEFT JOIN companies c ON c.id = j.company_id
            WHERE a.id = $1
            """,
            uuid.UUID(application_id),
        )

        if not app:
            return None

        app_dict = dict(app)
        return {
            "application": app_dict,
            "job": {
                "id": str(app_dict["job_id"]),
                "title": app_dict["title"],
                "company_name": app_dict["company_name"],
                "description": app_dict["description"],
                "requirements": app_dict["requirements"],
                "company_id": str(app_dict["company_id"]) if app_dict.get("company_id") else None,
            },
        }
    finally:
        await conn.close()


@activity.defn
async def get_company(company_id: str) -> Optional[dict]:
    """Get company by ID."""
    conn = await get_db_connection()
    try:
        import uuid
        row = await conn.fetchrow("SELECT * FROM companies WHERE id = $1", uuid.UUID(company_id))
        return dict(row) if row else None
    finally:
        await conn.close()


@activity.defn
async def research_company_recent(company_name: str, domain: Optional[str]) -> dict:
    """Research recent company news and initiatives."""
    activity.logger.info(f"Researching recent news for {company_name}")

    # This would integrate with web search/news APIs
    # For now, return placeholder
    return {
        "recent_news": [],
        "key_initiatives": [],
        "mission": None,
        "values": [],
        "culture_keywords": [],
        "competitors": [],
        "challenges": [],
        "growth_areas": [],
    }


@activity.defn
async def research_interviewer(
    name: str,
    company: str,
    linkedin_url: Optional[str],
) -> Optional[dict]:
    """Research individual interviewer."""
    activity.logger.info(f"Researching interviewer: {name}")

    # This would integrate with LinkedIn/web search
    # For now, return placeholder
    return {
        "name": name,
        "title": None,
        "linkedin_url": linkedin_url,
        "background": None,
        "expertise": [],
        "interests": [],
        "tenure": None,
        "previous_companies": [],
        "education": None,
        "likely_focus_areas": [],
        "connection_points": [],
    }


@activity.defn
async def generate_interview_questions(context: dict) -> dict:
    """Generate likely interview questions based on context using LLM."""
    activity.logger.info("Generating interview questions")

    try:
        from utils.llm import get_xai_client, DEFAULT_MODEL
        import json
        import time

        client = get_xai_client()

        interview_type = context.get("interview_type", "general")
        job = context.get("job", {})
        company = context.get("company", {})
        interviewer_profiles = context.get("interviewer_profiles", [])

        # Build interviewer context
        interviewer_context = ""
        if interviewer_profiles:
            interviewer_lines = []
            for interviewer in interviewer_profiles[:3]:  # Limit to 3
                interviewer_lines.append(
                    f"- {interviewer.get('name', 'Unknown')}: "
                    f"{interviewer.get('title', 'Unknown role')}"
                )
            interviewer_context = f"""
Interviewers:
{chr(10).join(interviewer_lines)}
"""

        prompt = f"""Generate personalized interview questions for this opportunity.

Job Details:
- Title: {job.get('title', 'Unknown')}
- Company: {job.get('company_name', company.get('name', 'Unknown'))}
- Industry: {company.get('industry', 'Unknown')}
- Description: {(job.get('description') or '')[:1500]}
- Requirements: {(job.get('requirements') or '')[:800]}

Interview Type: {interview_type}
{interviewer_context}

Generate specific, relevant interview questions. Respond ONLY with valid JSON:
{{
    "behavioral_questions": [
        {{"question": "<specific question>", "tip": "<preparation tip>", "sample_answer_points": ["<point1>", "<point2>"]}}
    ],
    "technical_questions": [
        {{"question": "<specific technical question>", "tip": "<how to approach>", "key_concepts": ["<concept1>", "<concept2>"]}}
    ],
    "role_specific_questions": [
        {{"question": "<question specific to this role>", "tip": "<preparation tip>"}}
    ],
    "questions_to_ask": [
        {{"question": "<insightful question to ask interviewer>", "why": "<why this question is valuable>"}}
    ]
}}

Guidelines:
- Behavioral: 3-4 STAR-format questions relevant to the role
- Technical: 3-5 questions based on job requirements and tech stack
- Role-specific: 2-3 questions about the specific position
- Questions to ask: 3-4 thoughtful questions showing research and interest

Make questions SPECIFIC to this job posting, not generic templates."""

        start_time = time.time()

        response = await client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "You are an experienced technical recruiter and interview coach. "
                               "Generate specific, relevant interview questions based on the job "
                               "posting. Respond only with valid JSON."
                },
                {"role": "user", "content": prompt}
            ],
            temperature=0.5,
            max_tokens=1200,
        )

        latency_ms = int((time.time() - start_time) * 1000)
        activity.logger.info(f"LLM interview questions call completed in {latency_ms}ms")

        # Parse response
        content = response.choices[0].message.content or "{}"

        # Clean up potential markdown formatting
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        content = content.strip()

        result = extract_json(content)

        # Flatten into unified questions list with type
        questions = []

        for q in result.get("behavioral_questions", []):
            questions.append({
                "question": q.get("question", ""),
                "type": "behavioral",
                "tip": q.get("tip", ""),
                "sample_answer_points": q.get("sample_answer_points", []),
            })

        for q in result.get("technical_questions", []):
            questions.append({
                "question": q.get("question", ""),
                "type": "technical",
                "tip": q.get("tip", ""),
                "key_concepts": q.get("key_concepts", []),
            })

        for q in result.get("role_specific_questions", []):
            questions.append({
                "question": q.get("question", ""),
                "type": "role_specific",
                "tip": q.get("tip", ""),
            })

        for q in result.get("questions_to_ask", []):
            questions.append({
                "question": q.get("question", ""),
                "type": "questions_to_ask",
                "why": q.get("why", ""),
            })

        return {
            "questions": questions,
            "categorized": result,
            "_metadata": {
                "model": DEFAULT_MODEL,
                "latency_ms": latency_ms,
            }
        }

    except Exception as e:
        activity.logger.error(f"LLM interview questions generation failed: {e}")
        # Fallback to basic questions
        interview_type = context.get("interview_type", "general")
        questions = []

        questions.extend([
            {
                "question": "Tell me about yourself",
                "type": "behavioral",
                "tip": "Focus on relevant experience"
            },
            {
                "question": "Why are you interested in this role?",
                "type": "behavioral",
                "tip": "Connect to company mission"
            },
            {
                "question": "Tell me about a challenging project you worked on",
                "type": "behavioral",
                "tip": "Use STAR format"
            },
        ])

        if interview_type == "technical":
            questions.extend([
                {
                    "question": "Describe your experience with the technologies in this role",
                    "type": "technical"
                },
                {
                    "question": "How would you design a scalable system for this use case?",
                    "type": "technical"
                },
                {
                    "question": "Walk me through debugging a production issue",
                    "type": "technical"
                },
            ])

        questions.extend([
            {
                "question": "What does success look like in this role after 6 months?",
                "type": "questions_to_ask"
            },
            {
                "question": "What are the biggest challenges facing the team?",
                "type": "questions_to_ask"
            },
        ])

        return {
            "questions": questions,
            "error": f"Fallback questions used (LLM error: {str(e)[:100]})"
        }


@activity.defn
async def generate_talking_points(
    job: dict,
    company_context: dict,
    interviewer_profiles: list[dict],
    questions: list[dict],
) -> dict:
    """Generate suggested talking points using LLM."""
    activity.logger.info("Generating talking points")

    try:
        from utils.llm import get_xai_client, DEFAULT_MODEL
        import json
        import time

        client = get_xai_client()

        # Get user profile for personalized talking points
        user_profile = await get_user_profile()

        # Build interviewer context
        interviewer_context = ""
        if interviewer_profiles:
            interviewer_lines = []
            for interviewer in interviewer_profiles[:3]:
                line = f"- {interviewer.get('name', 'Unknown')}: {interviewer.get('title', 'Unknown')}"
                if interviewer.get('expertise'):
                    line += f" (expertise: {', '.join(interviewer['expertise'][:3])})"
                interviewer_lines.append(line)
            interviewer_context = f"""
Interviewers:
{chr(10).join(interviewer_lines)}
"""

        # Build questions context
        questions_context = ""
        if questions:
            question_lines = [q.get("question", "") for q in questions[:8]]
            questions_context = f"""
Likely Questions:
{chr(10).join('- ' + q for q in question_lines if q)}
"""

        prompt = f"""Generate personalized talking points for this interview.

Job Details:
- Title: {job.get('title', 'Unknown')}
- Company: {job.get('company_name', 'Unknown')}
- Description: {(job.get('description') or '')[:1200]}
- Requirements: {(job.get('requirements') or '')[:600]}

Company Context:
- Industry: {company_context.get('industry', 'Unknown')}
- Description: {(company_context.get('description') or '')[:400]}
- Mission: {company_context.get('mission', 'Unknown')}
- Values: {', '.join(company_context.get('values', []))}
- Recent News: {', '.join(str(n) for n in company_context.get('recent_news', [])[:2])}
- Key Initiatives: {', '.join(company_context.get('key_initiatives', [])[:3])}
{interviewer_context}

Candidate Profile:
- Name: {user_profile.get('name', 'Unknown')}
- Current Title: {user_profile.get('title', 'Unknown')}
- Years Experience: {user_profile.get('years_experience', 'Unknown')}
- Skills: {', '.join(user_profile.get('skills', []))}
- Summary: {user_profile.get('summary', '')}
{questions_context}

Generate specific, personalized talking points. Respond ONLY with valid JSON:
{{
    "talking_points": [
        {{
            "topic": "<topic name>",
            "points": ["<specific point with example/detail>", ...],
            "use_when": "<when to bring this up in interview>"
        }}
    ],
    "key_stories": [
        {{
            "situation": "<brief STAR story setup>",
            "demonstrates": ["<skill1>", "<skill2>"],
            "best_for_questions_about": "<topic>"
        }}
    ],
    "company_specific_hooks": [
        {{
            "hook": "<specific thing to mention about company>",
            "why_it_matters": "<why this shows genuine interest>"
        }}
    ],
    "red_flags_to_avoid": ["<thing not to say>", ...]
}}

Guidelines:
- Make talking points SPECIFIC to this job and company
- Reference actual technologies and requirements from the posting
- Include concrete examples the candidate could use
- Create 5-7 topic areas with 2-4 points each
- Stories should be STAR-format ready
- Company hooks should show genuine research"""

        start_time = time.time()

        response = await client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "You are an experienced career coach helping a candidate prepare "
                               "for an interview. Generate specific, actionable talking points "
                               "tailored to the job and company. Respond only with valid JSON."
                },
                {"role": "user", "content": prompt}
            ],
            temperature=0.5,
            max_tokens=1500,
        )

        latency_ms = int((time.time() - start_time) * 1000)
        activity.logger.info(f"LLM talking points call completed in {latency_ms}ms")

        # Parse response
        content = response.choices[0].message.content or "{}"

        # Clean up potential markdown formatting
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        content = content.strip()

        result = extract_json(content)

        return {
            "talking_points": result.get("talking_points", []),
            "key_stories": result.get("key_stories", []),
            "company_specific_hooks": result.get("company_specific_hooks", []),
            "red_flags_to_avoid": result.get("red_flags_to_avoid", []),
            "_metadata": {
                "model": DEFAULT_MODEL,
                "latency_ms": latency_ms,
            }
        }

    except Exception as e:
        activity.logger.error(f"LLM talking points generation failed: {e}")
        # Fallback to basic talking points
        talking_points = [
            {
                "topic": "Why this company",
                "points": [
                    f"Interest in {company_context.get('industry', 'the industry')}",
                    "Alignment with company values",
                    "Excitement about the team's mission",
                ],
                "use_when": "When asked why you want to work here"
            },
            {
                "topic": "Relevant experience",
                "points": [
                    "Key accomplishments from recent roles",
                    "Technologies and skills that match requirements",
                    "Examples of similar problems you've solved",
                ],
                "use_when": "When asked about your background"
            },
            {
                "topic": "Technical expertise",
                "points": [
                    "Deep dive on your strongest technical skills",
                    "Architecture decisions you've made",
                    "How you approach technical challenges",
                ],
                "use_when": "During technical portions of interview"
            },
            {
                "topic": "Questions to ask",
                "points": [
                    "Team structure and collaboration",
                    "Growth opportunities",
                    "Current challenges and priorities",
                ],
                "use_when": "At the end of the interview"
            },
        ]

        return {
            "talking_points": talking_points,
            "key_stories": [],
            "company_specific_hooks": [],
            "red_flags_to_avoid": [],
            "error": f"Fallback talking points used (LLM error: {str(e)[:100]})"
        }


@activity.defn
async def generate_prep_document(prep_data: dict) -> Optional[str]:
    """Generate comprehensive prep document."""
    activity.logger.info("Generating prep document")

    # Generate a structured prep document
    doc = f"""
# Interview Prep: {prep_data.get('job_title')} at {prep_data.get('company_name')}

## Interview Details
- **Type:** {prep_data.get('interview_type', 'General')}
- **Round:** {prep_data.get('interview_round', 1)}
- **Scheduled:** {prep_data.get('scheduled_at', 'TBD')}

## Company Context
{prep_data.get('company_context', {}).get('description', 'Research pending...')}

## Interviewers
"""

    for interviewer in prep_data.get('interviewer_profiles', []):
        doc += f"- **{interviewer.get('name')}** - {interviewer.get('title', 'Title unknown')}\n"

    doc += """
## Key Questions to Prepare

"""

    for q in prep_data.get('suggested_questions', [])[:10]:
        doc += f"- {q.get('question')}\n"

    doc += """
## Your Talking Points

"""

    for tp in prep_data.get('talking_points', []):
        doc += f"### {tp.get('topic')}\n"
        for point in tp.get('points', []):
            doc += f"- {point}\n"

    return doc


@activity.defn
async def save_interview_prep(
    interview_id: str,
    prep_data: dict,
    prep_document: Optional[str],
) -> str:
    """Save interview prep to database."""
    activity.logger.info(f"Saving interview prep for {interview_id}")

    conn = await get_db_connection()
    try:
        import uuid
        import json
        prep_id = str(uuid.uuid4())

        await conn.execute(
            """
            INSERT INTO interview_prep (id, interview_id, prep_data, prep_document, created_at)
            VALUES ($1, $2, $3, $4, NOW())
            """,
            uuid.UUID(prep_id),
            uuid.UUID(interview_id),
            json.dumps(prep_data),
            prep_document,
        )

        return prep_id
    finally:
        await conn.close()


@activity.defn
async def update_interview_status(
    interview_id: str,
    status: str,
    metadata: Optional[dict] = None,
) -> None:
    """Update interview status."""
    activity.logger.info(f"Updating interview {interview_id} status to {status}")

    conn = await get_db_connection()
    try:
        import uuid
        await conn.execute(
            "UPDATE interviews SET status = $2, updated_at = NOW() WHERE id = $1",
            uuid.UUID(interview_id),
            status,
        )
    finally:
        await conn.close()


# =============================================================================
# SHARED ACTIVITIES
# =============================================================================

@activity.defn
async def notify_user(notification_type: str, data: dict) -> None:
    """Send notification to user (email, Slack, etc.)."""
    activity.logger.info(f"Notification: {notification_type}")

    # This would integrate with notification services
    # For now, just log
    activity.logger.info(f"Notification data: {data}")
