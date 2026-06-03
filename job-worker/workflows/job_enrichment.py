"""
JobEnrichmentWorkflow

Enriches a job posting with company data, hiring contacts,
culture research, and detailed fit scoring.
"""

import logging
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from activities import (
        get_job,
        get_company_by_domain,
        apollo_enrich_company,
        apollo_search_contacts,
        research_company_culture,
        calculate_detailed_fit_score,
        save_company,
        update_company,
        update_job_enrichment,
        link_job_to_company,
        save_contacts,
        log_job_event,
    )

log = logging.getLogger(__name__)


@workflow.defn
class JobEnrichmentWorkflow:
    """
    Workflow for enriching a job with company research.

    Steps:
    1. Get job from database
    2. Enrich company via Apollo (or retrieve if cached)
    3. Find hiring contacts (recruiters, hiring managers)
    4. Research company culture (Glassdoor, news, etc.)
    5. Calculate detailed fit score with reasoning
    6. Update job and company in database
    """

    def __init__(self):
        self._stage = "initializing"
        self._company_found = False
        self._contacts_found = 0

    @workflow.query
    def get_status(self) -> dict:
        """Query current enrichment status."""
        return {
            "stage": self._stage,
            "company_found": self._company_found,
            "contacts_found": self._contacts_found,
        }

    @workflow.run
    async def run(
        self,
        job_id: str,
        force_refresh: bool = False,
        include_culture_research: bool = True,
    ) -> dict:
        """
        Execute the job enrichment workflow.

        Args:
            job_id: The job to enrich
            force_refresh: Force re-enrichment even if data exists
            include_culture_research: Whether to research company culture (slower)

        Returns:
            Enriched job data with company info, contacts, and fit score
        """
        workflow.logger.info(f"Starting enrichment for job {job_id}")

        workflow_run_id = workflow.info().run_id

        retry_policy = RetryPolicy(
            initial_interval=timedelta(seconds=2),
            maximum_interval=timedelta(minutes=5),
            maximum_attempts=3,
        )

        # Step 1: Get job from database
        self._stage = "loading_job"

        job = await workflow.execute_activity(
            get_job,
            args=[job_id],
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=retry_policy,
        )

        if not job:
            workflow.logger.error(f"Job {job_id} not found")
            return {
                "job_id": job_id,
                "success": False,
                "error": "Job not found",
            }

        company_name = job.get("company_name", "")
        company_domain = job.get("company_domain")
        job_title = job.get("title", "")

        workflow.logger.info(f"Enriching job: {job_title} at {company_name}")

        # Check if already enriched (unless force_refresh)
        if not force_refresh and job.get("enriched_at"):
            workflow.logger.info("Job already enriched, skipping (use force_refresh=True to override)")
            return {
                "job_id": job_id,
                "success": True,
                "skipped": True,
                "message": "Already enriched",
                "enriched_at": job.get("enriched_at"),
            }

        # Step 2: Enrich company via Apollo (or use cached)
        self._stage = "enriching_company"

        company = None
        company_id = job.get("company_id")

        # Check if we already have this company
        if company_domain:
            existing_company = await workflow.execute_activity(
                get_company_by_domain,
                args=[company_domain],
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=retry_policy,
            )
            if existing_company and not force_refresh:
                company = existing_company
                company_id = company.get("id")
                self._company_found = True
                workflow.logger.info(f"Found existing company record for {company_domain}")

        # Enrich via Apollo if needed
        if not company or force_refresh:
            try:
                apollo_result = await workflow.execute_activity(
                    apollo_enrich_company,
                    args=[company_name, company_domain],
                    start_to_close_timeout=timedelta(minutes=2),
                    retry_policy=retry_policy,
                )

                if apollo_result and apollo_result.get("found"):
                    self._company_found = True
                    company_data = {
                        "name": apollo_result.get("name", company_name),
                        "domain": apollo_result.get("domain", company_domain),
                        "description": apollo_result.get("description"),
                        "industry": apollo_result.get("industry"),
                        "employee_count": apollo_result.get("employees"),
                        "employee_range": apollo_result.get("employee_range"),
                        "headquarters_city": apollo_result.get("city"),
                        "headquarters_state": apollo_result.get("state"),
                        "headquarters_country": apollo_result.get("country"),
                        "linkedin_url": apollo_result.get("linkedin_url"),
                        "website": apollo_result.get("website_url"),
                        "founded_year": apollo_result.get("founded_year"),
                        "funding_stage": apollo_result.get("funding_stage"),
                        "total_funding": apollo_result.get("total_funding"),
                        "technologies": apollo_result.get("technologies", []),
                        "keywords": apollo_result.get("keywords", []),
                        "apollo_id": apollo_result.get("id"),
                    }

                    # Save or update company
                    if company_id:
                        await workflow.execute_activity(
                            update_company,
                            args=[company_id, company_data],
                            start_to_close_timeout=timedelta(seconds=30),
                            retry_policy=retry_policy,
                        )
                        company = {**company_data, "id": company_id}
                    else:
                        company_id = await workflow.execute_activity(
                            save_company,
                            args=[company_data],
                            start_to_close_timeout=timedelta(seconds=30),
                            retry_policy=retry_policy,
                        )
                        company = {**company_data, "id": company_id}

                    workflow.logger.info(
                        f"Company enriched: {company.get('name')} ({company.get('employee_count')} employees)"
                    )
                else:
                    workflow.logger.warning(f"Apollo did not find company: {company_name}")

            except Exception as e:
                workflow.logger.warning(f"Apollo company enrichment failed: {e}")

        # Link job to company if we have one
        if company_id and not job.get("company_id"):
            await workflow.execute_activity(
                link_job_to_company,
                args=[job_id, company_id],
                start_to_close_timeout=timedelta(seconds=30),
            )

        # Step 3: Find hiring contacts
        self._stage = "finding_contacts"

        contacts = []
        if company_domain:
            try:
                # Search for relevant contacts at the company
                contact_titles = self._get_relevant_contact_titles(job_title)

                contact_result = await workflow.execute_activity(
                    apollo_search_contacts,
                    args=[company_domain, contact_titles],
                    start_to_close_timeout=timedelta(minutes=2),
                    retry_policy=retry_policy,
                )

                contacts = contact_result.get("contacts", [])
                self._contacts_found = len(contacts)

                if contacts:
                    # Save contacts to database
                    await workflow.execute_activity(
                        save_contacts,
                        args=[job_id, company_id, contacts],
                        start_to_close_timeout=timedelta(seconds=60),
                        retry_policy=retry_policy,
                    )
                    workflow.logger.info(f"Found {len(contacts)} relevant contacts")

            except Exception as e:
                workflow.logger.warning(f"Contact search failed: {e}")

        # Step 4: Research company culture (optional, slower)
        self._stage = "researching_culture"

        culture_data = {}
        if include_culture_research and company_name:
            try:
                culture_result = await workflow.execute_activity(
                    research_company_culture,
                    args=[company_name, company_domain],
                    start_to_close_timeout=timedelta(minutes=3),
                    retry_policy=retry_policy,
                )

                culture_data = {
                    "glassdoor_rating": culture_result.get("glassdoor_rating"),
                    "glassdoor_reviews_count": culture_result.get("reviews_count"),
                    "culture_keywords": culture_result.get("culture_keywords", []),
                    "pros": culture_result.get("pros", []),
                    "cons": culture_result.get("cons", []),
                    "interview_difficulty": culture_result.get("interview_difficulty"),
                    "recent_news": culture_result.get("recent_news", []),
                    "growth_signals": culture_result.get("growth_signals", []),
                }

                workflow.logger.info(
                    f"Culture research complete: Glassdoor rating {culture_data.get('glassdoor_rating')}"
                )

            except Exception as e:
                workflow.logger.warning(f"Culture research failed: {e}")

        # Step 5: Calculate detailed fit score
        self._stage = "scoring"

        fit_result = await workflow.execute_activity(
            calculate_detailed_fit_score,
            args=[job, company, contacts, culture_data],
            start_to_close_timeout=timedelta(minutes=2),
            retry_policy=retry_policy,
        )

        fit_score = fit_result.get("score", 0.5)
        fit_reasoning = fit_result.get("reasoning", "")
        fit_signals = fit_result.get("signals", [])
        fit_recommendation = fit_result.get("recommendation", "review")

        workflow.logger.info(
            f"Fit score: {fit_score:.2f} - {fit_recommendation}"
        )

        # Step 6: Update job with enrichment data
        self._stage = "saving"

        enrichment_data = {
            "company_id": company_id,
            "enriched_at": workflow.now().isoformat(),
            "fit_score": fit_score,
            "fit_reasoning": fit_reasoning,
            "fit_signals": fit_signals,
            "fit_recommendation": fit_recommendation,
            "contacts_count": len(contacts),
            "has_culture_data": bool(culture_data),
            "culture_data": culture_data if culture_data else None,
        }

        await workflow.execute_activity(
            update_job_enrichment,
            args=[job_id, enrichment_data],
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=retry_policy,
        )

        # Log enrichment event
        await workflow.execute_activity(
            log_job_event,
            args=[
                job_id,
                "enriched",
                {
                    "company_found": self._company_found,
                    "contacts_found": self._contacts_found,
                    "fit_score": fit_score,
                    "fit_recommendation": fit_recommendation,
                },
            ],
            start_to_close_timeout=timedelta(seconds=10),
        )

        self._stage = "complete"

        workflow.logger.info(f"Enrichment complete for job {job_id}")

        return {
            "job_id": job_id,
            "success": True,
            "workflow_run_id": workflow_run_id,
            "company": {
                "id": company_id,
                "name": company.get("name") if company else company_name,
                "domain": company.get("domain") if company else company_domain,
                "employee_count": company.get("employee_count") if company else None,
                "industry": company.get("industry") if company else None,
            } if company else None,
            "contacts": [
                {
                    "name": c.get("name"),
                    "title": c.get("title"),
                    "email": c.get("email"),
                }
                for c in contacts[:5]  # Return top 5 contacts
            ],
            "culture": culture_data if culture_data else None,
            "fit_score": fit_score,
            "fit_reasoning": fit_reasoning,
            "fit_signals": fit_signals,
            "fit_recommendation": fit_recommendation,
        }

    def _get_relevant_contact_titles(self, job_title: str) -> list[str]:
        """Determine relevant contact titles based on the job being applied to."""
        job_lower = job_title.lower()

        # Always look for recruiters
        titles = ["recruiter", "talent acquisition", "hr manager"]

        # Engineering roles
        if any(kw in job_lower for kw in ["engineer", "developer", "architect", "devops", "sre"]):
            titles.extend([
                "engineering manager",
                "vp of engineering",
                "director of engineering",
                "cto",
                "head of engineering",
            ])

        # Product roles
        elif any(kw in job_lower for kw in ["product manager", "product owner", "product lead"]):
            titles.extend([
                "head of product",
                "vp of product",
                "director of product",
                "cpo",
            ])

        # Design roles
        elif any(kw in job_lower for kw in ["designer", "ux", "ui"]):
            titles.extend([
                "head of design",
                "design director",
                "vp of design",
            ])

        # Data roles
        elif any(kw in job_lower for kw in ["data scientist", "data engineer", "ml engineer", "ai"]):
            titles.extend([
                "head of data",
                "vp of data",
                "chief data officer",
                "director of data science",
            ])

        # Default: general management
        else:
            titles.extend([
                "hiring manager",
                "department head",
                "director",
            ])

        return titles
