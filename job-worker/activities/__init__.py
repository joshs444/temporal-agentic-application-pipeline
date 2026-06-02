# Temporal Activities for JobHunt
# - Job discovery activities
# - Enrichment activities
# - Application generation activities
# - Job matching activities
# - Cover letter and content generation activities
# - Email activities

from .company import (
    enrich_company,
    find_hiring_contacts,
    get_company_hiring_signals,
    research_company_culture,
    batch_enrich_companies,
)

from .matching import (
    quick_filter_job,
    calculate_fit_score,
    rank_jobs,
    identify_skill_gaps,
    batch_quick_filter,
    extract_requirements,
)

from .cover_letter import (
    generate_cover_letter,
    generate_email_to_recruiter,
    tailor_resume_bullets,
    generate_thank_you_email,
    COVER_LETTER_ACTIVITIES,
)

from .jobs import (
    discover_jobs,
    parse_job_requirements,
    check_job_still_active,
    save_jobs_to_db,
    get_search_configs,
    enrich_job_company_info,
    score_job_fit,
)

from .email import (
    send_outreach_email,
    check_for_replies,
    classify_reply,
    schedule_follow_up,
    generate_outreach_email,
    process_reply,
)

# Additional activities needed by workflows (placeholders for now)
from .workflow_activities import (
    # Job discovery
    search_jobs_searchapi,
    search_jobs_serpapi,
    search_jobs_grok,
    analyze_resume_for_job_search,
    enrich_job_contacts,
    dedupe_jobs,
    parse_job_listing,
    calculate_initial_fit_score,
    save_job,
    get_job_by_url,
    update_search_config_last_run,
    log_job_event,
    # Job enrichment
    get_job,
    get_company_by_domain,
    apollo_enrich_company,
    apollo_search_contacts,
    calculate_detailed_fit_score,
    save_company,
    update_company,
    update_job_enrichment,
    link_job_to_company,
    save_contacts,
    # Application
    get_job_with_company,
    get_user_profile,
    get_best_contact,
    save_application_draft,
    update_application_status,
    send_application_email,
    create_application_record,
    # Follow-up
    get_application,
    check_application_replied,
    generate_follow_up_email,
    send_follow_up_email,
    update_follow_up_record,
    # Interview prep
    get_interview,
    get_application_with_job,
    get_company,
    research_company_recent,
    research_interviewer,
    generate_interview_questions,
    generate_talking_points,
    generate_prep_document,
    save_interview_prep,
    update_interview_status,
    # Shared
    notify_user,
)

__all__ = [
    # Company enrichment
    "enrich_company",
    "find_hiring_contacts",
    "get_company_hiring_signals",
    "research_company_culture",
    "batch_enrich_companies",
    # Job matching
    "quick_filter_job",
    "calculate_fit_score",
    "rank_jobs",
    "identify_skill_gaps",
    "batch_quick_filter",
    "extract_requirements",
    # Cover letter and content generation
    "generate_cover_letter",
    "generate_email_to_recruiter",
    "tailor_resume_bullets",
    "generate_thank_you_email",
    "COVER_LETTER_ACTIVITIES",
    # Jobs
    "discover_jobs",
    "parse_job_requirements",
    "check_job_still_active",
    "save_jobs_to_db",
    "get_search_configs",
    "enrich_job_company_info",
    "score_job_fit",
    # Email
    "send_outreach_email",
    "check_for_replies",
    "classify_reply",
    "schedule_follow_up",
    "generate_outreach_email",
    "process_reply",
    # Workflow activities
    "search_jobs_searchapi",
    "search_jobs_serpapi",
    "search_jobs_grok",
    "analyze_resume_for_job_search",
    "enrich_job_contacts",
    "dedupe_jobs",
    "parse_job_listing",
    "calculate_initial_fit_score",
    "save_job",
    "get_job_by_url",
    "update_search_config_last_run",
    "log_job_event",
    "get_job",
    "get_company_by_domain",
    "apollo_enrich_company",
    "apollo_search_contacts",
    "calculate_detailed_fit_score",
    "save_company",
    "update_company",
    "update_job_enrichment",
    "link_job_to_company",
    "save_contacts",
    "get_job_with_company",
    "get_user_profile",
    "get_best_contact",
    "save_application_draft",
    "update_application_status",
    "send_application_email",
    "create_application_record",
    "get_application",
    "check_application_replied",
    "generate_follow_up_email",
    "send_follow_up_email",
    "update_follow_up_record",
    "get_interview",
    "get_application_with_job",
    "get_company",
    "research_company_recent",
    "research_interviewer",
    "generate_interview_questions",
    "generate_talking_points",
    "generate_prep_document",
    "save_interview_prep",
    "update_interview_status",
    "notify_user",
]
