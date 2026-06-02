-- 0009_resume_profiles.sql
-- Resume and profile management for targeted applications

CREATE TABLE IF NOT EXISTS resume_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Profile identification
    name TEXT NOT NULL, -- e.g., "AI/ML Focus", "Full Stack", "Leadership"
    description TEXT,
    is_default BOOLEAN DEFAULT FALSE,

    -- File storage
    file_path TEXT, -- path to PDF/DOCX
    file_url TEXT, -- S3/MinIO URL
    file_hash TEXT, -- for detecting changes
    last_file_updated TIMESTAMPTZ,

    -- Parsed resume data (structured)
    parsed_data JSONB,
    raw_text TEXT, -- extracted text content

    -- Skills inventory
    skills TEXT[],
    skill_levels JSONB, -- {"python": "expert", "react": "intermediate"}
    certifications TEXT[],

    -- Experience summary
    experience_years INT,
    experience_summary TEXT,
    key_achievements TEXT[],
    notable_projects JSONB,

    -- Education
    education JSONB,

    -- Targeting preferences
    target_titles TEXT[],
    target_industries TEXT[],
    target_company_sizes TEXT[],
    preferred_remote TEXT, -- 'remote', 'hybrid', 'onsite', 'any'

    -- Salary expectations
    salary_expectation_min INT,
    salary_expectation_max INT,
    salary_currency TEXT DEFAULT 'USD',
    open_to_equity BOOLEAN DEFAULT TRUE,
    equity_preference TEXT, -- 'prefer_salary', 'balanced', 'prefer_equity'

    -- Availability
    available_start_date DATE,
    notice_period_weeks INT,

    -- Keywords for ATS optimization
    ats_keywords TEXT[],

    -- Usage tracking
    times_used INT DEFAULT 0,
    last_used_at TIMESTAMPTZ,
    success_rate FLOAT, -- percentage of applications that got response

    -- Version control
    version INT DEFAULT 1,
    parent_profile_id UUID REFERENCES resume_profiles(id) ON DELETE SET NULL,

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- Constraints
    CONSTRAINT resume_profiles_preferred_remote_check
        CHECK (preferred_remote IS NULL OR preferred_remote IN ('remote', 'hybrid', 'onsite', 'any')),
    CONSTRAINT resume_profiles_equity_preference_check
        CHECK (equity_preference IS NULL OR equity_preference IN ('prefer_salary', 'balanced', 'prefer_equity'))
);

-- Ensure only one default profile
CREATE UNIQUE INDEX IF NOT EXISTS idx_resume_profiles_single_default
    ON resume_profiles(is_default) WHERE is_default = TRUE;

-- Other indexes
CREATE INDEX IF NOT EXISTS idx_resume_profiles_name ON resume_profiles(name);
CREATE INDEX IF NOT EXISTS idx_resume_profiles_is_default ON resume_profiles(is_default);
CREATE INDEX IF NOT EXISTS idx_resume_profiles_last_used ON resume_profiles(last_used_at DESC);

-- GIN indexes for skill/title matching
CREATE INDEX IF NOT EXISTS idx_resume_profiles_skills ON resume_profiles USING GIN(skills);
CREATE INDEX IF NOT EXISTS idx_resume_profiles_target_titles ON resume_profiles USING GIN(target_titles);
CREATE INDEX IF NOT EXISTS idx_resume_profiles_target_industries ON resume_profiles USING GIN(target_industries);
CREATE INDEX IF NOT EXISTS idx_resume_profiles_ats_keywords ON resume_profiles USING GIN(ats_keywords);

-- Resume-Application tracking (which resume used for which application)
CREATE TABLE IF NOT EXISTS resume_applications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    resume_profile_id UUID NOT NULL REFERENCES resume_profiles(id) ON DELETE CASCADE,
    application_id UUID NOT NULL REFERENCES applications(id) ON DELETE CASCADE,

    -- Customization for this application
    customized BOOLEAN DEFAULT FALSE,
    customization_notes TEXT,
    tailored_summary TEXT, -- modified summary for this job
    highlighted_skills TEXT[], -- skills emphasized for this role

    -- Outcome tracking
    outcome TEXT, -- 'no_response', 'rejected', 'interview', 'offer'

    created_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(application_id), -- one resume per application
    CONSTRAINT resume_applications_outcome_check
        CHECK (outcome IS NULL OR outcome IN
            ('no_response', 'rejected', 'interview', 'offer'))
);

CREATE INDEX IF NOT EXISTS idx_resume_applications_resume_profile_id ON resume_applications(resume_profile_id);
CREATE INDEX IF NOT EXISTS idx_resume_applications_application_id ON resume_applications(application_id);
CREATE INDEX IF NOT EXISTS idx_resume_applications_outcome ON resume_applications(outcome);

-- Cover letter templates associated with resume profiles
CREATE TABLE IF NOT EXISTS cover_letter_templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    resume_profile_id UUID REFERENCES resume_profiles(id) ON DELETE SET NULL,

    name TEXT NOT NULL,
    description TEXT,

    -- Template content with placeholders
    template_content TEXT NOT NULL,
    available_variables TEXT[], -- e.g., '{{company_name}}', '{{job_title}}'

    -- Targeting
    target_industries TEXT[],
    target_company_sizes TEXT[],
    target_job_types TEXT[],

    -- Usage
    times_used INT DEFAULT 0,
    last_used_at TIMESTAMPTZ,

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_cover_letter_templates_resume_profile_id ON cover_letter_templates(resume_profile_id);
CREATE INDEX IF NOT EXISTS idx_cover_letter_templates_name ON cover_letter_templates(name);

-- Apply updated_at triggers
DROP TRIGGER IF EXISTS update_resume_profiles_updated_at ON resume_profiles;
CREATE TRIGGER update_resume_profiles_updated_at BEFORE UPDATE ON resume_profiles
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_cover_letter_templates_updated_at ON cover_letter_templates;
CREATE TRIGGER update_cover_letter_templates_updated_at BEFORE UPDATE ON cover_letter_templates
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
