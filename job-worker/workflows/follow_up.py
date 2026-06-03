"""
FollowUpWorkflow

Automated follow-up sequence for job applications.
Uses durable timers to send follow-ups at strategic intervals.
Automatically stops when a reply is received.
"""

import logging
from datetime import timedelta
from typing import Optional

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from activities import (
        get_application,
        get_job,
        check_application_replied,
        check_job_still_active,
        generate_follow_up_email,
        send_follow_up_email,
        update_application_status,
        update_follow_up_record,
        log_job_event,
        notify_user,
    )

log = logging.getLogger(__name__)


# Default follow-up cadence
FOLLOW_UP_CADENCE = [
    {
        "step": 1,
        "wait_days": 5,
        "type": "gentle_bump",
        "description": "First follow-up - gentle check-in",
    },
    {
        "step": 2,
        "wait_days": 7,  # 12 days total from application
        "type": "value_add",
        "description": "Second follow-up - add value/different angle",
    },
    {
        "step": 3,
        "wait_days": 9,  # 21 days total from application
        "type": "graceful_close",
        "description": "Final check-in - graceful close",
    },
]


@workflow.defn
class FollowUpWorkflow:
    """
    Workflow for handling follow-up sequence for an application.

    Follow-up sequence:
    - Day 0: Initial application sent (by ApplicationWorkflow)
    - Day 5: First follow-up (if no reply)
    - Day 12: Second follow-up (different angle)
    - Day 21: Final check-in (graceful close)

    For each step:
    1. Wait for timer
    2. Check if job still active
    3. Check if already replied
    4. Generate follow-up email
    5. Send and record

    Stops if:
    - Reply received (positive or rejection)
    - Job no longer posted
    - User manually stops
    """

    def __init__(self):
        self._current_step = 0
        self._stopped = False
        self._reply_received = False
        self._reply_data = None
        self._completed = False

    @workflow.signal
    async def reply_received(self, reply_data: dict):
        """
        Signal that a reply was received.

        Args:
            reply_data: Information about the reply (sentiment, content preview, etc.)
        """
        self._reply_received = True
        self._reply_data = reply_data
        workflow.logger.info(
            f"Reply received signal: sentiment={reply_data.get('sentiment', 'unknown')}"
        )

    @workflow.signal
    async def stop_sequence(self):
        """User wants to stop follow-ups."""
        self._stopped = True
        workflow.logger.info("Stop sequence signal received")

    @workflow.signal
    async def pause_sequence(self):
        """Pause the sequence temporarily."""
        self._stopped = True
        workflow.logger.info("Sequence paused")

    @workflow.signal
    async def resume_sequence(self):
        """Resume a paused sequence."""
        self._stopped = False
        workflow.logger.info("Sequence resumed")

    @workflow.query
    def get_status(self) -> dict:
        """Query current follow-up status."""
        return {
            "current_step": self._current_step,
            "stopped": self._stopped,
            "reply_received": self._reply_received,
            "reply_data": self._reply_data,
            "completed": self._completed,
        }

    @workflow.run
    async def run(
        self,
        application_id: str,
        custom_cadence: Optional[list] = None,
        start_delay_days: int = 0,
    ) -> dict:
        """
        Execute the follow-up workflow.

        Args:
            application_id: The application to follow up on
            custom_cadence: Optional custom follow-up schedule
            start_delay_days: Initial delay before first follow-up check

        Returns:
            Follow-up results with emails sent and outcome
        """
        workflow.logger.info(f"Starting follow-up workflow for application {application_id}")

        workflow_run_id = workflow.info().run_id

        retry_policy = RetryPolicy(
            initial_interval=timedelta(seconds=2),
            maximum_interval=timedelta(minutes=5),
            maximum_attempts=3,
        )

        # Get application data
        application = await workflow.execute_activity(
            get_application,
            args=[application_id],
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=retry_policy,
        )

        if not application:
            workflow.logger.error(f"Application {application_id} not found")
            return {
                "application_id": application_id,
                "success": False,
                "error": "Application not found",
            }

        job_id = application.get("job_id")
        job = await workflow.execute_activity(
            get_job,
            args=[job_id],
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=retry_policy,
        )

        if not job:
            workflow.logger.warning(f"Job {job_id} not found, but continuing with follow-ups")

        job_title = job.get("title", "the position") if job else "the position"
        company_name = job.get("company_name", "the company") if job else "the company"

        # Use custom cadence or default
        cadence = custom_cadence or FOLLOW_UP_CADENCE

        workflow.logger.info(
            f"Follow-up cadence: {len(cadence)} steps for {job_title} at {company_name}"
        )

        follow_ups_sent = []
        final_outcome = "completed"

        # Initial delay if specified
        if start_delay_days > 0:
            workflow.logger.info(f"Initial delay: waiting {start_delay_days} days")
            await workflow.sleep(timedelta(days=start_delay_days))

        # Execute follow-up sequence
        for step_config in cadence:
            step_num = step_config["step"]
            wait_days = step_config["wait_days"]
            follow_up_type = step_config["type"]

            self._current_step = step_num
            workflow.logger.info(f"Processing follow-up step {step_num}: {follow_up_type}")

            # Wait for the specified interval (durable timer)
            if wait_days > 0:
                workflow.logger.info(f"Waiting {wait_days} days before step {step_num}")
                await workflow.sleep(timedelta(days=wait_days))

            # Check stop conditions after wait
            if self._stopped:
                workflow.logger.info("Follow-up sequence stopped by user")
                final_outcome = "stopped"
                break

            if self._reply_received:
                workflow.logger.info("Reply received, ending follow-up sequence")
                final_outcome = "replied"

                # Notify user about the reply
                await workflow.execute_activity(
                    notify_user,
                    args=[
                        "application_reply_received",
                        {
                            "job_title": job_title,
                            "company_name": company_name,
                            "application_id": application_id,
                            "reply_data": self._reply_data,
                        },
                    ],
                    start_to_close_timeout=timedelta(seconds=30),
                )
                break

            # Check database for reply (in case signal was missed)
            has_replied = await workflow.execute_activity(
                check_application_replied,
                args=[application_id],
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=retry_policy,
            )

            if has_replied:
                workflow.logger.info("Application has reply (from DB check), ending sequence")
                final_outcome = "replied"
                break

            # Check if job is still active/posted
            if job_id:
                job_active = await workflow.execute_activity(
                    check_job_still_active,
                    args=[job_id],
                    start_to_close_timeout=timedelta(seconds=30),
                    retry_policy=retry_policy,
                )

                if not job_active:
                    workflow.logger.info("Job no longer active, ending follow-up sequence")
                    final_outcome = "job_closed"

                    # Update application status
                    await workflow.execute_activity(
                        update_application_status,
                        args=[application_id, "job_closed", "Position appears to be filled/closed"],
                        start_to_close_timeout=timedelta(seconds=30),
                    )
                    break

            # Generate follow-up email
            try:
                email_result = await workflow.execute_activity(
                    generate_follow_up_email,
                    args=[application_id, step_num, follow_up_type],
                    start_to_close_timeout=timedelta(minutes=2),
                    retry_policy=retry_policy,
                )

                if not email_result.get("subject") or not email_result.get("body"):
                    workflow.logger.warning(f"Follow-up email generation failed for step {step_num}")
                    continue

            except Exception as e:
                workflow.logger.error(f"Follow-up generation failed: {e}")
                continue

            # Send follow-up email
            try:
                send_result = await workflow.execute_activity(
                    send_follow_up_email,
                    args=[
                        application_id,
                        email_result.get("to"),
                        email_result.get("subject"),
                        email_result.get("body"),
                        email_result.get("body_html"),
                        email_result.get("thread_id"),  # For threading with original
                    ],
                    start_to_close_timeout=timedelta(minutes=2),
                    retry_policy=RetryPolicy(
                        maximum_attempts=2,
                        initial_interval=timedelta(seconds=5),
                    ),
                )

                if send_result.get("success"):
                    follow_up_record = {
                        "step": step_num,
                        "type": follow_up_type,
                        "message_id": send_result.get("message_id"),
                        "sent_at": workflow.now().isoformat(),
                        "sent_to": email_result.get("to"),
                    }
                    follow_ups_sent.append(follow_up_record)

                    workflow.logger.info(f"Follow-up {step_num} sent successfully")

                    # Record in database
                    await workflow.execute_activity(
                        update_follow_up_record,
                        args=[application_id, follow_up_record],
                        start_to_close_timeout=timedelta(seconds=30),
                    )

                    # Log event
                    await workflow.execute_activity(
                        log_job_event,
                        args=[
                            job_id,
                            f"follow_up_{step_num}_sent",
                            {
                                "application_id": application_id,
                                "follow_up_type": follow_up_type,
                                "message_id": send_result.get("message_id"),
                            },
                        ],
                        start_to_close_timeout=timedelta(seconds=10),
                    )
                else:
                    workflow.logger.warning(
                        f"Follow-up {step_num} send failed: {send_result.get('error')}"
                    )

            except Exception as e:
                workflow.logger.error(f"Follow-up send failed: {e}")
                continue

        # Update application with final follow-up status
        self._completed = True

        status_map = {
            "completed": "follow_ups_complete",
            "replied": "replied",
            "stopped": "follow_ups_stopped",
            "job_closed": "job_closed",
        }
        new_status = status_map.get(final_outcome, "follow_ups_complete")

        await workflow.execute_activity(
            update_application_status,
            args=[
                application_id,
                new_status,
                f"Follow-up sequence {final_outcome}: {len(follow_ups_sent)} emails sent",
            ],
            start_to_close_timeout=timedelta(seconds=30),
        )

        # Log completion event
        await workflow.execute_activity(
            log_job_event,
            args=[
                job_id,
                "follow_up_sequence_complete",
                {
                    "application_id": application_id,
                    "outcome": final_outcome,
                    "follow_ups_sent": len(follow_ups_sent),
                    "final_step": self._current_step,
                },
            ],
            start_to_close_timeout=timedelta(seconds=10),
        )

        workflow.logger.info(
            f"Follow-up workflow complete: {final_outcome}, {len(follow_ups_sent)} emails sent"
        )

        return {
            "application_id": application_id,
            "success": True,
            "workflow_run_id": workflow_run_id,
            "outcome": final_outcome,
            "follow_ups_sent": follow_ups_sent,
            "total_follow_ups": len(follow_ups_sent),
            "final_step": self._current_step,
            "reply_received": self._reply_received,
            "reply_data": self._reply_data,
        }
