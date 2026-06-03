"""
ApplicationWorkflow

Full application workflow that generates materials, waits for approval,
sends the application, and schedules follow-ups.
"""

import asyncio
import logging
from datetime import timedelta
from typing import Optional

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from activities import (
        get_job_with_company,
        get_user_profile,
        get_best_contact,
        generate_cover_letter,
        tailor_resume_bullets,
        generate_outreach_email,
        save_application_draft,
        update_application_status,
        send_application_email,
        create_application_record,
        log_job_event,
        notify_user,
    )
    from workflows.follow_up import FollowUpWorkflow

log = logging.getLogger(__name__)


@workflow.defn
class ApplicationWorkflow:
    """
    Workflow for applying to a job with generated materials.

    Steps:
    1. Get job and company data
    2. Generate cover letter
    3. Optionally tailor resume bullets
    4. Find best contact (recruiter/hiring manager)
    5. Generate outreach email
    6. WAIT for user approval (workflow signal)
    7. Send email
    8. Create application record
    9. Spawn follow-up workflow
    """

    def __init__(self):
        self._draft = None
        self._approval_received = False
        self._approved = False
        self._edits = None
        self._cancelled = False
        self._stage = "initializing"
        self._application_id = None

    @workflow.signal
    async def approve_send(self, approved: bool, edits: Optional[dict] = None):
        """
        User approves or rejects the application.

        Args:
            approved: Whether to proceed with sending
            edits: Optional dictionary with edited fields (subject, body, etc.)
        """
        self._approval_received = True
        self._approved = approved
        self._edits = edits
        if approved:
            workflow.logger.info("Application approved by user")
        else:
            workflow.logger.info("Application rejected by user")

    @workflow.signal
    async def cancel_application(self):
        """Cancel the application workflow entirely."""
        self._cancelled = True
        workflow.logger.info("Application cancelled by user")

    @workflow.query
    def get_draft(self) -> dict:
        """Return current draft for review."""
        return {
            "draft": self._draft,
            "stage": self._stage,
            "approval_received": self._approval_received,
            "approved": self._approved,
            "application_id": self._application_id,
        }

    @workflow.query
    def get_status(self) -> dict:
        """Get current workflow status."""
        return {
            "stage": self._stage,
            "approval_received": self._approval_received,
            "approved": self._approved,
            "cancelled": self._cancelled,
            "application_id": self._application_id,
        }

    @workflow.run
    async def run(
        self,
        job_id: str,
        method: str = "email",
        include_cover_letter: bool = True,
        tailor_resume: bool = False,
        auto_send: bool = False,
    ) -> dict:
        """
        Execute the application workflow.

        Args:
            job_id: The job to apply to
            method: Application method ("email", "linkedin", "portal")
            include_cover_letter: Whether to generate a cover letter
            tailor_resume: Whether to tailor resume bullets
            auto_send: Skip approval and send immediately (use with caution)

        Returns:
            Application result with application_id and email status
        """
        workflow.logger.info(f"Starting application workflow for job {job_id}, method={method}")

        workflow_run_id = workflow.info().run_id

        retry_policy = RetryPolicy(
            initial_interval=timedelta(seconds=2),
            maximum_interval=timedelta(minutes=5),
            maximum_attempts=3,
        )

        # Step 1: Get job and company data
        self._stage = "loading_data"

        job_data = await workflow.execute_activity(
            get_job_with_company,
            args=[job_id],
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=retry_policy,
        )

        if not job_data or not job_data.get("job"):
            workflow.logger.error(f"Job {job_id} not found")
            return {
                "job_id": job_id,
                "success": False,
                "error": "Job not found",
            }

        job = job_data["job"]
        company = job_data.get("company", {})

        job_title = job.get("title", "")
        company_name = job.get("company_name", "") or company.get("name", "")

        workflow.logger.info(f"Applying to: {job_title} at {company_name}")

        # Get user profile for personalization
        user_profile = await workflow.execute_activity(
            get_user_profile,
            args=[],
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=retry_policy,
        )

        if not user_profile:
            workflow.logger.error("User profile not found")
            return {
                "job_id": job_id,
                "success": False,
                "error": "User profile not configured",
            }

        # Step 2: Generate cover letter (if requested)
        self._stage = "generating_cover_letter"

        cover_letter = None
        if include_cover_letter:
            try:
                cover_letter_result = await workflow.execute_activity(
                    generate_cover_letter,
                    args=[job, company, user_profile],
                    start_to_close_timeout=timedelta(minutes=3),
                    retry_policy=retry_policy,
                )
                cover_letter = cover_letter_result.get("cover_letter")
                workflow.logger.info("Cover letter generated")
            except Exception as e:
                workflow.logger.warning(f"Cover letter generation failed: {e}")

        # Step 3: Tailor resume bullets (if requested)
        self._stage = "tailoring_resume"

        tailored_bullets = None
        if tailor_resume:
            try:
                resume_result = await workflow.execute_activity(
                    tailor_resume_bullets,
                    args=[job, user_profile],
                    start_to_close_timeout=timedelta(minutes=2),
                    retry_policy=retry_policy,
                )
                tailored_bullets = resume_result.get("bullets")
                workflow.logger.info(f"Tailored {len(tailored_bullets or [])} resume bullets")
            except Exception as e:
                workflow.logger.warning(f"Resume tailoring failed: {e}")

        # Step 4: Find best contact
        self._stage = "finding_contact"

        contact = None
        if method == "email":
            try:
                contact = await workflow.execute_activity(
                    get_best_contact,
                    args=[job_id, job.get("company_id")],
                    start_to_close_timeout=timedelta(seconds=30),
                    retry_policy=retry_policy,
                )
                if contact:
                    workflow.logger.info(
                        f"Found contact: {contact.get('name')} ({contact.get('title')})"
                    )
            except Exception as e:
                workflow.logger.warning(f"Contact lookup failed: {e}")

        # Step 5: Generate outreach email
        self._stage = "generating_email"

        email_result = await workflow.execute_activity(
            generate_outreach_email,
            args=[job, company, user_profile, contact, cover_letter],
            start_to_close_timeout=timedelta(minutes=3),
            retry_policy=retry_policy,
        )

        if not email_result.get("subject") or not email_result.get("body"):
            workflow.logger.error("Email generation failed")
            return {
                "job_id": job_id,
                "success": False,
                "error": "Email generation failed",
            }

        # Build draft for review
        self._draft = {
            "job_id": job_id,
            "job_title": job_title,
            "company_name": company_name,
            "method": method,
            "contact": {
                "name": contact.get("name") if contact else None,
                "email": contact.get("email") if contact else None,
                "title": contact.get("title") if contact else None,
            } if contact else None,
            "email": {
                "to": contact.get("email") if contact else job.get("application_email"),
                "subject": email_result.get("subject"),
                "body": email_result.get("body"),
                "body_html": email_result.get("body_html"),
            },
            "cover_letter": cover_letter,
            "tailored_bullets": tailored_bullets,
            "generated_at": workflow.now().isoformat(),
        }

        # Save draft to database
        draft_id = await workflow.execute_activity(
            save_application_draft,
            args=[job_id, self._draft],
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=retry_policy,
        )

        self._draft["draft_id"] = draft_id

        workflow.logger.info(f"Application draft saved: {draft_id}")

        # Log draft generation event
        await workflow.execute_activity(
            log_job_event,
            args=[
                job_id,
                "application_draft_created",
                {
                    "draft_id": draft_id,
                    "has_cover_letter": cover_letter is not None,
                    "has_tailored_resume": tailored_bullets is not None,
                    "has_contact": contact is not None,
                },
            ],
            start_to_close_timeout=timedelta(seconds=10),
        )

        # Notify user that draft is ready for review
        await workflow.execute_activity(
            notify_user,
            args=[
                "application_ready",
                {
                    "job_title": job_title,
                    "company_name": company_name,
                    "workflow_id": workflow.info().workflow_id,
                    "draft_id": draft_id,
                },
            ],
            start_to_close_timeout=timedelta(seconds=30),
        )

        # Step 6: Wait for user approval (unless auto_send)
        self._stage = "awaiting_approval"

        if not auto_send:
            workflow.logger.info("Waiting for user approval...")

            # Wait for approval signal (with 7-day timeout). A timeout raises
            # asyncio.TimeoutError; let other exceptions (e.g. cancellation) propagate.
            try:
                await workflow.wait_condition(
                    lambda: self._approval_received or self._cancelled,
                    timeout=timedelta(days=7),
                )
            except asyncio.TimeoutError:
                workflow.logger.warning("Approval timeout - application expired")
                await workflow.execute_activity(
                    update_application_status,
                    args=[draft_id, "expired", "Approval timeout after 7 days"],
                    start_to_close_timeout=timedelta(seconds=30),
                )
                return {
                    "job_id": job_id,
                    "success": False,
                    "error": "Approval timeout",
                    "draft_id": draft_id,
                }

            if self._cancelled:
                await workflow.execute_activity(
                    update_application_status,
                    args=[draft_id, "cancelled", "Cancelled by user"],
                    start_to_close_timeout=timedelta(seconds=30),
                )
                return {
                    "job_id": job_id,
                    "success": False,
                    "cancelled": True,
                    "draft_id": draft_id,
                }

            if not self._approved:
                await workflow.execute_activity(
                    update_application_status,
                    args=[draft_id, "rejected", "Rejected by user"],
                    start_to_close_timeout=timedelta(seconds=30),
                )
                return {
                    "job_id": job_id,
                    "success": False,
                    "rejected": True,
                    "draft_id": draft_id,
                }

        # Apply any user edits
        if self._edits:
            if self._edits.get("subject"):
                self._draft["email"]["subject"] = self._edits["subject"]
            if self._edits.get("body"):
                self._draft["email"]["body"] = self._edits["body"]
            if self._edits.get("to"):
                self._draft["email"]["to"] = self._edits["to"]
            workflow.logger.info("Applied user edits to draft")

        # Step 7: Send email
        self._stage = "sending"

        recipient_email = self._draft["email"]["to"]

        if not recipient_email:
            workflow.logger.error("No recipient email address")
            await workflow.execute_activity(
                update_application_status,
                args=[draft_id, "failed", "No recipient email address"],
                start_to_close_timeout=timedelta(seconds=30),
            )
            return {
                "job_id": job_id,
                "success": False,
                "error": "No recipient email address",
                "draft_id": draft_id,
            }

        try:
            recipient_name = (contact.get("name") if contact else None) or recipient_email
            send_result = await workflow.execute_activity(
                send_application_email,
                args=[
                    recipient_email,
                    recipient_name,
                    self._draft["email"]["subject"],
                    self._draft["email"]["body"],
                    self._draft["email"].get("body_html"),
                    job_id,
                ],
                start_to_close_timeout=timedelta(minutes=2),
                retry_policy=RetryPolicy(
                    maximum_attempts=2,
                    initial_interval=timedelta(seconds=5),
                ),
            )

            if not send_result.get("success"):
                raise Exception(send_result.get("error", "Send failed"))

            message_id = send_result.get("message_id")
            workflow.logger.info(f"Email sent successfully: {message_id}")

        except Exception as e:
            workflow.logger.error(f"Email send failed: {e}")
            await workflow.execute_activity(
                update_application_status,
                args=[draft_id, "send_failed", str(e)],
                start_to_close_timeout=timedelta(seconds=30),
            )
            return {
                "job_id": job_id,
                "success": False,
                "error": f"Email send failed: {str(e)}",
                "draft_id": draft_id,
            }

        # Step 8: Create application record
        self._stage = "recording"

        application_data = {
            "job_id": job_id,
            "company_id": job.get("company_id"),
            "method": method,
            "status": "applied",
            "applied_at": workflow.now().isoformat(),
            "contact_id": contact.get("id") if contact else None,
            "email_message_id": message_id,
            "email_subject": self._draft["email"]["subject"],
            "email_sent_to": recipient_email,
            "has_cover_letter": cover_letter is not None,
            "draft_id": draft_id,
        }

        self._application_id = await workflow.execute_activity(
            create_application_record,
            args=[application_data],
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=retry_policy,
        )

        workflow.logger.info(f"Application record created: {self._application_id}")

        # Log application event
        await workflow.execute_activity(
            log_job_event,
            args=[
                job_id,
                "applied",
                {
                    "application_id": self._application_id,
                    "method": method,
                    "sent_to": recipient_email,
                    "message_id": message_id,
                },
            ],
            start_to_close_timeout=timedelta(seconds=10),
        )

        # Step 9: Spawn follow-up workflow
        self._stage = "scheduling_followup"

        try:
            followup_handle = await workflow.start_child_workflow(
                FollowUpWorkflow.run,
                args=[self._application_id],
                id=f"followup-{self._application_id}",
                task_queue="jobhunt-worker",
            )
            workflow.logger.info(
                f"Follow-up workflow scheduled: {followup_handle.id}"
            )
        except Exception as e:
            workflow.logger.warning(f"Failed to schedule follow-up workflow: {e}")
            # Non-fatal - application was still successful

        self._stage = "complete"

        workflow.logger.info(f"Application workflow complete for job {job_id}")

        return {
            "job_id": job_id,
            "success": True,
            "application_id": self._application_id,
            "draft_id": draft_id,
            "email_sent": True,
            "message_id": message_id,
            "sent_to": recipient_email,
            "method": method,
            "workflow_run_id": workflow_run_id,
        }
