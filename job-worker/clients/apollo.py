"""
Apollo.io API Client for Job Search

Simplified client for company enrichment and contact discovery,
tailored for job search use cases.
"""

import asyncio
import hashlib
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

import httpx

log = logging.getLogger(__name__)

APOLLO_BASE_URL = "https://api.apollo.io/v1"


@dataclass
class Company:
    """Company data from Apollo enrichment."""

    apollo_id: str
    name: str
    domain: str
    industry: Optional[str]
    employee_count: Optional[int]
    employee_range: Optional[str]
    founded_year: Optional[int]
    funding_stage: Optional[str]
    total_funding: Optional[int]
    headquarters: Optional[str]
    description: Optional[str]
    tech_stack: list[str] = field(default_factory=list)
    linkedin_url: Optional[str] = None
    website_url: Optional[str] = None
    keywords: list[str] = field(default_factory=list)
    # Raw API response for additional data mining
    _raw: dict = field(default_factory=dict)


@dataclass
class Contact:
    """Contact data from Apollo search."""

    apollo_id: str
    name: str
    email: Optional[str]
    email_status: Optional[str]  # verified, guessed, unavailable
    title: Optional[str]
    linkedin_url: Optional[str]
    seniority: Optional[str]
    department: Optional[str]
    # Raw API response
    _raw: dict = field(default_factory=dict)


@dataclass
class JobPosting:
    """Job posting data from Apollo."""

    title: str
    department: Optional[str]
    location: Optional[str]
    posted_date: Optional[str]
    url: Optional[str]
    # Raw API response
    _raw: dict = field(default_factory=dict)


class ApolloCache:
    """Simple in-memory cache for Apollo API responses."""

    def __init__(self, default_ttl: int = 3600):
        """Initialize cache with default TTL in seconds."""
        self._cache: dict[str, tuple[datetime, any]] = {}
        self._default_ttl = default_ttl

    def _make_key(self, prefix: str, *args) -> str:
        """Create a cache key from prefix and arguments."""
        key_data = f"{prefix}:{':'.join(str(a) for a in args)}"
        return hashlib.md5(key_data.encode()).hexdigest()

    def get(self, prefix: str, *args) -> Optional[any]:
        """Get cached value if not expired."""
        key = self._make_key(prefix, *args)
        if key in self._cache:
            expires, value = self._cache[key]
            if datetime.now() < expires:
                log.debug(f"Cache hit: {prefix}")
                return value
            else:
                del self._cache[key]
        return None

    def set(self, prefix: str, *args, value: any, ttl: Optional[int] = None) -> None:
        """Set cached value with TTL."""
        key = self._make_key(prefix, *args)
        expires = datetime.now() + timedelta(seconds=ttl or self._default_ttl)
        self._cache[key] = (expires, value)
        log.debug(f"Cache set: {prefix}")

    def clear(self) -> None:
        """Clear all cached values."""
        self._cache.clear()


