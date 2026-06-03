"""
Temporal Activities for Company Research and Enrichment

These activities handle company enrichment via Apollo.io, contact discovery,
hiring signal detection, and company culture research.
"""

import logging
from typing import Optional

from temporalio import activity

from clients.apollo import ApolloClient, Company
from utils.domain_finder import find_domain, normalize_company_name

log = logging.getLogger(__name__)

# Singleton Apollo client to reuse connections
_apollo_client: Optional[ApolloClient] = None


def get_apollo_client() -> ApolloClient:
    """Get or create Apollo client singleton."""
    global _apollo_client
    if _apollo_client is None:
        _apollo_client = ApolloClient()
    return _apollo_client


@activity.defn
async def enrich_company(company_name: str, domain: Optional[str] = None) -> dict:
    """
    Enrich company data via Apollo.

    If no domain is provided, attempts to find it using the domain finder utility.

    Args:
        company_name: Name of the company
        domain: Optional domain (e.g., "stripe.com")

    Returns:
        Dict with enriched company data, or empty dict if not found
    """
    log.info(f"Activity: enrich_company - {company_name} (domain={domain})")

    apollo = get_apollo_client()

    # Try to find domain if not provided
    if not domain:
        domain = await find_domain(company_name)
        if domain:
            log.info(f"Found domain for {company_name}: {domain}")

    company: Optional[Company] = None

    if domain:
        # Enrich by domain (most reliable)
        company = await apollo.enrich_company(domain)
    else:
        # Fall back to name search
        company = await apollo.search_company_by_name(company_name)

    if not company:
        log.warning(f"Could not enrich company: {company_name}")
        return {}

    return {
        "apollo_id": company.apollo_id,
        "name": company.name,
        "domain": company.domain,
        "industry": company.industry,
        "employee_count": company.employee_count,
        "employee_range": company.employee_range,
        "founded_year": company.founded_year,
        "funding_stage": company.funding_stage,
        "total_funding": company.total_funding,
        "headquarters": company.headquarters,
        "description": company.description,
        "tech_stack": company.tech_stack,
        "linkedin_url": company.linkedin_url,
        "website_url": company.website_url,
        "keywords": company.keywords,
    }


@activity.defn
async def find_hiring_contacts(company_domain: str, job_title: str) -> list[dict]:
    """
    Find recruiters and hiring managers at a company.

    Searches for relevant contacts based on the job title:
    - For engineering roles: Engineering Managers, Tech Leads, CTOs
    - For all roles: Recruiters, Talent Acquisition, HR

    Args:
        company_domain: Company domain (e.g., "stripe.com")
        job_title: The job title being applied for

    Returns:
        List of contact dicts with name, email, title, linkedin_url
    """
    log.info(f"Activity: find_hiring_contacts - {company_domain} for role: {job_title}")

    apollo = get_apollo_client()

    # Determine relevant titles to search based on job type
    job_lower = job_title.lower()

    # Always include recruitment-focused roles
    search_titles = [
        "Recruiter",
        "Technical Recruiter",
        "Talent Acquisition",
        "HR Manager",
        "People Operations",
    ]

    # Add role-specific hiring managers
    if any(term in job_lower for term in ["engineer", "developer", "software", "sre", "devops"]):
        search_titles.extend([
            "Engineering Manager",
            "Director of Engineering",
            "VP of Engineering",
            "CTO",
            "Tech Lead",
            "Head of Engineering",
        ])
    elif any(term in job_lower for term in ["product", "pm"]):
        search_titles.extend([
            "Product Manager",
            "Director of Product",
            "VP of Product",
            "Head of Product",
            "CPO",
        ])
    elif any(term in job_lower for term in ["design", "ux", "ui"]):
        search_titles.extend([
            "Design Manager",
            "Head of Design",
            "Director of Design",
            "VP of Design",
        ])
    elif any(term in job_lower for term in ["data", "analytics", "ml", "machine learning", "ai"]):
        search_titles.extend([
            "Data Science Manager",
            "Head of Data",
            "Director of Data",
            "VP of Data",
            "Chief Data Officer",
        ])
    elif any(term in job_lower for term in ["marketing"]):
        search_titles.extend([
            "Marketing Manager",
            "Director of Marketing",
            "VP of Marketing",
            "CMO",
        ])
    elif any(term in job_lower for term in ["sales", "account", "business development"]):
        search_titles.extend([
            "Sales Manager",
            "Director of Sales",
            "VP of Sales",
            "CRO",
        ])

    # Search for contacts
    contacts = await apollo.search_contacts(
        domain=company_domain,
        titles=search_titles,
        seniorities=["director", "vp", "manager", "c_suite"],
        per_page=20,
    )

    # Convert to dict format and prioritize recruiters
    result = []
    recruiters = []
    hiring_managers = []

    for contact in contacts:
        contact_dict = {
            "apollo_id": contact.apollo_id,
            "name": contact.name,
            "email": contact.email,
            "email_status": contact.email_status,
            "title": contact.title,
            "linkedin_url": contact.linkedin_url,
            "seniority": contact.seniority,
            "department": contact.department,
            "is_recruiter": _is_recruiter(contact.title),
        }

        if contact_dict["is_recruiter"]:
            recruiters.append(contact_dict)
        else:
            hiring_managers.append(contact_dict)

    # Return recruiters first, then hiring managers
    result = recruiters + hiring_managers

    log.info(
        f"Found {len(recruiters)} recruiters and {len(hiring_managers)} hiring managers "
        f"at {company_domain}"
    )

    return result


