#!/bin/bash
# Production deployment (example / template).
#
# Deploys only the job-worker and frontend containers to a remote host, where
# Temporal, Redis, and the database run as shared/managed infrastructure
# (see docker-compose.prod.yml).
#
# No real infrastructure is committed. Configure these before running, e.g. by
# sourcing an untracked deploy.env:
#
#   DEPLOY_HOST=user@your-server.example.com
#   DEPLOY_SSH_KEY=$HOME/.ssh/your-deploy-key
#   DEPLOY_REMOTE_PATH=/home/user/jobhunt
#   PUBLIC_DOMAIN=your-domain.example.com

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

SERVER="${DEPLOY_HOST:-user@your-server.example.com}"
SSH_KEY="${DEPLOY_SSH_KEY:-$HOME/.ssh/your-deploy-key}"
REMOTE_PATH="${DEPLOY_REMOTE_PATH:-/home/user/jobhunt}"
PUBLIC_DOMAIN="${PUBLIC_DOMAIN:-your-domain.example.com}"

echo -e "${GREEN}========================================"
echo -e "  JobHunt Production Deployment"
echo -e "========================================${NC}"
echo ""

# Get commit message from argument or prompt
COMMIT_MSG="${1:-}"
if [ -z "$COMMIT_MSG" ]; then
    read -p "Commit message: " COMMIT_MSG
fi

# 1. Commit and push
echo -e "${YELLOW}[1/4] Git commit and push...${NC}"
git add -A
git commit -m "$COMMIT_MSG" || echo "Nothing to commit"
git push origin main &

# 2. SSH to server and pull
echo -e "${YELLOW}[2/4] Pulling code on server...${NC}"
ssh -i "$SSH_KEY" "$SERVER" "cd $REMOTE_PATH && git pull"

# Wait for push to complete
wait

# 3. Rebuild and restart containers using production compose
echo -e "${YELLOW}[3/4] Rebuilding containers...${NC}"
ssh -i "$SSH_KEY" "$SERVER" "cd $REMOTE_PATH && docker-compose -f docker-compose.prod.yml up -d --build"

# 4. Check health
echo -e "${YELLOW}[4/4] Checking health...${NC}"
sleep 5
ssh -i "$SSH_KEY" "$SERVER" "docker ps --filter 'name=jobhunt' --format '{{.Names}}: {{.Status}}'"

echo ""
echo -e "${GREEN}Deployment complete!${NC}"
echo "Frontend: https://${PUBLIC_DOMAIN}/jobhunt/"
echo "API: https://${PUBLIC_DOMAIN}/api/jobhunt/"
