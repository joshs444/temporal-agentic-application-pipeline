-- 0016_source_column_size.sql
-- Increase source column size to handle longer source names from job APIs

ALTER TABLE jobs
ALTER COLUMN source TYPE VARCHAR(255);
