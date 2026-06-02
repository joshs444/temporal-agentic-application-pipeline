"""
SerpApi client for Google Jobs search.

This module provides an async client for querying job postings via SerpApi's
Google Jobs API, with rate limiting, error handling, and structured parsing.
"""

import asyncio
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Optional

import httpx
from pydantic import BaseModel


# Rate limiting: SerpApi allows 100 requests/month on free tier, more on paid
# We'll implement a simple token bucket rate limiter
MAX_REQUESTS_PER_MINUTE = 10
REQUEST_INTERVAL = 60.0 / MAX_REQUESTS_PER_MINUTE  # 6 seconds between requests

SERPAPI_BASE_URL = "https://serpapi.com/search"


@dataclass
class JobPosting:
    """Structured job posting data extracted from SerpApi results."""

    external_id: str
    title: str
    company_name: str
    location: str
    description: str
    salary_min: Optional[int]
    salary_max: Optional[int]
    job_type: str  # full_time, contract, part_time, internship
    remote_type: str  # remote, hybrid, onsite, unknown
    posted_at: datetime
    url: str
    source: str  # linkedin, indeed, glassdoor, etc (via google jobs)
    requirements: list[str] = field(default_factory=list)
    benefits: list[str] = field(default_factory=list)
    company_logo_url: Optional[str] = None
    company_rating: Optional[float] = None
    company_reviews_count: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "external_id": self.external_id,
            "title": self.title,
            "company_name": self.company_name,
            "location": self.location,
            "description": self.description,
            "salary_min": self.salary_min,
            "salary_max": self.salary_max,
            "job_type": self.job_type,
            "remote_type": self.remote_type,
            "posted_at": self.posted_at.isoformat(),
            "url": self.url,
            "source": self.source,
            "requirements": self.requirements,
            "benefits": self.benefits,
            "company_logo_url": self.company_logo_url,
            "company_rating": self.company_rating,
            "company_reviews_count": self.company_reviews_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "JobPosting":
        """Create from dictionary."""
        data = data.copy()
        if isinstance(data.get("posted_at"), str):
            data["posted_at"] = datetime.fromisoformat(data["posted_at"])
        return cls(**data)


class SerpApiError(Exception):
    """Base exception for SerpApi errors."""

    pass


class RateLimitError(SerpApiError):
    """Rate limit exceeded."""

    pass


class AuthenticationError(SerpApiError):
    """Invalid API key."""

    pass


