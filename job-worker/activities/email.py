"""
Email Activities for JobHunt Outreach.

Temporal activities for:
- Sending outreach emails to hiring managers/recruiters
- Checking for replies
- Classifying reply sentiment
- Scheduling follow-up emails
"""

import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import asyncpg
import httpx
from temporalio import activity

from clients.gmail import (
    GmailClient,
    GmailClientError,
    GmailMessage,
    TokenExpiredError,
    TokenRevokedError,
    RateLimitError,
    get_valid_access_token,
    get_stored_credentials,
)
from utils.email_templates import (
    render_template,
    INITIAL_OUTREACH_TEMPLATE,
    FOLLOW_UP_TEMPLATE,
    THANK_YOU_TEMPLATE,
)

from utils.llm import extract_json
from utils.llm_config import LLM_API_KEY, LLM_BASE_URL, LLM_LIGHT_MODEL
from utils.profile import candidate, candidate_name

log = logging.getLogger(__name__)

# Configuration
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://jobhunt:jobhunt_secret@localhost:5433/jobhunt_db"
)
# LLM config is centralized in utils.llm_config (provider-agnostic).
XAI_API_KEY = LLM_API_KEY
XAI_API_BASE = LLM_BASE_URL


def _sender_info_block() -> str:
    """Render the sender's identity from the candidate profile for LLM prompts."""
    c = candidate()
    lines = [c.get("name", ""), c.get("headline", ""), c.get("phone", ""), c.get("linkedin", "")]
    return "\n".join(line for line in lines if line)


# =============================================================================
# Database Connection
# =============================================================================


async def get_connection() -> asyncpg.Connection:
    """Get a database connection."""
    return await asyncpg.connect(DATABASE_URL)


# =============================================================================
# Email Sending Activity
# =============================================================================


@activity.defn
async def send_outreach_email(
    to_email: str,
    to_name: str,
    subject: str,
    body: str,
    job_id: str,
    email_type: str,  # 'initial', 'follow_up', 'thank_you'
    html_body: Optional[str] = None,
    in_reply_to: Optional[str] = None,
    thread_id: Optional[str] = None,
) -> dict:
    """
    Send outreach email and record in database.

    Args:
        to_email: Recipient email address
        to_name: Recipient name (for personalization)
        subject: Email subject line
        body: Plain text email body
        job_id: Associated job ID for tracking
        email_type: Type of email (initial, follow_up, thank_you)
        html_body: Optional HTML version of body
        in_reply_to: Message-ID for threading
        thread_id: Gmail thread ID for replies

    Returns:
        Dict with email_id, message_id, thread_id, sent_at
    """
    log.info(f"Sending {email_type} email to {to_email} for job {job_id}")

    conn = await get_connection()
    try:
        # Get valid access token
        token_result = await get_valid_access_token(conn)
        if not token_result:
            log.error("No valid Gmail credentials available")
            return {
                "success": False,
                "error": "No Gmail account connected. Please authorize Gmail access.",
                "action_required": "connect_gmail",
            }

        access_token, from_email = token_result

        # Generate tracking ID
        tracking_id = str(uuid.uuid4())

        # Get sender display name
        creds = await get_stored_credentials(conn)
        from_name = creds.get("display_name") if creds else None
        from_name = from_name or candidate_name()

        # Send via Gmail API
        client = GmailClient()
        try:
            result = await client.send_email(
                access_token=access_token,
                to=to_email,
                subject=subject,
                body_text=body,
                body_html=html_body,
                from_name=from_name,
                from_email=from_email,
                thread_id=thread_id,
                tracking_id=tracking_id,
                in_reply_to=in_reply_to,
            )

            # Record in database
            email_id = await _record_sent_email(
                conn=conn,
                job_id=job_id,
                to_email=to_email,
                to_name=to_name,
                subject=subject,
                body_text=body,
                body_html=html_body,
                email_type=email_type,
                tracking_id=tracking_id,
                gmail_message_id=result["message_id"],
                gmail_thread_id=result["thread_id"],
                sent_at=result["sent_at"],
            )

            log.info(f"Email sent successfully: {email_id}")

            return {
                "success": True,
                "email_id": email_id,
                "message_id": result["message_id"],
                "thread_id": result["thread_id"],
                "sent_at": result["sent_at"].isoformat(),
            }

        except TokenExpiredError:
            log.error("Access token expired during send")
            return {
                "success": False,
                "error": "Gmail token expired. Please re-authorize.",
                "action_required": "reauthorize_gmail",
            }

        except TokenRevokedError:
            log.error("Gmail access revoked")
            return {
                "success": False,
                "error": "Gmail access was revoked. Please reconnect your account.",
                "action_required": "connect_gmail",
            }

        except RateLimitError:
            log.warning("Gmail rate limit hit")
            return {
                "success": False,
                "error": "Gmail rate limit exceeded. Please try again later.",
                "retry_after_seconds": 60,
            }

        except GmailClientError as e:
            log.error(f"Gmail API error: {e}")
            return {
                "success": False,
                "error": str(e),
            }

    finally:
        await conn.close()


