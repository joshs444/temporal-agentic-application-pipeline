-- 0014_preferred_locations.sql
-- Add preferred_locations column and fix preferred_remote constraint for multi-select

-- Add preferred_locations column (array of location strings)
ALTER TABLE resume_profiles
ADD COLUMN IF NOT EXISTS preferred_locations TEXT[];

-- Drop the old constraint that only allows single values
ALTER TABLE resume_profiles
DROP CONSTRAINT IF EXISTS resume_profiles_preferred_remote_check;

-- Add index for location-based queries
CREATE INDEX IF NOT EXISTS idx_resume_profiles_preferred_locations
ON resume_profiles USING GIN(preferred_locations);
