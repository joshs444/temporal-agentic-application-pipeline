"""
Gmail Inbox Poller for JobHunt.

Standalone service that polls Gmail inbox for replies to outreach emails.
Runs continuously as a background service with configurable poll interval.

Features:
- Polls for new unread messages
- Matches replies to sent outreach emails
- Classifies reply sentiment using LLM
- Updates database with reply information
- Optionally signals Temporal workflows on reply detection
"""

import asyncio
import logging
import os
import signal
import sys
from datetime import datetime, timedelta, timezone
from typing import Optional

import asyncpg

from clients.gmail import (
    GmailClient,
    GmailMessage,
    GmailClientError,
    TokenExpiredError,
    TokenRevokedError,
    RateLimitError,
    get_valid_access_token,
    get_stored_credentials,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
log = logging.getLogger(__name__)

# Configuration
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://jobhunt:jobhunt_secret@localhost:5433/jobhunt_db"
)
POLL_INTERVAL_SECONDS = int(os.environ.get("POLL_INTERVAL_SECONDS", "300"))  # 5 minutes
TEMPORAL_ADDRESS = os.environ.get("TEMPORAL_ADDRESS", "localhost:7233")
ENABLE_TEMPORAL_SIGNALS = os.environ.get("ENABLE_TEMPORAL_SIGNALS", "false").lower() == "true"

# Global flag for graceful shutdown
shutdown_requested = False


def handle_shutdown(signum, frame):
    """Handle shutdown signals gracefully."""
    global shutdown_requested
    log.info(f"Received signal {signum}, initiating graceful shutdown...")
    shutdown_requested = True


async def get_last_poll_time(conn: asyncpg.Connection) -> datetime:
    """Get the last successful poll time from database."""
    row = await conn.fetchrow("""
        SELECT last_poll_at FROM email_poll_state
        WHERE id = 1
    """)

    if row and row["last_poll_at"]:
        return row["last_poll_at"]

    # Default: look back 24 hours on first run
    return datetime.now(timezone.utc) - timedelta(hours=24)


async def update_last_poll_time(
    conn: asyncpg.Connection,
    poll_time: datetime,
    messages_found: int,
    replies_matched: int,
) -> None:
    """Update the poll state in database."""
    await conn.execute("""
        INSERT INTO email_poll_state (id, last_poll_at, messages_found, replies_matched)
        VALUES (1, $1, $2, $3)
        ON CONFLICT (id) DO UPDATE SET
            last_poll_at = $1,
            messages_found = email_poll_state.messages_found + $2,
            replies_matched = email_poll_state.replies_matched + $3,
            updated_at = NOW()
    """, poll_time, messages_found, replies_matched)


async def match_reply_to_email(
    conn: asyncpg.Connection,
    message: GmailMessage,
) -> Optional[dict]:
    """
    Match an incoming message to a sent outreach email.

    Matching strategies:
    1. Thread ID match - most reliable
    2. In-Reply-To header matches our Gmail message ID
    3. Sender email matches a recipient we've emailed
    """
    # Strategy 1: Thread ID match
    if message.thread_id:
        row = await conn.fetchrow("""
            SELECT id as email_id, job_id, to_email, subject
            FROM outreach_emails
            WHERE gmail_thread_id = $1
            ORDER BY sent_at DESC
            LIMIT 1
        """, message.thread_id)

        if row:
            log.info(f"Matched reply via thread_id: {message.thread_id}")
            return dict(row)

    # Strategy 2: In-Reply-To header match
    if message.in_reply_to:
        in_reply_to = message.in_reply_to.strip("<>")
        row = await conn.fetchrow("""
            SELECT id as email_id, job_id, to_email, subject
            FROM outreach_emails
            WHERE gmail_message_id = $1
            ORDER BY sent_at DESC
            LIMIT 1
        """, in_reply_to)

        if row:
            log.info(f"Matched reply via In-Reply-To: {in_reply_to}")
            return dict(row)

    # Strategy 3: Sender email lookup
    if message.from_email:
        sender_email = message.from_email.lower()
        row = await conn.fetchrow("""
            SELECT id as email_id, job_id, to_email, subject
            FROM outreach_emails
            WHERE LOWER(to_email) = $1
              AND replied_at IS NULL
            ORDER BY sent_at DESC
            LIMIT 1
        """, sender_email)

        if row:
            log.info(f"Matched reply via sender email: {sender_email}")
            return dict(row)

    return None


