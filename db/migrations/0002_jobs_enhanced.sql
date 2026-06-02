-- 0002_jobs_enhanced.sql
-- Enhanced jobs table with additional fields for better tracking and fit analysis

-- Add job_type enum-like constraint
DO $$ BEGIN
    ALTER TABLE jobs ADD COLUMN IF NOT EXISTS job_type TEXT;
    ALTER TABLE jobs ADD CONSTRAINT jobs_job_type_check
        CHECK (job_type IS NULL OR job_type IN ('full_time', 'contract', 'part_time', 'internship'));
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- Add experience_level with constraint
DO $$ BEGIN
    ALTER TABLE jobs ADD COLUMN IF NOT EXISTS experience_level TEXT;
    ALTER TABLE jobs ADD CONSTRAINT jobs_experience_level_check
        CHECK (experience_level IS NULL OR experience_level IN
            ('entry', 'mid', 'senior', 'staff', 'principal', 'director', 'vp', 'c_level'));
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- Add requirements as JSONB (parsed skills/requirements structure)
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS requirements_parsed JSONB;

-- Add benefits JSONB
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS benefits JSONB;

-- Fit scoring fields (0-1 scale)
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS fit_score FLOAT;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS fit_reasoning TEXT;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS skills_matched TEXT[];
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS skills_missing TEXT[];

-- Add fit_score constraint
DO $$ BEGIN
    ALTER TABLE jobs ADD CONSTRAINT jobs_fit_score_check
        CHECK (fit_score IS NULL OR (fit_score >= 0 AND fit_score <= 1));
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- Enhanced status tracking
DO $$ BEGIN
    -- Drop the old column if it exists and recreate with proper constraint
    -- First add new status column if not exists
    ALTER TABLE jobs ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'new';
    ALTER TABLE jobs ADD CONSTRAINT jobs_status_check
        CHECK (status IN ('new', 'interested', 'applying', 'applied', 'interviewing',
                          'offer', 'rejected', 'withdrawn', 'closed', 'not_interested'));
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- Priority (1-5, user can set importance)
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS priority INT DEFAULT 3;
DO $$ BEGIN
    ALTER TABLE jobs ADD CONSTRAINT jobs_priority_check
        CHECK (priority IS NULL OR (priority >= 1 AND priority <= 5));
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- User notes
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS notes TEXT;

-- Key date tracking
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS applied_at TIMESTAMPTZ;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS rejected_at TIMESTAMPTZ;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS offer_at TIMESTAMPTZ;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS deadline TIMESTAMPTZ;

-- Company reference (optional FK to companies table)
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS company_id UUID;
DO $$ BEGIN
    ALTER TABLE jobs ADD CONSTRAINT jobs_company_id_fkey
        FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE SET NULL;
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- Create indexes for new columns
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_fit_score ON jobs(fit_score DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS idx_jobs_priority ON jobs(priority DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_deadline ON jobs(deadline);
CREATE INDEX IF NOT EXISTS idx_jobs_job_type ON jobs(job_type);
CREATE INDEX IF NOT EXISTS idx_jobs_experience_level ON jobs(experience_level);
CREATE INDEX IF NOT EXISTS idx_jobs_remote_type ON jobs(remote_type);
CREATE INDEX IF NOT EXISTS idx_jobs_company_id ON jobs(company_id);

-- GIN index for skills arrays
CREATE INDEX IF NOT EXISTS idx_jobs_skills_matched ON jobs USING GIN(skills_matched);
CREATE INDEX IF NOT EXISTS idx_jobs_skills_missing ON jobs USING GIN(skills_missing);

-- Composite indexes for common queries
CREATE INDEX IF NOT EXISTS idx_jobs_status_fit_score ON jobs(status, fit_score DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS idx_jobs_status_priority ON jobs(status, priority DESC);
