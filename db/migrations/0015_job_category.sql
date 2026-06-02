-- 0015_job_category.sql
-- Add category column for job type bucketing (AI/ML, Full Stack, Backend, etc.)

ALTER TABLE jobs ADD COLUMN IF NOT EXISTS category TEXT;

-- Add constraint for valid categories
DO $$ BEGIN
    ALTER TABLE jobs ADD CONSTRAINT jobs_category_check
        CHECK (category IS NULL OR category IN (
            'ai_ml',          -- AI/ML Engineer, Data Scientist, ML Platform
            'full_stack',     -- Full Stack Engineer
            'backend',        -- Backend Engineer, API Engineer
            'frontend',       -- Frontend Engineer, UI Engineer
            'devops',         -- DevOps, SRE, Platform Engineer, Infrastructure
            'data',           -- Data Engineer, Analytics Engineer
            'mobile',         -- iOS, Android, Mobile Engineer
            'security',       -- Security Engineer
            'management',     -- Engineering Manager, Tech Lead, Director
            'other'           -- Uncategorized
        ));
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- Create index for category filtering
CREATE INDEX IF NOT EXISTS idx_jobs_category ON jobs(category);

-- Composite index for category + status filtering
CREATE INDEX IF NOT EXISTS idx_jobs_category_status ON jobs(category, status);
