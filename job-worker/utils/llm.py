"""
LLM utilities for job matching.

Talks to any OpenAI-compatible chat-completions endpoint (default: xAI Grok).
All provider configuration lives in ``utils.llm_config``.
"""

import json
import re
import time
from typing import Any, Dict, Optional

from .llm_config import LLM_MODEL, get_llm_client

# Primary model, resolved from the environment (LLM_MODEL).
DEFAULT_MODEL = LLM_MODEL

# Backwards-compatible alias: existing call sites import ``get_xai_client``.
get_xai_client = get_llm_client


def extract_json(content: Optional[str]) -> Any:
    """Best-effort parse of a JSON value from an LLM response.

    Handles ```json fenced blocks, raw JSON, and JSON embedded in prose. Returns
    an empty dict on failure rather than raising, so callers degrade gracefully.
    """
    if not content:
        return {}
    fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", content, re.S)
    candidate = (fenced.group(1) if fenced else content).strip()
    try:
        return json.loads(candidate)
    except (json.JSONDecodeError, ValueError):
        match = re.search(r"(\{.*\}|\[.*\])", candidate, re.S)
        if match:
            try:
                return json.loads(match.group(1))
            except (json.JSONDecodeError, ValueError):
                return {}
        return {}


async def analyze_job_fit(job_description: str, resume: Dict[str, Any]) -> Dict[str, Any]:
    """
    Use LLM to analyze how well a job matches the candidate's resume.

    Args:
        job_description: Full job posting text
        resume: Structured resume data

    Returns:
        dict with:
            - fit_score: 0-100 overall match score
            - skills_matched: List of matching skills
            - skills_missing: List of required skills not possessed
            - experience_match: Assessment of experience level fit
            - reasoning: Detailed explanation of scoring
            - strengths: Why candidate is a good fit
            - concerns: Potential concerns or gaps
    """
    client = get_xai_client()

    # Build resume summary for context
    skills_flat = []
    for category, skills in resume.get("skills", {}).items():
        skills_flat.extend(skills)

    experience_summary = []
    for exp in resume.get("experience", []):
        exp_text = f"- {exp.get('title')} at {exp.get('company')}"
        if exp.get("highlights"):
            exp_text += f": {'; '.join(exp['highlights'][:2])}"
        experience_summary.append(exp_text)

    # Build education summary
    education_summary = []
    for edu in resume.get("education", []):
        degree = edu.get("degree", "")
        field = edu.get("field", "")
        institution = edu.get("institution", "")
        edu_text = f"- {degree}"
        if field:
            edu_text += f" in {field}"
        if institution:
            edu_text += f" from {institution}"
        education_summary.append(edu_text)

    resume_context = f"""
CANDIDATE: {resume.get('name', 'Unknown')}
TITLES: {', '.join(resume.get('titles', []))}
LOCATION: {resume.get('location', 'Unknown')}
YEARS OF EXPERIENCE: {resume.get('years_of_experience', 'Unknown')}

EDUCATION:
{chr(10).join(education_summary) if education_summary else 'Not specified'}

SKILLS:
{', '.join(skills_flat)}

EXPERIENCE:
{chr(10).join(experience_summary)}

KEY ACHIEVEMENTS:
{chr(10).join('- ' + a for a in resume.get('achievements', [])[:5])}
"""

    prompt = f"""Analyze how well this job posting matches the candidate's background.

JOB POSTING:
{job_description}

{resume_context}

Provide a JSON response with these exact fields:
{{
    "fit_score": <0-100 integer>,
    "skills_matched": ["skill1", "skill2", ...],
    "skills_missing": ["skill1", "skill2", ...],
    "experience_match": "strong" | "moderate" | "weak",
    "title_alignment": "strong" | "moderate" | "weak",
    "reasoning": "2-3 sentence explanation of the score",
    "strengths": ["strength1", "strength2", ...],
    "concerns": ["concern1", "concern2", ...]
}}

Scoring guide:
- 90-100: Excellent match, meets/exceeds all requirements
- 75-89: Strong match, meets most requirements with minor gaps
- 60-74: Moderate match, meets core requirements but has notable gaps
- 45-59: Weak match, meets some requirements but significant gaps
- 0-44: Poor match, does not meet core requirements

Be specific about which skills match and which are missing.
Focus on hard requirements vs nice-to-haves.
"""

    start_time = time.time()

    response = await client.chat.completions.create(
        model=DEFAULT_MODEL,
        messages=[
            {
                "role": "system",
                "content": "You are a technical recruiter analyzing job fit. "
                           "Respond only with valid JSON, no markdown formatting."
            },
            {"role": "user", "content": prompt}
        ],
        temperature=0.3,
        max_tokens=1000,
    )

    latency_ms = int((time.time() - start_time) * 1000)

    # Parse response
    content = response.choices[0].message.content or "{}"

    # Clean up potential markdown formatting
    if content.startswith("```"):
        content = content.split("```")[1]
        if content.startswith("json"):
            content = content[4:]
    content = content.strip()

    try:
        result = json.loads(content)
        # Ensure result is a dict, not a string or other type
        if not isinstance(result, dict):
            raise ValueError(f"LLM returned non-dict type: {type(result)}")
    except (json.JSONDecodeError, ValueError) as e:
        # Fallback structure if parsing fails
        result = {
            "fit_score": 50,
            "skills_matched": [],
            "skills_missing": [],
            "experience_match": "moderate",
            "title_alignment": "moderate",
            "reasoning": f"Could not parse LLM response: {str(e)[:100]}",
            "strengths": [],
            "concerns": ["LLM response parsing failed"],
        }

    # Add metadata
    result["_metadata"] = {
        "model": DEFAULT_MODEL,
        "latency_ms": latency_ms,
        "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
        "completion_tokens": response.usage.completion_tokens if response.usage else 0,
    }

    return result


