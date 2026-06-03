"""
Temporal activities for job matching and scoring.

These activities handle the job-resume matching pipeline,
from fast filtering to detailed LLM analysis.
"""

from typing import Any, Dict, List, Optional

from temporalio import activity

# Import utilities using absolute imports
from utils.matching import (
    calculate_quick_score,
    extract_salary_from_text,
)
from utils.llm import (
    analyze_job_fit,
    extract_job_requirements,
    generate_skill_gap_analysis,
)
from utils.database import fetch_one, record_to_dict
from utils.profile import resume_dict
from utils import profile as profile_module


async def get_default_resume_profile() -> Optional[Dict[str, Any]]:
    """
    Fetch the default resume profile from the database.

    Returns:
        Resume dict in the format expected by matching functions, or None if not found.
    """
    record = await fetch_one(
        "SELECT * FROM resume_profiles WHERE is_default = TRUE LIMIT 1"
    )

    if record is None:
        return None

    db_resume = record_to_dict(record)
    return convert_db_resume_to_dict(db_resume)


def convert_db_resume_to_dict(db_resume: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert a database resume_profiles record to the nested dict format
    expected by the matching functions.

    Args:
        db_resume: Dict from resume_profiles table

    Returns:
        Resume dict with the nested structure the matching functions expect.
    """
    # Get skills as a flat list from the DB array
    skills_list = db_resume.get("skills") or []

    # Categorize skills into groups (best effort based on common patterns)
    skills_categorized = {
        "ai_automation": [],
        "backend": [],
        "frontend": [],
        "domain": [],
        "other": []
    }

    # Keyword-based categorization
    ai_keywords = ["ai", "ml", "llm", "agent", "autonomous", "prompt", "machine learning"]
    backend_keywords = ["python", "fastapi", "temporal", "postgresql", "sql", "redis",
                        "docker", "kubernetes", "api", "backend", "node", "java", "go"]
    frontend_keywords = ["react", "typescript", "javascript", "css", "tailwind", "vue",
                         "angular", "frontend", "ui", "ux", "html"]
    # Domain-expertise keywords are configured per candidate in the profile.
    domain_keywords = profile_module.domain_keywords()

    for skill in skills_list:
        skill_lower = skill.lower()
        if any(kw in skill_lower for kw in ai_keywords):
            skills_categorized["ai_automation"].append(skill)
        elif any(kw in skill_lower for kw in backend_keywords):
            skills_categorized["backend"].append(skill)
        elif any(kw in skill_lower for kw in frontend_keywords):
            skills_categorized["frontend"].append(skill)
        elif any(kw in skill_lower for kw in domain_keywords):
            skills_categorized["domain"].append(skill)
        else:
            skills_categorized["other"].append(skill)

    # Remove empty categories
    skills_categorized = {k: v for k, v in skills_categorized.items() if v}

    # If no categorization worked, just put all skills in "other"
    if not skills_categorized:
        skills_categorized = {"other": skills_list}

    # Map preferred_remote to work_types list
    work_types = []
    preferred_remote = db_resume.get("preferred_remote", "").lower()
    if preferred_remote == "remote":
        work_types = ["remote"]
    elif preferred_remote == "hybrid":
        work_types = ["remote", "hybrid"]
    elif preferred_remote == "onsite":
        work_types = ["onsite"]
    else:
        work_types = ["remote", "hybrid"]  # Default to flexible

    # Build the resume dict in expected format
    return {
        "name": db_resume.get("full_name", ""),
        "email": db_resume.get("email", ""),
        "location": db_resume.get("location", ""),
        "summary": db_resume.get("experience_summary", ""),
        "skills": skills_categorized,
        "years_of_experience": db_resume.get("experience_years", 5),
        "preferences": {
            "target_roles": db_resume.get("target_titles") or [],
            "industries": db_resume.get("target_industries") or [],
            "work_types": work_types,
            "salary_expectation": {
                "min": db_resume.get("salary_expectation_min", 0),
                "max": db_resume.get("salary_expectation_max", 999999),
                "currency": "USD"
            }
        },
        # Preserve original DB fields for reference
        "_db_id": db_resume.get("id"),
        "_db_user_id": db_resume.get("user_id"),
    }


def load_resume_from_profile() -> Dict[str, Any]:
    """Load the resume from the configured candidate profile (offline fallback)."""
    return resume_dict()


async def load_resume() -> Dict[str, Any]:
    """
    Load resume from the database (preferred) or fall back to the candidate profile.

    Queries the resume_profiles table for the default resume first. If none is
    found, falls back to the resume defined in the candidate profile
    (see ``utils.profile`` / ``profile.example.yaml``).

    Returns:
        Resume dict in the format expected by matching functions.
    """
    # Try database first
    try:
        db_resume = await get_default_resume_profile()
        if db_resume is not None:
            activity.logger.info("Loaded resume from database (is_default=TRUE)")
            return db_resume
    except Exception as e:
        activity.logger.warning(f"Failed to load resume from database: {e}")

    # Fallback to the candidate profile
    activity.logger.info("Falling back to candidate profile resume")
    return load_resume_from_profile()


@activity.defn
async def quick_filter_job(job: Dict[str, Any]) -> Dict[str, Any]:
    """
    Fast pre-filtering of a job before expensive LLM analysis.

    Args:
        job: Job data dict with title, description, location, etc.

    Returns:
        dict with:
            - job_id: The job's ID
            - quick_score: 0-100 fast score
            - components: Breakdown of score components
            - should_analyze: Whether to proceed with LLM analysis
    """
    activity.logger.info(f"Quick filtering job: {job.get('title', 'Unknown')}")

    resume = await load_resume()

    # Extract salary if not already present
    if not job.get("salary_min") and not job.get("salary_max"):
        description = job.get("description", "")
        min_sal, max_sal = extract_salary_from_text(description)
        if min_sal:
            job["salary_min"] = min_sal
            job["salary_max"] = max_sal

    result = calculate_quick_score(job, resume)
    result["job_id"] = job.get("id")
    result["job_title"] = job.get("title")
    result["company"] = job.get("company_name")

    activity.logger.info(
        f"Quick score for {job.get('title')}: {result['quick_score']} "
        f"(analyze: {result['should_analyze']})"
    )

    return result


@activity.defn
async def calculate_fit_score(job: Dict[str, Any], resume: Optional[Dict[str, Any]] = None) -> dict:
    """
    Calculate detailed fit score using LLM analysis.

    This is the main matching activity that uses Grok to analyze
    how well a job matches the candidate's background.

    Args:
        job: Job data dict with full description
        resume: Optional resume dict (loads default if not provided)

    Returns:
        dict with:
            - fit_score: 0-100 overall match score
            - skills_matched: List of matching skills
            - skills_missing: List of required skills not possessed
            - experience_match: Assessment of experience fit
            - title_alignment: How well title matches target roles
            - reasoning: Detailed explanation
            - strengths: Why candidate is a good fit
            - concerns: Potential concerns or gaps
    """
    activity.logger.info(f"Calculating fit score for: {job.get('title', 'Unknown')}")

    if resume is None:
        resume = await load_resume()

    # Build job description text
    job_text = f"""
Title: {job.get('title', 'Unknown')}
Company: {job.get('company_name', 'Unknown')}
Location: {job.get('location', 'Unknown')}
Remote: {job.get('remote_type', 'Unknown')}

Description:
{job.get('description', 'No description')}

Requirements:
{job.get('requirements', 'No requirements listed')}
"""

    # Get LLM analysis
    result = await analyze_job_fit(job_text, resume)

    # Add job metadata
    result["job_id"] = job.get("id")
    result["job_title"] = job.get("title")
    result["company"] = job.get("company_name")

    activity.logger.info(
        f"Fit score for {job.get('title')}: {result.get('fit_score', 'N/A')}"
    )

    return result


@activity.defn
async def rank_jobs(job_ids: List[str], jobs_data: List[Dict[str, Any]]) -> List[dict]:
    """
    Rank multiple jobs by fit score.

    Performs quick filtering first, then detailed analysis
    on promising jobs.

    Args:
        job_ids: List of job IDs to rank
        jobs_data: List of job data dicts corresponding to IDs

    Returns:
        List of ranked jobs with scores, sorted by fit_score desc
    """
    activity.logger.info(f"Ranking {len(job_ids)} jobs")

    resume = await load_resume()
    results = []

    # Phase 1: Quick filter all jobs
    quick_results = []
    for job in jobs_data:
        score_result = calculate_quick_score(job, resume)
        quick_results.append({
            "job": job,
            "quick_score": score_result["quick_score"],
            "should_analyze": score_result["should_analyze"],
            "components": score_result["components"],
        })

    # Sort by quick score
    quick_results.sort(key=lambda x: x["quick_score"], reverse=True)

    # Phase 2: Detailed analysis on top candidates
    analyze_count = 0
    max_analyze = 10  # Limit LLM calls

    for item in quick_results:
        job = item["job"]

        if item["should_analyze"] and analyze_count < max_analyze:
            # Get detailed LLM analysis
            detailed = await calculate_fit_score(job, resume)
            analyze_count += 1

            results.append({
                "job_id": job.get("id"),
                "job_title": job.get("title"),
                "company": job.get("company_name"),
                "quick_score": item["quick_score"],
                "fit_score": detailed.get("fit_score", item["quick_score"]),
                "skills_matched": detailed.get("skills_matched", []),
                "skills_missing": detailed.get("skills_missing", []),
                "reasoning": detailed.get("reasoning", ""),
                "strengths": detailed.get("strengths", []),
                "concerns": detailed.get("concerns", []),
                "analyzed": True,
            })
        else:
            # Use quick score only
            results.append({
                "job_id": job.get("id"),
                "job_title": job.get("title"),
                "company": job.get("company_name"),
                "quick_score": item["quick_score"],
                "fit_score": item["quick_score"],
                "components": item["components"],
                "analyzed": False,
            })

    # Final sort by fit score
    results.sort(key=lambda x: x["fit_score"], reverse=True)

    activity.logger.info(
        f"Ranked {len(results)} jobs, analyzed {analyze_count} in detail"
    )

    return results


@activity.defn
async def identify_skill_gaps(job_id: str, job_data: Dict[str, Any]) -> dict:
    """
    Identify skills the candidate would need to learn for a specific job.

    Provides detailed analysis of:
    - Critical missing skills
    - Transferable skills
    - Learning recommendations
    - Time to readiness

    Args:
        job_id: The job's ID
        job_data: Full job data dict

    Returns:
        dict with gap analysis and recommendations
    """
    activity.logger.info(f"Identifying skill gaps for job: {job_id}")

    resume = await load_resume()

    # First extract structured requirements
    job_text = f"""
{job_data.get('title', '')}

{job_data.get('description', '')}

Requirements:
{job_data.get('requirements', '')}
"""

    requirements = await extract_job_requirements(job_text)

    # Then analyze gaps
    gap_analysis = await generate_skill_gap_analysis(requirements, resume)

    # Combine results
    result = {
        "job_id": job_id,
        "job_title": job_data.get("title"),
        "company": job_data.get("company_name"),
        "extracted_requirements": {
            "required_skills": requirements.get("required_skills", []),
            "preferred_skills": requirements.get("preferred_skills", []),
            "tech_stack": requirements.get("tech_stack", []),
            "years_experience": requirements.get("years_experience", {}),
            "level": requirements.get("level"),
        },
        "gap_analysis": {
            "critical_gaps": gap_analysis.get("critical_gaps", []),
            "transferable_skills": gap_analysis.get("transferable_skills", []),
            "experience_gap": gap_analysis.get("experience_gap", {}),
            "quick_wins": gap_analysis.get("quick_wins", []),
            "time_to_ready": gap_analysis.get("time_to_ready", "unknown"),
            "overall_readiness": gap_analysis.get("overall_readiness", "unknown"),
        },
        "_metadata": {
            "requirements_llm": requirements.get("_metadata", {}),
            "gap_llm": gap_analysis.get("_metadata", {}),
        }
    }

    activity.logger.info(
        f"Gap analysis complete: {gap_analysis.get('overall_readiness', 'unknown')} readiness"
    )

    return result


@activity.defn
async def batch_quick_filter(jobs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Quickly filter a batch of jobs without LLM calls.

    Use this for high-volume initial filtering.

    Args:
        jobs: List of job data dicts

    Returns:
        List of jobs with quick scores, filtered to promising candidates
    """
    activity.logger.info(f"Batch quick filtering {len(jobs)} jobs")

    resume = await load_resume()
    results = []

    for job in jobs:
        # Extract salary if needed
        if not job.get("salary_min") and not job.get("salary_max"):
            description = job.get("description", "")
            min_sal, max_sal = extract_salary_from_text(description)
            if min_sal:
                job["salary_min"] = min_sal
                job["salary_max"] = max_sal

        score_result = calculate_quick_score(job, resume)

        results.append({
            "job_id": job.get("id"),
            "job_title": job.get("title"),
            "company": job.get("company_name"),
            "location": job.get("location"),
            "remote_type": job.get("remote_type"),
            "quick_score": score_result["quick_score"],
            "components": score_result["components"],
            "should_analyze": score_result["should_analyze"],
            "url": job.get("url"),
        })

    # Sort by score
    results.sort(key=lambda x: x["quick_score"], reverse=True)

    # Return only promising candidates
    promising = [r for r in results if r["should_analyze"]]

    activity.logger.info(
        f"Filtered to {len(promising)} promising jobs out of {len(jobs)}"
    )

    return promising


@activity.defn
async def extract_requirements(job_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract structured requirements from a job posting.

    Args:
        job_data: Job data dict with description

    Returns:
        Structured requirements dict
    """
    activity.logger.info(f"Extracting requirements for: {job_data.get('title', 'Unknown')}")

    job_text = f"""
{job_data.get('title', '')}
{job_data.get('company_name', '')}

{job_data.get('description', '')}

Requirements:
{job_data.get('requirements', '')}
"""

    requirements = await extract_job_requirements(job_text)
    requirements["job_id"] = job_data.get("id")
    requirements["job_title"] = job_data.get("title")

    return requirements
