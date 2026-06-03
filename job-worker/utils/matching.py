"""
Matching utilities for fast job filtering and scoring.

These are lightweight, fast functions for pre-filtering jobs
before expensive LLM analysis.
"""

import re
from typing import Any, List, Dict, Tuple, Optional

from . import profile


def keyword_match_score(job_description: str, skills: List[str]) -> float:
    """
    Fast keyword matching to pre-filter jobs.

    Args:
        job_description: Job posting text (title + description)
        skills: List of candidate skills to match

    Returns:
        float: Score from 0.0 to 1.0 representing match percentage
    """
    if not job_description or not skills:
        return 0.0

    # Normalize text for matching
    job_lower = job_description.lower()

    # Track weighted match score
    weighted_matches = 0.0

    # Skills that get extra weight — configured per candidate in the profile
    # (see utils.profile / profile.example.yaml), never hardcoded.
    high_value_skills = profile.boost_skills()

    for skill in skills:
        skill_lower = skill.lower()

        # Check for exact or partial match
        if skill_lower in job_lower:
            weight = 1.5 if skill_lower in high_value_skills else 1.0
            weighted_matches += weight
        # Check for word variations (e.g., "Python" matches "python3")
        elif any(word in job_lower for word in skill_lower.split()):
            weighted_matches += 0.5

    if not skills:
        return 0.0

    # Return weighted score normalized to 0-1
    max_weighted = len(skills) * 1.5  # Max if all skills were high-value
    return min(1.0, weighted_matches / max_weighted)


def experience_level_match(job_level: str, candidate_years: int) -> float:
    """
    Check if experience level matches job requirements.

    Args:
        job_level: Job level string (junior, mid, senior, staff, principal)
        candidate_years: Candidate's years of experience

    Returns:
        float: Score from 0.0 to 1.0
    """
    # Level to years mapping (typical expectations)
    level_ranges = {
        "junior": (0, 2),
        "entry": (0, 2),
        "mid": (2, 5),
        "senior": (5, 10),
        "staff": (7, 15),
        "principal": (10, 20),
        "lead": (5, 15),
        "architect": (8, 20),
    }

    job_level_lower = job_level.lower().strip()

    # Find matching level
    min_years, max_years = None, None
    for level, (min_y, max_y) in level_ranges.items():
        if level in job_level_lower:
            min_years, max_years = min_y, max_y
            break

    # Default to mid-level if unknown
    if min_years is None:
        min_years, max_years = 2, 8

    # Score based on fit
    if min_years <= candidate_years <= max_years:
        return 1.0
    elif candidate_years > max_years:
        # Overqualified - slight penalty
        overage = candidate_years - max_years
        return max(0.5, 1.0 - (overage * 0.1))
    else:
        # Underqualified - larger penalty
        shortage = min_years - candidate_years
        return max(0.0, 1.0 - (shortage * 0.25))


def location_match(
    job_location: str,
    candidate_location: str,
    remote_ok: bool,
    job_remote_type: Optional[str] = None
) -> float:
    """
    Check location compatibility.

    Args:
        job_location: Job's location string
        candidate_location: Candidate's location
        remote_ok: Whether candidate accepts remote
        job_remote_type: "remote", "hybrid", "onsite", or None

    Returns:
        float: Score from 0.0 to 1.0
    """
    if not job_location:
        return 0.5  # Unknown location, neutral score

    job_lower = job_location.lower()
    candidate_lower = candidate_location.lower()
    job_remote = (job_remote_type or "").lower()

    # Remote job
    if "remote" in job_lower or job_remote == "remote":
        return 1.0 if remote_ok else 0.5

    # Hybrid - partial match if remote ok
    if "hybrid" in job_lower or job_remote == "hybrid":
        # Commutable metro areas come from the candidate profile, not hardcoded.
        metro_areas = profile.metro_areas()

        for metro, cities in metro_areas.items():
            candidate_in_metro = any(city in candidate_lower for city in cities)
            job_in_metro = any(city in job_lower for city in cities)
            if candidate_in_metro and job_in_metro:
                return 1.0

        # Hybrid but not in area - partial match if remote ok
        return 0.7 if remote_ok else 0.3

    # Onsite - check location match
    if job_remote == "onsite" or "on-site" in job_lower:
        # Check state match
        states = ["ma", "massachusetts", "ny", "new york", "ca", "california"]
        for state in states:
            if state in candidate_lower and state in job_lower:
                return 0.8

        # Check city match
        if any(word in job_lower for word in candidate_lower.split()):
            return 1.0

        return 0.2 if remote_ok else 0.0

    # Unknown remote type - check for location overlap
    if any(word in job_lower for word in candidate_lower.split(",")):
        return 0.9

    return 0.5  # Uncertain


def salary_match(
    job_salary: Tuple[Optional[int], Optional[int]],
    expectation: Tuple[int, int]
) -> float:
    """
    Check salary alignment.

    Args:
        job_salary: (min, max) job salary or (None, None) if unknown
        expectation: (min, max) candidate expectation

    Returns:
        float: Score from 0.0 to 1.0
    """
    job_min, job_max = job_salary
    exp_min, exp_max = expectation

    # No salary info - neutral
    if job_min is None and job_max is None:
        return 0.5

    # Use available values
    if job_min is None:
        job_min = job_max * 0.8 if job_max else 0
    if job_max is None:
        job_max = job_min * 1.2 if job_min else 0

    # Check overlap
    if job_max < exp_min:
        # Job pays less than minimum expectation
        gap_pct = (exp_min - job_max) / exp_min
        return max(0.0, 1.0 - gap_pct * 2)

    if job_min > exp_max:
        # Job pays more than expectation (great!)
        return 1.0

    # Ranges overlap
    overlap_start = max(job_min, exp_min)
    overlap_end = min(job_max, exp_max)
    overlap = overlap_end - overlap_start

    exp_range = exp_max - exp_min
    if exp_range == 0:
        return 1.0 if job_min <= exp_min <= job_max else 0.5

    return min(1.0, overlap / exp_range)