def _is_recruiter(title: Optional[str]) -> bool:
    """Check if a title is recruitment-related."""
    if not title:
        return False
    title_lower = title.lower()
    recruiter_keywords = [
        "recruiter",
        "recruiting",
        "talent acquisition",
        "talent partner",
        "hr ",
        "human resource",
        "people operations",
        "people partner",
    ]
    return any(kw in title_lower for kw in recruiter_keywords)


@activity.defn
async def get_company_hiring_signals(company_domain: str) -> dict:
    """
    Get hiring velocity and open positions for a company.

    This uses Apollo's job postings endpoint to detect hiring activity.

    Args:
        company_domain: Company domain (e.g., "stripe.com")

    Returns:
        Dict with:
        - open_positions: Total number of open positions
        - positions_by_department: Breakdown by department
        - positions_by_location: Breakdown by location
        - hiring_velocity: Qualitative assessment (high/medium/low)
        - sample_positions: List of sample job titles
    """
    log.info(f"Activity: get_company_hiring_signals - {company_domain}")

    apollo = get_apollo_client()

    job_postings = await apollo.get_job_postings(company_domain)

    if not job_postings:
        return {
            "open_positions": 0,
            "positions_by_department": {},
            "positions_by_location": {},
            "hiring_velocity": "unknown",
            "sample_positions": [],
        }

    # Analyze job postings
    positions_by_department: dict[str, int] = {}
    positions_by_location: dict[str, int] = {}
    sample_positions = []

    for posting in job_postings[:50]:  # Analyze up to 50 postings
        # Count by department
        dept = posting.department or "Unknown"
        positions_by_department[dept] = positions_by_department.get(dept, 0) + 1

        # Count by location
        loc = posting.location or "Remote/Unknown"
        positions_by_location[loc] = positions_by_location.get(loc, 0) + 1

        # Collect sample titles
        if len(sample_positions) < 10:
            sample_positions.append(posting.title)

    # Determine hiring velocity
    total = len(job_postings)
    if total >= 50:
        velocity = "very_high"
    elif total >= 20:
        velocity = "high"
    elif total >= 10:
        velocity = "medium"
    elif total >= 5:
        velocity = "low"
    else:
        velocity = "minimal"

    result = {
        "open_positions": total,
        "positions_by_department": positions_by_department,
        "positions_by_location": positions_by_location,
        "hiring_velocity": velocity,
        "sample_positions": sample_positions,
    }

    log.info(f"Hiring signals for {company_domain}: {total} open positions, velocity={velocity}")

    return result


@activity.defn
async def research_company_culture(
    company_name: str, company_domain: Optional[str] = None
) -> dict:
    """
    Research company culture using web search and LLM analysis.

    This activity searches for information about:
    - Glassdoor reviews
    - Interview process
    - Company values and culture
    - Work-life balance
    - Remote work policies

    Args:
        company_name: Company name to research
        company_domain: Optional company domain to disambiguate the search

    Returns:
        Dict with culture information:
        - glassdoor_rating: Numeric rating if available
        - culture_summary: LLM-generated summary
        - interview_process: Summary of interview process
        - remote_policy: Remote work policy if found
        - notable_benefits: List of notable benefits
        - red_flags: Any concerns found
        - sources: List of sources used
    """
    log.info(f"Activity: research_company_culture - {company_name}")

    # Normalize company name for search
    normalized_name = normalize_company_name(company_name)

    # This is a placeholder for LLM + web search integration
    # In production, this would:
    # 1. Use web search API (e.g., Perplexity, Google) to find culture info
    # 2. Parse Glassdoor, Blind, LinkedIn, etc.
    # 3. Use LLM to synthesize findings

    # For now, return a structured placeholder that can be filled in
    # when web search integration is added

    result = {
        "company_name": company_name,
        "company_domain": company_domain,
        "normalized_name": normalized_name,
        "glassdoor_rating": None,
        "culture_summary": None,
        "interview_process": None,
        "remote_policy": None,
        "notable_benefits": [],
        "red_flags": [],
        "sources": [],
        "status": "pending_integration",
        "message": (
            "Web search integration required. "
            "This activity will search Glassdoor, Blind, and other sources "
            "when the web search client is implemented."
        ),
    }

    log.info(f"Culture research for {company_name}: pending web search integration")

    return result


@activity.defn
async def batch_enrich_companies(companies: list[dict]) -> list[dict]:
    """
    Enrich multiple companies in batch.

    Useful for processing a list of companies from job search results.

    Args:
        companies: List of dicts with 'name' and optional 'domain' keys

    Returns:
        List of enriched company dicts
    """
    log.info(f"Activity: batch_enrich_companies - {len(companies)} companies")

    results = []
    for company_info in companies:
        name = company_info.get("name")
        domain = company_info.get("domain")

        if not name:
            continue

        try:
            enriched = await enrich_company(name, domain)
            if enriched:
                results.append(enriched)
            else:
                # Return minimal info if enrichment fails
                results.append({
                    "name": name,
                    "domain": domain,
                    "enrichment_status": "failed",
                })
        except Exception as e:
            log.warning(f"Failed to enrich {name}: {e}")
            results.append({
                "name": name,
                "domain": domain,
                "enrichment_status": "error",
                "error": str(e),
            })

    log.info(f"Batch enrichment complete: {len(results)}/{len(companies)} companies processed")

    return results