async def extract_job_requirements(job_description: str) -> Dict[str, Any]:
    """
    Extract structured requirements from a job posting.

    Args:
        job_description: Full job posting text

    Returns:
        dict with:
            - title: Job title
            - level: junior/mid/senior/staff/principal
            - required_skills: Hard requirements
            - preferred_skills: Nice-to-haves
            - years_experience: Required years
            - education: Education requirements
            - remote_type: remote/hybrid/onsite
            - salary_range: If mentioned
            - key_responsibilities: Main duties
    """
    client = get_xai_client()

    prompt = f"""Extract structured information from this job posting.

JOB POSTING:
{job_description}

Provide a JSON response with these exact fields:
{{
    "title": "extracted job title",
    "level": "junior" | "mid" | "senior" | "staff" | "principal" | "lead",
    "required_skills": ["skill1", "skill2", ...],
    "preferred_skills": ["skill1", "skill2", ...],
    "years_experience": {{"min": <int or null>, "max": <int or null>}},
    "education": ["requirement1", ...],
    "remote_type": "remote" | "hybrid" | "onsite" | "unknown",
    "salary_range": {{"min": <int or null>, "max": <int or null>, "currency": "USD"}},
    "key_responsibilities": ["responsibility1", "responsibility2", ...],
    "tech_stack": ["tech1", "tech2", ...],
    "industry": "extracted industry or domain",
    "company_stage": "startup" | "scaleup" | "enterprise" | "unknown"
}}

Be precise:
- Only include skills explicitly mentioned as required in required_skills
- Infer level from title and years of experience if not explicit
- Extract salary only if explicitly mentioned (not estimated)
"""

    start_time = time.time()

    response = await client.chat.completions.create(
        model=DEFAULT_MODEL,
        messages=[
            {
                "role": "system",
                "content": "You are a job posting parser. "
                           "Extract information precisely. "
                           "Respond only with valid JSON, no markdown formatting."
            },
            {"role": "user", "content": prompt}
        ],
        temperature=0.1,
        max_tokens=800,
    )

    latency_ms = int((time.time() - start_time) * 1000)

    # Parse response
    content = response.choices[0].message.content or "{}"

    # Clean up potential markdown formatting
    if content.startswith("```"):
        content = content.split("```")[1]
        if content.startswith("json"):
            content = content[4:]
    content = content.strip()

    try:
        result = json.loads(content)
    except json.JSONDecodeError:
        result = {
            "title": "Unknown",
            "level": "unknown",
            "required_skills": [],
            "preferred_skills": [],
            "years_experience": {"min": None, "max": None},
            "education": [],
            "remote_type": "unknown",
            "salary_range": {"min": None, "max": None, "currency": "USD"},
            "key_responsibilities": [],
            "tech_stack": [],
            "industry": "unknown",
            "company_stage": "unknown",
        }

    # Add metadata
    result["_metadata"] = {
        "model": DEFAULT_MODEL,
        "latency_ms": latency_ms,
        "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
        "completion_tokens": response.usage.completion_tokens if response.usage else 0,
    }

    return result