async def process_reply(
    conn: asyncpg.Connection,
    message: GmailMessage,
    match: dict,
) -> dict:
    """
    Process a matched reply:
    - Record the reply in database
    - Classify sentiment
    - Update outreach email record
    - Optionally signal waiting workflows
    """
    from activities.email import classify_reply

    log.info(f"Processing reply from {message.from_email} for job {match['job_id']}")

    # Get context for classification
    job_info = await conn.fetchrow("""
        SELECT title, company_name
        FROM jobs
        WHERE id = $1
    """, match["job_id"])

    context = None
    if job_info:
        context = {
            "job_title": job_info["title"],
            "company": job_info["company_name"],
            "subject": match.get("subject", ""),
        }

    # Classify the reply
    classification = await classify_reply(
        email_body=message.body_text or message.snippet or "",
        context=context,
    )

    # Record reply in inbox_messages for audit trail
    await conn.execute("""
        INSERT INTO inbox_messages (
            gmail_message_id,
            gmail_thread_id,
            from_email,
            from_name,
            to_email,
            subject,
            body_text,
            body_html,
            received_at,
            matched_email_id,
            matched_job_id,
            sentiment,
            sentiment_summary
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
        ON CONFLICT (gmail_message_id) DO UPDATE SET
            sentiment = EXCLUDED.sentiment,
            sentiment_summary = EXCLUDED.sentiment_summary,
            updated_at = NOW()
    """,
        message.message_id,
        message.thread_id,
        message.from_email,
        message.from_name,
        message.to_email,
        message.subject,
        message.body_text[:10000] if message.body_text else None,
        message.body_html[:20000] if message.body_html else None,
        message.internal_date or datetime.now(timezone.utc),
        match["email_id"],
        match["job_id"],
        classification["sentiment"],
        classification["summary"],
    )

    # Update the outreach email record
    await conn.execute("""
        UPDATE outreach_emails
        SET replied_at = $2,
            reply_sentiment = $3,
            reply_summary = $4,
            reply_gmail_message_id = $5,
            updated_at = NOW()
        WHERE id = $1 AND replied_at IS NULL
    """,
        match["email_id"],
        message.internal_date or datetime.now(timezone.utc),
        classification["sentiment"],
        classification["summary"],
        message.message_id,
    )

    # Update application status based on sentiment
    if classification["sentiment"] == "positive":
        await conn.execute("""
            UPDATE applications
            SET status = 'interviewing',
                notes = COALESCE(notes, '') || E'\n\n[Auto] Positive reply received: ' || $2,
                updated_at = NOW()
            WHERE job_id = $1
        """, match["job_id"], classification["summary"])

    elif classification["sentiment"] == "rejection":
        await conn.execute("""
            UPDATE applications
            SET status = 'rejected',
                notes = COALESCE(notes, '') || E'\n\n[Auto] Rejection received: ' || $2,
                updated_at = NOW()
            WHERE job_id = $1
        """, match["job_id"], classification["summary"])

    # Signal waiting workflows if enabled
    if ENABLE_TEMPORAL_SIGNALS:
        await signal_workflow(match["job_id"], classification)

    return {
        "email_id": str(match["email_id"]),
        "job_id": str(match["job_id"]),
        "sentiment": classification["sentiment"],
        "summary": classification["summary"],
    }


async def signal_workflow(job_id: str, classification: dict) -> None:
    """Signal any waiting Temporal workflow about the reply."""
    try:
        from temporalio.client import Client

        client = await Client.connect(TEMPORAL_ADDRESS)

        # Try to signal workflow (may not exist)
        try:
            handle = client.get_workflow_handle(f"job-outreach-{job_id}")
            await handle.signal(
                "reply_received",
                {
                    "sentiment": classification["sentiment"],
                    "summary": classification["summary"],
                    "suggested_action": classification.get("suggested_action", ""),
                },
            )
            log.info(f"Signaled workflow for job {job_id}")
        except Exception as e:
            log.debug(f"No active workflow to signal for job {job_id}: {e}")

    except Exception as e:
        log.warning(f"Failed to signal workflow: {e}")


