-- Store the actual PDF file content for viewing
ALTER TABLE resume_profiles ADD COLUMN IF NOT EXISTS file_content BYTEA;

-- Index for quick existence check
CREATE INDEX IF NOT EXISTS idx_resume_profiles_has_file
    ON resume_profiles ((file_content IS NOT NULL));
