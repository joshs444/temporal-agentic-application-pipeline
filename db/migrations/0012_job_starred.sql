-- 0012_job_starred.sql
-- Add starred column for bookmarking jobs

ALTER TABLE jobs ADD COLUMN IF NOT EXISTS starred BOOLEAN DEFAULT FALSE;
CREATE INDEX IF NOT EXISTS idx_jobs_starred ON jobs(starred) WHERE starred = TRUE;
