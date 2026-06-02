"""
Cover Letter Generation Activities

Temporal activities for generating cover letters, recruiter emails, resume bullets,
and thank you emails. Uses Grok (grok-4-1-fast) via xAI API.

Usage:
    These activities are called by Temporal workflows to generate tailored content
    for job applications.
"""

import json
import logging
import time
from dataclasses import dataclass
from typing import Optional

from temporalio import activity

from prompts.cover_letter import (
    COVER_LETTER_SYSTEM_PROMPT,
    COVER_LETTER_USER_TEMPLATE,
    RECRUITER_EMAIL_SYSTEM_PROMPT,
    RECRUITER_EMAIL_COLD_TEMPLATE,
    RECRUITER_EMAIL_FOLLOWUP_TEMPLATE,
    RECRUITER_EMAIL_REFERRAL_TEMPLATE,
    RESUME_BULLET_SYSTEM_PROMPT,
    RESUME_BULLET_USER_TEMPLATE,
    THANK_YOU_SYSTEM_PROMPT,
    THANK_YOU_USER_TEMPLATE,
    format_requirements_list,
    format_experience_list,
    get_tone_description,
)
from utils.content_formatter import (
    format_cover_letter,
    format_email,
    validate_cover_letter,
    validate_email,
    clean_text,
)

log = logging.getLogger(__name__)

# =============================================================================
# CONFIGURATION
# =============================================================================
# Provider/model config is centralized in utils.llm_config (provider-agnostic).

from utils.llm_config import LLM_MODEL, estimate_cost_usd, get_llm_client

DEFAULT_MODEL = LLM_MODEL


@dataclass
class LLMResponse:
    """Structured response from an LLM call with cost/latency metadata."""
    content: str
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: int

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def cost_usd(self) -> float:
        return estimate_cost_usd(self.input_tokens, self.output_tokens)


async def call_llm(
    system_prompt: str,
    user_prompt: str,
    model: str = DEFAULT_MODEL,
    temperature: float = 0.7,
    max_tokens: int = 1000,
) -> LLMResponse:
    """
    Make an LLM call and return structured response.

    Args:
        system_prompt: System instructions
        user_prompt: User message/request
        model: Model to use (default: grok-4-1-fast)
        temperature: Creativity (0-1)
        max_tokens: Max response length

    Returns:
        LLMResponse with content and metadata
    """
    client = get_llm_client()

    start_time = time.time()

    response = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )

    latency_ms = int((time.time() - start_time) * 1000)

    content = response.choices[0].message.content or ""
    usage = response.usage

    return LLMResponse(
        content=content,
        model=model,
        input_tokens=usage.prompt_tokens if usage else 0,
        output_tokens=usage.completion_tokens if usage else 0,
        latency_ms=latency_ms,
    )


# =============================================================================
# COVER LETTER ACTIVITY
# =============================================================================


