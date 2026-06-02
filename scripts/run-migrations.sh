#!/bin/bash
# Run database migrations in order
# Usage: ./scripts/run-migrations.sh

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
MIGRATIONS_DIR="$(dirname "$0")/../db/migrations"
DATABASE_URL="${DATABASE_URL:-postgresql://jobhunt:jobhunt_secret@localhost:5433/jobhunt_db}"

echo -e "${YELLOW}Running JobHunt migrations...${NC}"
echo "Database: ${DATABASE_URL%%@*}@***"

# Check if migrations directory exists
if [ ! -d "$MIGRATIONS_DIR" ]; then
    echo -e "${RED}Error: Migrations directory not found: $MIGRATIONS_DIR${NC}"
    exit 1
fi

# Create schema_migrations table if it doesn't exist
psql "$DATABASE_URL" -c "
CREATE TABLE IF NOT EXISTS schema_migrations (
    version VARCHAR(255) PRIMARY KEY,
    applied_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
" 2>/dev/null || {
    echo -e "${RED}Error: Could not connect to database${NC}"
    exit 1
}

# Get list of applied migrations
APPLIED=$(psql "$DATABASE_URL" -t -c "SELECT version FROM schema_migrations ORDER BY version;" 2>/dev/null | tr -d ' ')

# Count migrations
TOTAL=0
APPLIED_COUNT=0
NEW_COUNT=0

# Run each migration in order
for migration in $(ls -1 "$MIGRATIONS_DIR"/*.sql 2>/dev/null | sort); do
    TOTAL=$((TOTAL + 1))
    filename=$(basename "$migration")
    version="${filename%.sql}"

    # Check if already applied
    if echo "$APPLIED" | grep -q "^${version}$"; then
        echo -e "${GREEN}[SKIP]${NC} $filename (already applied)"
        APPLIED_COUNT=$((APPLIED_COUNT + 1))
        continue
    fi

    # Apply migration
    echo -e "${YELLOW}[APPLYING]${NC} $filename..."

    if psql "$DATABASE_URL" -f "$migration" 2>&1; then
        # Record migration
        psql "$DATABASE_URL" -c "INSERT INTO schema_migrations (version) VALUES ('$version');" 2>/dev/null
        echo -e "${GREEN}[SUCCESS]${NC} $filename"
        NEW_COUNT=$((NEW_COUNT + 1))
    else
        echo -e "${RED}[FAILED]${NC} $filename"
        exit 1
    fi
done

# Summary
echo ""
echo -e "${GREEN}Migration complete!${NC}"
echo "  Total migrations: $TOTAL"
echo "  Previously applied: $APPLIED_COUNT"
echo "  Newly applied: $NEW_COUNT"

if [ $TOTAL -eq 0 ]; then
    echo -e "${YELLOW}No migration files found in $MIGRATIONS_DIR${NC}"
fi
