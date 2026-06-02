#!/bin/bash
# Query JobHunt's RDS database directly
# Usage: ./scripts/rds-psql.sh "SELECT COUNT(*) FROM jobs"

set -e

# Load environment variables
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SCRIPT_DIR/../.env" ]; then
    source "$SCRIPT_DIR/../.env"
fi

# Use JOBHUNT_DATABASE_URL or fall back to DATABASE_URL
DB_URL="${JOBHUNT_DATABASE_URL:-$DATABASE_URL}"

if [ -z "$DB_URL" ]; then
    echo "Error: JOBHUNT_DATABASE_URL or DATABASE_URL not set"
    echo "Set it in .env or export it:"
    echo "  export JOBHUNT_DATABASE_URL=postgresql://user:pass@host:5432/jobhunt_db"
    exit 1
fi

# If query provided as argument, run it
if [ -n "$1" ]; then
    psql "$DB_URL" -c "$1"
else
    # Interactive mode
    psql "$DB_URL"
fi