@activity.defn
async def generate_cover_letter(
    job: dict,
    company: dict,
    resume: dict,
    tone: str = "professional",
) -> dict:
    """
    Generate a tailored cover letter.

    Args:
        job: Job details (title, description, requirements, url)
        company: Company info (name, description, mission, culture, recent_news)
        resume: Resume data (experiences, skills, achievements)
        tone: Writing tone - "professional", "conversational", or "technical"

    Returns:
        Dict with:
            - cover_letter_text: The generated cover letter
            - key_points_addressed: List of requirements addressed
            - personalization_notes: Company-specific personalizations
            - format_versions: Dict with text, markdown, html versions
            - metadata: Token usage, cost, latency
    """
    activity.logger.info(f"Generating cover letter for {job.get('title')} at {company.get('name')}")

    # Extract and format inputs
    job_title = job.get("title", "Unknown Position")
    company_name = company.get("name", "Unknown Company")
    job_description = job.get("description", "No description provided")
    requirements = job.get("requirements", [])

    # Build company info section
    company_info_parts = []
    if company.get("description"):
        company_info_parts.append(f"About: {company['description']}")
    if company.get("mission"):
        company_info_parts.append(f"Mission: {company['mission']}")
    if company.get("culture"):
        company_info_parts.append(f"Culture: {company['culture']}")
    if company.get("recent_news"):
        company_info_parts.append(f"Recent News: {company['recent_news']}")
    company_info = "\n".join(company_info_parts) or "No company information available"

    # Format requirements
    requirements_text = format_requirements_list(requirements)

    # Format relevant experience
    experiences = resume.get("experiences", [])
    relevant_experience = format_experience_list(experiences[:3])

    # Add key achievements if available
    if resume.get("achievements"):
        relevant_experience += "\n\n**Key Achievements:**\n"
        relevant_experience += "\n".join(f"- {a}" for a in resume["achievements"][:5])

    # Get tone description
    tone_desc = get_tone_description(tone)

    # Build the prompt
    user_prompt = COVER_LETTER_USER_TEMPLATE.format(
        job_title=job_title,
        company_name=company_name,
        job_description=job_description[:2000],  # Limit length
        company_info=company_info,
        requirements=requirements_text,
        relevant_experience=relevant_experience,
        tone=f"{tone} - {tone_desc}",
    )

    # Call LLM
    response = await call_llm(
        system_prompt=COVER_LETTER_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        temperature=0.7,
        max_tokens=800,
    )

    cover_letter_text = clean_text(response.content)

    # Validate the output
    is_valid, issues = validate_cover_letter(cover_letter_text)
    if not is_valid:
        activity.logger.warning(f"Cover letter validation issues: {issues}")

    # Identify which requirements were addressed
    key_points = []
    text_lower = cover_letter_text.lower()
    for req in requirements[:10]:
        # Simple keyword matching - could be enhanced with embeddings
        req_keywords = req.lower().split()[:3]
        if any(kw in text_lower for kw in req_keywords if len(kw) > 3):
            key_points.append(req)

    # Identify personalizations
    personalization_notes = []
    if company.get("name") and company["name"].lower() in text_lower:
        personalization_notes.append(f"References company name: {company['name']}")
    if company.get("mission") and any(w in text_lower for w in company["mission"].lower().split()[:5]):
        personalization_notes.append("References company mission")
    if company.get("recent_news"):
        personalization_notes.append("Could reference recent news")

    # Generate format versions
    format_versions = {
        "text": format_cover_letter(
            cover_letter_text,
            format="text",
            company_name=company_name,
            job_title=job_title,
        ),
        "markdown": format_cover_letter(
            cover_letter_text,
            format="markdown",
            company_name=company_name,
            job_title=job_title,
        ),
        "html": format_cover_letter(
            cover_letter_text,
            format="html",
            company_name=company_name,
            job_title=job_title,
        ),
    }

    return {
        "cover_letter_text": cover_letter_text,
        "key_points_addressed": key_points,
        "personalization_notes": personalization_notes,
        "format_versions": format_versions,
        "validation": {"is_valid": is_valid, "issues": issues},
        "metadata": {
            "model": response.model,
            "input_tokens": response.input_tokens,
            "output_tokens": response.output_tokens,
            "total_tokens": response.total_tokens,
            "cost_usd": response.cost_usd,
            "latency_ms": response.latency_ms,
            "tone": tone,
        },
    }


# =============================================================================
# RECRUITER EMAIL ACTIVITY
# =============================================================================


