"""
InterviewPrepWorkflow

Prepares comprehensive materials for an upcoming interview.
Researches company, interviewers, and generates likely questions
with suggested talking points.
"""

import logging
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from activities import (
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
        log_job_event,
        notify_user,
    )

log = logging.getLogger(__name__)


@workflow.defn
class InterviewPrepWorkflow:
    """
    Workflow for preparing for an upcoming interview.

    Steps:
    1. Get interview and application details
    2. Deep research on company (recent news, culture)
    3. Research interviewers (LinkedIn, background)
    4. Generate likely questions based on:
       - Job requirements
       - Interview type (technical, behavioral, etc.)
       - Interviewer backgrounds
    5. Generate suggested talking points
    6. Create comprehensive prep document
    """

    def __init__(self):
        self._stage = "initializing"
        self._interviewers_researched = 0
        self._questions_generated = 0

    @workflow.query
    def get_status(self) -> dict:
        """Query current prep status."""
        return {
            "stage": self._stage,
            "interviewers_researched": self._interviewers_researched,
            "questions_generated": self._questions_generated,
        }

    @workflow.run
    async def run(
        self,
        interview_id: str,
        include_interviewer_research: bool = True,
        deep_company_research: bool = True,
    ) -> dict:
        """
        Execute the interview prep workflow.

        Args:
            interview_id: The interview to prepare for
            include_interviewer_research: Whether to research individual interviewers
            deep_company_research: Whether to do comprehensive company research

        Returns:
            Prep document, interviewer profiles, and suggested questions
        """
        workflow.logger.info(f"Starting interview prep for interview {interview_id}")

        workflow_run_id = workflow.info().run_id

        retry_policy = RetryPolicy(
            initial_interval=timedelta(seconds=2),
            maximum_interval=timedelta(minutes=5),
            maximum_attempts=3,
        )

        # Step 1: Get interview and application details
        self._stage = "loading_data"

        interview = await workflow.execute_activity(
            get_interview,
            args=[interview_id],
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=retry_policy,
        )

        if not interview:
            workflow.logger.error(f"Interview {interview_id} not found")
            return {
                "interview_id": interview_id,
                "success": False,
                "error": "Interview not found",
            }

        application_id = interview.get("application_id")
        interview_type = interview.get("interview_type", "general")
        interview_round = interview.get("round", 1)
        scheduled_at = interview.get("scheduled_at")
        interviewers = interview.get("interviewers", [])

        workflow.logger.info(
            f"Interview: {interview_type} (round {interview_round}), "
            f"{len(interviewers)} interviewer(s)"
        )

        # Get application and job details
        app_data = await workflow.execute_activity(
            get_application_with_job,
            args=[application_id],
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=retry_policy,
        )

        if not app_data:
            workflow.logger.error(f"Application {application_id} not found")
            return {
                "interview_id": interview_id,
                "success": False,
                "error": "Application not found",
            }

        job = app_data.get("job", {})
        company_id = job.get("company_id")

        job_title = job.get("title", "")
        company_name = job.get("company_name", "")
        job_description = job.get("description", "")
        job_requirements = job.get("requirements", [])

        workflow.logger.info(f"Preparing for: {job_title} at {company_name}")

        # Get company details
        company = {}
        if company_id:
            company = await workflow.execute_activity(
                get_company,
                args=[company_id],
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=retry_policy,
            ) or {}

        # Step 2: Deep research on company
        self._stage = "researching_company"

        company_research = {}
        if deep_company_research:
            try:
                company_research = await workflow.execute_activity(
                    research_company_recent,
                    args=[company_name, company.get("domain")],
                    start_to_close_timeout=timedelta(minutes=5),
                    retry_policy=retry_policy,
                )

                workflow.logger.info(
                    f"Company research complete: {len(company_research.get('recent_news', []))} news items, "
                    f"{len(company_research.get('key_initiatives', []))} initiatives"
                )

            except Exception as e:
                workflow.logger.warning(f"Company research failed: {e}")

        # Build company context
        company_context = {
            "name": company_name,
            "domain": company.get("domain"),
            "industry": company.get("industry"),
            "employee_count": company.get("employee_count"),
            "description": company.get("description"),
            "mission": company_research.get("mission"),
            "values": company_research.get("values", []),
            "culture_keywords": company_research.get("culture_keywords", []),
            "recent_news": company_research.get("recent_news", []),
            "key_initiatives": company_research.get("key_initiatives", []),
            "competitors": company_research.get("competitors", []),
            "challenges": company_research.get("challenges", []),
            "growth_areas": company_research.get("growth_areas", []),
            "tech_stack": company.get("technologies", []),
        }

        # Step 3: Research interviewers
        self._stage = "researching_interviewers"

        interviewer_profiles = []
        if include_interviewer_research and interviewers:
            for interviewer in interviewers:
                interviewer_name = interviewer.get("name")
                interviewer_title = interviewer.get("title")
                interviewer_linkedin = interviewer.get("linkedin_url")

                if not interviewer_name:
                    continue

                workflow.logger.info(f"Researching interviewer: {interviewer_name}")

                try:
                    profile = await workflow.execute_activity(
                        research_interviewer,
                        args=[interviewer_name, company_name, interviewer_linkedin],
                        start_to_close_timeout=timedelta(minutes=2),
                        retry_policy=retry_policy,
                    )

                    if profile:
                        interviewer_profiles.append({
                            "name": interviewer_name,
                            "title": interviewer_title or profile.get("title"),
                            "linkedin_url": interviewer_linkedin or profile.get("linkedin_url"),
                            "background": profile.get("background"),
                            "expertise": profile.get("expertise", []),
                            "interests": profile.get("interests", []),
                            "tenure_at_company": profile.get("tenure"),
                            "previous_companies": profile.get("previous_companies", []),
                            "education": profile.get("education"),
                            "likely_focus_areas": profile.get("likely_focus_areas", []),
                            "connection_points": profile.get("connection_points", []),
                        })
                        self._interviewers_researched += 1

                except Exception as e:
                    workflow.logger.warning(f"Interviewer research failed for {interviewer_name}: {e}")
                    # Add basic profile anyway
                    interviewer_profiles.append({
                        "name": interviewer_name,
                        "title": interviewer_title,
                        "linkedin_url": interviewer_linkedin,
                        "research_failed": True,
                    })

            workflow.logger.info(f"Researched {self._interviewers_researched} interviewers")

        # Step 4: Generate likely interview questions
        self._stage = "generating_questions"

        questions_context = {
            "job_title": job_title,
            "job_description": job_description,
            "job_requirements": job_requirements,
            "interview_type": interview_type,
            "interview_round": interview_round,
            "company_context": company_context,
            "interviewer_profiles": interviewer_profiles,
        }

        try:
            questions_result = await workflow.execute_activity(
                generate_interview_questions,
                args=[questions_context],
                start_to_close_timeout=timedelta(minutes=3),
                retry_policy=retry_policy,
            )

            suggested_questions = questions_result.get("questions", [])
            self._questions_generated = len(suggested_questions)

            workflow.logger.info(f"Generated {self._questions_generated} likely questions")

        except Exception as e:
            workflow.logger.error(f"Question generation failed: {e}")
            suggested_questions = []

        # Categorize questions by type
        questions_by_type = {
            "behavioral": [],
            "technical": [],
            "situational": [],
            "company_specific": [],
            "role_specific": [],
            "questions_to_ask": [],
        }

        for q in suggested_questions:
            q_type = q.get("type", "general")
            if q_type in questions_by_type:
                questions_by_type[q_type].append(q)
            else:
                questions_by_type["role_specific"].append(q)

        # Step 5: Generate talking points
        self._stage = "generating_talking_points"

        try:
            talking_points_result = await workflow.execute_activity(
                generate_talking_points,
                args=[job, company_context, interviewer_profiles, suggested_questions],
                start_to_close_timeout=timedelta(minutes=3),
                retry_policy=retry_policy,
            )

            talking_points = talking_points_result.get("talking_points", [])

            workflow.logger.info(f"Generated {len(talking_points)} talking points")

        except Exception as e:
            workflow.logger.warning(f"Talking points generation failed: {e}")
            talking_points = []

        # Step 6: Create comprehensive prep document
        self._stage = "creating_prep_document"

        prep_data = {
            "interview_id": interview_id,
            "job_title": job_title,
            "company_name": company_name,
            "interview_type": interview_type,
            "interview_round": interview_round,
            "scheduled_at": scheduled_at,
            "company_context": company_context,
            "interviewer_profiles": interviewer_profiles,
            "suggested_questions": suggested_questions,
            "questions_by_type": questions_by_type,
            "talking_points": talking_points,
        }

        try:
            prep_document = await workflow.execute_activity(
                generate_prep_document,
                args=[prep_data],
                start_to_close_timeout=timedelta(minutes=2),
                retry_policy=retry_policy,
            )

            workflow.logger.info("Prep document generated")

        except Exception as e:
            workflow.logger.error(f"Prep document generation failed: {e}")
            prep_document = None

        # Save prep to database
        prep_id = await workflow.execute_activity(
            save_interview_prep,
            args=[interview_id, prep_data, prep_document],
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=retry_policy,
        )

        # Update interview status
        await workflow.execute_activity(
            update_interview_status,
            args=[interview_id, "prep_complete", {"prep_id": prep_id}],
            start_to_close_timeout=timedelta(seconds=30),
        )

        # Log completion
        await workflow.execute_activity(
            log_job_event,
            args=[
                job.get("id"),
                "interview_prep_complete",
                {
                    "interview_id": interview_id,
                    "prep_id": prep_id,
                    "questions_count": self._questions_generated,
                    "interviewers_researched": self._interviewers_researched,
                },
            ],
            start_to_close_timeout=timedelta(seconds=10),
        )

        # Notify user that prep is ready
        await workflow.execute_activity(
            notify_user,
            args=[
                "interview_prep_ready",
                {
                    "job_title": job_title,
                    "company_name": company_name,
                    "interview_type": interview_type,
                    "scheduled_at": scheduled_at,
                    "prep_id": prep_id,
                    "questions_count": self._questions_generated,
                },
            ],
            start_to_close_timeout=timedelta(seconds=30),
        )

        self._stage = "complete"

        workflow.logger.info(f"Interview prep complete: {prep_id}")

        return {
            "interview_id": interview_id,
            "success": True,
            "workflow_run_id": workflow_run_id,
            "prep_id": prep_id,
            "job_title": job_title,
            "company_name": company_name,
            "interview_type": interview_type,
            "interview_round": interview_round,
            "scheduled_at": scheduled_at,
            "company_context": {
                "recent_news_count": len(company_context.get("recent_news", [])),
                "key_initiatives_count": len(company_context.get("key_initiatives", [])),
                "has_culture_info": bool(company_context.get("values") or company_context.get("culture_keywords")),
            },
            "interviewer_profiles": [
                {
                    "name": p.get("name"),
                    "title": p.get("title"),
                    "researched": not p.get("research_failed", False),
                }
                for p in interviewer_profiles
            ],
            "suggested_questions": suggested_questions[:10],  # Return top 10 in summary
            "questions_count": self._questions_generated,
            "questions_by_type_counts": {
                k: len(v) for k, v in questions_by_type.items()
            },
            "talking_points_count": len(talking_points),
            "prep_document": prep_document,
        }