def title_match_score(job_title: str, target_titles: List[str]) -> float:
    """
    Check how well job title matches target roles.

    Args:
        job_title: The job's title
        target_titles: List of desired role titles

    Returns:
        float: Score from 0.0 to 1.0
    """
    if not job_title or not target_titles:
        return 0.5

    job_lower = job_title.lower()

    # Direct matches
    for target in target_titles:
        target_lower = target.lower()
        if target_lower in job_lower or job_lower in target_lower:
            return 1.0

    # Keyword matches
    high_value_keywords = [
        "engineer", "architect", "developer", "ai", "ml", "machine learning",
        "solutions", "forward deployed", "staff", "senior", "lead"
    ]

    matches = sum(1 for kw in high_value_keywords if kw in job_lower)

    # Check against target keywords
    target_keywords = set()
    for title in target_titles:
        target_keywords.update(title.lower().split())

    title_words = set(job_lower.split())
    keyword_overlap = len(target_keywords & title_words)

    # Combine scores
    return min(1.0, (matches * 0.1) + (keyword_overlap * 0.15))


def calculate_quick_score(job: Dict[str, Any], resume: Dict[str, Any]) -> Dict[str, Any]:
    """
    Fast composite scoring for job pre-filtering.

    Use this to quickly filter jobs before expensive LLM analysis.
    Only jobs scoring above threshold should go to LLM.

    Args:
        job: Job data with title, description, location, salary, remote_type
        resume: Structured resume data

    Returns:
        dict with component scores and total
    """
    # Flatten skills
    all_skills = []
    for category, skills in resume.get("skills", {}).items():
        all_skills.extend(skills)

    # Get job text for matching
    job_text = f"{job.get('title', '')} {job.get('description', '')} {job.get('requirements', '')}"

    # Calculate component scores
    keyword_score = keyword_match_score(job_text, all_skills)

    title_score = title_match_score(
        job.get("title", ""),
        resume.get("preferences", {}).get("target_roles", [])
    )

    exp_score = experience_level_match(
        job.get("title", "") + " " + str(job.get("level", "")),
        resume.get("years_of_experience", 5)
    )

    # Location
    prefs = resume.get("preferences", {})
    remote_ok = "remote" in [w.lower() for w in prefs.get("work_types", [])]
    location_score = location_match(
        job.get("location", ""),
        resume.get("location", ""),
        remote_ok,
        job.get("remote_type")
    )

    # Salary
    salary_exp = prefs.get("salary_expectation", {})
    salary_score = salary_match(
        (job.get("salary_min"), job.get("salary_max")),
        (salary_exp.get("min", 0), salary_exp.get("max", 999999))
    )

    # Weighted total
    weights = {
        "keyword": 0.35,
        "title": 0.25,
        "experience": 0.15,
        "location": 0.15,
        "salary": 0.10,
    }

    total = (
        keyword_score * weights["keyword"] +
        title_score * weights["title"] +
        exp_score * weights["experience"] +
        location_score * weights["location"] +
        salary_score * weights["salary"]
    )

    return {
        "quick_score": round(total * 100, 1),
        "components": {
            "keyword_match": round(keyword_score * 100, 1),
            "title_match": round(title_score * 100, 1),
            "experience_match": round(exp_score * 100, 1),
            "location_match": round(location_score * 100, 1),
            "salary_match": round(salary_score * 100, 1),
        },
        "weights": weights,
        "should_analyze": total >= 0.4,  # Threshold for LLM analysis
    }


def extract_salary_from_text(text: str) -> Tuple[Optional[int], Optional[int]]:
    """
    Extract salary range from job posting text.

    Args:
        text: Job description text

    Returns:
        Tuple of (min_salary, max_salary) or (None, None)
    """
    if not text:
        return (None, None)

    text_lower = text.lower()

    # Common patterns
    patterns = [
        # $150,000 - $200,000
        r'\$\s*([\d,]+)\s*[-–]\s*\$?\s*([\d,]+)',
        # $150K - $200K
        r'\$\s*([\d.]+)\s*k\s*[-–]\s*\$?\s*([\d.]+)\s*k',
        # 150,000 - 200,000 (context: salary, compensation)
        r'([\d,]+)\s*[-–]\s*([\d,]+)(?:\s*(?:per year|annually|/year))',
    ]

    for pattern in patterns:
        match = re.search(pattern, text_lower)
        if match:
            try:
                min_str = match.group(1).replace(',', '')
                max_str = match.group(2).replace(',', '')

                min_val = float(min_str)
                max_val = float(max_str)

                # Handle K notation
                if 'k' in pattern:
                    min_val *= 1000
                    max_val *= 1000

                # Sanity check
                if 30000 <= min_val <= 1000000 and min_val <= max_val:
                    return (int(min_val), int(max_val))
            except (ValueError, IndexError):
                continue

    return (None, None)
