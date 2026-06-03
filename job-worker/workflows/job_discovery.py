"""
JobDiscoveryWorkflow

Daily workflow to discover new jobs matching search criteria.
Uses SerpAPI Google Jobs to find jobs across LinkedIn, Indeed,
Glassdoor, and company career pages. Google Jobs automatically
filters out expired listings. Dedupes against existing jobs
and stores new opportunities in the database.
"""

import logging
from datetime import timedelta
from typing import Optional

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from activities import (
        get_search_configs,
        search_jobs_searchapi,
        enrich_job_contacts,
        dedupe_jobs,
        parse_job_listing,
        save_job,
        update_search_config_last_run,
        log_job_event,
        analyze_resume_for_job_search,
    )

log = logging.getLogger(__name__)


@workflow.defn
class JobDiscoveryWorkflow:
    """
    Workflow for discovering new jobs matching search criteria.

    Steps:
    1. Load search configs (all active or specific one)
    2. For each config:
       - Call Grok agentic web search to find jobs
       - Dedupe against existing jobs
       - Parse and enrich new jobs
       - Calculate initial fit scores
       - Enrich high-fit jobs with contact info
       - Save to database
    3. Return: jobs_found, jobs_new, jobs_by_config
    """

    def __init__(self):
        self._cancelled = False
        self._current_config = None
        self._jobs_processed = 0

    @workflow.signal
    def cancel_discovery(self):
        """Signal to cancel the discovery workflow."""
        self._cancelled = True
        workflow.logger.info("Discovery cancellation signal received")

    @workflow.query
    def get_progress(self) -> dict:
        """Query current discovery progress."""
        return {
            "current_config": self._current_config,
            "jobs_processed": self._jobs_processed,
            "cancelled": self._cancelled,
        }

    @workflow.run
    async def run(
        self,
        search_config_id: Optional[str] = None,
        max_results_per_config: int = 50,
        use_resume: bool = False,
        resume_profile_id: Optional[str] = None,
        salary_override: Optional[int] = None,
    ) -> dict:
        """
        Execute the job discovery workflow.

        Args:
            search_config_id: Optional specific config to run (runs all active if None)
            max_results_per_config: Maximum jobs to fetch per search config
            use_resume: If True, analyze resume to generate search terms automatically
            resume_profile_id: Specific resume to use (uses default if None)
            salary_override: Override salary minimum from resume

        Returns:
            Discovery results with jobs found/new counts
        """
        workflow.logger.info(
            f"Starting job discovery, config_id={search_config_id or 'all active'}, "
            f"use_resume={use_resume}"
        )

        workflow_run_id = workflow.info().run_id

        retry_policy = RetryPolicy(
            initial_interval=timedelta(seconds=2),
            maximum_interval=timedelta(minutes=5),
            maximum_attempts=3,
        )

        # Step 1: Load search configurations (or generate from resume)
        configs = []

        if use_resume:
            # Analyze resume to generate search config automatically
            workflow.logger.info("Using resume-driven discovery mode")
            try:
                resume_analysis = await workflow.execute_activity(
                    analyze_resume_for_job_search,
                    args=[resume_profile_id],
                    start_to_close_timeout=timedelta(minutes=2),
                    retry_policy=retry_policy,
                )

                if resume_analysis.get("error"):
                    return {
                        "success": False,
                        "error": f"Resume analysis failed: {resume_analysis['error']}",
                        "jobs_found": 0,
                        "jobs_new": 0,
                    }

                # Create a synthetic config from resume analysis
                job_titles = resume_analysis.get("job_titles", [])
                if not job_titles:
                    return {
                        "success": False,
                        "error": "No job titles suggested from resume",
                        "jobs_found": 0,
                        "jobs_new": 0,
                    }

                # Use salary override if provided, otherwise from resume
                salary_min = salary_override
                if salary_min is None:
                    salary_range = resume_analysis.get("salary_range", {})
                    salary_min = salary_range.get("min")

                synthetic_config = {
                    "id": "resume-driven",
                    "name": f"Resume: {resume_analysis.get('resume_name', 'Auto')}",
                    "keywords": job_titles,
                    "locations": resume_analysis.get("locations", ["Remote"]),
                    "include_remote": resume_analysis.get("remote_preference") in (
                        "remote", "hybrid"
                    ),
                    "salary_min": salary_min,
                    "years_experience_min": None,  # Let LLM figure it out
                    "excluded_companies": [],
                    "target_companies": [],
                    "is_synthetic": True,  # Flag to skip last_run update
                }

                configs = [synthetic_config]
                workflow.logger.info(
                    f"Generated config from resume: {job_titles}, "
                    f"salary_min={salary_min}, locations={synthetic_config['locations']}"
                )

            except Exception as e:
                workflow.logger.error(f"Resume analysis failed: {e}")
                return {
                    "success": False,
                    "error": f"Resume analysis failed: {str(e)}",
                    "jobs_found": 0,
                    "jobs_new": 0,
                }
        else:
            # Traditional mode: load search configs from database
            try:
                configs = await workflow.execute_activity(
                    get_search_configs,
                    args=[search_config_id],
                    start_to_close_timeout=timedelta(seconds=30),
                    retry_policy=retry_policy,
                )
            except Exception as e:
                workflow.logger.error(f"Failed to load search configs: {e}")
                return {
                    "success": False,
                    "error": f"Failed to load search configs: {str(e)}",
                    "jobs_found": 0,
                    "jobs_new": 0,
                }

        if not configs:
            workflow.logger.warning("No search configs found")
            return {
                "success": True,
                "jobs_found": 0,
                "jobs_new": 0,
                "message": "No active search configs found. Try use_resume=True to auto-generate.",
            }

        workflow.logger.info(f"Processing {len(configs)} search config(s)")

        total_jobs_found = 0
        total_jobs_new = 0
        jobs_by_config = {}
        errors = []

        # Step 2: Process each search config
        for config in configs:
            if self._cancelled:
                workflow.logger.info("Discovery cancelled by signal")
                break

            config_id = config.get("id")
            config_name = config.get("name", "Unnamed")
            self._current_config = config_name

            workflow.logger.info(f"Processing config: {config_name} ({config_id})")

            try:
                # Extract search parameters from config
                keywords = self._get_keywords_list(config)
                locations = self._get_locations_list(config)
                # Database uses 'include_remote', fallback to 'remote_ok'
                remote_ok = config.get("include_remote", config.get("remote_ok", True))
                salary_min = config.get("salary_min")

                # Step 2a: Search for jobs via SearchAPI Google Jobs
                # Search each keyword/title individually for better results
                all_jobs = []
                search_keywords = keywords[:4] if keywords else ["software engineer"]
                results_per_search = max(10, max_results_per_config // (len(search_keywords) * len(locations)))

                for keyword in search_keywords:
                    for loc in locations:
                        search_result = await workflow.execute_activity(
                            search_jobs_searchapi,
                            args=[keyword, loc, results_per_search],
                            start_to_close_timeout=timedelta(minutes=3),
                            retry_policy=retry_policy,
                        )
                        all_jobs.extend(search_result.get("jobs", []))

                    # Also search remote for each keyword if enabled
                    if remote_ok and "remote" not in [loc.lower() for loc in locations]:
                        search_result = await workflow.execute_activity(
                            search_jobs_searchapi,
                            args=[keyword, "Remote", results_per_search],
                            start_to_close_timeout=timedelta(minutes=3),
                            retry_policy=retry_policy,
                        )
                        all_jobs.extend(search_result.get("jobs", []))

                raw_jobs = all_jobs
                workflow.logger.info(
                    f"SearchAPI returned {len(raw_jobs)} jobs for '{config_name}'"
                )

                if not raw_jobs:
                    jobs_by_config[config_id] = {"found": 0, "new": 0, "jobs": []}
                    continue

                # Step 2b: Dedupe against existing jobs
                dedupe_result = await workflow.execute_activity(
                    dedupe_jobs,
                    args=[raw_jobs],
                    start_to_close_timeout=timedelta(seconds=60),
                    retry_policy=retry_policy,
                )

                new_job_listings = dedupe_result.get("new_jobs", [])
                duplicate_count = dedupe_result.get("duplicate_count", 0)

                workflow.logger.info(
                    f"Deduplication: {len(new_job_listings)} new, {duplicate_count} duplicates"
                )

                config_jobs_new = []

                # Step 2c: Process each new job
                for job_listing in new_job_listings:
                    if self._cancelled:
                        break

                    try:
                        # Parse and extract structured data
                        parsed_job = await workflow.execute_activity(
                            parse_job_listing,
                            args=[job_listing],
                            start_to_close_timeout=timedelta(seconds=30),
                            retry_policy=retry_policy,
                        )

                        if not parsed_job:
                            continue

                        parsed_job["search_config_id"] = config_id

                        # Save to database
                        job_id = await workflow.execute_activity(
                            save_job,
                            args=[parsed_job],
                            start_to_close_timeout=timedelta(seconds=30),
                            retry_policy=retry_policy,
                        )

                        if job_id:
                            parsed_job["id"] = job_id
                            config_jobs_new.append({
                                "id": job_id,
                                "title": parsed_job.get("title"),
                                "company": parsed_job.get("company_name"),
                                "fit_score": parsed_job.get("fit_score"),
                            })
                            self._jobs_processed += 1

                            # Log discovery event
                            await workflow.execute_activity(
                                log_job_event,
                                args=[
                                    job_id,
                                    "discovered",
                                    {
                                        "search_config": config_name,
                                        "fit_score": parsed_job.get("fit_score"),
                                        "source": "serpapi",
                                    },
                                ],
                                start_to_close_timeout=timedelta(seconds=10),
                            )

                            # Enrich high-fit jobs with contact info
                            if parsed_job.get("fit_score", 0) >= 0.7:
                                try:
                                    contact_result = await workflow.execute_activity(
                                        enrich_job_contacts,
                                        args=[job_id, parsed_job.get("company_name", "")],
                                        start_to_close_timeout=timedelta(minutes=2),
                                        retry_policy=retry_policy,
                                    )
                                    if contact_result and not contact_result.get("error"):
                                        workflow.logger.info(
                                            f"Enriched contacts for {parsed_job.get('title')} "
                                            f"at {parsed_job.get('company_name')}"
                                        )
                                except Exception as e:
                                    workflow.logger.warning(
                                        f"Contact enrichment failed for job {job_id}: {e}"
                                    )

                    except Exception as e:
                        workflow.logger.warning(
                            f"Failed to process job listing: {e}",
                            extra={"job_title": job_listing.get("title", "unknown")},
                        )
                        continue

                jobs_by_config[config_id] = {
                    "config_name": config_name,
                    "found": len(raw_jobs),
                    "new": len(config_jobs_new),
                    "duplicates": duplicate_count,
                    "jobs": config_jobs_new,
                }

                total_jobs_found += len(raw_jobs)
                total_jobs_new += len(config_jobs_new)

                # Update last run timestamp on config (skip for synthetic/resume-driven configs)
                if not config.get("is_synthetic"):
                    await workflow.execute_activity(
                        update_search_config_last_run,
                        args=[config_id, len(raw_jobs), len(config_jobs_new)],
                        start_to_close_timeout=timedelta(seconds=10),
                    )

            except Exception as e:
                workflow.logger.error(f"Config {config_name} failed: {e}")
                errors.append({
                    "config_id": config_id,
                    "config_name": config_name,
                    "error": str(e),
                })
                continue

        self._current_config = None

        workflow.logger.info(
            f"Job discovery complete: {total_jobs_found} found, {total_jobs_new} new"
        )

        return {
            "success": True,
            "workflow_run_id": workflow_run_id,
            "jobs_found": total_jobs_found,
            "jobs_new": total_jobs_new,
            "configs_processed": len(configs),
            "jobs_by_config": jobs_by_config,
            "errors": errors if errors else None,
            "cancelled": self._cancelled,
        }

    def _get_keywords_list(self, config: dict) -> list[str]:
        """Extract keywords as a list from config."""
        keywords = config.get("keywords", "")
        if isinstance(keywords, list):
            return keywords
        if isinstance(keywords, str) and keywords:
            # Split by comma or space if it's a string
            if "," in keywords:
                return [k.strip() for k in keywords.split(",") if k.strip()]
            return [keywords]
        # Fall back to name or default
        return [config.get("name", "software engineer")]

    def _get_locations_list(self, config: dict) -> list[str]:
        """Extract locations as a list from config."""
        # Database uses 'locations' (array), fallback to 'location' (string)
        locations = config.get("locations") or config.get("location", "")
        if isinstance(locations, list) and locations:
            return locations
        if isinstance(locations, str) and locations:
            if "," in locations:
                return [loc.strip() for loc in locations.split(",") if loc.strip()]
            return [locations]
        return ["Remote"]  # Default to remote if no locations

    def _get_posted_within_days(self, date_posted: str | None) -> int:
        """Convert date_posted string to days integer."""
        if not date_posted:
            return 7  # Default to 1 week
        mapping = {
            "day": 1,
            "3days": 3,
            "week": 7,
            "2weeks": 14,
            "month": 30,
        }
        return mapping.get(date_posted.lower(), 7)