async def generate_skill_gap_analysis(
    job_requirements: Dict[str, Any],
    resume: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Generate detailed analysis of skill gaps and learning recommendations.

    Args:
        job_requirements: Extracted job requirements
        resume: Structured resume data

    Returns:
        dict with gap analysis and recommendations
    """
    client = get_xai_client()

    # Build skills list
    candidate_skills = []
    for category, skills in resume.get("skills", {}).items():
        candidate_skills.extend(skills)

    prompt = f"""Analyze skill gaps between a candidate and job requirements.

JOB REQUIREMENTS:
Title: {job_requirements.get('title', 'Unknown')}
Level: {job_requirements.get('level', 'Unknown')}
Required Skills: {', '.join(job_requirements.get('required_skills', []))}
Preferred Skills: {', '.join(job_requirements.get('preferred_skills', []))}
Tech Stack: {', '.join(job_requirements.get('tech_stack', []))}
Years Required: {job_requirements.get('years_experience', {})}

CANDIDATE SKILLS:
{', '.join(candidate_skills)}
Years of Experience: {resume.get('years_of_experience', 'Unknown')}

Provide a JSON response:
{{
    "critical_gaps": [
        {{"skill": "skill name", "importance": "critical" | "important", "learning_path": "how to learn"}}
    ],
    "transferable_skills": [
        {{"candidate_skill": "skill", "applies_to": "required skill", "transfer_rating": "direct" | "partial"}}
    ],
    "experience_gap": {{
        "years_short": <int or 0>,
        "can_compensate": true | false,
        "compensation_factors": ["factor1", ...]
    }},
    "quick_wins": ["skill that can be learned quickly", ...],
    "time_to_ready": "1 week" | "1 month" | "3 months" | "6+ months",
    "overall_readiness": "ready" | "nearly_ready" | "needs_development" | "significant_gap"
}}
"""

    start_time = time.time()

    response = await client.chat.completions.create(
        model=DEFAULT_MODEL,
        messages=[
            {
                "role": "system",
                "content": "You are a career development advisor. "
                           "Provide practical, actionable skill gap analysis. "
                           "Respond only with valid JSON."
            },
            {"role": "user", "content": prompt}
        ],
        temperature=0.3,
        max_tokens=800,
    )

    latency_ms = int((time.time() - start_time) * 1000)

    content = response.choices[0].message.content or "{}"

    if content.startswith("```"):
        content = content.split("```")[1]
        if content.startswith("json"):
            content = content[4:]
    content = content.strip()

    try:
        result = json.loads(content)
    except json.JSONDecodeError:
        result = {
            "critical_gaps": [],
            "transferable_skills": [],
            "experience_gap": {"years_short": 0, "can_compensate": True, "compensation_factors": []},
            "quick_wins": [],
            "time_to_ready": "unknown",
            "overall_readiness": "unknown",
        }

    result["_metadata"] = {
        "model": DEFAULT_MODEL,
        "latency_ms": latency_ms,
        "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
        "completion_tokens": response.usage.completion_tokens if response.usage else 0,
    }

    return result