@activity.defn
async def generate_email_to_recruiter(
    job: dict,
    contact: dict,
    resume: dict,
    is_cold_outreach: bool = True,
    referrer_name: Optional[str] = None,
    application_date: Optional[str] = None,
) -> dict:
    """
    Generate outreach email to recruiter/hiring manager.

    Args:
        job: Job details (title, company_name, description)
        contact: Contact info (name, title, email)
        resume: Resume data for personalization
        is_cold_outreach: True for cold outreach, False for follow-up
        referrer_name: Name of mutual connection (for referral emails)
        application_date: Date of original application (for follow-ups)

    Returns:
        Dict with:
            - subject: Email subject line
            - body: Email body (without signature)
            - full_email: Complete email with signature
            - metadata: Token usage, cost, latency
    """
    contact_name = contact.get("name", "Hiring Manager")
    contact_title = contact.get("title", "Recruiter")
    company_name = job.get("company_name", "Unknown Company")
    job_title = job.get("title", "Unknown Position")

    activity.logger.info(f"Generating email to {contact_name} at {company_name}")

    # Determine which template to use
    if referrer_name:
        # Referral email
        template = RECRUITER_EMAIL_REFERRAL_TEMPLATE
        user_prompt = template.format(
            referrer_name=referrer_name,
            contact_name=contact_name,
            contact_title=contact_title,
            company_name=company_name,
            job_title=job_title,
            referral_context=contact.get("referral_context", "No specific context provided"),
            fit_reasons=_build_fit_reasons(job, resume),
        )
    elif not is_cold_outreach and application_date:
        # Follow-up email
        template = RECRUITER_EMAIL_FOLLOWUP_TEMPLATE
        user_prompt = template.format(
            application_date=application_date,
            job_title=job_title,
            company_name=company_name,
            updates=resume.get("recent_updates", "No recent updates"),
            context=job.get("description", "")[:500],
        )
    else:
        # Cold outreach
        template = RECRUITER_EMAIL_COLD_TEMPLATE
        user_prompt = template.format(
            contact_name=contact_name,
            contact_title=contact_title,
            company_name=company_name,
            job_title=job_title,
            company_context=job.get("description", "No context available")[:500],
            fit_reasons=_build_fit_reasons(job, resume),
        )

    # Call LLM
    response = await call_llm(
        system_prompt=RECRUITER_EMAIL_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        temperature=0.7,
        max_tokens=400,
    )

    # Parse response to extract subject and body
    content = response.content
    subject, body = _parse_email_response(content)

    # Validate
    is_valid, issues = validate_email(subject, body)
    if not is_valid:
        activity.logger.warning(f"Email validation issues: {issues}")

    # Format with signature
    formatted = format_email(
        subject=subject,
        body=body,
        signature_type="email",
        recipient_name=contact_name.split()[0] if contact_name != "Hiring Manager" else None,
    )

    return {
        "subject": formatted["subject"],
        "body": formatted["body"],
        "full_email": formatted["full_text"],
        "email_type": "referral" if referrer_name else ("follow_up" if not is_cold_outreach else "cold"),
        "validation": {"is_valid": is_valid, "issues": issues},
        "metadata": {
            "model": response.model,
            "input_tokens": response.input_tokens,
            "output_tokens": response.output_tokens,
            "total_tokens": response.total_tokens,
            "cost_usd": response.cost_usd,
            "latency_ms": response.latency_ms,
        },
    }


def _build_fit_reasons(job: dict, resume: dict) -> str:
    """Build a string of reasons why this is a good fit."""
    reasons = []

    # Match skills
    job_skills = set(s.lower() for s in job.get("required_skills", []))
    resume_skills = set(s.lower() for s in resume.get("skills", []))
    matching_skills = job_skills & resume_skills
    if matching_skills:
        reasons.append(f"Skills match: {', '.join(list(matching_skills)[:5])}")

    # Key achievements
    if resume.get("achievements"):
        reasons.append(f"Key achievement: {resume['achievements'][0]}")

    # Domain experience
    if resume.get("domain_expertise"):
        reasons.append(f"Domain expertise: {resume['domain_expertise']}")

    return "\n".join(reasons) if reasons else "Strong technical background with relevant experience"


def _parse_email_response(content: str) -> tuple[str, str]:
    """Parse LLM response to extract subject and body."""
    lines = content.strip().split("\n")
    subject = ""
    body_lines = []
    in_body = False

    for line in lines:
        line_lower = line.lower().strip()
        if line_lower.startswith("subject:") or line_lower.startswith("subject line:"):
            subject = line.split(":", 1)[1].strip()
            subject = subject.strip('"\'')
        elif line_lower.startswith("email:") or line_lower.startswith("body:"):
            in_body = True
        elif line_lower.startswith("1.") and "subject" in line_lower:
            # Format: "1. Subject line: ..."
            subject = line.split(":", 1)[1].strip() if ":" in line else ""
            subject = subject.strip('"\'')
        elif line_lower.startswith("2.") and ("email" in line_lower or "body" in line_lower):
            in_body = True
        elif subject and not in_body and line.strip():
            # If we have subject but haven't hit body marker, this is probably the body
            in_body = True
            body_lines.append(line)
        elif in_body:
            body_lines.append(line)

    body = "\n".join(body_lines).strip()

    # If parsing failed, treat entire content as body and generate generic subject
    if not subject or not body:
        if not subject:
            subject = "Quick Question"
        if not body:
            body = clean_text(content)

    return subject, body


# =============================================================================
# RESUME TAILORING ACTIVITY
# =============================================================================