class ApolloClient:
    """Client for Apollo.io API, optimized for job search use cases."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        timeout: float = 30.0,
        cache_ttl: int = 3600,
    ):
        """
        Initialize Apollo client.

        Args:
            api_key: Apollo API key. If not provided, reads from APOLLO_API_KEY env var.
            timeout: HTTP request timeout in seconds.
            cache_ttl: Default cache TTL in seconds (1 hour default).
        """
        self.api_key = api_key or os.getenv("APOLLO_API_KEY")
        if not self.api_key:
            raise ValueError("Apollo API key required. Set APOLLO_API_KEY environment variable.")

        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None
        self._cache = ApolloCache(default_ttl=cache_ttl)

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=APOLLO_BASE_URL,
                timeout=self.timeout,
                headers={
                    "Content-Type": "application/json",
                    "Cache-Control": "no-cache",
                    "X-Api-Key": self.api_key,
                },
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _request_with_retry(
        self,
        method: str,
        endpoint: str,
        payload: Optional[dict] = None,
        max_retries: int = 3,
    ) -> Optional[dict]:
        """Make HTTP request with retry logic for rate limits."""
        client = await self._get_client()

        for attempt in range(max_retries):
            try:
                if method == "POST":
                    response = await client.post(endpoint, json=payload)
                else:
                    response = await client.get(endpoint)

                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 60))
                    wait_time = min(retry_after, 120)
                    log.warning(
                        f"Apollo rate limited, waiting {wait_time}s (attempt {attempt + 1}/{max_retries})"
                    )
                    await asyncio.sleep(wait_time)
                    continue

                if response.status_code == 404:
                    return None

                response.raise_for_status()
                return response.json()

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429 and attempt < max_retries - 1:
                    await asyncio.sleep(30 * (attempt + 1))
                    continue
                raise

        return None

    async def enrich_company(self, domain: str, use_cache: bool = True) -> Optional[Company]:
        """
        Enrich company data by domain.

        Args:
            domain: Company domain (e.g., "stripe.com")
            use_cache: Whether to use cached results

        Returns:
            Company dataclass with enriched data, or None if not found
        """
        # Check cache first
        if use_cache:
            cached = self._cache.get("company", domain)
            if cached:
                return cached

        log.info(f"Apollo company enrichment: domain={domain}")

        data = await self._request_with_retry(
            "POST",
            "/organizations/enrich",
            payload={"domain": domain},
        )

        if not data or "organization" not in data:
            log.info(f"Apollo: no company found for domain={domain}")
            return None

        org = data["organization"]

        company = Company(
            apollo_id=org.get("id", ""),
            name=org.get("name", ""),
            domain=org.get("primary_domain", domain),
            industry=org.get("industry"),
            employee_count=org.get("estimated_num_employees"),
            employee_range=self._format_employee_range(org.get("estimated_num_employees")),
            founded_year=org.get("founded_year"),
            funding_stage=org.get("latest_funding_stage"),
            total_funding=org.get("total_funding"),
            headquarters=self._format_location(org),
            description=org.get("short_description"),
            tech_stack=org.get("technologies", []) or [],
            linkedin_url=org.get("linkedin_url"),
            website_url=org.get("website_url"),
            keywords=org.get("keywords", []) or [],
            _raw=org,
        )

        # Cache the result
        self._cache.set("company", domain, value=company)

        log.info(f"Apollo: enriched company {company.name} ({company.employee_count} employees)")
        return company

    async def search_contacts(
        self,
        domain: str,
        titles: list[str],
        seniorities: Optional[list[str]] = None,
        per_page: int = 10,
        use_cache: bool = True,
    ) -> list[Contact]:
        """
        Search for contacts at a company by title.

        Args:
            domain: Company domain
            titles: List of job titles to search for (e.g., ["Recruiter", "HR Manager"])
            seniorities: Optional list of seniority levels (e.g., ["director", "manager"])
            per_page: Number of results to return (max 100)
            use_cache: Whether to use cached results

        Returns:
            List of Contact dataclasses
        """
        cache_key = f"{domain}:{','.join(sorted(titles))}"
        if use_cache:
            cached = self._cache.get("contacts", cache_key)
            if cached:
                return cached

        log.info(f"Apollo contact search: domain={domain}, titles={titles}")

        payload = {
            "q_organization_domains_list": [domain],
            "person_titles": titles,
            "per_page": min(per_page, 100),
            "page": 1,
            "reveal_personal_emails": True,
        }

        if seniorities:
            payload["person_seniorities"] = seniorities

        data = await self._request_with_retry("POST", "/mixed_people/api_search", payload)

        if not data:
            return []

        contacts = []
        for person in data.get("people", []):
            contact = Contact(
                apollo_id=person.get("id", ""),
                name=f"{person.get('first_name', '')} {person.get('last_name', '')}".strip(),
                email=person.get("email"),
                email_status=person.get("email_status"),
                title=person.get("title"),
                linkedin_url=person.get("linkedin_url"),
                seniority=person.get("seniority"),
                department=person.get("departments", [None])[0] if person.get("departments") else None,
                _raw=person,
            )
            contacts.append(contact)

        # Cache the results
        self._cache.set("contacts", cache_key, value=contacts)

        log.info(f"Apollo: found {len(contacts)} contacts at {domain}")
        return contacts

    async def get_job_postings(
        self,
        domain: str,
        use_cache: bool = True,
    ) -> list[JobPosting]:
        """
        Get current job postings for a company.

        This is useful for detecting hiring signals and understanding
        what roles a company is actively recruiting for.

        Args:
            domain: Company domain
            use_cache: Whether to use cached results

        Returns:
            List of JobPosting dataclasses
        """
        if use_cache:
            cached = self._cache.get("jobs", domain)
            if cached:
                return cached

        # First, we need the organization ID
        company = await self.enrich_company(domain, use_cache=True)
        if not company or not company.apollo_id:
            log.info(f"Apollo: cannot get job postings without org ID for {domain}")
            return []

        log.info(f"Apollo job postings: org_id={company.apollo_id}")

        data = await self._request_with_retry(
            "GET",
            f"/organizations/{company.apollo_id}/job_postings",
        )

        if not data:
            return []

        postings = []
        for job in data.get("job_postings", []):
            posting = JobPosting(
                title=job.get("title", ""),
                department=job.get("department"),
                location=job.get("location"),
                posted_date=job.get("posted_at"),
                url=job.get("url"),
                _raw=job,
            )
            postings.append(posting)

        # Cache the results (shorter TTL since job postings change frequently)
        self._cache.set("jobs", domain, value=postings, ttl=1800)  # 30 min cache

        log.info(f"Apollo: found {len(postings)} job postings at {domain}")
        return postings

    async def search_company_by_name(
        self,
        company_name: str,
        use_cache: bool = True,
    ) -> Optional[Company]:
        """
        Search for a company by name and return enriched data.

        This is useful when you don't have the domain but have the company name.

        Args:
            company_name: Company name to search for
            use_cache: Whether to use cached results

        Returns:
            Company dataclass if found, None otherwise
        """
        if use_cache:
            cached = self._cache.get("company_name", company_name)
            if cached:
                return cached

        log.info(f"Apollo company search by name: {company_name}")

        # Use the organizations search endpoint
        payload = {
            "q_organization_name": company_name,
            "per_page": 1,
            "page": 1,
        }

        data = await self._request_with_retry("POST", "/mixed_companies/search", payload)

        if not data or not data.get("organizations"):
            log.info(f"Apollo: no company found for name={company_name}")
            return None

        org = data["organizations"][0]
        domain = org.get("primary_domain")

        if domain:
            # Now enrich with full data
            company = await self.enrich_company(domain, use_cache=True)
            if company:
                self._cache.set("company_name", company_name, value=company)
                return company

        # Fallback: create Company from search result
        company = Company(
            apollo_id=org.get("id", ""),
            name=org.get("name", company_name),
            domain=domain or "",
            industry=org.get("industry"),
            employee_count=org.get("estimated_num_employees"),
            employee_range=self._format_employee_range(org.get("estimated_num_employees")),
            founded_year=org.get("founded_year"),
            funding_stage=org.get("latest_funding_stage"),
            total_funding=org.get("total_funding"),
            headquarters=self._format_location(org),
            description=org.get("short_description"),
            tech_stack=org.get("technologies", []) or [],
            linkedin_url=org.get("linkedin_url"),
            website_url=org.get("website_url"),
            keywords=org.get("keywords", []) or [],
            _raw=org,
        )

        self._cache.set("company_name", company_name, value=company)
        return company

    def _format_location(self, org: dict) -> Optional[str]:
        """Format organization location from raw data."""
        parts = []
        if org.get("city"):
            parts.append(org["city"])
        if org.get("state"):
            parts.append(org["state"])
        if org.get("country"):
            parts.append(org["country"])
        return ", ".join(parts) if parts else None

    def _format_employee_range(self, count: Optional[int]) -> Optional[str]:
        """Convert employee count to human-readable range."""
        if not count:
            return None
        if count <= 10:
            return "1-10"
        elif count <= 50:
            return "11-50"
        elif count <= 200:
            return "51-200"
        elif count <= 500:
            return "201-500"
        elif count <= 1000:
            return "501-1000"
        elif count <= 5000:
            return "1001-5000"
        elif count <= 10000:
            return "5001-10000"
        else:
            return "10000+"

    def clear_cache(self) -> None:
        """Clear all cached data."""
        self._cache.clear()
        log.info("Apollo cache cleared")
