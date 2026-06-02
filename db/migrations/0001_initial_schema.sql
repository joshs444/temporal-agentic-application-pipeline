-- 0001_initial_schema.sql
-- Initial database schema for JobHunt

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "vector";

-- Jobs table - stores discovered job postings
CREATE TABLE IF NOT EXISTS jobs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    external_id VARCHAR(255),
    source VARCHAR(50) NOT NULL, -- 'serpapi', 'linkedin', 'indeed', 'manual'
    title VARCHAR(500) NOT NULL,
    company_name VARCHAR(255) NOT NULL,
    company_url VARCHAR(500),
    location VARCHAR(255),
    remote_type VARCHAR(50), -- 'remote', 'hybrid', 'onsite'
    salary_min INTEGER,
    salary_max INTEGER,
    salary_currency VARCHAR(10) DEFAULT 'USD',
    description TEXT,
    requirements TEXT,
    url VARCHAR(1000),
    posted_at TIMESTAMP WITH TIME ZONE,
    expires_at TIMESTAMP WITH TIME ZONE,

    -- Scoring
    match_score DECIMAL(5,2), -- 0-100 score based on profile match
    score_breakdown JSONB, -- detailed scoring factors

    -- Metadata
    raw_data JSONB, -- original API response
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    UNIQUE(source, external_id)
);

-- Applications table - tracks application status
CREATE TABLE IF NOT EXISTS applications (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    job_id UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    status VARCHAR(50) NOT NULL DEFAULT 'draft', -- 'draft', 'applied', 'interviewing', 'offered', 'rejected', 'withdrawn'
    applied_at TIMESTAMP WITH TIME ZONE,

    -- Application materials
    resume_version VARCHAR(100),
    cover_letter TEXT,
    custom_answers JSONB, -- answers to application questions

    -- Tracking
    notes TEXT,
    next_action VARCHAR(255),
    next_action_date TIMESTAMP WITH TIME ZONE,

    -- Metadata
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Interviews table - tracks interview stages
CREATE TABLE IF NOT EXISTS interviews (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    application_id UUID NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
    stage VARCHAR(100) NOT NULL, -- 'phone_screen', 'technical', 'onsite', 'final'
    scheduled_at TIMESTAMP WITH TIME ZONE,
    duration_minutes INTEGER,
    location VARCHAR(500), -- URL for video or address
    interviewer_names TEXT[], -- array of interviewer names
    interviewer_titles TEXT[], -- array of titles

    -- Preparation
    prep_notes TEXT,
    questions_to_ask TEXT,

    -- Post-interview
    feedback TEXT,
    outcome VARCHAR(50), -- 'passed', 'failed', 'pending'

    -- Metadata
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Companies table - enriched company information
CREATE TABLE IF NOT EXISTS companies (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL UNIQUE,
    domain VARCHAR(255),
    industry VARCHAR(100),
    size_range VARCHAR(50), -- '1-10', '11-50', '51-200', etc.
    founded_year INTEGER,
    headquarters VARCHAR(255),
    description TEXT,

    -- Enrichment data
    linkedin_url VARCHAR(500),
    glassdoor_url VARCHAR(500),
    glassdoor_rating DECIMAL(3,2),
    funding_stage VARCHAR(50),
    total_funding BIGINT, -- in cents

    -- Metadata
    enriched_at TIMESTAMP WITH TIME ZONE,
    raw_data JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Search queries table - tracks job search configurations
CREATE TABLE IF NOT EXISTS search_queries (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    query_params JSONB NOT NULL, -- search parameters
    is_active BOOLEAN DEFAULT true,
    last_run_at TIMESTAMP WITH TIME ZONE,
    run_frequency_hours INTEGER DEFAULT 24,

    -- Metadata
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- LLM call logs - track all LLM usage
CREATE TABLE IF NOT EXISTS llm_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    model VARCHAR(100) NOT NULL,
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    total_tokens INTEGER,
    latency_ms INTEGER,
    cost_cents DECIMAL(10,4),

    -- Context
    context_type VARCHAR(50), -- 'job_scoring', 'cover_letter', 'interview_prep'
    context_id UUID, -- reference to related entity

    -- Request/Response (optional, for debugging)
    request_summary TEXT,
    response_summary TEXT,

    -- Metadata
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes for common queries
CREATE INDEX IF NOT EXISTS idx_jobs_source ON jobs(source);
CREATE INDEX IF NOT EXISTS idx_jobs_company ON jobs(company_name);
CREATE INDEX IF NOT EXISTS idx_jobs_match_score ON jobs(match_score DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_applications_status ON applications(status);
CREATE INDEX IF NOT EXISTS idx_applications_job_id ON applications(job_id);

CREATE INDEX IF NOT EXISTS idx_interviews_application_id ON interviews(application_id);
CREATE INDEX IF NOT EXISTS idx_interviews_scheduled_at ON interviews(scheduled_at);

CREATE INDEX IF NOT EXISTS idx_llm_logs_created_at ON llm_logs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_llm_logs_context ON llm_logs(context_type, context_id);

-- Add updated_at trigger function
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Apply triggers
DROP TRIGGER IF EXISTS update_jobs_updated_at ON jobs;
CREATE TRIGGER update_jobs_updated_at BEFORE UPDATE ON jobs
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_applications_updated_at ON applications;
CREATE TRIGGER update_applications_updated_at BEFORE UPDATE ON applications
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_interviews_updated_at ON interviews;
CREATE TRIGGER update_interviews_updated_at BEFORE UPDATE ON interviews
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_companies_updated_at ON companies;
CREATE TRIGGER update_companies_updated_at BEFORE UPDATE ON companies
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_search_queries_updated_at ON search_queries;
CREATE TRIGGER update_search_queries_updated_at BEFORE UPDATE ON search_queries
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
