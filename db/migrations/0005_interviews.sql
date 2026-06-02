-- 0005_interviews.sql
-- Enhanced interviews table with comprehensive tracking

-- Add new columns to existing interviews table
ALTER TABLE interviews ADD COLUMN IF NOT EXISTS round INT DEFAULT 1;

-- Enhanced interview_type (rename from 'stage' if needed)
DO $$ BEGIN
    ALTER TABLE interviews ADD COLUMN IF NOT EXISTS interview_type TEXT;
    ALTER TABLE interviews ADD CONSTRAINT interviews_interview_type_check
        CHECK (interview_type IS NULL OR interview_type IN
            ('phone_screen', 'recruiter_screen', 'technical', 'coding', 'system_design',
             'behavioral', 'hiring_manager', 'team', 'culture', 'onsite', 'final', 'offer_call'));
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- Interviewer LinkedIn profiles
ALTER TABLE interviews ADD COLUMN IF NOT EXISTS interviewer_linkedin TEXT[];

-- Video/location details
ALTER TABLE interviews ADD COLUMN IF NOT EXISTS meeting_url TEXT;
ALTER TABLE interviews ADD COLUMN IF NOT EXISTS meeting_platform TEXT; -- 'zoom', 'teams', 'meet', 'phone'
ALTER TABLE interviews ADD COLUMN IF NOT EXISTS dial_in_number TEXT;
ALTER TABLE interviews ADD COLUMN IF NOT EXISTS passcode TEXT;

-- Questions tracking
ALTER TABLE interviews ADD COLUMN IF NOT EXISTS questions_asked JSONB;
ALTER TABLE interviews ADD COLUMN IF NOT EXISTS my_questions TEXT[];
ALTER TABLE interviews ADD COLUMN IF NOT EXISTS my_answers JSONB;

-- Enhanced outcome tracking
DO $$ BEGIN
    ALTER TABLE interviews DROP CONSTRAINT IF EXISTS interviews_outcome_check;
    ALTER TABLE interviews ADD CONSTRAINT interviews_outcome_check
        CHECK (outcome IS NULL OR outcome IN
            ('pending', 'passed', 'failed', 'rescheduled', 'cancelled', 'no_show'));
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- Next steps and follow-up
ALTER TABLE interviews ADD COLUMN IF NOT EXISTS next_steps TEXT;
ALTER TABLE interviews ADD COLUMN IF NOT EXISTS next_interview_date TIMESTAMPTZ;
ALTER TABLE interviews ADD COLUMN IF NOT EXISTS thank_you_sent BOOLEAN DEFAULT FALSE;
ALTER TABLE interviews ADD COLUMN IF NOT EXISTS thank_you_sent_at TIMESTAMPTZ;

-- Interview feedback received
ALTER TABLE interviews ADD COLUMN IF NOT EXISTS feedback_received BOOLEAN DEFAULT FALSE;
ALTER TABLE interviews ADD COLUMN IF NOT EXISTS feedback_received_at TIMESTAMPTZ;

-- Difficulty and experience rating (1-5)
ALTER TABLE interviews ADD COLUMN IF NOT EXISTS difficulty_rating INT;
ALTER TABLE interviews ADD COLUMN IF NOT EXISTS experience_rating INT;
DO $$ BEGIN
    ALTER TABLE interviews ADD CONSTRAINT interviews_difficulty_rating_check
        CHECK (difficulty_rating IS NULL OR (difficulty_rating >= 1 AND difficulty_rating <= 5));
    ALTER TABLE interviews ADD CONSTRAINT interviews_experience_rating_check
        CHECK (experience_rating IS NULL OR (experience_rating >= 1 AND experience_rating <= 5));
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- Notes about how it went
ALTER TABLE interviews ADD COLUMN IF NOT EXISTS post_interview_notes TEXT;
ALTER TABLE interviews ADD COLUMN IF NOT EXISTS things_went_well TEXT[];
ALTER TABLE interviews ADD COLUMN IF NOT EXISTS things_to_improve TEXT[];

-- Create additional indexes
CREATE INDEX IF NOT EXISTS idx_interviews_round ON interviews(round);
CREATE INDEX IF NOT EXISTS idx_interviews_interview_type ON interviews(interview_type);
CREATE INDEX IF NOT EXISTS idx_interviews_outcome ON interviews(outcome);
CREATE INDEX IF NOT EXISTS idx_interviews_thank_you_sent ON interviews(thank_you_sent) WHERE thank_you_sent = FALSE;

-- Composite index for upcoming interviews
CREATE INDEX IF NOT EXISTS idx_interviews_upcoming
    ON interviews(scheduled_at)
    WHERE outcome = 'pending' AND scheduled_at > NOW();

-- Interview preparation resources table
CREATE TABLE IF NOT EXISTS interview_prep (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    interview_id UUID REFERENCES interviews(id) ON DELETE CASCADE,

    -- Company research
    company_research TEXT,
    recent_news JSONB,
    interviewer_background JSONB,

    -- Role preparation
    role_requirements TEXT[],
    key_talking_points TEXT[],
    star_stories JSONB, -- structured STAR method stories

    -- Technical prep (if applicable)
    technical_topics TEXT[],
    practice_problems TEXT[],
    resources_reviewed TEXT[],

    -- Questions to ask
    questions_for_interviewer TEXT[],
    questions_about_role TEXT[],
    questions_about_team TEXT[],
    questions_about_company TEXT[],

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_interview_prep_interview_id ON interview_prep(interview_id);

-- Apply updated_at trigger
DROP TRIGGER IF EXISTS update_interview_prep_updated_at ON interview_prep;
CREATE TRIGGER update_interview_prep_updated_at BEFORE UPDATE ON interview_prep
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
