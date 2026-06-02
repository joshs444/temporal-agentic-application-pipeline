-- 0007_contacts.sql
-- Recruiter, hiring manager, and networking contacts

CREATE TABLE IF NOT EXISTS contacts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Company association (optional - may be independent recruiter)
    company_id UUID REFERENCES companies(id) ON DELETE SET NULL,

    -- Basic information
    name TEXT NOT NULL,
    first_name TEXT,
    last_name TEXT,
    email TEXT,
    phone TEXT,

    -- Professional details
    title TEXT,
    role_type TEXT, -- type of role they play in hiring
    department TEXT,
    seniority TEXT, -- 'individual', 'manager', 'director', 'vp', 'c_level'

    -- Social profiles
    linkedin_url TEXT,
    twitter_url TEXT,
    github_url TEXT,
    personal_website TEXT,

    -- Source and verification
    source TEXT, -- where we found them
    source_url TEXT,
    email_verified BOOLEAN DEFAULT FALSE,
    email_verified_at TIMESTAMPTZ,

    -- Relationship tracking
    relationship_strength TEXT DEFAULT 'cold',
    relationship_notes TEXT,
    how_we_met TEXT,
    mutual_connections TEXT[],

    -- Communication history
    first_contacted_at TIMESTAMPTZ,
    last_contacted_at TIMESTAMPTZ,
    total_emails_sent INT DEFAULT 0,
    total_emails_received INT DEFAULT 0,
    last_response_at TIMESTAMPTZ,
    response_rate FLOAT, -- percentage of emails they respond to

    -- Engagement quality
    is_responsive BOOLEAN,
    typical_response_time TEXT, -- 'same_day', 'few_days', 'week_plus', 'never'
    best_contact_method TEXT, -- 'email', 'linkedin', 'phone'

    -- Notes and context
    notes TEXT,
    interests TEXT[], -- shared interests for rapport building
    previous_companies TEXT[],

    -- Status
    is_active BOOLEAN DEFAULT TRUE, -- still at company / relevant
    do_not_contact BOOLEAN DEFAULT FALSE,

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- Constraints
    CONSTRAINT contacts_role_type_check
        CHECK (role_type IS NULL OR role_type IN
            ('recruiter', 'internal_recruiter', 'agency_recruiter', 'hiring_manager',
             'engineer', 'engineering_manager', 'hr', 'talent_acquisition',
             'referral', 'networking', 'founder', 'other')),
    CONSTRAINT contacts_relationship_strength_check
        CHECK (relationship_strength IN ('cold', 'warm', 'hot', 'friend', 'colleague')),
    CONSTRAINT contacts_source_check
        CHECK (source IS NULL OR source IN
            ('apollo', 'hunter', 'linkedin', 'referral', 'event', 'email', 'manual', 'other')),
    CONSTRAINT contacts_seniority_check
        CHECK (seniority IS NULL OR seniority IN
            ('individual', 'manager', 'senior_manager', 'director', 'vp', 'c_level'))
);

-- Indexes for contacts
CREATE INDEX IF NOT EXISTS idx_contacts_company_id ON contacts(company_id);
CREATE INDEX IF NOT EXISTS idx_contacts_email ON contacts(email);
CREATE INDEX IF NOT EXISTS idx_contacts_role_type ON contacts(role_type);
CREATE INDEX IF NOT EXISTS idx_contacts_relationship_strength ON contacts(relationship_strength);
CREATE INDEX IF NOT EXISTS idx_contacts_source ON contacts(source);
CREATE INDEX IF NOT EXISTS idx_contacts_last_contacted_at ON contacts(last_contacted_at DESC);
CREATE INDEX IF NOT EXISTS idx_contacts_is_active ON contacts(is_active) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_contacts_is_responsive ON contacts(is_responsive) WHERE is_responsive = TRUE;

-- Full text search on name
CREATE INDEX IF NOT EXISTS idx_contacts_name_search ON contacts USING GIN(to_tsvector('english', name));

-- Contact-job relationship (a contact may be relevant to multiple jobs)
CREATE TABLE IF NOT EXISTS contact_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    contact_id UUID NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
    job_id UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    relationship TEXT, -- 'recruiter', 'hiring_manager', 'interviewer', 'referrer'
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(contact_id, job_id),
    CONSTRAINT contact_jobs_relationship_check
        CHECK (relationship IS NULL OR relationship IN
            ('recruiter', 'hiring_manager', 'interviewer', 'referrer', 'team_member', 'other'))
);

CREATE INDEX IF NOT EXISTS idx_contact_jobs_contact_id ON contact_jobs(contact_id);
CREATE INDEX IF NOT EXISTS idx_contact_jobs_job_id ON contact_jobs(job_id);

-- Contact interactions log
CREATE TABLE IF NOT EXISTS contact_interactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    contact_id UUID NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
    interaction_type TEXT NOT NULL, -- 'email_sent', 'email_received', 'call', 'meeting', 'linkedin_message'
    direction TEXT NOT NULL, -- 'outbound', 'inbound'
    subject TEXT,
    summary TEXT,
    sentiment TEXT, -- 'positive', 'neutral', 'negative'
    outcome TEXT, -- 'no_response', 'interested', 'not_interested', 'referral_made', etc.
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Optional references
    outreach_email_id UUID REFERENCES outreach_emails(id) ON DELETE SET NULL,
    job_id UUID REFERENCES jobs(id) ON DELETE SET NULL,

    created_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT contact_interactions_type_check
        CHECK (interaction_type IN
            ('email_sent', 'email_received', 'call', 'video_call', 'meeting',
             'linkedin_message', 'linkedin_connection', 'event', 'coffee_chat', 'other')),
    CONSTRAINT contact_interactions_direction_check
        CHECK (direction IN ('outbound', 'inbound')),
    CONSTRAINT contact_interactions_sentiment_check
        CHECK (sentiment IS NULL OR sentiment IN ('positive', 'neutral', 'negative'))
);

CREATE INDEX IF NOT EXISTS idx_contact_interactions_contact_id ON contact_interactions(contact_id);
CREATE INDEX IF NOT EXISTS idx_contact_interactions_occurred_at ON contact_interactions(occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_contact_interactions_type ON contact_interactions(interaction_type);

-- Apply updated_at trigger
DROP TRIGGER IF EXISTS update_contacts_updated_at ON contacts;
CREATE TRIGGER update_contacts_updated_at BEFORE UPDATE ON contacts
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
