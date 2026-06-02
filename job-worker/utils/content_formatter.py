"""
Content Formatter Utilities

Format generated content for different outputs: plain text, markdown, HTML, PDF-ready.
Handles cover letters, emails, and other generated content.
"""

import re
from datetime import datetime
from typing import Optional

from .profile import build_signature

# =============================================================================
# SIGNATURE CONFIGURATION
# =============================================================================
# Built from the configured candidate profile (see utils.profile), never hardcoded.

DEFAULT_SIGNATURE = build_signature("default")
EMAIL_SIGNATURE = build_signature("email")
FORMAL_SIGNATURE = build_signature("formal")


# =============================================================================
# COVER LETTER FORMATTING
# =============================================================================


def format_cover_letter(
    text: str,
    format: str = "text",
    company_name: Optional[str] = None,
    job_title: Optional[str] = None,
    hiring_manager: Optional[str] = None,
    include_header: bool = True,
    include_signature: bool = True,
) -> str:
    """
    Format a cover letter for different output formats.

    Args:
        text: The raw cover letter body text
        format: Output format - "text", "markdown", "html", "pdf-ready"
        company_name: Company name for header
        job_title: Job title for header
        hiring_manager: Hiring manager name (optional)
        include_header: Whether to include the header block
        include_signature: Whether to include signature

    Returns:
        Formatted cover letter string
    """
    # Clean up the text
    text = clean_text(text)

    # Build header if requested
    header = ""
    if include_header:
        header = _build_cover_letter_header(
            company_name=company_name,
            job_title=job_title,
            hiring_manager=hiring_manager,
            format=format,
        )

    # Build signature if requested
    signature = ""
    if include_signature:
        signature = DEFAULT_SIGNATURE

    # Format based on output type
    if format == "text":
        return _format_text(header, text, signature)
    elif format == "markdown":
        return _format_markdown(header, text, signature)
    elif format == "html":
        return _format_html(header, text, signature, job_title, company_name)
    elif format == "pdf-ready":
        return _format_pdf_ready(header, text, signature)
    else:
        return _format_text(header, text, signature)


def _build_cover_letter_header(
    company_name: Optional[str],
    job_title: Optional[str],
    hiring_manager: Optional[str],
    format: str,
) -> str:
    """Build the cover letter header section."""
    date_str = datetime.now().strftime("%B %d, %Y")

    if hiring_manager:
        greeting = f"Dear {hiring_manager},"
    else:
        greeting = "Dear Hiring Manager,"

    re_line = ""
    if job_title:
        re_line = f"RE: {job_title} Position"
        if company_name:
            re_line = f"RE: {job_title} Position at {company_name}"

    if format == "markdown":
        header_parts = [date_str, ""]
        if re_line:
            header_parts.append(f"**{re_line}**")
            header_parts.append("")
        header_parts.append(greeting)
        return "\n".join(header_parts)
    else:
        header_parts = [date_str, ""]
        if re_line:
            header_parts.append(re_line)
            header_parts.append("")
        header_parts.append(greeting)
        return "\n".join(header_parts)


def _format_text(header: str, body: str, signature: str) -> str:
    """Format as plain text."""
    parts = []
    if header:
        parts.append(header)
        parts.append("")
    parts.append(body)
    if signature:
        parts.append("")
        parts.append(signature)
    return "\n".join(parts)


def _format_markdown(header: str, body: str, signature: str) -> str:
    """Format as Markdown."""
    parts = []
    if header:
        parts.append(header)
        parts.append("")
    parts.append(body)
    if signature:
        parts.append("")
        parts.append("---")
        parts.append("")
        parts.append(signature)
    return "\n".join(parts)


