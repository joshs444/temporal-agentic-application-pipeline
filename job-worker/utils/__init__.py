# Shared Utilities
# - Database helpers
# - LLM logging
# - Configuration
# - Job matching utilities
# - Content formatting

from .domain_finder import (
    normalize_company_name,
    company_name_to_domain_candidates,
    find_domain,
    find_domain_sequential,
    extract_domain_from_url,
    domains_match,
)

from .matching import (
    keyword_match_score,
    experience_level_match,
    location_match,
    salary_match,
    title_match_score,
    calculate_quick_score,
    extract_salary_from_text,
)

from .llm_config import get_llm_client

from .llm import (
    get_xai_client,
    analyze_job_fit,
    extract_job_requirements,
    generate_skill_gap_analysis,
)

from .profile import (
    load_profile,
    candidate,
    candidate_name,
    resume_dict,
)

from .content_formatter import (
    format_cover_letter,
    format_email,
    add_signature,
    get_signature,
    clean_text,
    clean_subject_line,
    validate_cover_letter,
    validate_email,
    word_count,
    estimate_read_time,
)

from .email_templates import (
    render_template,
    render_html_email,
    build_initial_outreach,
    build_follow_up,
    build_thank_you,
    build_recruiter_outreach,
    build_referral_outreach,
    get_email_type_template,
    INITIAL_OUTREACH_TEMPLATE,
    FOLLOW_UP_TEMPLATE,
    THANK_YOU_TEMPLATE,
    EMAIL_SIGNATURE,
    EMAIL_SIGNATURE_HTML,
)

__all__ = [
    # Domain finder
    "normalize_company_name",
    "company_name_to_domain_candidates",
    "find_domain",
    "find_domain_sequential",
    "extract_domain_from_url",
    "domains_match",
    # Matching utilities
    "keyword_match_score",
    "experience_level_match",
    "location_match",
    "salary_match",
    "title_match_score",
    "calculate_quick_score",
    "extract_salary_from_text",
    # LLM utilities
    "get_llm_client",
    "get_xai_client",
    "analyze_job_fit",
    "extract_job_requirements",
    "generate_skill_gap_analysis",
    # Candidate profile
    "load_profile",
    "candidate",
    "candidate_name",
    "resume_dict",
    # Content formatting
    "format_cover_letter",
    "format_email",
    "add_signature",
    "get_signature",
    "clean_text",
    "clean_subject_line",
    "validate_cover_letter",
    "validate_email",
    "word_count",
    "estimate_read_time",
    # Email templates
    "render_template",
    "render_html_email",
    "build_initial_outreach",
    "build_follow_up",
    "build_thank_you",
    "build_recruiter_outreach",
    "build_referral_outreach",
    "get_email_type_template",
    "INITIAL_OUTREACH_TEMPLATE",
    "FOLLOW_UP_TEMPLATE",
    "THANK_YOU_TEMPLATE",
    "EMAIL_SIGNATURE",
    "EMAIL_SIGNATURE_HTML",
]
