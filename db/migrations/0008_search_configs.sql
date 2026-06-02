-- 0008_search_configs.sql
-- Saved search configurations for job discovery

-- Drop old table if migrating from search_queries
-- (keeping search_queries for backwards compatibility, this is the enhanced version)

CREATE TABLE IF NOT EXISTS search_configs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Basic search parameters
    name TEXT NOT NULL,
    description TEXT,
    query TEXT, -- main search query/keywords

    -- Location settings
    location TEXT,
    location_radius_miles INT,
    remote_only BOOLEAN DEFAULT FALSE,
    include_remote BOOLEAN DEFAULT TRUE,
    locations TEXT[], -- multiple location support
    excluded_locations TEXT[],

    -- Salary requirements
    salary_min INT,
    salary_max INT,
    salary_currency TEXT DEFAULT 'USD',

    -- Experience and seniority
    experience_levels TEXT[],
    years_experience_min INT,
    years_experience_max INT,

    -- Company filters
    company_sizes TEXT[], -- '1-10', '11-50', etc.
    industries TEXT[],
    excluded_companies TEXT[],
    target_companies TEXT[], -- prioritize these
    funding_stages TEXT[], -- 'seed', 'series_a', etc.

    -- Job characteristics
    job_types TEXT[], -- 'full_time', 'contract', etc.

    -- Keywords
    keywords TEXT[], -- must-have keywords
    negative_keywords TEXT[], -- exclude jobs with these
    title_keywords TEXT[], -- keywords that should be in title

    -- Source settings
    sources TEXT[], -- which job boards to search

    -- Scoring and filtering
    min_fit_score FLOAT, -- only show jobs above this score
    auto_hide_below_score FLOAT, -- auto-dismiss jobs below this

    -- Automation settings
    is_active BOOLEAN DEFAULT TRUE,
    run_frequency TEXT DEFAULT 'daily',
    last_run_at TIMESTAMPTZ,
    next_run_at TIMESTAMPTZ,
    last_run_job_count INT,
    total_jobs_found INT DEFAULT 0,

    -- Notifications
    notify_new_jobs BOOLEAN DEFAULT TRUE,
    notify_high_fit_only BOOLEAN DEFAULT FALSE,
    notification_email TEXT,
    slack_webhook TEXT,

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- Constraints
    CONSTRAINT search_configs_run_frequency_check
        CHECK (run_frequency IN ('hourly', 'daily', 'weekly', 'manual')),
    CONSTRAINT search_configs_min_fit_score_check
        CHECK (min_fit_score IS NULL OR (min_fit_score >= 0 AND min_fit_score <= 1)),
    CONSTRAINT search_configs_auto_hide_score_check
        CHECK (auto_hide_below_score IS NULL OR (auto_hide_below_score >= 0 AND auto_hide_below_score <= 1))
);

-- Indexes for search_configs
CREATE INDEX IF NOT EXISTS idx_search_configs_is_active ON search_configs(is_active) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_search_configs_next_run_at ON search_configs(next_run_at);
CREATE INDEX IF NOT EXISTS idx_search_configs_name ON search_configs(name);

-- GIN indexes for array searches
CREATE INDEX IF NOT EXISTS idx_search_configs_keywords ON search_configs USING GIN(keywords);
CREATE INDEX IF NOT EXISTS idx_search_configs_industries ON search_configs USING GIN(industries);
CREATE INDEX IF NOT EXISTS idx_search_configs_experience_levels ON search_configs USING GIN(experience_levels);

-- Search run history (track each execution)
CREATE TABLE IF NOT EXISTS search_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    search_config_id UUID NOT NULL REFERENCES search_configs(id) ON DELETE CASCADE,

    -- Run details
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    duration_ms INT,
    status TEXT NOT NULL DEFAULT 'running',

    -- Results
    jobs_found INT DEFAULT 0,
    new_jobs INT DEFAULT 0, -- jobs not previously seen
    high_fit_jobs INT DEFAULT 0, -- jobs above threshold

    -- Errors
    error_message TEXT,
    error_details JSONB,

    -- API usage (for rate limiting awareness)
    api_calls_made INT DEFAULT 0,
    api_credits_used INT DEFAULT 0,

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT search_runs_status_check
        CHECK (status IN ('running', 'completed', 'failed', 'cancelled'))
);

CREATE INDEX IF NOT EXISTS idx_search_runs_search_config_id ON search_runs(search_config_id);
CREATE INDEX IF NOT EXISTS idx_search_runs_started_at ON search_runs(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_search_runs_status ON search_runs(status);

-- Track which jobs came from which search
CREATE TABLE IF NOT EXISTS search_job_sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    search_config_id UUID NOT NULL REFERENCES search_configs(id) ON DELETE CASCADE,
    search_run_id UUID REFERENCES search_runs(id) ON DELETE SET NULL,
    job_id UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,

    -- Discovery details
    discovered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    initial_fit_score FLOAT, -- score at time of discovery

    UNIQUE(search_config_id, job_id)
);

CREATE INDEX IF NOT EXISTS idx_search_job_sources_search_config_id ON search_job_sources(search_config_id);
CREATE INDEX IF NOT EXISTS idx_search_job_sources_job_id ON search_job_sources(job_id);
CREATE INDEX IF NOT EXISTS idx_search_job_sources_discovered_at ON search_job_sources(discovered_at DESC);

-- Apply updated_at trigger
DROP TRIGGER IF EXISTS update_search_configs_updated_at ON search_configs;
CREATE TRIGGER update_search_configs_updated_at BEFORE UPDATE ON search_configs
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
