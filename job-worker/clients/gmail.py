"""
Gmail OAuth Client for JobHunt Email Outreach.

Provides Gmail API access using OAuth 2.0 for:
- Sending emails with tracking headers
- Polling inbox for replies
- Thread management for conversation tracking
"""

import base64
import hashlib
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Optional

import asyncpg
import httpx
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

log = logging.getLogger(__name__)

# Gmail API base URL
GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1"

# OAuth endpoints
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"

# Required scopes for Gmail access
GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
]


class GmailClientError(Exception):
    """Base exception for Gmail client errors."""
    pass


class TokenExpiredError(GmailClientError):
    """OAuth token has expired and needs refresh."""
    pass


class TokenRevokedError(GmailClientError):
    """OAuth token has been revoked."""
    pass


class RateLimitError(GmailClientError):
    """Gmail API rate limit exceeded."""
    pass


@dataclass
class GmailMessage:
    """Parsed Gmail message."""
    message_id: str
    thread_id: str
    label_ids: list[str]
    snippet: str
    from_email: Optional[str]
    from_name: Optional[str]
    to_email: Optional[str]
    subject: Optional[str]
    internal_date: Optional[datetime]
    body_text: Optional[str]
    body_html: Optional[str]
    has_attachments: bool
    in_reply_to: Optional[str]
    references: Optional[str]


# =============================================================================
# Token Encryption Utilities
# =============================================================================


def derive_key(master_key: str, salt: str) -> bytes:
    """
    Derive a Fernet-compatible key from master key + salt.

    Uses PBKDF2 with SHA256 to derive a 32-byte key, then base64-encodes
    it for use with Fernet.
    """
    try:
        master_bytes = base64.urlsafe_b64decode(master_key)
    except Exception:
        master_bytes = master_key.encode('utf-8')

    salt_bytes = hashlib.sha256(salt.encode('utf-8')).digest()

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt_bytes,
        iterations=100_000,
    )
    derived_key = kdf.derive(master_bytes)

    return base64.urlsafe_b64encode(derived_key)


def encrypt_token(token: str, master_key: str, salt: str = "jobhunt") -> str:
    """Encrypt an OAuth token using Fernet."""
    if not master_key:
        raise ValueError("OAUTH_MASTER_KEY is required for token encryption")

    key = derive_key(master_key, salt)
    fernet = Fernet(key)
    encrypted = fernet.encrypt(token.encode('utf-8'))
    return encrypted.decode('utf-8')


def decrypt_token(encrypted_token: str, master_key: str, salt: str = "jobhunt") -> Optional[str]:
    """Decrypt an OAuth token using Fernet."""
    if not master_key:
        raise ValueError("OAUTH_MASTER_KEY is required for token decryption")

    try:
        key = derive_key(master_key, salt)
        fernet = Fernet(key)
        decrypted = fernet.decrypt(encrypted_token.encode('utf-8'))
        return decrypted.decode('utf-8')
    except InvalidToken:
        log.error("Failed to decrypt OAuth token: invalid token")
        return None
    except Exception as e:
        log.error(f"Unexpected error decrypting OAuth token: {e}")
        return None


# =============================================================================
# Gmail Client
# =============================================================================