async def poll_inbox(pool: asyncpg.Pool) -> dict:
    """
    Poll inbox for new replies.

    Returns stats about the poll cycle.
    """
    stats = {"checked": 0, "matched": 0, "errors": 0}

    async with pool.acquire() as conn:
        # Get credentials
        token_result = await get_valid_access_token(conn)
        if not token_result:
            log.warning("No valid Gmail credentials available")
            return stats

        access_token, email_address = token_result
        log.debug(f"Polling inbox for {email_address}")

        # Get last poll time
        since = await get_last_poll_time(conn)
        log.info(f"Checking messages since {since}")

        try:
            # Get recent inbox messages
            client = GmailClient()
            messages = await client.check_inbox(
                access_token=access_token,
                since=since,
                max_results=50,
                label_ids=["INBOX", "UNREAD"],
            )

            stats["checked"] = len(messages)

            if not messages:
                log.debug("No new messages found")
                await update_last_poll_time(
                    conn, datetime.now(timezone.utc), 0, 0
                )
                return stats

            log.info(f"Found {len(messages)} unread messages to check")

            # Process each message
            for msg_stub in messages:
                try:
                    # Get full message
                    message = await client.get_message(
                        access_token=access_token,
                        message_id=msg_stub["id"],
                    )

                    # Try to match to a sent email
                    match = await match_reply_to_email(conn, message)

                    if match:
                        # Process the reply
                        result = await process_reply(conn, message, match)
                        stats["matched"] += 1
                        log.info(
                            f"Processed reply: {result['sentiment']} from "
                            f"{message.from_email} for job {result['job_id']}"
                        )

                except Exception as e:
                    log.warning(f"Error processing message {msg_stub['id']}: {e}")
                    stats["errors"] += 1

            # Update poll state
            await update_last_poll_time(
                conn,
                datetime.now(timezone.utc),
                stats["checked"],
                stats["matched"],
            )

        except TokenExpiredError:
            log.error("Access token expired during poll")
            stats["errors"] += 1

        except TokenRevokedError:
            log.error("Gmail access was revoked - marking account inactive")
            await conn.execute("""
                UPDATE email_accounts
                SET is_active = FALSE, updated_at = NOW()
            """)
            stats["errors"] += 1

        except RateLimitError:
            log.warning("Gmail API rate limit hit, will retry next cycle")
            stats["errors"] += 1

        except GmailClientError as e:
            log.error(f"Gmail API error: {e}")
            stats["errors"] += 1

    return stats


async def main():
    """Main polling loop."""
    global shutdown_requested

    log.info("Starting JobHunt Gmail inbox poller")
    log.info(f"Database: {DATABASE_URL.split('@')[1] if '@' in DATABASE_URL else 'configured'}")
    log.info(f"Poll interval: {POLL_INTERVAL_SECONDS}s")
    log.info(f"Temporal signals: {'enabled' if ENABLE_TEMPORAL_SIGNALS else 'disabled'}")

    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)

    # Create connection pool
    pool = await asyncpg.create_pool(
        DATABASE_URL,
        min_size=1,
        max_size=3,
    )

    try:
        poll_count = 0
        total_matched = 0

        while not shutdown_requested:
            poll_count += 1
            log.info(f"Starting poll cycle #{poll_count}")

            try:
                stats = await poll_inbox(pool)
                total_matched += stats["matched"]

                if stats["matched"] > 0:
                    log.info(
                        f"Poll #{poll_count} complete: "
                        f"{stats['checked']} checked, "
                        f"{stats['matched']} matched, "
                        f"{stats['errors']} errors "
                        f"(total matched: {total_matched})"
                    )
                else:
                    log.debug(
                        f"Poll #{poll_count} complete: {stats['checked']} checked, no matches"
                    )

            except Exception as e:
                log.error(f"Error in poll cycle #{poll_count}: {e}")

            # Sleep until next poll, checking for shutdown every second
            for _ in range(POLL_INTERVAL_SECONDS):
                if shutdown_requested:
                    break
                await asyncio.sleep(1)

    except asyncio.CancelledError:
        log.info("Poll loop cancelled")

    finally:
        log.info(f"Shutting down after {poll_count} poll cycles, {total_matched} total matches")
        await pool.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Keyboard interrupt received, exiting")
        sys.exit(0)
