-- 0017_schema_reconciliation.sql
-- Reconcile the activity layer's reads/writes with the schema so the
-- end-to-end pipeline runs cleanly. All changes are additive/idempotent.

-- jobs: enrichment payload, scoring payload, scraped-company display fields,
-- enrichment + inactivity timestamps that the discovery/enrichment activities write.
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS fit_analysis JSONB;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS company_info JSONB;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS enriched_at TIMESTAMPTZ;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS inactive_at TIMESTAMPTZ;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS company_logo_url TEXT;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS company_rating NUMERIC(3, 2);
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS company_reviews_count INTEGER;

-- applications: durable follow-up history appended by FollowUpWorkflow.
ALTER TABLE applications ADD COLUMN IF NOT EXISTS follow_ups JSONB DEFAULT '[]'::jsonb;

-- interviews: lightweight status used by InterviewPrepWorkflow.
ALTER TABLE interviews ADD COLUMN IF NOT EXISTS status TEXT;

-- outreach_emails: optional scheduling note, and widen reply_sentiment to the
-- full set the reply classifier can emit.
ALTER TABLE outreach_emails ADD COLUMN IF NOT EXISTS notes TEXT;
DO $$
BEGIN
    ALTER TABLE outreach_emails DROP CONSTRAINT IF EXISTS outreach_emails_reply_sentiment_check;
    ALTER TABLE outreach_emails ADD CONSTRAINT outreach_emails_reply_sentiment_check
        CHECK (reply_sentiment IS NULL OR reply_sentiment IN
            ('positive', 'neutral', 'negative', 'rejection', 'interested', 'not_now',
             'request_info', 'auto_reply'));
END $$;

-- contacts / companies: unique indexes enable upsert-by-email and
-- upsert-by-domain used by the enrichment activities. These are non-partial so
-- `ON CONFLICT (email)` / `ON CONFLICT (domain)` can infer them; Postgres treats
-- NULLs as distinct, so multiple rows with a NULL email/domain are still allowed.
CREATE UNIQUE INDEX IF NOT EXISTS uq_contacts_email ON contacts(email);
CREATE UNIQUE INDEX IF NOT EXISTS uq_companies_domain ON companies(domain);

-- application_drafts: ApplicationWorkflow persists the generated draft here while
-- it awaits human approval (the human-in-the-loop gate).
CREATE TABLE IF NOT EXISTS application_drafts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID REFERENCES jobs(id) ON DELETE CASCADE,
    draft_data JSONB NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    status_reason TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_application_drafts_job_id ON application_drafts(job_id);

-- interview_prep: InterviewPrepWorkflow stores the assembled payload + rendered
-- prep document alongside the structured columns.
ALTER TABLE interview_prep ADD COLUMN IF NOT EXISTS prep_data JSONB;
ALTER TABLE interview_prep ADD COLUMN IF NOT EXISTS prep_document TEXT;
