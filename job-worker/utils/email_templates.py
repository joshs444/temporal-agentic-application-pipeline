"""
Email Templates for JobHunt Outreach.

Provides professional, personalized templates for:
- Initial outreach to hiring managers/recruiters
- Follow-up emails
- Thank you notes after interviews
"""

from typing import Optional

from .profile import build_html_signature, build_signature, candidate


# =============================================================================
# Template Constants
# =============================================================================


INITIAL_OUTREACH_TEMPLATE = {
    "subject": "{job_title} at {company}",
    "body": """Hi {first_name},

I came across the {job_title} role at {company} and wanted to reach out directly.

I'm a Senior Software Engineer with experience building scalable systems and leading technical projects. My background includes full-stack development, system architecture, and shipping products from concept to production.

I'd love to learn more about what you're building and discuss how I might contribute.

Would you have 15 minutes for a quick call this week?""",
}


FOLLOW_UP_TEMPLATE = {
    "subject": "Re: {original_subject}",
    "body": """Hi {first_name},

Quick follow-up on my note about the role. I'm still very interested in the opportunity.

Is this something worth discussing further? Happy to work around your schedule.

Thanks,""",
}


THANK_YOU_TEMPLATE = {
    "subject": "Thank you - {job_title} conversation",
    "body": """Hi {interviewer_name},

Thank you for taking the time to speak with me about the {job_title} position today.

I enjoyed learning more about the team and the technical challenges you're tackling. The {highlight} particularly resonated with me.

I'm excited about the opportunity and look forward to hearing about next steps.

Best regards,""",
}


SECOND_FOLLOW_UP_TEMPLATE = {
    "subject": "Re: {original_subject}",
    "body": """Hi {first_name},

I wanted to circle back one more time. I understand things can get busy.

If the timing isn't right or the role has been filled, no worries at all. I'd appreciate a quick note either way.

Thanks for your time,""",
}


BREAKUP_TEMPLATE = {
    "subject": "Closing the loop",
    "body": """{first_name},

I'll assume the timing isn't right and step back.

If the {job_title} role opens up again or another opportunity comes along that might be a fit, feel free to reach out.

Wishing you and the team continued success.

Best,""",
}


# Email signature (appended to all outreach), built from the candidate profile.
EMAIL_SIGNATURE = "\n" + build_signature("default") + "\n"

EMAIL_SIGNATURE_HTML = build_html_signature()


# =============================================================================
# Template Rendering Functions
# =============================================================================


def render_template(
    template: dict,
    add_signature: bool = True,
    **kwargs
) -> dict:
    """
    Render a template with the provided variables.

    Args:
        template: Template dict with 'subject' and 'body' keys
        add_signature: Whether to append the email signature
        **kwargs: Variables to substitute in the template

    Returns:
        Dict with rendered 'subject' and 'body'
    """
    subject = template["subject"]
    body = template["body"]

    # Substitute variables
    for key, value in kwargs.items():
        placeholder = "{" + key + "}"
        subject = subject.replace(placeholder, str(value) if value else "")
        body = body.replace(placeholder, str(value) if value else "")

    # Add signature
    if add_signature:
        body = body.rstrip() + "\n" + EMAIL_SIGNATURE

    return {
        "subject": subject.strip(),
        "body": body.strip(),
    }


def render_html_email(
    body_text: str,
    add_signature: bool = True,
) -> str:
    """
    Convert plain text email to HTML format.

    Args:
        body_text: Plain text email body
        add_signature: Whether to include HTML signature

    Returns:
        HTML formatted email
    """
    # Convert newlines to <br> tags
    body_html = body_text.replace("\n", "<br>\n")

    # Wrap in basic HTML structure
    html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="font-family: Arial, sans-serif; font-size: 14px; line-height: 1.6; color: #333; max-width: 600px;">
{body_html}
"""

    if add_signature:
        html += EMAIL_SIGNATURE_HTML

    html += """
</body>
</html>"""

    return html


# =============================================================================
# Template Builders for Different Scenarios
# =============================================================================


def build_initial_outreach(
    first_name: str,
    company: str,
    job_title: str,
    custom_hook: Optional[str] = None,
    highlight_skill: Optional[str] = None,
) -> dict:
    """
    Build an initial outreach email.

    Args:
        first_name: Recipient's first name
        company: Company name
        job_title: Job title
        custom_hook: Custom personalization hook (optional)
        highlight_skill: Specific skill to highlight (optional)

    Returns:
        Dict with subject and body
    """
    if custom_hook:
        # Use personalized version
        body = f"""Hi {first_name},

{custom_hook}

I'm a Senior Software Engineer with experience building scalable systems and leading technical projects. {f'My work with {highlight_skill} ' if highlight_skill else ''}would translate well to what you're building.