@activity.defn
async def tailor_resume_bullets(
    job: dict,
    resume: dict,
    section: str,
    num_bullets: int = 4,
) -> list[str]:
    """
    Generate tailored bullet points for a specific resume section.

    Args:
        job: Job details (title, description, requirements, keywords)
        resume: Resume data with experiences
        section: Which experience section to tailor (by company or index)
        num_bullets: Number of bullets to generate

    Returns:
        List of tailored bullet point strings
    """
    activity.logger.info(f"Tailoring resume bullets for section: {section}")

    # Find the relevant section
    experiences = resume.get("experiences", [])
    target_exp = None

    for exp in experiences:
        if exp.get("company", "").lower() == section.lower():
            target_exp = exp
            break
        if exp.get("title", "").lower() == section.lower():
            target_exp = exp
            break

    if not target_exp and experiences:
        # Default to first experience
        target_exp = experiences[0]

    if not target_exp:
        return ["No experience data available to tailor"]

    # Format original bullets
    original_bullets = target_exp.get("highlights", target_exp.get("bullets", []))
    original_text = "\n".join(f"- {b}" for b in original_bullets)

    # Extract keywords from job
    job_keywords = job.get("keywords", [])
    if not job_keywords and job.get("description"):
        # Extract some keywords from description
        desc = job.get("description", "")
        # Simple keyword extraction - could be enhanced
        common_tech = ["python", "sql", "aws", "kubernetes", "docker", "react", "api",
                       "machine learning", "ai", "data", "cloud", "agile"]
        job_keywords = [kw for kw in common_tech if kw.lower() in desc.lower()]

    # Build prompt
    user_prompt = RESUME_BULLET_USER_TEMPLATE.format(
        section_name=f"{target_exp.get('title', 'Unknown')} at {target_exp.get('company', 'Unknown')}",
        original_bullets=original_text or "No original bullets provided",
        job_requirements=format_requirements_list(job.get("requirements", [])),
        job_keywords=", ".join(job_keywords) or "No specific keywords",
        num_bullets=num_bullets,
    )

    # Call LLM
    response = await call_llm(
        system_prompt=RESUME_BULLET_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        temperature=0.6,
        max_tokens=500,
    )

    # Parse bullets from response
    bullets = []
    for line in response.content.split("\n"):
        line = line.strip()
        if line.startswith("-") or line.startswith("*") or line.startswith("•"):
            bullet = line[1:].strip()
            if bullet:
                bullets.append(bullet)
        elif line and len(line) > 20 and not line.endswith(":"):
            # Might be a bullet without marker
            bullets.append(line)

    # Ensure we have the right number
    bullets = bullets[:num_bullets]

    activity.logger.info(f"Generated {len(bullets)} tailored bullets")
    return bullets


# =============================================================================
# THANK YOU EMAIL ACTIVITY
# =============================================================================


@activity.defn
async def generate_thank_you_email(
    interview: dict,
    interviewer_names: list[str],
    discussion_points: list[str],
) -> str:
    """
    Generate post-interview thank you email.

    Args:
        interview: Interview details (job_title, company_name, date)
        interviewer_names: Names of interviewers
        discussion_points: Key topics discussed in interview

    Returns:
        Complete thank you email text
    """
    job_title = interview.get("job_title", "the position")
    company_name = interview.get("company_name", "your company")
    interview_date = interview.get("date", "recently")

    activity.logger.info(f"Generating thank you email for {company_name} interview")

    # Build prompt
    user_prompt = THANK_YOU_USER_TEMPLATE.format(
        job_title=job_title,
        company_name=company_name,
        interview_date=interview_date,
        interviewers=", ".join(interviewer_names) or "the team",
        discussion_points="\n".join(f"- {p}" for p in discussion_points) or "General role discussion",
        strong_fit_topics=interview.get("strong_fit", "Technical skills and experience"),
        concerns_to_address=interview.get("concerns", "None identified"),
    )

    # Call LLM
    response = await call_llm(
        system_prompt=THANK_YOU_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        temperature=0.6,
        max_tokens=400,
    )

    # Parse and format
    content = response.content
    subject, body = _parse_email_response(content)

    if not subject:
        subject = f"Thank you - {job_title} Interview"

    formatted = format_email(
        subject=subject,
        body=body,
        signature_type="email",
        recipient_name=interviewer_names[0].split()[0] if interviewer_names else None,
    )

    return formatted["full_text"]


# =============================================================================
# ACTIVITY REGISTRATION
# =============================================================================

# List of all activities for Temporal worker registration
COVER_LETTER_ACTIVITIES = [
    generate_cover_letter,
    generate_email_to_recruiter,
    tailor_resume_bullets,
    generate_thank_you_email,
]
