-- 0010_analytics.sql
-- Tracking and analytics for job search performance

-- Job events - detailed activity log
CREATE TABLE IF NOT EXISTS job_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Entity references (at least one should be set)
    job_id UUID REFERENCES jobs(id) ON DELETE CASCADE,
    application_id UUID REFERENCES applications(id) ON DELETE CASCADE,
    contact_id UUID REFERENCES contacts(id) ON DELETE SET NULL,
    company_id UUID REFERENCES companies(id) ON DELETE SET NULL,

    -- Event details
    event_type TEXT NOT NULL,
    event_subtype TEXT, -- more specific categorization
    event_data JSONB, -- flexible additional data

    -- Context
    source TEXT, -- 'user', 'system', 'api', 'email'
    user_agent TEXT, -- if from web interface

    -- Timestamp
    created_at TIMESTAMPTZ DEFAULT NOW(),

    -- Constraints
    CONSTRAINT job_events_event_type_check
        CHECK (event_type IN (
            -- Discovery events
            'job_discovered', 'job_viewed', 'job_saved', 'job_dismissed',
            -- Application events
            'application_started', 'application_submitted', 'application_acknowledged',
            'application_in_review', 'application_rejected', 'application_withdrawn',
            -- Interview events
            'interview_scheduled', 'interview_completed', 'interview_cancelled',
            'interview_passed', 'interview_failed',
            -- Offer events
            'offer_received', 'offer_accepted', 'offer_declined', 'offer_negotiating',
            -- Communication events
            'email_sent', 'email_opened', 'email_replied', 'email_bounced',
            -- Contact events
            'contact_added', 'contact_reached_out', 'contact_responded',
            -- Company events
            'company_researched', 'company_targeted',
            -- General events
            'note_added', 'status_changed', 'score_updated'
        ))
);

-- Indexes for job_events
CREATE INDEX IF NOT EXISTS idx_job_events_job_id ON job_events(job_id);
CREATE INDEX IF NOT EXISTS idx_job_events_application_id ON job_events(application_id);
CREATE INDEX IF NOT EXISTS idx_job_events_contact_id ON job_events(contact_id);
CREATE INDEX IF NOT EXISTS idx_job_events_event_type ON job_events(event_type);
CREATE INDEX IF NOT EXISTS idx_job_events_created_at ON job_events(created_at DESC);