Would you have 15 minutes for a quick call this week?"""
    else:
        # Use standard template
        return render_template(
            INITIAL_OUTREACH_TEMPLATE,
            first_name=first_name,
            company=company,
            job_title=job_title,
        )

    return {
        "subject": f"{job_title} at {company}",
        "body": body.strip() + "\n" + EMAIL_SIGNATURE,
    }


def build_follow_up(
    first_name: str,
    original_subject: str,
    sequence_number: int = 1,
    days_since_last: int = 3,
) -> dict:
    """
    Build a follow-up email.

    Args:
        first_name: Recipient's first name
        original_subject: Subject of the original email
        sequence_number: Which follow-up this is (1, 2, or 3)
        days_since_last: Days since last email

    Returns:
        Dict with subject and body
    """
    if sequence_number == 1:
        return render_template(
            FOLLOW_UP_TEMPLATE,
            first_name=first_name,
            original_subject=original_subject,
        )
    elif sequence_number == 2:
        return render_template(
            SECOND_FOLLOW_UP_TEMPLATE,
            first_name=first_name,
            original_subject=original_subject,
        )
    else:
        # Final breakup email
        job_title = original_subject.split(" at ")[0] if " at " in original_subject else "position"
        return render_template(
            BREAKUP_TEMPLATE,
            first_name=first_name,
            job_title=job_title,
        )


def build_thank_you(
    interviewer_name: str,
    job_title: str,
    highlight: str = "opportunity to contribute",
    custom_note: Optional[str] = None,
) -> dict:
    """
    Build a thank you email after an interview.

    Args:
        interviewer_name: Interviewer's name
        job_title: Job title
        highlight: Specific thing that resonated (optional)
        custom_note: Additional personalized note (optional)

    Returns:
        Dict with subject and body
    """
    base = render_template(
        THANK_YOU_TEMPLATE,
        interviewer_name=interviewer_name,
        job_title=job_title,
        highlight=highlight,
    )

    if custom_note:
        # Insert custom note before the closing
        body_lines = base["body"].split("\n")
        # Find "I'm excited" line and insert before
        insert_idx = next(
            (i for i, line in enumerate(body_lines) if "I'm excited" in line),
            -2
        )
        body_lines.insert(insert_idx, f"\n{custom_note}\n")
        base["body"] = "\n".join(body_lines)

    return base


# =============================================================================
# Recruiter-Specific Templates
# =============================================================================


RECRUITER_INITIAL_TEMPLATE = {
    "subject": "{job_title} - {company}",
    "body": """Hi {first_name},

I saw you're working with {company} on the {job_title} search and wanted to connect.

Quick background: I'm a Senior Software Engineer with {years_exp} years of experience building scalable systems. Most recently at {current_company}, I've been {recent_work}.

I'd love to learn more about the role and see if there's a fit. Do you have a few minutes this week?""",
}


INTERNAL_REFERRAL_TEMPLATE = {
    "subject": "Referral for {job_title} - connected with {referrer_name}",
    "body": """Hi {first_name},

{referrer_name} suggested I reach out about the {job_title} position.

A bit about me: I'm a Senior Software Engineer focused on {specialty}. {referrer_name} thought my experience with {shared_experience} might be relevant to what you're building.

Would love to hear more about the role if you have a few minutes.""",
}


def build_recruiter_outreach(
    first_name: str,
    company: str,
    job_title: str,
    years_exp: Optional[int] = None,
    current_company: Optional[str] = None,
    recent_work: str = "building scalable backend and AI systems",
) -> dict:
    """Build outreach to an external recruiter (defaults from the candidate profile)."""
    profile = candidate()
    return render_template(
        RECRUITER_INITIAL_TEMPLATE,
        first_name=first_name,
        company=company,
        job_title=job_title,
        years_exp=years_exp if years_exp is not None else profile.get("years_experience", 5),
        current_company=current_company or profile.get("current_company", ""),
        recent_work=recent_work,
    )


def build_referral_outreach(
    first_name: str,
    job_title: str,
    referrer_name: str,
    specialty: str = "distributed systems and full-stack development",
    shared_experience: str = "building scalable backend services",
) -> dict:
    """Build outreach when you have an internal referral."""
    return render_template(
        INTERNAL_REFERRAL_TEMPLATE,
        first_name=first_name,
        job_title=job_title,
        referrer_name=referrer_name,
        specialty=specialty,
        shared_experience=shared_experience,
    )


# =============================================================================
# Email Type Detection
# =============================================================================


def get_email_type_template(email_type: str) -> dict:
    """
    Get the appropriate template for an email type.

    Args:
        email_type: One of 'initial', 'follow_up', 'thank_you', 'recruiter', 'referral'

    Returns:
        Template dict
    """
    templates = {
        "initial": INITIAL_OUTREACH_TEMPLATE,
        "follow_up": FOLLOW_UP_TEMPLATE,
        "thank_you": THANK_YOU_TEMPLATE,
        "recruiter": RECRUITER_INITIAL_TEMPLATE,
        "referral": INTERNAL_REFERRAL_TEMPLATE,
        "second_follow_up": SECOND_FOLLOW_UP_TEMPLATE,
        "breakup": BREAKUP_TEMPLATE,
    }

    if email_type not in templates:
        raise ValueError(f"Unknown email type: {email_type}. Valid types: {list(templates.keys())}")

    return templates[email_type]