async def _record_sent_email(
    conn: asyncpg.Connection,
    job_id: str,
    to_email: str,
    to_name: str,
    subject: str,
    body_text: str,
    body_html: Optional[str],
    email_type: str,
    tracking_id: str,
    gmail_message_id: str,
    gmail_thread_id: Optional[str],
    sent_at: datetime,
) -> str:
    """Record sent email in the database."""
    row = await conn.fetchrow("""
        INSERT INTO outreach_emails (
            job_id,
            recipient_email,
            to_name,
            subject,
            body,
            body_html,
            email_type,
            tracking_id,
            gmail_message_id,
            gmail_thread_id,
            sent_at,
            status
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, 'sent')
        RETURNING id
    """,
        uuid.UUID(job_id),
        to_email,
        to_name,
        subject,
        body_text,
        body_html,
        email_type,
        tracking_id,
        gmail_message_id,
        gmail_thread_id,
        sent_at,
    )

    return str(row["id"])


# =============================================================================
# Reply Checking Activity
# =============================================================================


@activity.defn
async def check_for_replies(since_hours: int = 24) -> list[dict]:
    """
    Poll Gmail for new replies to sent emails.

    Matches replies to sent emails via:
    - X-Jobhunt-Email-ID header
    - In-Reply-To message ID
    - Sender email lookup

    Args:
        since_hours: Only check messages from the last N hours

    Returns:
        List of replies with matched job_id and email details
    """
    log.info(f"Checking for replies in the last {since_hours} hours")

    conn = await get_connection()
    try:
        # Get valid access token
        token_result = await get_valid_access_token(conn)
        if not token_result:
            log.warning("No valid Gmail credentials for reply checking")
            return []

        access_token, _ = token_result

        # Calculate since time
        since = datetime.now(timezone.utc) - timedelta(hours=since_hours)

        # Get recent inbox messages
        client = GmailClient()
        messages = await client.check_inbox(
            access_token=access_token,
            since=since,
            max_results=50,
            label_ids=["INBOX"],
        )

        if not messages:
            log.info("No new messages found")
            return []

        log.info(f"Found {len(messages)} messages to check")

        # Process each message
        replies = []
        for msg_stub in messages:
            try:
                # Get full message
                message = await client.get_message(
                    access_token=access_token,
                    message_id=msg_stub["id"],
                )

                # Try to match to a sent email
                match = await _match_reply_to_email(conn, message)
                if match:
                    replies.append({
                        "message_id": message.message_id,
                        "thread_id": message.thread_id,
                        "from_email": message.from_email,
                        "from_name": message.from_name,
                        "subject": message.subject,
                        "body_text": message.body_text,
                        "received_at": message.internal_date.isoformat() if message.internal_date else None,
                        "matched_email_id": match["email_id"],
                        "matched_job_id": match["job_id"],
                    })

            except Exception as e:
                log.warning(f"Error processing message {msg_stub['id']}: {e}")

        log.info(f"Found {len(replies)} replies to outreach emails")
        return replies

    except TokenExpiredError:
        log.error("Access token expired during reply check")
        return []

    except Exception as e:
        log.error(f"Error checking for replies: {e}")
        return []

    finally:
        await conn.close()