-- Composite indexes for common queries
CREATE INDEX IF NOT EXISTS idx_job_events_job_type_date ON job_events(job_id, event_type, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_job_events_type_date ON job_events(event_type, created_at DESC);

-- Daily statistics - aggregated metrics
CREATE TABLE IF NOT EXISTS daily_stats (
    date DATE PRIMARY KEY,

    -- Job discovery
    jobs_discovered INT DEFAULT 0,
    jobs_viewed INT DEFAULT 0,
    jobs_saved INT DEFAULT 0,
    jobs_dismissed INT DEFAULT 0,

    -- Applications
    applications_started INT DEFAULT 0,
    applications_submitted INT DEFAULT 0,
    applications_acknowledged INT DEFAULT 0,

    -- Interview pipeline
    interviews_scheduled INT DEFAULT 0,
    interviews_completed INT DEFAULT 0,
    interviews_passed INT DEFAULT 0,
    interviews_failed INT DEFAULT 0,

    -- Outcomes
    offers_received INT DEFAULT 0,
    offers_accepted INT DEFAULT 0,
    rejections_received INT DEFAULT 0,

    -- Communications
    emails_sent INT DEFAULT 0,
    emails_opened INT DEFAULT 0,
    emails_replied INT DEFAULT 0,
    emails_bounced INT DEFAULT 0,

    -- Contacts
    contacts_added INT DEFAULT 0,
    contacts_reached INT DEFAULT 0,
    contacts_responded INT DEFAULT 0,

    -- Quality metrics
    avg_fit_score_discovered FLOAT,
    avg_fit_score_applied FLOAT,

    -- Time spent (if tracking)
    time_spent_minutes INT,

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_daily_stats_date ON daily_stats(date DESC);

-- Weekly summary stats (for trend analysis)
CREATE TABLE IF NOT EXISTS weekly_stats (
    week_start DATE PRIMARY KEY, -- Monday of the week

    -- Funnel metrics
    jobs_discovered INT DEFAULT 0,
    jobs_applied INT DEFAULT 0,
    application_rate FLOAT, -- applied / discovered

    interviews_scheduled INT DEFAULT 0,
    interview_rate FLOAT, -- interviews / applied

    offers_received INT DEFAULT 0,
    offer_rate FLOAT, -- offers / interviews

    -- Response metrics
    response_count INT DEFAULT 0,
    response_rate FLOAT,
    avg_response_time_hours FLOAT,

    -- Rejection analysis
    rejections_total INT DEFAULT 0,
    rejections_no_response INT DEFAULT 0,
    rejections_after_apply INT DEFAULT 0,
    rejections_after_interview INT DEFAULT 0,

    -- Quality metrics
    avg_fit_score FLOAT,
    high_fit_jobs_discovered INT DEFAULT 0, -- above 0.7

    -- Effort tracking
    applications_per_day FLOAT,
    emails_per_day FLOAT,

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_weekly_stats_week_start ON weekly_stats(week_start DESC);

-- Pipeline snapshot - current state of the job search funnel
CREATE TABLE IF NOT EXISTS pipeline_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    snapshot_date DATE NOT NULL,

    -- Current pipeline counts
    jobs_new INT DEFAULT 0,
    jobs_interested INT DEFAULT 0,
    jobs_applying INT DEFAULT 0,
    applications_submitted INT DEFAULT 0,
    applications_in_review INT DEFAULT 0,
    interviews_scheduled INT DEFAULT 0,
    interviews_in_progress INT DEFAULT 0,
    offers_pending INT DEFAULT 0,

    -- Totals
    total_active_opportunities INT DEFAULT 0,
    total_closed_won INT DEFAULT 0, -- accepted offers
    total_closed_lost INT DEFAULT 0, -- rejections + withdrawals

    -- Age metrics (how long things sit in each stage)
    avg_days_in_new FLOAT,
    avg_days_to_apply FLOAT,
    avg_days_to_interview FLOAT,
    avg_days_to_offer FLOAT,

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(snapshot_date)
);

CREATE INDEX IF NOT EXISTS idx_pipeline_snapshots_date ON pipeline_snapshots(snapshot_date DESC);

-- Goal tracking
CREATE TABLE IF NOT EXISTS goals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Goal definition
    name TEXT NOT NULL,
    description TEXT,
    metric TEXT NOT NULL, -- 'applications_per_week', 'interviews_per_week', etc.
    target_value INT NOT NULL,

    -- Time period
    period TEXT NOT NULL, -- 'daily', 'weekly', 'monthly'
    start_date DATE,
    end_date DATE,

    -- Current progress
    current_value INT DEFAULT 0,
    last_updated_at TIMESTAMPTZ,

    -- Status
    is_active BOOLEAN DEFAULT TRUE,
    achieved BOOLEAN DEFAULT FALSE,
    achieved_at TIMESTAMPTZ,

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT goals_period_check
        CHECK (period IN ('daily', 'weekly', 'monthly')),
    CONSTRAINT goals_metric_check
        CHECK (metric IN (
            'applications_per_day', 'applications_per_week', 'applications_per_month',
            'interviews_per_week', 'interviews_per_month',
            'emails_per_day', 'emails_per_week',
            'contacts_per_week', 'networking_events_per_month',
            'jobs_reviewed_per_day'
        ))
);

CREATE INDEX IF NOT EXISTS idx_goals_is_active ON goals(is_active) WHERE is_active = TRUE;

-- Function to aggregate daily stats from events
CREATE OR REPLACE FUNCTION aggregate_daily_stats(target_date DATE)
RETURNS VOID AS $$
BEGIN
    INSERT INTO daily_stats (date,
        jobs_discovered, jobs_viewed, jobs_saved, jobs_dismissed,
        applications_started, applications_submitted, applications_acknowledged,
        interviews_scheduled, interviews_completed, interviews_passed, interviews_failed,
        offers_received, rejections_received,
        emails_sent, emails_opened, emails_replied, emails_bounced,
        contacts_added, contacts_reached, contacts_responded
    )
    SELECT
        target_date,
        COUNT(*) FILTER (WHERE event_type = 'job_discovered'),
        COUNT(*) FILTER (WHERE event_type = 'job_viewed'),
        COUNT(*) FILTER (WHERE event_type = 'job_saved'),
        COUNT(*) FILTER (WHERE event_type = 'job_dismissed'),
        COUNT(*) FILTER (WHERE event_type = 'application_started'),
        COUNT(*) FILTER (WHERE event_type = 'application_submitted'),
        COUNT(*) FILTER (WHERE event_type = 'application_acknowledged'),
        COUNT(*) FILTER (WHERE event_type = 'interview_scheduled'),
        COUNT(*) FILTER (WHERE event_type = 'interview_completed'),
        COUNT(*) FILTER (WHERE event_type = 'interview_passed'),
        COUNT(*) FILTER (WHERE event_type = 'interview_failed'),
        COUNT(*) FILTER (WHERE event_type = 'offer_received'),
        COUNT(*) FILTER (WHERE event_type = 'application_rejected'),
        COUNT(*) FILTER (WHERE event_type = 'email_sent'),
        COUNT(*) FILTER (WHERE event_type = 'email_opened'),
        COUNT(*) FILTER (WHERE event_type = 'email_replied'),
        COUNT(*) FILTER (WHERE event_type = 'email_bounced'),
        COUNT(*) FILTER (WHERE event_type = 'contact_added'),
        COUNT(*) FILTER (WHERE event_type = 'contact_reached_out'),
        COUNT(*) FILTER (WHERE event_type = 'contact_responded')
    FROM job_events
    WHERE created_at::date = target_date
    ON CONFLICT (date) DO UPDATE SET
        jobs_discovered = EXCLUDED.jobs_discovered,
        jobs_viewed = EXCLUDED.jobs_viewed,
        jobs_saved = EXCLUDED.jobs_saved,
        jobs_dismissed = EXCLUDED.jobs_dismissed,
        applications_started = EXCLUDED.applications_started,
        applications_submitted = EXCLUDED.applications_submitted,
        applications_acknowledged = EXCLUDED.applications_acknowledged,
        interviews_scheduled = EXCLUDED.interviews_scheduled,
        interviews_completed = EXCLUDED.interviews_completed,
        interviews_passed = EXCLUDED.interviews_passed,
        interviews_failed = EXCLUDED.interviews_failed,
        offers_received = EXCLUDED.offers_received,
        rejections_received = EXCLUDED.rejections_received,
        emails_sent = EXCLUDED.emails_sent,
        emails_opened = EXCLUDED.emails_opened,
        emails_replied = EXCLUDED.emails_replied,
        emails_bounced = EXCLUDED.emails_bounced,
        contacts_added = EXCLUDED.contacts_added,
        contacts_reached = EXCLUDED.contacts_reached,
        contacts_responded = EXCLUDED.contacts_responded,
        updated_at = NOW();
END;
$$ LANGUAGE plpgsql;

-- Apply updated_at triggers
DROP TRIGGER IF EXISTS update_daily_stats_updated_at ON daily_stats;
CREATE TRIGGER update_daily_stats_updated_at BEFORE UPDATE ON daily_stats
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_weekly_stats_updated_at ON weekly_stats;
CREATE TRIGGER update_weekly_stats_updated_at BEFORE UPDATE ON weekly_stats
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_goals_updated_at ON goals;
CREATE TRIGGER update_goals_updated_at BEFORE UPDATE ON goals
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
