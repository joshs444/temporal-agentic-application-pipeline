# External API Clients
# - SerpAPI client for job search
# - Apollo client for company enrichment
# - xAI/Grok client for LLM calls
# - Gmail client for email outreach

from .apollo import ApolloClient, Company, Contact, JobPosting
from .gmail import (
    GmailClient,
    GmailMessage,
    GmailClientError,
    TokenExpiredError,
    TokenRevokedError,
    RateLimitError,
    encrypt_token,
    decrypt_token,
    get_stored_credentials,
    save_credentials,
    update_access_token,
    get_valid_access_token,
)

__all__ = [
    # Apollo
    "ApolloClient",
    "Company",
    "Contact",
    "JobPosting",
    # Gmail
    "GmailClient",
    "GmailMessage",
    "GmailClientError",
    "TokenExpiredError",
    "TokenRevokedError",
    "RateLimitError",
    "encrypt_token",
    "decrypt_token",
    "get_stored_credentials",
    "save_credentials",
    "update_access_token",
    "get_valid_access_token",
]
