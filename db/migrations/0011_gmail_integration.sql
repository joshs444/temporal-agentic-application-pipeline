-- 0011_gmail_integration.sql
-- Gmail OAuth integration and inbox polling for JobHunt
-- NOTE: outreach_emails table already exists in 0004_outreach.sql
-- This migration adds email_accounts, inbox_messages, and poll state tracking

-- Email accounts table - stores OAuth credentials for Gmail
CREATE TABLE IF NOT EXISTS email_accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email_address TEXT NOT NULL UNIQUE,
    display_name TEXT,

    -- OAuth tokens (encrypted with OAUTH_MASTER_KEY)
    encrypted_access_token TEXT,
    encrypted_refresh_token TEXT,
    token_expires_at TIMESTAMPTZ,

    -- Status
    is_active BOOLEAN DEFAULT TRUE,

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Add Gmail-specific columns to outreach_emails if they don't exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'outreach_emails' AND column_name = 'gmail_message_id') THEN
        ALTER TABLE outreach_emails ADD COLUMN gmail_message_id TEXT;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'outreach_emails' AND column_name = 'gmail_thread_id') THEN
        ALTER TABLE outreach_emails ADD COLUMN gmail_thread_id TEXT;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'outreach_emails' AND column_name = 'tracking_id') THEN
        ALTER TABLE outreach_emails ADD COLUMN tracking_id TEXT UNIQUE;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'outreach_emails' AND column_name = 'body_html') THEN
        ALTER TABLE outreach_emails ADD COLUMN body_html TEXT;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'outreach_emails' AND column_name = 'to_name') THEN
        ALTER TABLE outreach_emails ADD COLUMN to_name TEXT;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'outreach_emails' AND column_name = 'reply_gmail_message_id') THEN
        ALTER TABLE outreach_emails ADD COLUMN reply_gmail_message_id TEXT;
    END IF;
END $$;

-- Inbox messages table - stores received replies for audit trail
CREATE TABLE IF NOT EXISTS inbox_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    gmail_message_id TEXT UNIQUE NOT NULL,
    gmail_thread_id TEXT,

    -- Sender info
    from_email TEXT,
    from_name TEXT,
    to_email TEXT,

    -- Message content
    subject TEXT,
    body_text TEXT,
    body_html TEXT,

    -- Timestamps
    received_at TIMESTAMPTZ,

    -- Matching
    matched_email_id UUID REFERENCES outreach_emails(id) ON DELETE SET NULL,
    matched_job_id UUID REFERENCES jobs(id) ON DELETE SET NULL,

    -- Classification
    sentiment TEXT,
    sentiment_summary TEXT,

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- Constraints
    CONSTRAINT inbox_messages_sentiment_check
        CHECK (sentiment IS NULL OR sentiment IN
            ('positive', 'neutral', 'rejection', 'request_info', 'auto_reply'))
);

-- Email poll state - tracks polling progress (singleton table)
CREATE TABLE IF NOT EXISTS email_poll_state (
    id INTEGER PRIMARY KEY DEFAULT 1,
    last_poll_at TIMESTAMPTZ,
    messages_found INTEGER DEFAULT 0,
    replies_matched INTEGER DEFAULT 0,
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- Ensure only one row
    CONSTRAINT email_poll_state_single_row CHECK (id = 1)
);

-- Insert initial poll state row
INSERT INTO email_poll_state (id, last_poll_at)
VALUES (1, NOW() - INTERVAL '24 hours')
ON CONFLICT (id) DO NOTHING;

-- Create indexes for email_accounts
CREATE INDEX IF NOT EXISTS idx_email_accounts_email ON email_accounts(email_address);
CREATE INDEX IF NOT EXISTS idx_email_accounts_active ON email_accounts(is_active) WHERE is_active = TRUE;

-- Create indexes for inbox_messages
CREATE INDEX IF NOT EXISTS idx_inbox_messages_from ON inbox_messages(from_email);
CREATE INDEX IF NOT EXISTS idx_inbox_messages_thread ON inbox_messages(gmail_thread_id);
CREATE INDEX IF NOT EXISTS idx_inbox_messages_matched_email ON inbox_messages(matched_email_id)
    WHERE matched_email_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_inbox_messages_matched_job ON inbox_messages(matched_job_id)
    WHERE matched_job_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_inbox_messages_received ON inbox_messages(received_at DESC);
CREATE INDEX IF NOT EXISTS idx_inbox_messages_sentiment ON inbox_messages(sentiment);

-- Additional indexes for outreach_emails Gmail columns
CREATE INDEX IF NOT EXISTS idx_outreach_emails_gmail_message ON outreach_emails(gmail_message_id)
    WHERE gmail_message_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_outreach_emails_gmail_thread ON outreach_emails(gmail_thread_id)
    WHERE gmail_thread_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_outreach_emails_tracking ON outreach_emails(tracking_id)
    WHERE tracking_id IS NOT NULL;

-- Apply updated_at triggers
DROP TRIGGER IF EXISTS update_email_accounts_updated_at ON email_accounts;
CREATE TRIGGER update_email_accounts_updated_at BEFORE UPDATE ON email_accounts
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_inbox_messages_updated_at ON inbox_messages;
CREATE TRIGGER update_inbox_messages_updated_at BEFORE UPDATE ON inbox_messages
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
