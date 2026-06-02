"""
SearchAPI.io client for Google Jobs search.

Uses SearchAPI.io's Google Jobs engine which aggregates from
LinkedIn, Indeed, Glassdoor, and company career pages.
Automatically filters out expired/closed listings.
"""

import asyncio
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Optional

import httpx


SEARCHAPI_BASE_URL = "https://www.searchapi.io/api/v1/search"


@dataclass
class JobPosting:
    """Structured job posting from SearchAPI."""

    external_id: str
    title: str
    company_name: str
    location: str
    description: str
    salary_min: Optional[int]
    salary_max: Optional[int]
    remote_type: str
    posted_at: datetime
    url: str
    source: str
    requirements: list[str] = field(default_factory=list)
    apply_email: Optional[str] = None  # Email found in posting for direct applications

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "external_id": self.external_id,
            "title": self.title,
            "company_name": self.company_name,
            "location": self.location,
            "description": self.description,
            "salary_min": self.salary_min,
            "salary_max": self.salary_max,
            "remote_type": self.remote_type,
            "posted_at": self.posted_at.isoformat() if self.posted_at else None,
            "url": self.url,
            "source": self.source,
            "requirements": self.requirements,
            "apply_email": self.apply_email,
        }


class SearchApiClient:
    """
    Async client for SearchAPI.io Google Jobs.

    Features:
    - Google Jobs aggregation (LinkedIn, Indeed, Glassdoor, etc.)
    - Automatic filtering of expired listings
    - Pagination support
    - Rate limiting
    """

    def __init__(self, api_key: Optional[str] = None, timeout: float = 30.0):
        self.api_key = api_key or os.getenv("SEARCHAPI_KEY")
        if not self.api_key:
            raise ValueError("SEARCHAPI_KEY environment variable required")
        self.timeout = timeout
        self._last_request = 0.0

    async def _rate_limit(self):
        """Simple rate limiting - 1 request per second."""
        now = asyncio.get_event_loop().time()
        if now - self._last_request < 1.0:
            await asyncio.sleep(1.0 - (now - self._last_request))
        self._last_request = asyncio.get_event_loop().time()

    async def search_jobs(
        self,
        query: str,
        location: Optional[str] = None,
        max_results: int = 50,
    ) -> list[JobPosting]:
        """
        Search for jobs using Google Jobs via SearchAPI.io.

        Args:
            query: Job search query (e.g., "machine learning engineer")
            location: Location filter (e.g., "Boston, MA" or "Remote")
            max_results: Maximum jobs to return

        Returns:
            List of JobPosting objects
        """
        all_jobs: list[JobPosting] = []
        next_page_token = None
        pages_fetched = 0
        max_pages = (max_results + 9) // 10  # ~10 results per page

        while pages_fetched < max_pages:
            await self._rate_limit()

            # For "Remote" location, add to query instead of location param
            # SearchAPI doesn't support "Remote" as a location value
            search_query = query
            if location and location.lower() == "remote":
                search_query = f"{query} remote"
                location = None  # Don't pass as location param

            params = {
                "engine": "google_jobs",
                "q": search_query,
                "api_key": self.api_key,
            }

            if location:
                params["location"] = location

            if next_page_token:
                params["next_page_token"] = next_page_token

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(SEARCHAPI_BASE_URL, params=params)
                response.raise_for_status()
                data = response.json()

            jobs_data = data.get("jobs", [])
            if not jobs_data:
                break

            for job_data in jobs_data:
                job = self._parse_job(job_data)
                if job:
                    all_jobs.append(job)

            # Check for pagination
            pagination = data.get("pagination", {})
            next_page_token = pagination.get("next_page_token")
            pages_fetched += 1

            if not next_page_token:
                break

            if len(all_jobs) >= max_results:
                break

        return all_jobs[:max_results]

    def _parse_job(self, data: dict) -> Optional[JobPosting]:
        """Parse raw job data into JobPosting."""
        try:
            # Extract salary
            salary_min, salary_max = self._parse_salary(data)

            # Determine remote type
            remote_type = self._parse_remote_type(data)

            # Parse posted date
            posted_at = self._parse_posted_date(data)

            # Get apply URL
            url = self._get_apply_url(data)

            # Get source
            source = self._parse_source(data)

            # Get description
            description = data.get("description", "")

            # Get requirements from highlights
            requirements = []
            for highlight in data.get("highlights", []):
                if "qualification" in highlight.get("title", "").lower():
                    requirements.extend(highlight.get("items", []))

            # Extract email from description for direct applications
            apply_email = self._extract_email(description)

            return JobPosting(
                external_id=data.get("id", ""),
                title=data.get("title", "Unknown"),
                company_name=data.get("company_name", "Unknown"),
                location=data.get("location", "Unknown"),
                description=description,
                salary_min=salary_min,
                salary_max=salary_max,
                remote_type=remote_type,
                posted_at=posted_at,
                url=url,
                source=source,
                requirements=requirements,
                apply_email=apply_email,
            )
        except Exception:
            return None

    def _parse_salary(self, data: dict) -> tuple[Optional[int], Optional[int]]:
        """Extract salary range from job data."""
        # Check detected_extensions
        extensions = data.get("detected_extensions", {})
        salary_text = extensions.get("salary", "")

        if not salary_text:
            # Check extensions array
            for ext in data.get("extensions", []):
                if "$" in str(ext):
                    salary_text = str(ext)
                    break

        if not salary_text:
            return None, None

        # Parse salary text
        text = salary_text.lower().replace(",", "").replace(" ", "")

        # Range pattern: $100k-$150k or $100,000-$150,000
        range_match = re.search(r"\$?(\d+(?:\.\d+)?)[k]?\s*[-–to]+\s*\$?(\d+(?:\.\d+)?)[k]?", text)
        if range_match:
            min_val = float(range_match.group(1))
            max_val = float(range_match.group(2))
            if "k" in text or min_val < 1000:
                min_val *= 1000
                max_val *= 1000
            return int(min_val), int(max_val)

        # Single value: $150k
        single_match = re.search(r"\$?(\d+(?:\.\d+)?)[k]?", text)
        if single_match:
            val = float(single_match.group(1))
            if "k" in text or val < 1000:
                val *= 1000
            return int(val), int(val)

        return None, None

    def _parse_remote_type(self, data: dict) -> str:
        """Determine remote work type."""
        title = data.get("title", "").lower()
        location = data.get("location", "").lower()
        description = data.get("description", "")[:500].lower()
        extensions = [str(e).lower() for e in data.get("extensions", [])]

        # Check detected_extensions
        detected = data.get("detected_extensions", {})
        if detected.get("work_from_home"):
            return "remote"

        all_text = f"{title} {location} {' '.join(extensions)} {description}"

        if any(x in all_text for x in ["remote", "work from home", "wfh"]):
            return "remote"
        if any(x in all_text for x in ["hybrid", "flexible"]):
            return "hybrid"
        if any(x in all_text for x in ["on-site", "onsite", "in-office"]):
            return "onsite"

        return "unknown"

    def _parse_posted_date(self, data: dict) -> datetime:
        """Parse posting date from job data."""
        detected = data.get("detected_extensions", {})
        posted_text = detected.get("posted_at", "")

        if not posted_text:
            for ext in data.get("extensions", []):
                if "ago" in str(ext).lower():
                    posted_text = str(ext)
                    break

        if posted_text:
            return self._parse_relative_date(posted_text)

        return datetime.utcnow()

    def _parse_relative_date(self, text: str) -> datetime:
        """Parse '3 days ago' style dates."""
        now = datetime.utcnow()
        text = text.lower()

        match = re.search(r"(\d+)\s*(hour|day|week|month)s?\s*ago", text)
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

        if "today" in text or "just" in text:
            return now
        if "yesterday" in text:
            return now - timedelta(days=1)

        return now

    def _get_apply_url(self, data: dict) -> str:
        """Get the best apply URL."""
        # Check apply_options (direct apply links)
        apply_options = data.get("apply_options", [])
        if apply_options:
            # Prefer direct company links over job boards
            for option in apply_options:
                link = option.get("link", "")
                if link and "linkedin" not in link.lower():
                    return link
            # Fall back to first available link
            if apply_options[0].get("link"):
                return apply_options[0]["link"]

        # Check share_link (Google Jobs share URL)
        if data.get("share_link"):
            return data["share_link"]

        # Check related_links
        related_links = data.get("related_links", [])
        if related_links:
            for link in related_links:
                if link.get("link"):
                    return link["link"]

        # Construct Google Jobs URL from job_id if available
        job_id = data.get("job_id") or data.get("id")
        if job_id:
            return f"https://www.google.com/search?q={job_id}&ibp=htl;jobs"

        return ""

    def _parse_source(self, data: dict) -> str:
        """Determine job source."""
        via = data.get("via", "")
        if via:
            via_lower = via.lower()
            if "linkedin" in via_lower:
                return "linkedin"
            if "indeed" in via_lower:
                return "indeed"
            if "glassdoor" in via_lower:
                return "glassdoor"
            return via.replace("via ", "").strip()

        return "google_jobs"

    def _extract_email(self, text: str) -> Optional[str]:
        """Extract first email address from text for direct applications."""
        if not text:
            return None
        # Match email addresses, prioritizing hiring/recruiting emails
        email_pattern = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
        emails = re.findall(email_pattern, text)
        if not emails:
            return None
        # Filter out common non-application emails
        filtered = [
            e for e in emails
            if not any(x in e.lower() for x in ["noreply", "no-reply", "donotreply", "unsubscribe"])
        ]
        return filtered[0] if filtered else emails[0]


async def search_jobs(
    query: str,
    location: Optional[str] = None,
    max_results: int = 50,
) -> list[JobPosting]:
    """Quick search function."""
    client = SearchApiClient()
    return await client.search_jobs(query, location, max_results)