async def _match_reply_to_email(
    conn: asyncpg.Connection,
    message: GmailMessage,
) -> Optional[dict]:
    """
    Try to match an incoming message to a sent outreach email.

    Matching strategies (in order):
    1. Thread ID match
    2. In-Reply-To header matches our message ID
    3. Sender email matches a recipient we've emailed
    """
    # Strategy 1: Thread ID match
    if message.thread_id:
        row = await conn.fetchrow("""
            SELECT id as email_id, job_id
            FROM outreach_emails
            WHERE gmail_thread_id = $1
            ORDER BY sent_at DESC
            LIMIT 1
        """, message.thread_id)

        if row:
            return {"email_id": str(row["email_id"]), "job_id": str(row["job_id"])}

    # Strategy 2: In-Reply-To header match
    if message.in_reply_to:
        # Extract message ID from In-Reply-To
        in_reply_to = message.in_reply_to.strip("<>")
        row = await conn.fetchrow("""
            SELECT id as email_id, job_id
            FROM outreach_emails
            WHERE gmail_message_id = $1
            ORDER BY sent_at DESC
            LIMIT 1
        """, in_reply_to)

        if row:
            return {"email_id": str(row["email_id"]), "job_id": str(row["job_id"])}

    # Strategy 3: Sender email lookup
    if message.from_email:
        row = await conn.fetchrow("""
            SELECT id as email_id, job_id
            FROM outreach_emails
            WHERE recipient_email = $1
            ORDER BY sent_at DESC
            LIMIT 1
        """, message.from_email.lower())

        if row:
            return {"email_id": str(row["email_id"]), "job_id": str(row["job_id"])}

    return None


# =============================================================================
# Reply Classification Activity
# =============================================================================


@activity.defn
async def classify_reply(email_body: str, context: Optional[dict] = None) -> dict:
    """
    Use LLM to classify reply sentiment and extract key information.

    Categories:
    - positive: Interest in moving forward, scheduling interview
    - neutral: Questions, requests for more info
    - rejection: Not interested, position filled
    - request_info: Asking for resume, portfolio, etc.
    - auto_reply: Out of office, auto-responder

    Args:
        email_body: The reply email body text
        context: Optional context (job title, company, etc.)

    Returns:
        Dict with sentiment, summary, suggested_action, confidence
    """
    log.info("Classifying reply sentiment")

    if not XAI_API_KEY:
        log.warning("XAI_API_KEY not set, using basic classification")
        return _basic_classification(email_body)

    # Build context string
    context_str = ""
    if context:
        context_str = f"""
Context:
- Job Title: {context.get('job_title', 'Unknown')}
- Company: {context.get('company', 'Unknown')}
- Original Subject: {context.get('subject', 'Unknown')}
"""

    prompt = f"""Classify this email reply to a job application outreach.

{context_str}

Email Reply:
---
{email_body[:2000]}
---

Classify the sentiment and provide a brief summary.

Categories:
- positive: Shows interest, wants to proceed, scheduling discussion
- neutral: Has questions, asking for clarification
- rejection: Not interested, position filled, bad fit
- request_info: Asking for resume, portfolio, references
- auto_reply: Out of office, automatic response

Return JSON:
{{"sentiment": "category", "summary": "1-2 sentence summary", "suggested_action": "what to do next", "confidence": 0.0-1.0}}"""

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{XAI_API_BASE}/chat/completions",
                headers={
                    "Authorization": f"Bearer {XAI_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": LLM_LIGHT_MODEL,
                    "messages": [
                        {"role": "system", "content": "You classify email replies. Return only valid JSON."},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.3,
                    "max_tokens": 200,
                },
            )

            response.raise_for_status()
            data = response.json()

            content = data["choices"][0]["message"]["content"]

            # Parse JSON from the response (handles fenced/raw/embedded JSON).
            # Fall back to rule-based classification if nothing parses.
            result = extract_json(content)
            if not result:
                return _basic_classification(email_body)

            # Log LLM usage
            await _log_llm_call(
                model=LLM_LIGHT_MODEL,
                prompt_tokens=data.get("usage", {}).get("prompt_tokens", 0),
                completion_tokens=data.get("usage", {}).get("completion_tokens", 0),
                context_type="reply_classification",
            )

            return {
                "sentiment": result.get("sentiment", "neutral"),
                "summary": result.get("summary", ""),
                "suggested_action": result.get("suggested_action", ""),
                "confidence": result.get("confidence", 0.7),
            }

    except Exception as e:
        log.error(f"LLM classification failed: {e}")
        return _basic_classification(email_body)


