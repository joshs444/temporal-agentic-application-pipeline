"""
Grok Agentic Job Search Client.

One of the pluggable job-discovery connectors. Uses xAI's Responses API with the
``web_search`` tool to discover job listings agentically (more cost-effective than
a paid search API since the tool calls are free - only tokens cost).

This connector is xAI-specific: the Responses API + web_search tool are not part
of the OpenAI-compatible surface, so it reads its own config. The API key falls
back to the shared LLM_API_KEY when XAI_API_KEY is not set.
"""

import json
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Optional

import httpx

from utils.llm_config import LLM_API_KEY

# Configuration
XAI_API_KEY = os.getenv("XAI_API_KEY", "") or LLM_API_KEY
XAI_RESPONSES_URL = os.getenv("XAI_RESPONSES_URL", "https://api.x.ai/v1/responses")
SEARCH_MODEL = os.getenv("LLM_SEARCH_MODEL", "grok-4-1-fast")  # Optimized for agentic search


@dataclass
class JobListing:
    """Structured job listing from Grok search."""

    external_id: str
    title: str
    company_name: str
    company_url: Optional[str]
    location: str
    remote_type: str  # remote, hybrid, onsite, unknown
    salary_min: Optional[int]
    salary_max: Optional[int]
    salary_currency: str
    description: str
    requirements: list[str]
    url: str
    source: str  # linkedin, indeed, company_career_page, etc
    posted_at: Optional[datetime]

    # Contact info for outreach
    recruiter_name: Optional[str] = None
    recruiter_email: Optional[str] = None
    recruiter_linkedin: Optional[str] = None
    hiring_manager_name: Optional[str] = None
    hiring_manager_linkedin: Optional[str] = None
    careers_email: Optional[str] = None

    # Company context
    company_industry: Optional[str] = None
    company_size: Optional[str] = None
    company_funding: Optional[str] = None
    tech_stack: list[str] = field(default_factory=list)

    # Application details
    apply_method: str = "url"  # url, email, linkedin_easy_apply
    application_deadline: Optional[datetime] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for database storage."""
        return {
            "external_id": self.external_id,
            "title": self.title,
            "company_name": self.company_name,
            "company_url": self.company_url,
            "location": self.location,
            "remote_type": self.remote_type,
            "salary_min": self.salary_min,
            "salary_max": self.salary_max,
            "salary_currency": self.salary_currency,
            "description": self.description,
            "requirements": self.requirements,
            "url": self.url,
            "source": self.source,
            "posted_at": self.posted_at.isoformat() if self.posted_at else None,
            "recruiter_name": self.recruiter_name,
            "recruiter_email": self.recruiter_email,
            "recruiter_linkedin": self.recruiter_linkedin,
            "hiring_manager_name": self.hiring_manager_name,
            "hiring_manager_linkedin": self.hiring_manager_linkedin,
            "careers_email": self.careers_email,
            "company_industry": self.company_industry,
            "company_size": self.company_size,
            "company_funding": self.company_funding,
            "tech_stack": self.tech_stack,
            "apply_method": self.apply_method,
            "application_deadline": self.application_deadline.isoformat() if self.application_deadline else None,
        }


async def call_xai_responses_api(
    prompt: str,
    system_prompt: str = "",
    tools: list[dict] | None = None,
    temperature: float = 0.2,
    max_tokens: int = 8000,
) -> dict[str, Any]:
    """
    Call xAI Responses API with web_search tool.

    Args:
        prompt: User prompt
        system_prompt: Optional system prompt
        tools: List of tools to enable (e.g., [{"type": "web_search"}])
        temperature: Sampling temperature
        max_tokens: Maximum tokens in response

    Returns:
        Response dict with content and usage info
    """
    if not XAI_API_KEY:
        raise ValueError("XAI_API_KEY environment variable is required")

    # Build input messages
    input_messages = []
    if system_prompt:
        input_messages.append({"role": "system", "content": system_prompt})
    input_messages.append({"role": "user", "content": prompt})

    # Build request body
    request_body = {
        "model": SEARCH_MODEL,
        "input": input_messages,
        "temperature": temperature,
        "max_output_tokens": max_tokens,
    }

    # Add tools if specified
    if tools:
        request_body["tools"] = tools

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {XAI_API_KEY}",
    }

    async with httpx.AsyncClient(timeout=180.0) as client:
        response = await client.post(
            XAI_RESPONSES_URL,
            headers=headers,
            json=request_body,
        )

        if response.status_code != 200:
            error_text = response.text
            print(f"[GrokSearch] API Error: {error_text}")
            return {
                "content": "",
                "error": error_text,
                "usage": {"prompt_tokens": 0, "completion_tokens": 0},
            }

        data = response.json()

        # Debug: log response structure
        print(f"[GrokSearch] Response keys: {list(data.keys())}")
        print(f"[GrokSearch] Top-level text length: {len(str(data.get('text', '')))}")
        if "output" in data:
            print(f"[GrokSearch] Output count: {len(data.get('output', []))}")
            for i, item in enumerate(data.get('output', [])):
                if item.get('type') == 'message' and 'content' in item:
                    for j, c in enumerate(item.get('content', [])):
                        text_val = c.get('text', '')
                        text_len = len(text_val) if isinstance(text_val, str) else 0
                        print(f"[GrokSearch] Output[{i}].content[{j}]: type={c.get('type')}, text_length={text_len}")
                        if text_len > 0:
                            preview = text_val[:300] if isinstance(text_val, str) else str(text_val)[:300]
                            print(f"[GrokSearch] Text preview: {preview}...")

        # Extract content from response
        # Responses API puts content in output.message.content
        content = ""

        # Look in output messages for the actual response text
        if "output" in data:
            for output_item in data.get("output", []):
                if output_item.get("type") == "message":
                    for content_item in output_item.get("content", []):
                        text_val = content_item.get("text", "")
                        if isinstance(text_val, str) and text_val:
                            # output_text is the actual text response
                            if content_item.get("type") in ("output_text", "text"):
                                content += text_val
            if content:
                print(f"[GrokSearch] Extracted message text, length: {len(content)}")

        # Get usage info
        usage = data.get("usage", {})

        return {
            "content": content,
            "usage": {
                "prompt_tokens": usage.get("input_tokens", 0),
                "completion_tokens": usage.get("output_tokens", 0),
            },
            "citations": data.get("citations", []),
        }


async def _search_single_batch(
    keywords: list[str],
    locations: list[str],
    remote_ok: bool,
    experience_years: Optional[int],
    salary_min: Optional[int],
    max_results: int,
    exclude_companies: Optional[list[str]],
    target_companies: Optional[list[str]],
    posted_within_days: int,
) -> dict[str, Any]:
    """Search for a single batch of job titles."""
    # Build the search prompt
    location_str = " OR ".join(locations) if locations else "anywhere"
    keyword_str = " OR ".join(f'"{k}"' for k in keywords)

    exclude_str = ""
    if exclude_companies:
        exclude_str = f"\n- EXCLUDE these companies: {', '.join(exclude_companies)}"

    target_str = ""
    if target_companies:
        target_str = f"\n- PRIORITIZE jobs at: {', '.join(target_companies)}"

    salary_str = ""
    if salary_min:
        salary_str = f"\n- Minimum salary: ${salary_min:,}/year"

    exp_str = ""
    if experience_years:
        exp_str = f"\n- Target experience level: ~{experience_years} years"

    # Allow up to 50 jobs per search (16k token budget supports this)
    jobs_to_find = min(max_results, 50)

    prompt = f"""Find {jobs_to_find} job listings for: {keyword_str}