def _format_html(
    header: str,
    body: str,
    signature: str,
    job_title: Optional[str] = None,
    company_name: Optional[str] = None,
) -> str:
    """Format as HTML."""
    # Convert body paragraphs to HTML
    paragraphs = body.split("\n\n")
    html_body = "\n".join(f"<p>{p.strip()}</p>" for p in paragraphs if p.strip())

    # Convert signature to HTML
    sig_lines = signature.split("\n")
    html_sig = "<br>\n".join(sig_lines)

    title = "Cover Letter"
    if job_title and company_name:
        title = f"Cover Letter - {job_title} at {company_name}"

    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>{title}</title>
    <style>
        body {{
            font-family: Georgia, 'Times New Roman', serif;
            max-width: 700px;
            margin: 40px auto;
            padding: 20px;
            line-height: 1.6;
            color: #333;
        }}
        .header {{
            margin-bottom: 24px;
        }}
        .date {{
            margin-bottom: 16px;
        }}
        .re-line {{
            font-weight: bold;
            margin-bottom: 16px;
        }}
        .greeting {{
            margin-bottom: 16px;
        }}
        .body p {{
            margin-bottom: 16px;
            text-align: justify;
        }}
        .signature {{
            margin-top: 24px;
            line-height: 1.4;
        }}
    </style>
</head>
<body>
    <div class="header">
        <div class="date">{datetime.now().strftime("%B %d, %Y")}</div>
        <div class="greeting">Dear Hiring Manager,</div>
    </div>
    <div class="body">
        {html_body}
    </div>
    <div class="signature">
        {html_sig}
    </div>