def _basic_classification(email_body: str) -> dict:
    """Basic rule-based classification fallback."""
    body_lower = email_body.lower()

    # Auto-reply detection
    auto_reply_keywords = [
        "out of office", "automatic reply", "auto-reply",
        "away from", "on vacation", "limited access",
    ]
    if any(kw in body_lower for kw in auto_reply_keywords):
        return {
            "sentiment": "auto_reply",
            "summary": "Automatic out-of-office reply",
            "suggested_action": "Wait for return and follow up",
            "confidence": 0.9,
        }

    # Positive indicators
    positive_keywords = [
        "interested", "let's chat", "schedule", "calendar",
        "would love to", "sounds great", "excited",
    ]
    if any(kw in body_lower for kw in positive_keywords):
        return {
            "sentiment": "positive",
            "summary": "Shows interest in continuing conversation",
            "suggested_action": "Respond promptly to schedule next steps",
            "confidence": 0.6,
        }

    # Rejection indicators
    rejection_keywords = [
        "not interested", "position filled", "decided to go",
        "not a fit", "unfortunately", "moving forward with",
        "other candidates",
    ]
    if any(kw in body_lower for kw in rejection_keywords):
        return {
            "sentiment": "rejection",
            "summary": "Not moving forward with opportunity",
            "suggested_action": "Thank them and move on",
            "confidence": 0.7,
        }

    # Request for info
    info_keywords = [
        "resume", "portfolio", "references", "more information",
        "can you send", "attach",
    ]
    if any(kw in body_lower for kw in info_keywords):
        return {
            "sentiment": "request_info",
            "summary": "Requesting additional information",
            "suggested_action": "Send requested materials promptly",
            "confidence": 0.7,
        }

    # Default to neutral
    return {
        "sentiment": "neutral",
        "summary": "Reply received, needs review",
        "suggested_action": "Review and respond appropriately",
        "confidence": 0.5,
    }


async def _log_llm_call(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    context_type: str,
    context_id: Optional[str] = None,
) -> None:
    """Log an LLM API call via the shared telemetry helper (one cost source)."""
    from utils.llm_logging import log_llm_call

    await log_llm_call(
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        context_type=context_type,
        context_id=context_id,
    )


# =============================================================================
# Follow-up Scheduling Activity
# =============================================================================


@activity.defn
async def schedule_follow_up(
    job_id: str,
    days_delay: int,
    email_type: str = "follow_up",
    notes: Optional[str] = None,
) -> str:
    """
    Schedule a follow-up email for later.

    Args:
        job_id: Job ID to follow up on
        days_delay: Days to wait before sending
        email_type: Type of follow-up email
        notes: Optional notes about the follow-up

    Returns:
        Scheduled email ID
    """
    log.info(f"Scheduling {email_type} follow-up for job {job_id} in {days_delay} days")

    scheduled_at = datetime.now(timezone.utc) + timedelta(days=days_delay)

    conn = await get_connection()
    try:
        # Get job and application info
        job_info = await conn.fetchrow("""
            SELECT j.title, j.company_name, a.id as application_id
            FROM jobs j
            LEFT JOIN applications a ON a.job_id = j.id
            WHERE j.id = $1
        """, uuid.UUID(job_id))

        if not job_info:
            raise ValueError(f"Job not found: {job_id}")

        row = await conn.fetchrow("""
            INSERT INTO outreach_emails (
                job_id,
                email_type,
                status,
                scheduled_at,
                notes
            ) VALUES ($1, $2, 'scheduled', $3, $4)
            RETURNING id
        """,
            uuid.UUID(job_id),
            email_type,
            scheduled_at,
            notes,
        )

        email_id = str(row["id"])
        log.info(f"Scheduled follow-up {email_id} for {scheduled_at}")

        return email_id

    finally:
        await conn.close()


