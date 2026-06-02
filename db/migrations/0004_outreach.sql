-- 0004_outreach.sql
-- Email outreach tracking for job hunt communications

CREATE TABLE IF NOT EXISTS outreach_emails (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- References (optional - an outreach email may be general networking)
    job_id UUID REFERENCES jobs(id) ON DELETE SET NULL,
    application_id UUID REFERENCES applications(id) ON DELETE SET NULL,

    -- Recipient information
    recipient_email TEXT NOT NULL,
    recipient_name TEXT,
    recipient_title TEXT,
    recipient_role TEXT, -- 'recruiter', 'hiring_manager', 'engineer', 'hr', 'referral', 'networking'
    recipient_company TEXT,
    recipient_linkedin TEXT,

    -- Email content
    subject TEXT,
    body TEXT,

    -- Email classification
    email_type TEXT NOT NULL DEFAULT 'initial',
    sequence_step INT DEFAULT 1,

    -- Scheduling
    scheduled_at TIMESTAMPTZ,

    -- Sending
    sent_at TIMESTAMPTZ,
    sent_from TEXT, -- which email account was used
    message_id TEXT, -- email message ID for threading
    thread_id TEXT, -- conversation thread ID

    -- Engagement tracking
    delivered_at TIMESTAMPTZ,
    bounced_at TIMESTAMPTZ,
    bounce_reason TEXT,
    opened_at TIMESTAMPTZ,
    open_count INT DEFAULT 0,
    clicked_at TIMESTAMPTZ,
    click_count INT DEFAULT 0,

    -- Reply tracking
    replied_at TIMESTAMPTZ,
    reply_message_id TEXT,
    reply_summary TEXT,
    reply_sentiment TEXT,

    -- Status
    status TEXT NOT NULL DEFAULT 'draft',

    -- Metadata
    template_used TEXT, -- reference to template name if used
    personalization_notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- Constraints
    CONSTRAINT outreach_emails_email_type_check
        CHECK (email_type IN ('initial', 'follow_up', 'thank_you', 'negotiation',
                              'networking', 'cold_outreach', 'referral_request')),
    CONSTRAINT outreach_emails_recipient_role_check
        CHECK (recipient_role IS NULL OR recipient_role IN
            ('recruiter', 'hiring_manager', 'engineer', 'hr', 'referral', 'networking', 'founder', 'other')),
    CONSTRAINT outreach_emails_reply_sentiment_check
        CHECK (reply_sentiment IS NULL OR reply_sentiment IN
            ('positive', 'neutral', 'negative', 'rejection', 'interested', 'not_now')),
    CONSTRAINT outreach_emails_status_check
        CHECK (status IN ('draft', 'scheduled', 'sent', 'delivered', 'opened',
                          'replied', 'bounced', 'failed', 'cancelled'))
);

-- Indexes for outreach_emails
CREATE INDEX IF NOT EXISTS idx_outreach_emails_job_id ON outreach_emails(job_id);
CREATE INDEX IF NOT EXISTS idx_outreach_emails_application_id ON outreach_emails(application_id);
CREATE INDEX IF NOT EXISTS idx_outreach_emails_recipient_email ON outreach_emails(recipient_email);
CREATE INDEX IF NOT EXISTS idx_outreach_emails_status ON outreach_emails(status);
CREATE INDEX IF NOT EXISTS idx_outreach_emails_scheduled_at ON outreach_emails(scheduled_at);
CREATE INDEX IF NOT EXISTS idx_outreach_emails_sent_at ON outreach_emails(sent_at DESC);
CREATE INDEX IF NOT EXISTS idx_outreach_emails_email_type ON outreach_emails(email_type);
CREATE INDEX IF NOT EXISTS idx_outreach_emails_thread_id ON outreach_emails(thread_id);

-- Composite indexes for common queries
CREATE INDEX IF NOT EXISTS idx_outreach_emails_status_scheduled
    ON outreach_emails(status, scheduled_at) WHERE status = 'scheduled';
CREATE INDEX IF NOT EXISTS idx_outreach_emails_needs_follow_up
    ON outreach_emails(sent_at, replied_at) WHERE replied_at IS NULL;

-- Email templates table for reusable content
CREATE TABLE IF NOT EXISTS email_templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    email_type TEXT NOT NULL,
    subject_template TEXT NOT NULL,
    body_template TEXT NOT NULL,
    variables TEXT[], -- list of {{variable}} placeholders used
    is_active BOOLEAN DEFAULT TRUE,
    usage_count INT DEFAULT 0,
    last_used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT email_templates_email_type_check
        CHECK (email_type IN ('initial', 'follow_up', 'thank_you', 'negotiation',
                              'networking', 'cold_outreach', 'referral_request'))
);

CREATE INDEX IF NOT EXISTS idx_email_templates_email_type ON email_templates(email_type);
CREATE INDEX IF NOT EXISTS idx_email_templates_is_active ON email_templates(is_active);

-- Apply updated_at trigger
DROP TRIGGER IF EXISTS update_outreach_emails_updated_at ON outreach_emails;
CREATE TRIGGER update_outreach_emails_updated_at BEFORE UPDATE ON outreach_emails
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_email_templates_updated_at ON email_templates;
CREATE TRIGGER update_email_templates_updated_at BEFORE UPDATE ON email_templates
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