Location: {location_str} (remote: {"yes" if remote_ok else "no"})
Posted within {posted_within_days} days{exp_str}{salary_str}{exclude_str}{target_str}

Search LinkedIn Jobs and Indeed. Return ONLY this JSON format:

{{"jobs":[{{"title":"..","company":"..","location":"..","remote":"remote|hybrid|onsite","salary_min":null,"salary_max":null,"description":"100 chars max","url":"..","source":"linkedin|indeed","posted_at":"2026-01-25"}}],"total":<count>}}

Rules: Real jobs only. Keep descriptions under 100 chars. Use null for missing salary. URL must be direct job link.
"""

    start_time = time.time()

    try:
        # Use Grok Responses API with web_search tool
        system_prompt = (
            "You are a job search assistant with web search capabilities. "
            "Search the web thoroughly for real job postings. "
            "Return only valid JSON with actual job listings you find. "
            "Do not fabricate or hallucinate job postings."
        )

        response = await call_xai_responses_api(
            prompt=prompt,
            system_prompt=system_prompt,
            tools=[{"type": "web_search"}],  # Enable agentic web search
            temperature=0.2,  # Low temp for factual search
            max_tokens=16000,  # Need room for multiple job listings
        )

        latency_ms = int((time.time() - start_time) * 1000)

        # Check for errors
        if response.get("error"):
            print(f"[GrokSearch] Error: {response['error']}")
            return {
                "jobs": [],
                "total_found": 0,
                "search_query": keyword_str,
                "latency_ms": latency_ms,
                "tokens_used": {
                    "prompt": response["usage"]["prompt_tokens"],
                    "completion": response["usage"]["completion_tokens"],
                },
                "error": response["error"],
            }

        # Extract content from response
        content = response.get("content", "{}")

        # Clean up markdown formatting if present
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]
        content = content.strip()

        # Parse JSON response
        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            print(f"[GrokSearch] JSON parse error: {e}")
            print(f"[GrokSearch] Raw content: {content[:500]}")
            return {
                "jobs": [],
                "total_found": 0,
                "search_query": keyword_str,
                "latency_ms": latency_ms,
                "tokens_used": {
                    "prompt": response["usage"]["prompt_tokens"],
                    "completion": response["usage"]["completion_tokens"],
                },
                "error": f"Failed to parse response: {str(e)}",
            }

        # Convert to JobListing objects
        jobs = []
        for job_data in data.get("jobs", []):
            try:
                # Generate unique external ID
                ext_id = f"grok-{uuid.uuid4().hex[:12]}"

                # Parse posted_at date
                posted_at = None
                if job_data.get("posted_at"):
                    try:
                        posted_at = datetime.fromisoformat(
                            job_data["posted_at"].replace("Z", "+00:00")
                        )
                    except (ValueError, TypeError):
                        # Try to parse relative dates like "2 days ago"
                        posted_str = str(job_data.get("posted_at", "")).lower()
                        if "day" in posted_str:
                            days = int(re.search(r"(\d+)", posted_str).group(1)) if re.search(r"(\d+)", posted_str) else 1
                            posted_at = datetime.utcnow() - timedelta(days=days)
                        elif "week" in posted_str:
                            weeks = int(re.search(r"(\d+)", posted_str).group(1)) if re.search(r"(\d+)", posted_str) else 1
                            posted_at = datetime.utcnow() - timedelta(weeks=weeks)
                        elif "hour" in posted_str:
                            posted_at = datetime.utcnow()

                job = JobListing(
                    external_id=ext_id,
                    title=job_data.get("title", "Unknown"),
                    # Handle both "company" and "company_name" field names
                    company_name=job_data.get("company") or job_data.get("company_name", "Unknown"),
                    company_url=job_data.get("company_url"),
                    location=job_data.get("location", "Unknown"),
                    # Handle both "remote" and "remote_type" field names
                    remote_type=job_data.get("remote") or job_data.get("remote_type", "unknown"),
                    salary_min=job_data.get("salary_min"),
                    salary_max=job_data.get("salary_max"),
                    salary_currency=job_data.get("salary_currency", "USD"),
                    description=job_data.get("description", "")[:2000],
                    requirements=job_data.get("requirements", []),
                    url=job_data.get("url", ""),
                    source=job_data.get("source", "grok_search"),
                    posted_at=posted_at,
                )
                jobs.append(job)
            except Exception as e:
                print(f"[GrokSearch] Error parsing job: {e}")
                continue

        # Handle both old "search_summary" format and new simplified "total" format
        total_found = data.get("total") or data.get("search_summary", {}).get("total_found") or len(jobs)

        return {
            "jobs": jobs,
            "total_found": total_found,
            "sites_searched": data.get("search_summary", {}).get("sites_searched", []),
            "search_query": keyword_str,
            "latency_ms": latency_ms,
            "tokens_used": {
                "prompt": response["usage"]["prompt_tokens"],
                "completion": response["usage"]["completion_tokens"],
            },
            "citations": response.get("citations", []),
        }

    except Exception as e:
        latency_ms = int((time.time() - start_time) * 1000)
        print(f"[GrokSearch] Error: {e}")
        return {
            "jobs": [],
            "total_found": 0,
            "search_query": keyword_str,
            "latency_ms": latency_ms,
            "tokens_used": {"prompt": 0, "completion": 0},
            "error": str(e),
        }


async def search_jobs_with_grok(
    keywords: list[str],
    locations: list[str],
    remote_ok: bool = True,
    experience_years: Optional[int] = None,
    salary_min: Optional[int] = None,
    max_results: int = 20,
    exclude_companies: Optional[list[str]] = None,
    target_companies: Optional[list[str]] = None,
    posted_within_days: int = 7,
) -> dict[str, Any]:
    """
    Use Grok agentic web search to find job listings.

    Batches keywords into groups of 2 to improve search quality.
    Each batch runs as a separate search, results are combined and deduplicated.
    """
    start_time = time.time()

    # Batch keywords into groups of 2 for better search focus
    batch_size = 2
    batches = [keywords[i:i + batch_size] for i in range(0, len(keywords), batch_size)]

    # Request 5 jobs per batch to avoid truncated JSON responses
    jobs_per_batch = 5

    print(f"[GrokSearch] Searching in {len(batches)} batches of ~{batch_size} titles each")

    all_jobs: list[JobListing] = []
    total_tokens = {"prompt": 0, "completion": 0}
    all_citations = []

    # Run batches (could be parallel but sequential is safer for rate limits)
    for i, batch in enumerate(batches):
        print(f"[GrokSearch] Batch {i + 1}/{len(batches)}: {batch}")
        result = await _search_single_batch(
            keywords=batch,
            locations=locations,
            remote_ok=remote_ok,
            experience_years=experience_years,
            salary_min=salary_min,
            max_results=jobs_per_batch,
            exclude_companies=exclude_companies,
            target_companies=target_companies,
            posted_within_days=posted_within_days,
        )

        if result.get("jobs"):
            all_jobs.extend(result["jobs"])

        tokens = result.get("tokens_used", {})
        total_tokens["prompt"] += tokens.get("prompt", 0)
        total_tokens["completion"] += tokens.get("completion", 0)

        if result.get("citations"):
            all_citations.extend(result["citations"])

        if result.get("error"):
            print(f"[GrokSearch] Batch {i + 1} error: {result['error']}")

    # Deduplicate by URL
    seen_urls = set()
    unique_jobs = []
    for job in all_jobs:
        if job.url and job.url not in seen_urls:
            seen_urls.add(job.url)
            unique_jobs.append(job)

    latency_ms = int((time.time() - start_time) * 1000)

    print(f"[GrokSearch] Total: {len(unique_jobs)} unique jobs from {len(all_jobs)} found")

    return {
        "jobs": unique_jobs[:max_results],
        "total_found": len(unique_jobs),
        "sites_searched": [],
        "search_query": " | ".join(keywords),
        "latency_ms": latency_ms,
        "tokens_used": total_tokens,
        "citations": all_citations,
    }


async def enrich_job_contacts(
    job: JobListing,
    company_name: str,
) -> dict[str, Any]:
    """
    Use Grok to find recruiter/hiring manager contacts for a specific job.

    This is a separate call for high-priority jobs to find outreach targets.
    """
    prompt = f"""Find contact information for outreach about this job:

Job: {job.title} at {company_name}
Job URL: {job.url}

Search for:
1. The recruiter who posted this job (check LinkedIn, the job posting)
2. The likely hiring manager (search LinkedIn for "{company_name} engineering manager" or similar)
3. General talent/careers email for {company_name}

Return JSON:
{{
    "recruiter": {{
        "name": "...",
        "email": "...",  // If publicly available
        "linkedin_url": "...",
        "title": "..."
    }},
    "hiring_manager": {{
        "name": "...",
        "linkedin_url": "...",
        "title": "..."
    }},
    "careers_email": "careers@company.com or null",
    "company_linkedin": "company LinkedIn page URL",
    "notes": "any relevant context about the company or role"
}}

Only include information you actually find - use null for missing fields.
"""

    try:
        system_prompt = (
            "You are a research assistant finding professional contact information. "
            "Only return real, publicly available information. Do not fabricate contacts."
        )

        response = await call_xai_responses_api(
            prompt=prompt,
            system_prompt=system_prompt,
            tools=[{"type": "web_search"}],
            temperature=0.1,
            max_tokens=1000,
        )

        if response.get("error"):
            print(f"[GrokSearch] Contact enrichment error: {response['error']}")
            return {
                "recruiter": None,
                "hiring_manager": None,
                "careers_email": None,
                "error": response["error"],
            }

        content = response.get("content", "{}")

        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]

        return json.loads(content.strip())

    except Exception as e:
        print(f"[GrokSearch] Contact enrichment error: {e}")
        return {
            "recruiter": None,
            "hiring_manager": None,
            "careers_email": None,
            "error": str(e),
        }


async def validate_job_url(url: str) -> dict[str, Any]:
    """
    Verify a job URL is real and still active.

    Returns validation status and any additional info found.
    """
    prompt = f"""Check if this job posting URL is valid and the job is still active:

URL: {url}

Return JSON:
{{
    "is_valid": true | false,
    "is_active": true | false,
    "job_title": "title if found",
    "company": "company if found",
    "reason": "why invalid/inactive if applicable"
}}
"""

    try:
        response = await call_xai_responses_api(
            prompt=prompt,
            system_prompt="Validate job posting URLs. Return factual status.",
            tools=[{"type": "web_search"}],
            temperature=0.1,
            max_tokens=500,
        )

        if response.get("error"):
            return {
                "is_valid": None,
                "is_active": None,
                "error": response["error"],
            }

        content = response.get("content", "{}")

        if "```" in content:
            content = content.split("```")[1].split("```")[0]
            if content.startswith("json"):
                content = content[4:]

        return json.loads(content.strip())

    except Exception as e:
        return {
            "is_valid": None,
            "is_active": None,
            "error": str(e),
        }