class SerpApiClient:
    """
    Async client for SerpApi Google Jobs API.

    Features:
    - Async HTTP requests via httpx
    - Rate limiting to respect API limits
    - Automatic retries with exponential backoff
    - Pagination support
    - Structured job data parsing
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        max_retries: int = 3,
        timeout: float = 30.0,
    ):
        """
        Initialize the SerpApi client.

        Args:
            api_key: SerpApi API key. Defaults to SERPAPI_KEY env var.
            max_retries: Maximum number of retries for failed requests.
            timeout: Request timeout in seconds.
        """
        self.api_key = api_key or os.getenv("SERPAPI_KEY")
        if not self.api_key:
            raise ValueError("SERPAPI_KEY environment variable or api_key required")

        self.max_retries = max_retries
        self.timeout = timeout
        self._last_request_time: Optional[float] = None
        self._lock = asyncio.Lock()

    async def _rate_limit(self) -> None:
        """Enforce rate limiting between requests."""
        async with self._lock:
            if self._last_request_time is not None:
                elapsed = asyncio.get_event_loop().time() - self._last_request_time
                if elapsed < REQUEST_INTERVAL:
                    await asyncio.sleep(REQUEST_INTERVAL - elapsed)
            self._last_request_time = asyncio.get_event_loop().time()

    async def _request(
        self,
        params: dict[str, Any],
        retry_count: int = 0,
    ) -> dict[str, Any]:
        """
        Make a rate-limited request to SerpApi.

        Args:
            params: Query parameters for the request.
            retry_count: Current retry attempt number.

        Returns:
            JSON response from SerpApi.

        Raises:
            SerpApiError: On API errors.
            RateLimitError: On rate limit exceeded.
            AuthenticationError: On invalid API key.
        """
        await self._rate_limit()

        params["api_key"] = self.api_key
        params["engine"] = "google_jobs"

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.get(SERPAPI_BASE_URL, params=params)

                if response.status_code == 401:
                    raise AuthenticationError("Invalid SerpApi API key")

                if response.status_code == 429:
                    if retry_count < self.max_retries:
                        wait_time = (2 ** retry_count) * 5  # 5, 10, 20 seconds
                        await asyncio.sleep(wait_time)
                        return await self._request(params, retry_count + 1)
                    raise RateLimitError("SerpApi rate limit exceeded")

                response.raise_for_status()
                return response.json()

            except httpx.HTTPStatusError as e:
                if retry_count < self.max_retries:
                    wait_time = (2 ** retry_count) * 2
                    await asyncio.sleep(wait_time)
                    return await self._request(params, retry_count + 1)
                raise SerpApiError(f"HTTP error: {e}") from e

            except httpx.RequestError as e:
                if retry_count < self.max_retries:
                    wait_time = (2 ** retry_count) * 2
                    await asyncio.sleep(wait_time)
                    return await self._request(params, retry_count + 1)
                raise SerpApiError(f"Request error: {e}") from e

    async def search_jobs(
        self,
        query: str,
        location: Optional[str] = None,
        ltype: Optional[int] = None,
        chips: Optional[str] = None,
        start: int = 0,
        num: int = 10,
    ) -> tuple[list[JobPosting], Optional[str]]:
        """
        Search for jobs using SerpApi Google Jobs.

        Args:
            query: Job search query (e.g., "Software Engineer Python").
            location: Location filter (e.g., "Boston, MA" or "Remote").
            ltype: Location type (1 = within X miles).
            chips: Filter chips for job type, date posted, etc.
            start: Pagination offset.
            num: Number of results (max 10 per page).

        Returns:
            Tuple of (list of JobPosting objects, next_page_token or None).
        """
        params: dict[str, Any] = {
            "q": query,
            "start": start,
        }

        if location:
            params["location"] = location

        if ltype:
            params["ltype"] = ltype

        if chips:
            params["chips"] = chips

        response = await self._request(params)
        jobs_results = response.get("jobs_results", [])
        jobs = [self._parse_job_result(job) for job in jobs_results]

        # Check for pagination
        serpapi_pagination = response.get("serpapi_pagination", {})
        next_page_token = serpapi_pagination.get("next_page_token")

        return jobs, next_page_token

    async def search_jobs_all_pages(
        self,
        query: str,
        location: Optional[str] = None,
        max_pages: int = 5,
        chips: Optional[str] = None,
    ) -> list[JobPosting]:
        """
        Search for jobs across multiple pages.

        Args:
            query: Job search query.
            location: Location filter.
            max_pages: Maximum number of pages to fetch.
            chips: Filter chips.

        Returns:
            List of all JobPosting objects found.
        """
        all_jobs: list[JobPosting] = []
        start = 0

        for page in range(max_pages):
            jobs, next_token = await self.search_jobs(
                query=query,
                location=location,
                start=start,
                chips=chips,
            )

            all_jobs.extend(jobs)

            if not next_token or not jobs:
                break

            start += 10  # SerpApi uses offset-based pagination

        return all_jobs

    async def get_job_details(self, job_id: str) -> Optional[JobPosting]:
        """
        Get detailed information for a specific job.

        Note: SerpApi Google Jobs doesn't have a direct job details endpoint.
        This searches for the job ID and returns details if found.

        Args:
            job_id: The external job ID (job_id from Google Jobs).

        Returns:
            JobPosting with details, or None if not found.
        """
        # SerpApi provides a job_id that can be used with htidocid parameter
        params: dict[str, Any] = {
            "q": "",  # Empty query when using htidocid
            "htidocid": job_id,
        }

        try:
            response = await self._request(params)
            jobs_results = response.get("jobs_results", [])

            if jobs_results:
                return self._parse_job_result(jobs_results[0])
            return None

        except SerpApiError:
            return None

    def _parse_job_result(self, job_data: dict[str, Any]) -> JobPosting:
        """
        Parse a job result from SerpApi into a JobPosting.

        Args:
            job_data: Raw job data from SerpApi response.

        Returns:
            Structured JobPosting object.
        """
        # Extract salary information
        salary_min, salary_max = self._parse_salary_from_job(job_data)

        # Determine job type
        job_type = self._determine_job_type(job_data)

        # Determine remote type
        remote_type = self._determine_remote_type(job_data)

        # Parse posting date
        posted_at = self._parse_posted_date(job_data)

        # Extract requirements and benefits from extensions
        requirements, benefits = self._parse_extensions(job_data)

        # Get description
        description = job_data.get("description", "")

        # Detect details array for additional info
        detected_extensions = job_data.get("detected_extensions", {})

        return JobPosting(
            external_id=job_data.get("job_id", ""),
            title=job_data.get("title", "Unknown Title"),
            company_name=job_data.get("company_name", "Unknown Company"),
            location=job_data.get("location", "Unknown Location"),
            description=description,
            salary_min=salary_min,
            salary_max=salary_max,
            job_type=job_type,
            remote_type=remote_type,
            posted_at=posted_at,
            url=self._get_apply_url(job_data),
            source=self._determine_source(job_data),
            requirements=requirements,
            benefits=benefits,
            company_logo_url=job_data.get("thumbnail"),
            company_rating=detected_extensions.get("company_rating"),
            company_reviews_count=detected_extensions.get("reviews_count"),
        )

    def _parse_salary_from_job(
        self, job_data: dict[str, Any]
    ) -> tuple[Optional[int], Optional[int]]:
        """Extract salary range from job data."""
        detected = job_data.get("detected_extensions", {})

        salary_min = None
        salary_max = None

        # Check for salary in detected_extensions
        if "salary" in detected:
            salary_text = detected["salary"]
            salary_min, salary_max = self._parse_salary_text(salary_text)

        # Also check extensions list
        for ext in job_data.get("extensions", []):
            if "$" in str(ext) or "salary" in str(ext).lower():
                parsed_min, parsed_max = self._parse_salary_text(str(ext))
                if parsed_min is not None:
                    salary_min = parsed_min
                if parsed_max is not None:
                    salary_max = parsed_max
                break

        return salary_min, salary_max

    def _parse_salary_text(self, text: str) -> tuple[Optional[int], Optional[int]]:
        """Parse salary text into min/max integers."""
        if not text:
            return None, None

        text = text.lower().replace(",", "").replace(" ", "")

        # Handle ranges like "$100k-$150k" or "$100,000 - $150,000"
        range_pattern = r"\$?(\d+(?:\.\d+)?)[k]?\s*[-–to]+\s*\$?(\d+(?:\.\d+)?)[k]?"
        match = re.search(range_pattern, text)

        if match:
            min_val = float(match.group(1))
            max_val = float(match.group(2))

            # Handle K notation
            if "k" in text or min_val < 1000:
                min_val *= 1000
                max_val *= 1000

            return int(min_val), int(max_val)

        # Handle single values like "$150k" or "$150,000"
        single_pattern = r"\$?(\d+(?:\.\d+)?)[k]?"
        match = re.search(single_pattern, text)

        if match:
            val = float(match.group(1))
            if "k" in text or val < 1000:
                val *= 1000
            return int(val), int(val)

        return None, None

    def _determine_job_type(self, job_data: dict[str, Any]) -> str:
        """Determine job type from job data."""
        detected = job_data.get("detected_extensions", {})
        extensions = job_data.get("extensions", [])

        # Check detected_extensions first
        if detected.get("schedule_type"):
            schedule = detected["schedule_type"].lower()
            if "full" in schedule:
                return "full_time"
            if "part" in schedule:
                return "part_time"
            if "contract" in schedule:
                return "contract"
            if "intern" in schedule:
                return "internship"

        # Check extensions list
        extensions_lower = [str(e).lower() for e in extensions]
        for ext in extensions_lower:
            if "full-time" in ext or "full time" in ext:
                return "full_time"
            if "part-time" in ext or "part time" in ext:
                return "part_time"
            if "contract" in ext:
                return "contract"
            if "intern" in ext:
                return "internship"
            if "temporary" in ext:
                return "temporary"

        return "full_time"  # Default assumption

    def _determine_remote_type(self, job_data: dict[str, Any]) -> str:
        """Determine remote work type from job data."""
        title = job_data.get("title", "").lower()
        location = job_data.get("location", "").lower()
        description = job_data.get("description", "").lower()
        extensions = [str(e).lower() for e in job_data.get("extensions", [])]
        detected = job_data.get("detected_extensions", {})

        # Check detected_extensions
        if detected.get("work_from_home"):
            return "remote"

        # Check for remote indicators
        remote_indicators = ["remote", "work from home", "wfh", "anywhere"]
        hybrid_indicators = ["hybrid", "flexible", "partial remote"]
        onsite_indicators = ["on-site", "onsite", "in-office", "in office"]

        all_text = f"{title} {location} {' '.join(extensions)} {description[:500]}"

        for indicator in remote_indicators:
            if indicator in all_text:
                return "remote"

        for indicator in hybrid_indicators:
            if indicator in all_text:
                return "hybrid"

        for indicator in onsite_indicators:
            if indicator in all_text:
                return "onsite"

        return "unknown"

    def _parse_posted_date(self, job_data: dict[str, Any]) -> datetime:
        """Parse the job posting date."""
        detected = job_data.get("detected_extensions", {})

        # Check for posted_at in detected_extensions
        if "posted_at" in detected:
            posted_text = detected["posted_at"].lower()
            return self._parse_relative_date(posted_text)

        # Check extensions
        for ext in job_data.get("extensions", []):
            ext_str = str(ext).lower()
            if "ago" in ext_str or "posted" in ext_str:
                return self._parse_relative_date(ext_str)

        # Default to now if no date found
        return datetime.utcnow()

    def _parse_relative_date(self, text: str) -> datetime:
        """Parse relative date text like '3 days ago'."""
        now = datetime.utcnow()

        # Pattern: X hours/days/weeks/months ago
        pattern = r"(\d+)\s*(hour|day|week|month)s?\s*ago"
        match = re.search(pattern, text.lower())

        if match:
            amount = int(match.group(1))
            unit = match.group(2)

            if unit == "hour":
                return now - timedelta(hours=amount)
            elif unit == "day":
                return now - timedelta(days=amount)
            elif unit == "week":
                return now - timedelta(weeks=amount)
            elif unit == "month":
                return now - timedelta(days=amount * 30)

        # Check for "today" or "just posted"
        if "today" in text or "just" in text:
            return now

        # Check for "yesterday"
        if "yesterday" in text:
            return now - timedelta(days=1)

        return now

    def _get_apply_url(self, job_data: dict[str, Any]) -> str:
        """Get the best apply URL for the job."""
        # Check for apply_options
        apply_options = job_data.get("apply_options", [])
        if apply_options:
            # Prefer direct company links over aggregators
            for option in apply_options:
                link = option.get("link", "")
                if link and "linkedin" not in link.lower():
                    return link
            # Fall back to first option
            if apply_options[0].get("link"):
                return apply_options[0]["link"]

        # Check for related_links
        related_links = job_data.get("related_links", [])
        if related_links:
            return related_links[0].get("link", "")

        # Check for share_link
        if job_data.get("share_link"):
            return job_data["share_link"]

        return ""

    def _determine_source(self, job_data: dict[str, Any]) -> str:
        """Determine the original source of the job posting."""
        # Check via field
        via = job_data.get("via", "")
        if via:
            via_lower = via.lower()
            if "linkedin" in via_lower:
                return "linkedin"
            if "indeed" in via_lower:
                return "indeed"
            if "glassdoor" in via_lower:
                return "glassdoor"
            if "ziprecruiter" in via_lower:
                return "ziprecruiter"
            # Clean up "via " prefix
            return via.replace("via ", "").strip()

        # Check apply_options
        for option in job_data.get("apply_options", []):
            title = option.get("title", "").lower()
            if "linkedin" in title:
                return "linkedin"
            if "indeed" in title:
                return "indeed"
            if "glassdoor" in title:
                return "glassdoor"

        return "google_jobs"

    def _parse_extensions(
        self, job_data: dict[str, Any]
    ) -> tuple[list[str], list[str]]:
        """Parse extensions to extract requirements and benefits."""
        requirements: list[str] = []
        benefits: list[str] = []

        # Job highlights often contain requirements and benefits
        highlights = job_data.get("job_highlights", [])

        for highlight in highlights:
            title = highlight.get("title", "").lower()
            items = highlight.get("items", [])

            if "qualifications" in title or "requirements" in title:
                requirements.extend(items)
            elif "benefits" in title or "perks" in title:
                benefits.extend(items)
            elif "responsibilities" in title:
                # Could be added to requirements context
                pass

        return requirements, benefits


# Convenience function for quick searches
async def search_jobs(
    query: str,
    location: Optional[str] = None,
    max_results: int = 50,
) -> list[JobPosting]:
    """
    Quick search for jobs.

    Args:
        query: Search query.
        location: Location filter.
        max_results: Maximum results to return.

    Returns:
        List of JobPosting objects.
    """
    client = SerpApiClient()
    max_pages = (max_results + 9) // 10  # Ceiling division

    jobs = await client.search_jobs_all_pages(
        query=query,
        location=location,
        max_pages=max_pages,
    )

    return jobs[:max_results]
