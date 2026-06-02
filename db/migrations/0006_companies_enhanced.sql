-- 0006_companies_enhanced.sql
-- Enhanced companies table with detailed intelligence

-- External ID references
ALTER TABLE companies ADD COLUMN IF NOT EXISTS apollo_id TEXT;
ALTER TABLE companies ADD COLUMN IF NOT EXISTS linkedin_id TEXT;
ALTER TABLE companies ADD COLUMN IF NOT EXISTS crunchbase_id TEXT;

-- Basic info enhancements
ALTER TABLE companies ADD COLUMN IF NOT EXISTS employee_count INT;
ALTER TABLE companies ADD COLUMN IF NOT EXISTS employee_range TEXT; -- '1-10', '11-50', etc (redundant but useful for search)
ALTER TABLE companies ADD COLUMN IF NOT EXISTS website TEXT;
ALTER TABLE companies ADD COLUMN IF NOT EXISTS logo_url TEXT;

-- Technology stack
ALTER TABLE companies ADD COLUMN IF NOT EXISTS tech_stack TEXT[];
ALTER TABLE companies ADD COLUMN IF NOT EXISTS engineering_blog TEXT;

-- Glassdoor data
ALTER TABLE companies ADD COLUMN IF NOT EXISTS glassdoor_review_count INT;
ALTER TABLE companies ADD COLUMN IF NOT EXISTS glassdoor_ceo_approval FLOAT;
ALTER TABLE companies ADD COLUMN IF NOT EXISTS glassdoor_recommend_percent FLOAT;

-- LinkedIn data
ALTER TABLE companies ADD COLUMN IF NOT EXISTS linkedin_followers INT;
ALTER TABLE companies ADD COLUMN IF NOT EXISTS careers_page TEXT;

-- News and updates
ALTER TABLE companies ADD COLUMN IF NOT EXISTS recent_news JSONB;
ALTER TABLE companies ADD COLUMN IF NOT EXISTS last_news_update TIMESTAMPTZ;

-- Hiring signals
ALTER TABLE companies ADD COLUMN IF NOT EXISTS hiring_velocity INT; -- jobs posted in last 30 days
ALTER TABLE companies ADD COLUMN IF NOT EXISTS hiring_trend TEXT; -- 'growing', 'stable', 'shrinking'
ALTER TABLE companies ADD COLUMN IF NOT EXISTS open_roles_count INT;
ALTER TABLE companies ADD COLUMN IF NOT EXISTS open_engineering_roles INT;

-- Culture and process insights
ALTER TABLE companies ADD COLUMN IF NOT EXISTS culture_notes TEXT;
ALTER TABLE companies ADD COLUMN IF NOT EXISTS values TEXT[];
ALTER TABLE companies ADD COLUMN IF NOT EXISTS interview_process TEXT;
ALTER TABLE companies ADD COLUMN IF NOT EXISTS interview_difficulty FLOAT; -- 1-5 average
ALTER TABLE companies ADD COLUMN IF NOT EXISTS interview_experience FLOAT; -- 1-5 average

-- Compensation data
ALTER TABLE companies ADD COLUMN IF NOT EXISTS salary_data JSONB;
ALTER TABLE companies ADD COLUMN IF NOT EXISTS equity_data JSONB;
ALTER TABLE companies ADD COLUMN IF NOT EXISTS benefits_summary TEXT[];

-- Personal notes and targeting
ALTER TABLE companies ADD COLUMN IF NOT EXISTS personal_notes TEXT;
ALTER TABLE companies ADD COLUMN IF NOT EXISTS target_priority INT; -- 1-5
ALTER TABLE companies ADD COLUMN IF NOT EXISTS why_interested TEXT;
ALTER TABLE companies ADD COLUMN IF NOT EXISTS concerns TEXT[];
ALTER TABLE companies ADD COLUMN IF NOT EXISTS is_target BOOLEAN DEFAULT FALSE;

-- Networking
ALTER TABLE companies ADD COLUMN IF NOT EXISTS connections_count INT DEFAULT 0;
ALTER TABLE companies ADD COLUMN IF NOT EXISTS has_referral BOOLEAN DEFAULT FALSE;

-- Constraints
DO $$ BEGIN
    ALTER TABLE companies ADD CONSTRAINT companies_target_priority_check
        CHECK (target_priority IS NULL OR (target_priority >= 1 AND target_priority <= 5));
    ALTER TABLE companies ADD CONSTRAINT companies_hiring_trend_check
        CHECK (hiring_trend IS NULL OR hiring_trend IN ('growing', 'stable', 'shrinking', 'unknown'));
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- Create indexes for new columns
CREATE INDEX IF NOT EXISTS idx_companies_apollo_id ON companies(apollo_id);
CREATE INDEX IF NOT EXISTS idx_companies_domain ON companies(domain);
CREATE INDEX IF NOT EXISTS idx_companies_industry ON companies(industry);
CREATE INDEX IF NOT EXISTS idx_companies_employee_count ON companies(employee_count);
CREATE INDEX IF NOT EXISTS idx_companies_glassdoor_rating ON companies(glassdoor_rating DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS idx_companies_funding_stage ON companies(funding_stage);
CREATE INDEX IF NOT EXISTS idx_companies_is_target ON companies(is_target) WHERE is_target = TRUE;
CREATE INDEX IF NOT EXISTS idx_companies_target_priority ON companies(target_priority DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS idx_companies_has_referral ON companies(has_referral) WHERE has_referral = TRUE;

-- GIN index for tech stack searching
CREATE INDEX IF NOT EXISTS idx_companies_tech_stack ON companies USING GIN(tech_stack);

-- Company funding rounds (for detailed funding history)
CREATE TABLE IF NOT EXISTS company_funding_rounds (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    round_type TEXT NOT NULL, -- 'seed', 'series_a', 'series_b', etc.
    amount BIGINT, -- in cents
    currency TEXT DEFAULT 'USD',
    announced_date DATE,
    lead_investors TEXT[],
    all_investors TEXT[],
    valuation BIGINT, -- post-money valuation in cents
    source TEXT,
    source_url TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_company_funding_rounds_company_id ON company_funding_rounds(company_id);
CREATE INDEX IF NOT EXISTS idx_company_funding_rounds_announced_date ON company_funding_rounds(announced_date DESC);

-- Company news articles
CREATE TABLE IF NOT EXISTS company_news (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    url TEXT,
    source TEXT,
    published_at TIMESTAMPTZ,
    summary TEXT,
    sentiment TEXT, -- 'positive', 'neutral', 'negative'
    relevance_score FLOAT,
    created_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT company_news_sentiment_check
        CHECK (sentiment IS NULL OR sentiment IN ('positive', 'neutral', 'negative'))
);

CREATE INDEX IF NOT EXISTS idx_company_news_company_id ON company_news(company_id);
CREATE INDEX IF NOT EXISTS idx_company_news_published_at ON company_news(published_at DESC);
