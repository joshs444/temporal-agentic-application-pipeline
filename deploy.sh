#!/bin/bash
set -e

# JobHunt Deploy Script
# Supports both local and production (AWS) deployment

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Production deploy config.
# Set these in your environment (e.g. an untracked deploy.env you `source`)
# before running with --prod. No real infrastructure is committed to the repo.
SSH_KEY="${DEPLOY_SSH_KEY:-$HOME/.ssh/your-deploy-key}"
SSH_HOST="${DEPLOY_HOST:-user@your-server.example.com}"
REMOTE_PATH="${DEPLOY_REMOTE_PATH:-/home/user/jobhunt}"
REPO_URL="${DEPLOY_REPO_URL:-https://github.com/your-org/temporal-agentic-application-pipeline.git}"
PUBLIC_DOMAIN="${PUBLIC_DOMAIN:-your-domain.example.com}"

# Parse arguments
MODE="local"
COMMIT_MSG="${1:-Auto-deploy}"

if [ "$1" = "--prod" ] || [ "$1" = "-p" ]; then
    MODE="prod"
    COMMIT_MSG="${2:-Auto-deploy}"
fi

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  JobHunt Deployment (${MODE})${NC}"
echo -e "${GREEN}========================================${NC}"

# =============================================================================
# LOCAL DEPLOYMENT
# =============================================================================
if [ "$MODE" = "local" ]; then
    echo -e "\n${YELLOW}[1/4] Git commit and push...${NC}"
    git add -A
    git commit -m "$COMMIT_MSG" || echo "Nothing to commit"
    git push origin main || git push origin master || echo "Push failed or no remote"

    echo -e "\n${YELLOW}[2/4] Waiting for PostgreSQL...${NC}"
    until docker exec jobhunt-postgres pg_isready -U jobhunt -d jobhunt_db 2>/dev/null; do
        echo -n "."
        sleep 1
    done
    echo " ready!"

    echo -e "\n${YELLOW}[3/4] Running migrations...${NC}"
    for f in db/migrations/*.sql; do
        if [ -f "$f" ]; then
            echo "  -> $(basename $f)"
            docker exec -i jobhunt-postgres psql -U jobhunt -d jobhunt_db < "$f" 2>/dev/null || true
        fi
    done

    echo -e "\n${YELLOW}[4/4] Rebuilding and restarting...${NC}"
    docker compose build --no-cache job-worker frontend
    docker compose up -d

    echo -e "\n${GREEN}========================================${NC}"
    echo -e "${GREEN}  Local deployment complete!${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo -e "\n  Dashboard: ${YELLOW}http://localhost:8084${NC}"
    echo -e "  API:       ${YELLOW}http://localhost:8080${NC}"
    exit 0
fi

# =============================================================================
# PRODUCTION DEPLOYMENT
# =============================================================================
echo -e "\n${BLUE}Deploying to production...${NC}"

# Step 1: Git commit and push
echo -e "\n${YELLOW}[1/6] Git commit and push...${NC}"
git add -A
git commit -m "$COMMIT_MSG" || echo "Nothing to commit"
git push origin main || git push origin master

CURRENT_COMMIT=$(git rev-parse HEAD)
echo "Current commit: $CURRENT_COMMIT"

# Step 2: Detect changed files
echo -e "\n${YELLOW}[2/6] Detecting changes...${NC}"
LAST_COMMIT=$(ssh -i "$SSH_KEY" "$SSH_HOST" "cat $REMOTE_PATH/.last_deployed_commit 2>/dev/null || echo ''")

if [ -n "$LAST_COMMIT" ]; then
    CHANGED_FILES=$(git diff --name-only "$LAST_COMMIT" "$CURRENT_COMMIT" 2>/dev/null || git diff --name-only HEAD~1 HEAD)
else
    CHANGED_FILES=$(git diff --name-only HEAD~1 HEAD)
fi

echo "Changed files:"
echo "$CHANGED_FILES" | head -20

# Determine services to rebuild
SERVICES_TO_REBUILD=""
if echo "$CHANGED_FILES" | grep -q "^job-worker/"; then
    SERVICES_TO_REBUILD="$SERVICES_TO_REBUILD job-worker"
fi
if echo "$CHANGED_FILES" | grep -q "^frontend/"; then
    SERVICES_TO_REBUILD="$SERVICES_TO_REBUILD frontend"
fi
if [ -z "$SERVICES_TO_REBUILD" ]; then
    SERVICES_TO_REBUILD="job-worker"
fi
echo "Services to rebuild: $SERVICES_TO_REBUILD"

# Step 3: SSH and pull code
echo -e "\n${YELLOW}[3/6] Pulling code on server...${NC}"
ssh -i "$SSH_KEY" "$SSH_HOST" << EOF
    set -e
    cd $REMOTE_PATH || { mkdir -p $REMOTE_PATH && cd $REMOTE_PATH && git clone "$REPO_URL" .; }
    git fetch origin
    git reset --hard origin/main
EOF

# Step 4: Rebuild and restart services (must happen BEFORE migrations so psql is available)
echo -e "\n${YELLOW}[4/6] Rebuilding services...${NC}"
ssh -i "$SSH_KEY" "$SSH_HOST" << EOF
    set -e
    cd $REMOTE_PATH

    # Build services
    docker-compose -f docker-compose.prod.yml build --no-cache $SERVICES_TO_REBUILD

    # Restart services
    docker-compose -f docker-compose.prod.yml up -d --force-recreate $SERVICES_TO_REBUILD

    # Show status
    docker-compose -f docker-compose.prod.yml ps
EOF

# Step 5: Run migrations on RDS (after container rebuild so psql is available)
echo -e "\n${YELLOW}[5/6] Running migrations on RDS...${NC}"
ssh -i "$SSH_KEY" "$SSH_HOST" "REMOTE_PATH='$REMOTE_PATH' bash -s" << 'EOF'
    set -e
    cd "$REMOTE_PATH"

    # Source environment
    if [ -f .env ]; then
        source .env
    fi

    DB_URL="${JOBHUNT_DATABASE_URL:-$DATABASE_URL}"

    if [ -z "$DB_URL" ]; then
        echo "Warning: No database URL configured, skipping migrations"
        exit 0
    fi

    # Create schema_migrations table if not exists
    docker exec jobhunt-worker psql "$DB_URL" -c "
        CREATE TABLE IF NOT EXISTS schema_migrations (
            id BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
            migration_name TEXT NOT NULL UNIQUE,
            applied_at TIMESTAMP DEFAULT NOW(),
            checksum TEXT,
            applied_by TEXT DEFAULT CURRENT_USER,
            execution_time_ms INTEGER,
            notes TEXT
        );
    " 2>/dev/null || true

    # Get applied migrations
    APPLIED=$(docker exec jobhunt-worker psql "$DB_URL" -t -c "SELECT migration_name FROM schema_migrations" 2>/dev/null | tr -d ' ' || echo "")

    # Run new migrations
    for f in db/migrations/*.sql; do
        if [ -f "$f" ]; then
            MIGRATION_NAME=$(basename "$f")
            if ! echo "$APPLIED" | grep -q "^${MIGRATION_NAME}$"; then
                echo "  -> Applying: $MIGRATION_NAME"
                START_TIME=$(date +%s%3N)
                docker exec -i jobhunt-worker psql "$DB_URL" < "$f"
                END_TIME=$(date +%s%3N)
                DURATION=$((END_TIME - START_TIME))
                docker exec jobhunt-worker psql "$DB_URL" -c "
                    INSERT INTO schema_migrations (migration_name, execution_time_ms)
                    VALUES ('$MIGRATION_NAME', $DURATION);
                "
            else
                echo "  -> Already applied: $MIGRATION_NAME"
            fi
        fi
    done
    echo "Migrations complete."
EOF

# Step 6: Configure nginx (if needed)
echo -e "\n${YELLOW}[6/6] Configuring nginx...${NC}"
ssh -i "$SSH_KEY" "$SSH_HOST" << 'EOF'
    # Check if jobhunt routes already configured
    if ! grep -q "/api/jobhunt/" /etc/nginx/sites-enabled/default 2>/dev/null; then
        echo "Adding nginx routes for JobHunt..."

        # Find the location to insert (before the last closing brace of server block)
        sudo sed -i '/^}$/i \
    # JobHunt API\
    location /api/jobhunt/ {\
        proxy_pass http://127.0.0.1:8090/;\
        proxy_set_header Host $host;\
        proxy_set_header X-Real-IP $remote_addr;\
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;\
        proxy_set_header X-Forwarded-Proto $scheme;\
    }\
    \
    # JobHunt Frontend\
    location /jobhunt/ {\
        proxy_pass http://127.0.0.1:8091/;\
        proxy_set_header Host $host;\
        proxy_set_header X-Real-IP $remote_addr;\
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;\
        proxy_set_header X-Forwarded-Proto $scheme;\
    }' /etc/nginx/sites-enabled/default

        # Test and reload
        sudo nginx -t && sudo systemctl reload nginx
        echo "Nginx configured."
    else
        echo "Nginx routes already configured."
    fi
EOF

# Save deployed commit
ssh -i "$SSH_KEY" "$SSH_HOST" "echo '$CURRENT_COMMIT' > $REMOTE_PATH/.last_deployed_commit"

echo -e "\n${GREEN}========================================${NC}"
echo -e "${GREEN}  Production deployment complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo -e "\n  Dashboard: ${YELLOW}https://${PUBLIC_DOMAIN}/jobhunt/${NC}"
echo -e "  API:       ${YELLOW}https://${PUBLIC_DOMAIN}/api/jobhunt/${NC}"
echo -e "  Health:    ${YELLOW}https://${PUBLIC_DOMAIN}/api/jobhunt/health${NC}"