</body>
</html>"""
    return html


def _format_pdf_ready(header: str, body: str, signature: str) -> str:
    """Format for PDF generation (clean text with proper spacing)."""
    parts = []
    if header:
        parts.append(header)
        parts.append("\n")
    parts.append(body)
    if signature:
        parts.append("\n\n")
        parts.append(signature)
    return "\n".join(parts)


# =============================================================================
# EMAIL FORMATTING
# =============================================================================


def format_email(
    subject: str,
    body: str,
    signature_type: str = "email",
    recipient_name: Optional[str] = None,
) -> dict:
    """
    Format an email with proper structure.

    Args:
        subject: Email subject line
        body: Email body text
        signature_type: "email" (casual), "formal", or "none"
        recipient_name: Name for greeting (optional)

    Returns:
        Dict with subject, body, full_text keys
    """
    # Clean subject line
    subject = clean_subject_line(subject)

    # Clean body
    body = clean_text(body)

    # Add greeting if we have a name and body doesn't start with one
    if recipient_name and not body.lower().startswith(("hi ", "hey ", "hello ", "dear ")):
        body = f"Hi {recipient_name},\n\n{body}"

    # Add signature
    if signature_type == "email":
        full_body = f"{body}\n\n{EMAIL_SIGNATURE}"
    elif signature_type == "formal":
        full_body = f"{body}\n\n{FORMAL_SIGNATURE}"
    else:
        full_body = body

    return {
        "subject": subject,
        "body": body,
        "signature": EMAIL_SIGNATURE if signature_type == "email" else FORMAL_SIGNATURE,
        "full_text": full_body,
    }


def clean_subject_line(subject: str) -> str:
    """Clean and validate email subject line."""
    # Remove any newlines
    subject = subject.replace("\n", " ").strip()

    # Remove surrounding quotes if present
    if subject.startswith('"') and subject.endswith('"'):
        subject = subject[1:-1]
    if subject.startswith("'") and subject.endswith("'"):
        subject = subject[1:-1]

    # Remove "Subject:" prefix if present
    if subject.lower().startswith("subject:"):
        subject = subject[8:].strip()

    # Truncate if too long (keep under 60 chars ideally)
    if len(subject) > 60:
        subject = subject[:57] + "..."

    return subject


# =============================================================================
# SIGNATURE UTILITIES
# =============================================================================


def add_signature(text: str, signature_type: str = "default") -> str:
    """
    Add the candidate's signature block to text.

    Args:
        text: Content to add signature to
        signature_type: "default", "email", or "formal"

    Returns:
        Text with signature appended
    """
    signatures = {
        "default": DEFAULT_SIGNATURE,
        "email": EMAIL_SIGNATURE,
        "formal": FORMAL_SIGNATURE,
    }

    signature = signatures.get(signature_type, DEFAULT_SIGNATURE)
    return f"{text.rstrip()}\n\n{signature}"


def get_signature(signature_type: str = "default") -> str:
    """Get a signature block by type."""
    signatures = {
        "default": DEFAULT_SIGNATURE,
        "email": EMAIL_SIGNATURE,
        "formal": FORMAL_SIGNATURE,
    }
    return signatures.get(signature_type, DEFAULT_SIGNATURE)


# =============================================================================
# TEXT CLEANING UTILITIES
# =============================================================================


def clean_text(text: str) -> str:
    """
    Clean generated text of common LLM artifacts.

    Removes:
    - Extra whitespace
    - Markdown formatting artifacts
    - Common LLM prefixes/suffixes
    """
    # Strip whitespace
    text = text.strip()

    # Remove common LLM artifacts
    artifacts_to_remove = [
        "Here is the cover letter:",
        "Here's the cover letter:",
        "Here is your cover letter:",
        "Here's your cover letter:",
        "Here is the email:",
        "Here's the email:",
        "Here is your email:",
        "[Cover letter begins]",
        "[End of cover letter]",
        "[Email begins]",
        "[End of email]",
    ]

    for artifact in artifacts_to_remove:
        text = text.replace(artifact, "")
        text = text.replace(artifact.lower(), "")

    # Remove leading/trailing quotes if the whole text is quoted
    if text.startswith('"""') and text.endswith('"""'):
        text = text[3:-3]
    if text.startswith("```") and text.endswith("```"):
        text = text[3:-3]

    # Clean up excessive newlines (more than 2 in a row)
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Clean up spaces before punctuation
    text = re.sub(r"\s+([.,!?;:])", r"\1", text)

    # Clean up multiple spaces
    text = re.sub(r"  +", " ", text)

    return text.strip()


def word_count(text: str) -> int:
    """Count words in text."""
    return len(text.split())


def estimate_read_time(text: str, wpm: int = 200) -> int:
    """Estimate read time in seconds."""
    words = word_count(text)
    return max(1, int((words / wpm) * 60))


# =============================================================================
# CONTENT VALIDATION
# =============================================================================


def validate_cover_letter(text: str) -> tuple[bool, list[str]]:
    """
    Validate a cover letter meets quality standards.

    Returns:
        (is_valid, list of issues)
    """
    issues = []

    # Check length
    words = word_count(text)
    if words < 100:
        issues.append(f"Too short ({words} words). Aim for 200-350 words.")
    if words > 500:
        issues.append(f"Too long ({words} words). Keep under 400 words.")

    # Check for AI-speak phrases
    ai_phrases = [
        "i am excited to",
        "i am writing to express",
        "i am passionate about",
        "leverage my",
        "synergy",
        "leverage",
        "utilize my skills",
        "throughout my career",
        "i believe i would be",
    ]
    text_lower = text.lower()
    for phrase in ai_phrases:
        if phrase in text_lower:
            issues.append(f'Contains AI-speak phrase: "{phrase}"')

    # Check for paragraph structure
    paragraphs = [p for p in text.split("\n\n") if p.strip()]
    if len(paragraphs) < 3:
        issues.append("Should have at least 3 paragraphs (opening, body, closing)")
    if len(paragraphs) > 5:
        issues.append("Too many paragraphs. Consolidate for readability.")

    # Check for metrics/numbers (good cover letters should have at least one)
    if not re.search(r"\$?\d+[%kKmMbB]?", text):
        issues.append("No quantified achievements found. Add at least one metric.")

    is_valid = len(issues) == 0
    return is_valid, issues


def validate_email(subject: str, body: str) -> tuple[bool, list[str]]:
    """
    Validate an email meets quality standards.

    Returns:
        (is_valid, list of issues)
    """
    issues = []

    # Check subject length
    if len(subject) > 60:
        issues.append(f"Subject too long ({len(subject)} chars). Keep under 50.")
    if len(subject) < 5:
        issues.append("Subject too short. Be more specific.")

    # Check body length
    words = word_count(body)
    if words > 200:
        issues.append(f"Email too long ({words} words). Keep under 150 for cold outreach.")
    if words < 20:
        issues.append("Email too short. Add more context.")

    # Check for clear ask
    ask_indicators = ["?", "would you", "could we", "can we", "let me know", "interested in"]
    has_ask = any(indicator in body.lower() for indicator in ask_indicators)
    if not has_ask:
        issues.append("No clear ask or call to action found.")

    is_valid = len(issues) == 0
    return is_valid, issues
