"""
Domain Finder Utility

Utilities for finding company domains from company names
and normalizing company names for matching.
"""

import asyncio
import logging
import re
from typing import Optional

import httpx

log = logging.getLogger(__name__)

# Common suffixes to strip from company names
COMPANY_SUFFIXES = [
    ", Inc.",
    ", Inc",
    " Inc.",
    " Inc",
    ", LLC",
    " LLC",
    ", Ltd.",
    ", Ltd",
    " Ltd.",
    " Ltd",
    ", Corp.",
    ", Corp",
    " Corp.",
    " Corp",
    " Corporation",
    ", Co.",
    ", Co",
    " Co.",
    " Co",
    " Company",
    " Holdings",
    " Group",
    ", LP",
    " LP",
    ", LLP",
    " LLP",
    " PLC",
    ", PLC",
    " S.A.",
    " SA",
    " GmbH",
    " AG",
    " B.V.",
    " BV",
    " Pty Ltd",
    " Pty",
    " Limited",
]

# Common TLDs to try
COMMON_TLDS = [".com", ".io", ".co", ".ai", ".dev", ".tech", ".app"]


def normalize_company_name(name: str) -> str:
    """
    Normalize a company name for matching and domain guessing.

    - Removes common suffixes (Inc, LLC, Corp, etc.)
    - Converts to lowercase
    - Strips whitespace
    - Removes special characters

    Args:
        name: Raw company name

    Returns:
        Normalized company name
    """
    if not name:
        return ""

    result = name.strip()

    # Remove common suffixes (case-insensitive)
    for suffix in COMPANY_SUFFIXES:
        if result.lower().endswith(suffix.lower()):
            result = result[: -len(suffix)]

    # Remove parenthetical content like "(formerly X)" or "(acquired)"
    result = re.sub(r"\s*\([^)]*\)\s*", " ", result)

    # Strip and lowercase
    result = result.strip().lower()

    # Remove special characters except spaces
    result = re.sub(r"[^\w\s-]", "", result)

    # Collapse multiple spaces
    result = re.sub(r"\s+", " ", result)

    return result.strip()


def company_name_to_domain_candidates(company_name: str) -> list[str]:
    """
    Generate domain candidates from a company name.

    Args:
        company_name: Company name (will be normalized)

    Returns:
        List of potential domain strings to check
    """
    normalized = normalize_company_name(company_name)
    if not normalized:
        return []

    candidates = []

    # Base variations
    # 1. No spaces: "openai" from "Open AI"
    no_spaces = normalized.replace(" ", "").replace("-", "")

    # 2. Hyphenated: "open-ai" from "Open AI"
    hyphenated = normalized.replace(" ", "-")

    # 3. First word only: "stripe" from "Stripe Inc"
    words = normalized.split()
    first_word = words[0] if words else normalized

    # 4. Initials: "ibm" from "International Business Machines"
    if len(words) > 1:
        initials = "".join(w[0] for w in words if w)
    else:
        initials = None

    # Build candidates with TLDs
    base_names = [no_spaces]
    if hyphenated != no_spaces:
        base_names.append(hyphenated)
    if first_word != no_spaces:
        base_names.append(first_word)
    if initials and len(initials) >= 2:
        base_names.append(initials)

    # Add variations with "hq" suffix (common for companies with generic names)
    base_names_with_hq = base_names + [f"{name}hq" for name in base_names[:2]]

    for base in base_names_with_hq:
        for tld in COMMON_TLDS:
            candidates.append(f"{base}{tld}")

    # Remove duplicates while preserving order
    seen = set()
    unique_candidates = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            unique_candidates.append(c)

    return unique_candidates


async def check_domain_exists(domain: str, timeout: float = 5.0) -> bool:
    """
    Check if a domain exists by making a HEAD request.

    Args:
        domain: Domain to check (e.g., "stripe.com")
        timeout: Request timeout in seconds

    Returns:
        True if domain responds, False otherwise
    """
    url = f"https://{domain}"

    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            verify=False,  # Some sites have cert issues
        ) as client:
            response = await client.head(url)
            # Accept any response (even errors) as evidence the domain exists
            return response.status_code < 500
    except httpx.ConnectTimeout:
        return False
    except httpx.ConnectError:
        return False
    except Exception as e:
        log.debug(f"Domain check failed for {domain}: {e}")
        return False


async def find_domain(company_name: str, max_checks: int = 10) -> Optional[str]:
    """
    Try to find a company's domain from its name.

    This function:
    1. Generates candidate domains from the company name
    2. Checks each candidate to see if it exists
    3. Returns the first valid domain found

    Args:
        company_name: Company name to find domain for
        max_checks: Maximum number of domains to check

    Returns:
        Domain string if found, None otherwise
    """
    if not company_name:
        return None

    log.info(f"Finding domain for: {company_name}")

    candidates = company_name_to_domain_candidates(company_name)

    if not candidates:
        log.warning(f"No domain candidates generated for: {company_name}")
        return None

    # Limit number of checks
    candidates = candidates[:max_checks]

    log.debug(f"Domain candidates: {candidates}")

    # Check candidates in parallel for speed
    async def check_candidate(domain: str) -> tuple[str, bool]:
        exists = await check_domain_exists(domain)
        return (domain, exists)

    tasks = [check_candidate(domain) for domain in candidates]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Return first valid domain
    for result in results:
        if isinstance(result, tuple):
            domain, exists = result
            if exists:
                log.info(f"Found domain for {company_name}: {domain}")
                return domain

    log.info(f"No valid domain found for: {company_name}")
    return None


async def find_domain_sequential(company_name: str, max_checks: int = 10) -> Optional[str]:
    """
    Try to find a company's domain, checking sequentially.

    This is slower than find_domain() but stops as soon as a valid domain is found,
    which is useful for rate-limited scenarios.

    Args:
        company_name: Company name to find domain for
        max_checks: Maximum number of domains to check

    Returns:
        Domain string if found, None otherwise
    """
    if not company_name:
        return None

    log.info(f"Finding domain (sequential) for: {company_name}")

    candidates = company_name_to_domain_candidates(company_name)[:max_checks]

    for domain in candidates:
        if await check_domain_exists(domain):
            log.info(f"Found domain for {company_name}: {domain}")
            return domain

    log.info(f"No valid domain found for: {company_name}")
    return None


def extract_domain_from_url(url: str) -> Optional[str]:
    """
    Extract domain from a URL.

    Args:
        url: Full URL or partial URL

    Returns:
        Domain string, or None if invalid
    """
    if not url:
        return None

    # Remove protocol
    url = re.sub(r"^https?://", "", url)

    # Remove path
    url = url.split("/")[0]

    # Remove port
    url = url.split(":")[0]

    # Remove www.
    if url.startswith("www."):
        url = url[4:]

    return url.lower() if url else None


def domains_match(domain1: Optional[str], domain2: Optional[str]) -> bool:
    """
    Check if two domains match (ignoring www prefix and case).

    Args:
        domain1: First domain
        domain2: Second domain

    Returns:
        True if domains match, False otherwise
    """
    if not domain1 or not domain2:
        return False

    d1 = domain1.lower().lstrip("www.")
    d2 = domain2.lower().lstrip("www.")

    return d1 == d2