# =============================================================================
# Email Generation Activity
# =============================================================================


@activity.defn
async def generate_outreach_email(
    job_id: str,
    recipient_name: str,
    recipient_title: Optional[str] = None,
    email_type: str = "initial",
    custom_hook: Optional[str] = None,
) -> dict:
    """
    Generate personalized outreach email using LLM.

    Args:
        job_id: Job ID for context
        recipient_name: Name of recipient
        recipient_title: Title of recipient (optional)
        email_type: Type of email to generate
        custom_hook: Custom personalization hook (optional)

    Returns:
        Dict with subject and body
    """
    log.info(f"Generating {email_type} email for job {job_id}")

    conn = await get_connection()
    try:
        # Get job details
        job = await conn.fetchrow("""
            SELECT title, company_name, description, requirements, location
            FROM jobs
            WHERE id = $1
        """, uuid.UUID(job_id))

        if not job:
            raise ValueError(f"Job not found: {job_id}")

        # Get previous emails for context (for follow-ups)
        previous_emails = []
        if email_type != "initial":
            rows = await conn.fetch("""
                SELECT subject, body AS body_text, email_type, sent_at
                FROM outreach_emails
                WHERE job_id = $1 AND status = 'sent'
                ORDER BY sent_at ASC
            """, uuid.UUID(job_id))
            previous_emails = [dict(r) for r in rows]

        # Generate email
        if not XAI_API_KEY:
            # Use template fallback
            return _generate_from_template(
                job=dict(job),
                recipient_name=recipient_name,
                recipient_title=recipient_title,
                email_type=email_type,
                previous_emails=previous_emails,
            )

        return await _generate_with_llm(
            job=dict(job),
            recipient_name=recipient_name,
            recipient_title=recipient_title,
            email_type=email_type,
            previous_emails=previous_emails,
            custom_hook=custom_hook,
        )

    finally:
        await conn.close()


def _generate_from_template(
    job: dict,
    recipient_name: str,
    recipient_title: Optional[str],
    email_type: str,
    previous_emails: list[dict],
) -> dict:
    """Generate email from templates (fallback)."""
    first_name = recipient_name.split()[0] if recipient_name else "there"
    company = job.get("company_name", "your company")
    title = job.get("title", "the position")

    if email_type == "initial":
        return render_template(
            INITIAL_OUTREACH_TEMPLATE,
            first_name=first_name,
            company=company,
            job_title=title,
        )
    elif email_type == "follow_up":
        original_subject = previous_emails[0]["subject"] if previous_emails else title
        return render_template(
            FOLLOW_UP_TEMPLATE,
            first_name=first_name,
            original_subject=original_subject,
        )
    elif email_type == "thank_you":
        interviewer_name = first_name
        return render_template(
            THANK_YOU_TEMPLATE,
            interviewer_name=interviewer_name,
            job_title=title,
        )
    else:
        raise ValueError(f"Unknown email type: {email_type}")


