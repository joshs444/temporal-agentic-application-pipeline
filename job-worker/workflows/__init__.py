# Temporal Workflows for JobHunt
# - JobDiscoveryWorkflow: Daily job discovery from search configs
# - JobEnrichmentWorkflow: Enrich jobs with company data and contacts
# - ApplicationWorkflow: Full application workflow with approval
# - FollowUpWorkflow: Automated follow-up sequence
# - InterviewPrepWorkflow: Interview preparation materials

from workflows.job_discovery import JobDiscoveryWorkflow
from workflows.job_enrichment import JobEnrichmentWorkflow
from workflows.application import ApplicationWorkflow
from workflows.follow_up import FollowUpWorkflow
from workflows.interview_prep import InterviewPrepWorkflow

__all__ = [
    "JobDiscoveryWorkflow",
    "JobEnrichmentWorkflow",
    "ApplicationWorkflow",
    "FollowUpWorkflow",
    "InterviewPrepWorkflow",
]
