-- 0003_applications_enhanced.sql
-- Enhanced applications table with detailed tracking

-- Application method
DO $$ BEGIN
    ALTER TABLE applications ADD COLUMN IF NOT EXISTS method TEXT;
    ALTER TABLE applications ADD CONSTRAINT applications_method_check
        CHECK (method IS NULL OR method IN ('direct', 'linkedin', 'referral', 'recruiter', 'email', 'other'));
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- Cover letter file path (for uploaded/generated PDFs)
ALTER TABLE applications ADD COLUMN IF NOT EXISTS cover_letter_file_path TEXT;

-- Referral tracking
ALTER TABLE applications ADD COLUMN IF NOT EXISTS referral_name TEXT;
ALTER TABLE applications ADD COLUMN IF NOT EXISTS referral_email TEXT;

-- Submission tracking
ALTER TABLE applications ADD COLUMN IF NOT EXISTS submitted_at TIMESTAMPTZ;
ALTER TABLE applications ADD COLUMN IF NOT EXISTS confirmation_received BOOLEAN DEFAULT FALSE;
ALTER TABLE applications ADD COLUMN IF NOT EXISTS confirmation_email TEXT;

-- Enhanced status with more granular states
DO $$ BEGIN
    -- Update status constraint for more detailed tracking
    ALTER TABLE applications DROP CONSTRAINT IF EXISTS applications_status_check;
    ALTER TABLE applications ADD CONSTRAINT applications_status_check
        CHECK (status IN ('draft', 'submitted', 'acknowledged', 'in_review',
                          'interviewing', 'offer', 'rejected', 'withdrawn', 'ghosted'));
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- Rejection tracking
ALTER TABLE applications ADD COLUMN IF NOT EXISTS rejection_reason TEXT;
ALTER TABLE applications ADD COLUMN IF NOT EXISTS rejection_stage TEXT;

-- Follow-up tracking
ALTER TABLE applications ADD COLUMN IF NOT EXISTS follow_up_count INT DEFAULT 0;
ALTER TABLE applications ADD COLUMN IF NOT EXISTS last_follow_up_at TIMESTAMPTZ;
ALTER TABLE applications ADD COLUMN IF NOT EXISTS next_follow_up_at TIMESTAMPTZ;

-- Application portal tracking
ALTER TABLE applications ADD COLUMN IF NOT EXISTS portal_url TEXT;
ALTER TABLE applications ADD COLUMN IF NOT EXISTS portal_username TEXT;
ALTER TABLE applications ADD COLUMN IF NOT EXISTS application_id_external TEXT;

-- Salary negotiation fields
ALTER TABLE applications ADD COLUMN IF NOT EXISTS salary_discussed INT;
ALTER TABLE applications ADD COLUMN IF NOT EXISTS salary_offered INT;

-- Create indexes for new columns
CREATE INDEX IF NOT EXISTS idx_applications_method ON applications(method);
CREATE INDEX IF NOT EXISTS idx_applications_submitted_at ON applications(submitted_at DESC);
CREATE INDEX IF NOT EXISTS idx_applications_next_follow_up ON applications(next_follow_up_at);
CREATE INDEX IF NOT EXISTS idx_applications_status_submitted ON applications(status, submitted_at DESC);
