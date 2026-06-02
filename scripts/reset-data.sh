#!/bin/bash
# Reset JobHunt database - clears all data but keeps schema
# Usage: ./scripts/reset-data.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SCRIPT_DIR/../.env" ]; then
    source "$SCRIPT_DIR/../.env"
fi

DB_URL="${JOBHUNT_DATABASE_URL:-$DATABASE_URL}"

if [ -z "$DB_URL" ]; then
    echo "Error: JOBHUNT_DATABASE_URL or DATABASE_URL not set"
    exit 1
fi

echo "WARNING: This will delete ALL data from JobHunt tables!"
echo "Tables to be cleared:"
echo "  - jobs"
echo "  - applications"
echo "  - interviews"
echo "  - companies"
echo "  - contacts"
echo "  - search_configs"
echo "  - job_events"
echo "  - llm_usage_logs"
echo ""
read -p "Are you sure? (type 'yes' to confirm): " confirm

if [ "$confirm" != "yes" ]; then
    echo "Aborted."
    exit 0
fi

echo "Clearing data..."

psql "$DB_URL" << 'EOF'
-- Clear all data (order matters due to foreign keys)
TRUNCATE TABLE interviews CASCADE;
TRUNCATE TABLE applications CASCADE;
TRUNCATE TABLE job_events CASCADE;
TRUNCATE TABLE contacts CASCADE;
TRUNCATE TABLE jobs CASCADE;
TRUNCATE TABLE companies CASCADE;
TRUNCATE TABLE search_configs CASCADE;
TRUNCATE TABLE llm_usage_logs CASCADE;

-- Keep resume_profiles but you can clear if needed:
-- TRUNCATE TABLE resume_profiles CASCADE;

-- Reset sequences
-- (TRUNCATE with CASCADE should handle this)

SELECT 'Data cleared successfully!' as status;
SELECT 'Tables reset:' as info;
SELECT 'jobs: ' || COUNT(*) FROM jobs;
SELECT 'applications: ' || COUNT(*) FROM applications;
SELECT 'companies: ' || COUNT(*) FROM companies;
SELECT 'search_configs: ' || COUNT(*) FROM search_configs;
EOF

echo ""
echo "Done! Database is now empty."
echo "Resume profiles were preserved. To clear those too, run:"
echo "  ./scripts/rds-psql.sh \"TRUNCATE TABLE resume_profiles CASCADE\""