class GmailClient:
    """
    Gmail API client with OAuth 2.0 support.

    Handles authorization, sending emails, polling inbox, and thread management.
    """

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        redirect_uri: str = "http://localhost:8080/oauth/callback",
    ):
        self.client_id = client_id or os.environ.get("GOOGLE_CLIENT_ID")
        self.client_secret = client_secret or os.environ.get("GOOGLE_CLIENT_SECRET")
        self.redirect_uri = redirect_uri
        self.master_key = os.environ.get("OAUTH_MASTER_KEY")

        if not self.client_id or not self.client_secret:
            raise GmailClientError("GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET are required")

    def get_authorization_url(self, state: Optional[str] = None) -> str:
        """
        Generate the OAuth authorization URL for user consent.

        Args:
            state: Optional state parameter for CSRF protection

        Returns:
            URL to redirect user for OAuth consent
        """
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": " ".join(GMAIL_SCOPES),
            "access_type": "offline",
            "prompt": "consent",
        }
        if state:
            params["state"] = state

        query = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{GOOGLE_AUTH_URL}?{query}"

    async def authorize(self, auth_code: str) -> dict:
        """
        Complete OAuth flow with authorization code.

        Args:
            auth_code: Authorization code from OAuth redirect

        Returns:
            Dict with access_token, refresh_token, expires_at, email_address
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "grant_type": "authorization_code",
                    "code": auth_code,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "redirect_uri": self.redirect_uri,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

            if response.status_code != 200:
                error_data = response.json()
                raise GmailClientError(f"OAuth token exchange failed: {error_data}")

            data = response.json()

            # Calculate expiry time
            expires_in = data.get("expires_in", 3600)
            expires_at = datetime.now(timezone.utc).timestamp() + expires_in

            # Get user email
            email_address = await self._get_user_email(data["access_token"])

            # Encrypt tokens for storage
            encrypted_access = None
            encrypted_refresh = None
            if self.master_key:
                encrypted_access = encrypt_token(data["access_token"], self.master_key)
                encrypted_refresh = encrypt_token(data["refresh_token"], self.master_key)

            return {
                "access_token": data["access_token"],
                "refresh_token": data["refresh_token"],
                "encrypted_access_token": encrypted_access,
                "encrypted_refresh_token": encrypted_refresh,
                "expires_at": datetime.fromtimestamp(expires_at, tz=timezone.utc),
                "email_address": email_address,
            }

    async def _get_user_email(self, access_token: str) -> str:
        """Get the email address associated with the OAuth token."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{GMAIL_API_BASE}/users/me/profile",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            response.raise_for_status()
            return response.json()["emailAddress"]

    async def refresh_access_token(self, refresh_token: str) -> dict:
        """
        Refresh an access token using the refresh token.

        Args:
            refresh_token: The refresh token (plaintext)

        Returns:
            Dict with access_token and expires_at
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

            if response.status_code == 400:
                error_data = response.json()
                error = error_data.get("error", "")
                if error in ("invalid_grant", "invalid_token"):
                    raise TokenRevokedError(
                        f"Refresh token revoked: {error_data.get('error_description', error)}"
                    )
                raise GmailClientError(f"Token refresh failed: {error_data}")

            if response.status_code == 429:
                raise RateLimitError("OAuth token refresh rate limited")

            response.raise_for_status()
            data = response.json()

            expires_in = data.get("expires_in", 3600)
            expires_at = datetime.now(timezone.utc).timestamp() + expires_in

            return {
                "access_token": data["access_token"],
                "expires_at": datetime.fromtimestamp(expires_at, tz=timezone.utc),
            }

    async def send_email(
        self,
        access_token: str,
        to: str,
        subject: str,
        body_text: str,
        body_html: Optional[str] = None,
        from_name: Optional[str] = None,
        from_email: Optional[str] = None,
        thread_id: Optional[str] = None,
        tracking_id: Optional[str] = None,
        in_reply_to: Optional[str] = None,
        references: Optional[str] = None,
    ) -> dict:
        """
        Send email with tracking headers.

        Args:
            access_token: Valid OAuth access token
            to: Recipient email address
            subject: Email subject
            body_text: Plain text body
            body_html: HTML body (optional)
            from_name: Sender display name
            from_email: Sender email (for display, actual sender is OAuth account)
            thread_id: Gmail thread ID for replies
            tracking_id: Tracking ID for reply matching
            in_reply_to: Message-ID for threading
            references: Reference chain for threading

        Returns:
            Dict with message_id, thread_id, sent_at
        """
        # Build MIME message
        if body_html:
            msg = MIMEMultipart("alternative")
            msg.attach(MIMEText(body_text, "plain"))
            msg.attach(MIMEText(body_html, "html"))
        else:
            msg = MIMEText(body_text, "plain")

        msg["To"] = to
        msg["Subject"] = subject

        if from_name and from_email:
            msg["From"] = f"{from_name} <{from_email}>"
        elif from_email:
            msg["From"] = from_email

        # Add tracking header for reply matching
        if tracking_id:
            msg["X-Jobhunt-Email-ID"] = tracking_id

        # Threading headers
        if in_reply_to:
            msg["In-Reply-To"] = in_reply_to
        if references:
            msg["References"] = references

        # Encode message for Gmail API
        raw_message = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")

        # Build request body
        request_body: dict[str, Any] = {"raw": raw_message}
        if thread_id:
            request_body["threadId"] = thread_id

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{GMAIL_API_BASE}/users/me/messages/send",
                headers={"Authorization": f"Bearer {access_token}"},
                json=request_body,
            )

            if response.status_code == 401:
                raise TokenExpiredError("Access token expired")
            if response.status_code == 429:
                raise RateLimitError("Gmail API rate limit exceeded")

            response.raise_for_status()
            data = response.json()

            return {
                "message_id": data["id"],
                "thread_id": data.get("threadId"),
                "sent_at": datetime.now(timezone.utc),
            }

    async def check_inbox(
        self,
        access_token: str,
        since: Optional[datetime] = None,
        max_results: int = 50,
        label_ids: Optional[list[str]] = None,
        query: Optional[str] = None,
    ) -> list[dict]:
        """
        Check for new messages (replies).

        Args:
            access_token: Valid OAuth access token
            since: Only return messages after this time
            max_results: Maximum messages to return
            label_ids: Filter by Gmail labels
            query: Gmail search query

        Returns:
            List of message stubs with id and threadId
        """
        params: dict[str, Any] = {"maxResults": min(max_results, 500)}

        if label_ids:
            params["labelIds"] = label_ids

        # Build query string
        query_parts = []
        if query:
            query_parts.append(query)
        if since:
            # Gmail uses Unix timestamp in seconds
            after_timestamp = int(since.timestamp())
            query_parts.append(f"after:{after_timestamp}")

        if query_parts:
            params["q"] = " ".join(query_parts)

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{GMAIL_API_BASE}/users/me/messages",
                params=params,
                headers={"Authorization": f"Bearer {access_token}"},
            )

            if response.status_code == 401:
                raise TokenExpiredError("Access token expired")
            if response.status_code == 429:
                raise RateLimitError("Gmail API rate limit exceeded")

            response.raise_for_status()
            data = response.json()

            return data.get("messages", [])

    async def get_message(
        self,
        access_token: str,
        message_id: str,
        format: str = "full",
    ) -> GmailMessage:
        """
        Get a single message with full details.

        Args:
            access_token: Valid OAuth access token
            message_id: Gmail message ID
            format: Message format ('full', 'metadata', 'minimal')

        Returns:
            Parsed GmailMessage object
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{GMAIL_API_BASE}/users/me/messages/{message_id}",
                params={"format": format},
                headers={"Authorization": f"Bearer {access_token}"},
            )

            if response.status_code == 401:
                raise TokenExpiredError("Access token expired")
            if response.status_code == 404:
                raise GmailClientError(f"Message not found: {message_id}")
            if response.status_code == 429:
                raise RateLimitError("Gmail API rate limit exceeded")

            response.raise_for_status()
            data = response.json()

        return self._parse_message(data)

    async def get_thread(self, access_token: str, thread_id: str) -> list[dict]:
        """
        Get full email thread.

        Args:
            access_token: Valid OAuth access token
            thread_id: Gmail thread ID

        Returns:
            List of messages in the thread
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{GMAIL_API_BASE}/users/me/threads/{thread_id}",
                params={"format": "full"},
                headers={"Authorization": f"Bearer {access_token}"},
            )

            if response.status_code == 401:
                raise TokenExpiredError("Access token expired")
            if response.status_code == 404:
                raise GmailClientError(f"Thread not found: {thread_id}")
            if response.status_code == 429:
                raise RateLimitError("Gmail API rate limit exceeded")

            response.raise_for_status()
            data = response.json()

            return [self._parse_message(msg) for msg in data.get("messages", [])]

    def _parse_message(self, data: dict[str, Any]) -> GmailMessage:
        """Parse Gmail API message response into GmailMessage object."""
        headers = {
            h["name"].lower(): h["value"]
            for h in data.get("payload", {}).get("headers", [])
        }

        # Parse from header
        from_header = headers.get("from", "")
        from_email, from_name = self._parse_email_address(from_header)

        # Parse to header
        to_header = headers.get("to", "")
        to_email, _ = self._parse_email_address(to_header)

        # Parse internal date (milliseconds since epoch)
        internal_date = None
        if data.get("internalDate"):
            try:
                ts = int(data["internalDate"]) / 1000
                internal_date = datetime.fromtimestamp(ts, tz=timezone.utc)
            except (ValueError, TypeError):
                pass

        # Extract body
        body_text, body_html = self._extract_body(data.get("payload", {}))

        # Check for attachments
        has_attachments = self._has_attachments(data.get("payload", {}))

        return GmailMessage(
            message_id=data["id"],
            thread_id=data["threadId"],
            label_ids=data.get("labelIds", []),
            snippet=data.get("snippet", ""),
            from_email=from_email,
            from_name=from_name,
            to_email=to_email,
            subject=headers.get("subject"),
            internal_date=internal_date,
            body_text=body_text,
            body_html=body_html,
            has_attachments=has_attachments,
            in_reply_to=headers.get("in-reply-to"),
            references=headers.get("references"),
        )

    def _parse_email_address(self, header: str) -> tuple[Optional[str], Optional[str]]:
        """Parse an email header into email and name."""
        if not header:
            return None, None

        if "<" in header and ">" in header:
            name_part = header.split("<")[0].strip().strip('"')
            email_part = header.split("<")[1].split(">")[0].strip()
            return email_part, name_part if name_part else None
        else:
            return header.strip(), None

    def _extract_body(self, payload: dict[str, Any]) -> tuple[Optional[str], Optional[str]]:
        """Extract text and HTML body from message payload."""
        body_text = None
        body_html = None

        mime_type = payload.get("mimeType", "")
        body = payload.get("body", {})

        if mime_type == "text/plain" and body.get("data"):
            body_text = self._decode_body(body["data"])
        elif mime_type == "text/html" and body.get("data"):
            body_html = self._decode_body(body["data"])
        elif "parts" in payload:
            for part in payload["parts"]:
                part_text, part_html = self._extract_body(part)
                if part_text and not body_text:
                    body_text = part_text
                if part_html and not body_html:
                    body_html = part_html

        return body_text, body_html

    def _decode_body(self, data: str) -> str:
        """Decode base64url encoded body data."""
        try:
            decoded = base64.urlsafe_b64decode(data)
            return decoded.decode("utf-8", errors="replace")
        except Exception:
            return ""

    def _has_attachments(self, payload: dict[str, Any]) -> bool:
        """Check if message has attachments."""
        if payload.get("filename"):
            return True
        for part in payload.get("parts", []):
            if self._has_attachments(part):
                return True
        return False


# =============================================================================
# Database Token Management
# =============================================================================


async def get_stored_credentials(conn: asyncpg.Connection) -> Optional[dict]:
    """
    Get stored Gmail credentials from database.

    Returns the first active email account credentials.
    """
    row = await conn.fetchrow("""
        SELECT
            id,
            email_address,
            display_name,
            encrypted_access_token,
            encrypted_refresh_token,
            token_expires_at,
            is_active
        FROM email_accounts
        WHERE is_active = TRUE
        ORDER BY created_at
        LIMIT 1
    """)

    if not row:
        return None

    master_key = os.environ.get("OAUTH_MASTER_KEY")
    if not master_key:
        raise GmailClientError("OAUTH_MASTER_KEY not configured")

    # Decrypt tokens
    access_token = None
    refresh_token = None

    if row["encrypted_access_token"]:
        access_token = decrypt_token(row["encrypted_access_token"], master_key)
    if row["encrypted_refresh_token"]:
        refresh_token = decrypt_token(row["encrypted_refresh_token"], master_key)

    return {
        "id": str(row["id"]),
        "email_address": row["email_address"],
        "display_name": row["display_name"],
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_at": row["token_expires_at"],
        "is_active": row["is_active"],
    }


async def save_credentials(
    conn: asyncpg.Connection,
    email_address: str,
    display_name: Optional[str],
    access_token: str,
    refresh_token: str,
    expires_at: datetime,
) -> str:
    """
    Save Gmail credentials to database.

    Returns the account ID.
    """
    master_key = os.environ.get("OAUTH_MASTER_KEY")
    if not master_key:
        raise GmailClientError("OAUTH_MASTER_KEY not configured")

    encrypted_access = encrypt_token(access_token, master_key)
    encrypted_refresh = encrypt_token(refresh_token, master_key)

    row = await conn.fetchrow("""
        INSERT INTO email_accounts (
            email_address,
            display_name,
            encrypted_access_token,
            encrypted_refresh_token,
            token_expires_at,
            is_active
        ) VALUES ($1, $2, $3, $4, $5, TRUE)
        ON CONFLICT (email_address) DO UPDATE SET
            display_name = EXCLUDED.display_name,
            encrypted_access_token = EXCLUDED.encrypted_access_token,
            encrypted_refresh_token = EXCLUDED.encrypted_refresh_token,
            token_expires_at = EXCLUDED.token_expires_at,
            is_active = TRUE,
            updated_at = NOW()
        RETURNING id
    """, email_address, display_name, encrypted_access, encrypted_refresh, expires_at)

    return str(row["id"])


async def update_access_token(
    conn: asyncpg.Connection,
    account_id: str,
    access_token: str,
    expires_at: datetime,
) -> None:
    """Update the access token after a refresh."""
    master_key = os.environ.get("OAUTH_MASTER_KEY")
    if not master_key:
        raise GmailClientError("OAUTH_MASTER_KEY not configured")

    encrypted_access = encrypt_token(access_token, master_key)

    await conn.execute("""
        UPDATE email_accounts
        SET encrypted_access_token = $2,
            token_expires_at = $3,
            updated_at = NOW()
        WHERE id = $1
    """, account_id, encrypted_access, expires_at)


async def get_valid_access_token(conn: asyncpg.Connection) -> Optional[tuple[str, str]]:
    """
    Get a valid access token, refreshing if needed.

    Returns tuple of (access_token, email_address) or None.
    """
    creds = await get_stored_credentials(conn)
    if not creds:
        return None

    if not creds["refresh_token"]:
        log.error("No refresh token available")
        return None

    # Check if token is expired or will expire in 5 minutes
    now = datetime.now(timezone.utc)
    if creds["expires_at"] and creds["expires_at"] > now:
        # Still valid
        if creds["access_token"]:
            return creds["access_token"], creds["email_address"]

    # Need to refresh
    log.info(f"Refreshing access token for {creds['email_address']}")
    client = GmailClient()

    try:
        new_tokens = await client.refresh_access_token(creds["refresh_token"])
        await update_access_token(
            conn,
            creds["id"],
            new_tokens["access_token"],
            new_tokens["expires_at"],
        )
        return new_tokens["access_token"], creds["email_address"]

    except TokenRevokedError as e:
        log.error(f"Token revoked for {creds['email_address']}: {e}")
        # Mark account as inactive
        await conn.execute("""
            UPDATE email_accounts
            SET is_active = FALSE, updated_at = NOW()
            WHERE id = $1
        """, creds["id"])
        return None

    except Exception as e:
        log.error(f"Failed to refresh token: {e}")
        return None
