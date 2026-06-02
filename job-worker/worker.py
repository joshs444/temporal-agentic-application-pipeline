"""
JobHunt Temporal Worker

Main entry point for the Temporal worker that processes all job hunt workflows.
Registers all workflows and activities, connects to Temporal server,
and runs the worker on the "jobhunt-worker" task queue.
"""

import asyncio
import logging
import os
import signal
import sys

from temporalio.client import Client
from temporalio.worker import Worker

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
log = logging.getLogger(__name__)

# Configuration from environment
TEMPORAL_ADDRESS = os.getenv("TEMPORAL_ADDRESS", "localhost:7233")
TEMPORAL_NAMESPACE = os.getenv("TEMPORAL_NAMESPACE", "default")
TASK_QUEUE = os.getenv("TASK_QUEUE", "jobhunt-worker")
MAX_CONCURRENT_ACTIVITIES = int(os.getenv("MAX_CONCURRENT_ACTIVITIES", "10"))
MAX_CONCURRENT_WORKFLOWS = int(os.getenv("MAX_CONCURRENT_WORKFLOWS", "20"))


def get_workflows():
    """Import and return all workflow classes."""
    from workflows.job_discovery import JobDiscoveryWorkflow
    from workflows.job_enrichment import JobEnrichmentWorkflow
    from workflows.application import ApplicationWorkflow
    from workflows.follow_up import FollowUpWorkflow
    from workflows.interview_prep import InterviewPrepWorkflow

    return [
        JobDiscoveryWorkflow,
        JobEnrichmentWorkflow,
        ApplicationWorkflow,
        FollowUpWorkflow,
        InterviewPrepWorkflow,
    ]


def get_activities():
    """Import and return all activity functions."""
    # Import from existing activity modules
    from activities.jobs import (
        discover_jobs,
        parse_job_requirements,
        check_job_still_active,
        save_jobs_to_db,
        get_search_configs,
        enrich_job_company_info,
        score_job_fit,
    )

    from activities.company import (
        enrich_company,
        find_hiring_contacts,
        get_company_hiring_signals,
        research_company_culture,
        batch_enrich_companies,
    )

    from activities.matching import (
        quick_filter_job,
        calculate_fit_score,
        rank_jobs,
        identify_skill_gaps,
        batch_quick_filter,
        extract_requirements,
    )

    from activities.cover_letter import (
        generate_cover_letter,
        generate_email_to_recruiter,
        tailor_resume_bullets,
        generate_thank_you_email,
    )

    from activities.email import (
        send_outreach_email,
        check_for_replies,
        classify_reply,
        schedule_follow_up,
        generate_outreach_email,
        process_reply,
    )

    # Import workflow-specific activities
    from activities.workflow_activities import (
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

    return [
        # Jobs activities
        discover_jobs,
        parse_job_requirements,
        check_job_still_active,
        save_jobs_to_db,
        get_search_configs,
        enrich_job_company_info,
        score_job_fit,
        # Company activities
        enrich_company,
        find_hiring_contacts,
        get_company_hiring_signals,
        research_company_culture,
        batch_enrich_companies,
        # Matching activities
        quick_filter_job,
        calculate_fit_score,
        rank_jobs,
        identify_skill_gaps,
        batch_quick_filter,
        extract_requirements,
        # Cover letter activities
        generate_cover_letter,
        generate_email_to_recruiter,
        tailor_resume_bullets,
        generate_thank_you_email,
        # Email activities
        send_outreach_email,
        check_for_replies,
        classify_reply,
        schedule_follow_up,
        generate_outreach_email,
        process_reply,
        # Workflow activities - Job discovery
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
        # Workflow activities - Job enrichment
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
        # Workflow activities - Application
        get_job_with_company,
        get_user_profile,
        get_best_contact,
        save_application_draft,
        update_application_status,
        send_application_email,
        create_application_record,
        # Workflow activities - Follow-up
        get_application,
        check_application_replied,
        generate_follow_up_email,
        send_follow_up_email,
        update_follow_up_record,
        # Workflow activities - Interview prep
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
    ]


async def run_worker():
    """Initialize and run the Temporal worker."""
    log.info(f"Connecting to Temporal at {TEMPORAL_ADDRESS}")

    # Connect to Temporal
    client = await Client.connect(
        TEMPORAL_ADDRESS,
        namespace=TEMPORAL_NAMESPACE,
    )

    log.info(f"Connected to Temporal namespace: {TEMPORAL_NAMESPACE}")

    # Get workflows and activities
    workflows = get_workflows()
    activities = get_activities()

    # Create the worker
    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=workflows,
        activities=activities,
        max_concurrent_activities=MAX_CONCURRENT_ACTIVITIES,
        max_concurrent_workflow_tasks=MAX_CONCURRENT_WORKFLOWS,
    )

    log.info(f"Starting worker on task queue: {TASK_QUEUE}")
    log.info(f"Registered {len(workflows)} workflows, {len(activities)} activities")
    log.info(f"Max concurrent activities: {MAX_CONCURRENT_ACTIVITIES}")
    log.info(f"Max concurrent workflows: {MAX_CONCURRENT_WORKFLOWS}")

    # Run the worker
    await worker.run()


async def main():
    """Main entry point with graceful shutdown handling."""
    # Set up signal handlers for graceful shutdown
    shutdown_event = asyncio.Event()

    def signal_handler():
        log.info("Shutdown signal received")
        shutdown_event.set()

    # Register signal handlers
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler)

    # Run worker with shutdown handling
    worker_task = asyncio.create_task(run_worker())

    # Wait for either worker completion or shutdown signal
    done, pending = await asyncio.wait(
        [worker_task, asyncio.create_task(shutdown_event.wait())],
        return_when=asyncio.FIRST_COMPLETED,
    )

    # Cancel pending tasks
    for task in pending:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    # Check if worker raised an exception
    for task in done:
        if task.exception():
            log.error(f"Worker error: {task.exception()}")
            sys.exit(1)

    log.info("Worker shutdown complete")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Worker interrupted")
    except Exception as e:
        log.error(f"Worker failed: {e}")
        sys.exit(1)