async def _generate_with_llm(
    job: dict,
    recipient_name: str,
    recipient_title: Optional[str],
    email_type: str,
    previous_emails: list[dict],
    custom_hook: Optional[str],
) -> dict:
    """Generate email using LLM."""

    # Build context
    job_context = f"""
Job Title: {job.get('title', 'Unknown')}
Company: {job.get('company_name', 'Unknown')}
Location: {job.get('location', 'Not specified')}
Description: {job.get('description', '')[:500]}...
"""

    previous_context = ""
    if previous_emails:
        previous_context = "\n\nPrevious emails sent:\n"
        for email in previous_emails[-3:]:  # Last 3 emails
            previous_context += f"- [{email['email_type']}] {email['subject']}\n"

    hook_context = ""
    if custom_hook:
        hook_context = f"\n\nPersonalization hook to use: {custom_hook}"

    prompt = f"""Write a {email_type} email for a job application outreach.

Recipient: {recipient_name}{f' ({recipient_title})' if recipient_title else ''}

{job_context}
{previous_context}
{hook_context}

STYLE GUIDELINES:
- Sound like a real person, not a form letter
- Be confident but not arrogant
- Keep it brief (under 150 words)
- No generic phrases like "I hope this email finds you well"
- End with a clear, simple call to action

SENDER INFO:
{_sender_info_block()}

Return JSON:
{{"subject": "email subject", "body": "email body (no signature, it's added automatically)"}}"""

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{XAI_API_BASE}/chat/completions",
                headers={
                    "Authorization": f"Bearer {XAI_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": LLM_LIGHT_MODEL,
                    "messages": [
                        {
                            "role": "system",
                            "content": "You write concise, effective job outreach emails. "
                                       "Return only valid JSON.",
                        },
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.7,
                    "max_tokens": 500,
                },
            )

            response.raise_for_status()
            data = response.json()

            content = data["choices"][0]["message"]["content"]

            # Parse JSON from the response (handles fenced/raw/embedded JSON).
            # An empty parse routes to the template fallback in the except below.
            result = extract_json(content)
            if not result:
                raise ValueError("Could not parse LLM email JSON")

            # Log LLM usage
            await _log_llm_call(
                model=LLM_LIGHT_MODEL,
                prompt_tokens=data.get("usage", {}).get("prompt_tokens", 0),
                completion_tokens=data.get("usage", {}).get("completion_tokens", 0),
                context_type="email_generation",
            )

            return {
                "subject": result.get("subject", ""),
                "body": result.get("body", ""),
            }

    except Exception as e:
        log.error(f"LLM email generation failed: {e}")
        # Fall back to template
        return _generate_from_template(
            job=job,
            recipient_name=recipient_name,
            recipient_title=recipient_title,
            email_type=email_type,
            previous_emails=previous_emails,
        )


# =============================================================================
# Reply Processing Activity
# =============================================================================


@activity.defn
async def process_reply(reply: dict) -> dict:
    """
    Process a reply: classify sentiment, update database, trigger actions.

    Args:
        reply: Reply dict from check_for_replies

    Returns:
        Processing result with sentiment and actions taken
    """
    log.info(f"Processing reply for job {reply.get('matched_job_id')}")

    conn = await get_connection()
    try:
        # Get context for classification
        email_info = await conn.fetchrow("""
            SELECT oe.subject, j.title as job_title, j.company_name
            FROM outreach_emails oe
            JOIN jobs j ON j.id = oe.job_id
            WHERE oe.id = $1
        """, uuid.UUID(reply["matched_email_id"]))

        context = None
        if email_info:
            context = {
                "job_title": email_info["job_title"],
                "company": email_info["company_name"],
                "subject": email_info["subject"],
            }

        # Classify the reply
        classification = await classify_reply(
            email_body=reply.get("body_text", ""),
            context=context,
        )

        # Update the outreach email record
        await conn.execute("""
            UPDATE outreach_emails
            SET replied_at = $2,
                reply_sentiment = $3,
                reply_summary = $4,
                updated_at = NOW()
            WHERE id = $1
        """,
            uuid.UUID(reply["matched_email_id"]),
            datetime.fromisoformat(reply["received_at"]) if reply.get("received_at") else datetime.now(timezone.utc),
            classification["sentiment"],
            classification["summary"],
        )

        # Update application status if positive
        if classification["sentiment"] == "positive":
            await conn.execute("""
                UPDATE applications
                SET status = 'interviewing',
                    notes = COALESCE(notes, '') || E'\n\nPositive reply received: ' || $2,
                    updated_at = NOW()
                WHERE job_id = $1
            """, uuid.UUID(reply["matched_job_id"]), classification["summary"])

        log.info(
            f"Reply processed: sentiment={classification['sentiment']}, "
            f"job={reply['matched_job_id']}"
        )

        return {
            "success": True,
            "email_id": reply["matched_email_id"],
            "job_id": reply["matched_job_id"],
            "sentiment": classification["sentiment"],
            "summary": classification["summary"],
            "suggested_action": classification["suggested_action"],
        }

    except Exception as e:
        log.error(f"Error processing reply: {e}")
        return {
            "success": False,
            "error": str(e),
        }

    finally:
        await conn.close()
