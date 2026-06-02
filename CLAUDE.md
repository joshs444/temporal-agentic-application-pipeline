# CLAUDE.md — Temporal Agentic Application Pipeline

Guidance for working in this repo (for contributors and for Claude Code / AI assistants).

**North Star:** ship small, production-shaped vertical slices with tests,
**exactly-once delivery** where it matters, and clear proofs (health checks, logs).
Prefer **KISS** and **YAGNI**.

**Decision order:** Correctness & Simplicity → Tests → Security → Observability → Performance

---

## System overview

A durable, human-in-the-loop application pipeline built on Temporal. Five long-running
workflows discover roles, score them against a candidate profile with an LLM, draft
tailored outreach, **pause for human approval**, send via Gmail, and run a multi-week
follow-up sequence on durable timers. See [README.md](README.md) for the architecture
diagrams and lifecycle.

The point of the project is the **orchestration substrate** (signals, queries, retries,
idempotency, the approval gate), not "a bot that applies to jobs."

---

## Local development

```bash
cp .env.example .env                          # first time; fill in API keys as needed
cp profile.example.yaml data/profile.yaml     # optional: your details (gitignored)
docker compose up -d
```

| Service | Port | Description |
|---------|------|-------------|
| job-worker | 8080 | FastAPI + Temporal worker |
| frontend | 8084 | Dashboard (nginx) |
| postgres | 5433 | PostgreSQL + pgvector |
| redis | 6381 | Cache / queues |
| temporal | 7233 | Workflow orchestration |
| temporal-ui | 8088 | Workflow monitoring |
| minio | 9002 / 9003 | S3-compatible storage |

```bash
docker compose logs -f job-worker             # view worker logs
docker compose exec postgres psql -U jobhunt -d jobhunt_db   # query the DB
./scripts/run-migrations.sh                   # apply db/migrations/*.sql
```

The default Postgres/Redis/MinIO credentials in `docker-compose.yml` are **local-dev
placeholders only**. Real secrets go in `.env` (gitignored).

---

## Architecture

```
discovery (SerpAPI / SearchAPI / Grok web-search)
    → enrichment (Apollo: company + contacts)
    → matching / scoring (LLM)
    → application material generation (LLM)
    → human approval gate (Temporal signal)
    → send (Gmail) + tracking
    → follow-up sequence (durable timers)
```

**Temporal workflows** (task queue: `jobhunt-worker`)

- `JobDiscoveryWorkflow` — discover new postings
- `JobEnrichmentWorkflow` — enrich company + contacts, compute fit score
- `ApplicationWorkflow` — generate materials, await approval, send, spawn follow-up
- `FollowUpWorkflow` — durable-timer follow-up cadence with early exit on reply
- `InterviewPrepWorkflow` — research + question/talking-point generation

Workflows live in `job-worker/workflows/`, activities in `job-worker/activities/`,
external connectors in `job-worker/clients/`, the API in `job-worker/routes/`.

---

## LLM usage

The pipeline uses any **OpenAI-compatible** chat-completions endpoint. Configuration is
centralized in `job-worker/utils/llm_config.py`:

- `LLM_BASE_URL` (default `https://api.x.ai/v1` — xAI Grok)
- `LLM_MODEL` (default `grok-4-1-fast`), `LLM_LIGHT_MODEL` (cheaper, for classify/extract)
- `LLM_API_KEY` (falls back to `XAI_API_KEY`)

Use `get_llm_client()` from `utils.llm_config` rather than constructing clients ad hoc.
LLM responses carry token/latency/cost metadata (`utils.llm_config.estimate_cost_usd`).

---

## Candidate profile (no PII in code)

All personal details (name, contact, background, resume) live in a YAML profile loaded by
`job-worker/utils/profile.py`, **never hardcoded**. Resolution order: `$PROFILE_PATH` →
`data/profile.yaml` → `profile.yaml` → `profile.example.yaml` → built-in generic defaults.
Prompts and email signatures are built from this profile at runtime.

When editing prompts or templates, pull identity from `utils.profile`
(`candidate()`, `candidate_name()`, `build_signature()`), not string literals.

---

## Database

- Database: `jobhunt_db`. Migrations: `db/migrations/*.sql` (numbered `0001_`, `0002_`, …),
  applied via `./scripts/run-migrations.sh` and tracked in a `schema_migrations` table.
- Query parameters are always bound (asyncpg) — never interpolate SQL strings.

---

## Code standards

- Line length: 100 chars. Type hints everywhere. Docstrings on workflows/activities.
- Fail fast; no bare `except`. SQL is parameterized only.
- Tests: pure/fast unit tests plus integration tests.
- Format/lint with `black` and `ruff`; type-check with `mypy`.

---

## Environment variables

Copy `.env.example` to `.env`. Required for full functionality: `LLM_API_KEY`
(or `XAI_API_KEY`), `SERPAPI_KEY`, `APOLLO_API_KEY`, `DATABASE_URL`, `REDIS_URL`. Optional:
Gmail OAuth (`GOOGLE_CLIENT_ID/SECRET`, `OAUTH_MASTER_KEY`), SMTP, Slack/Discord webhooks.
**Never commit real keys** — `.env`, `profile.yaml`, and key files are gitignored.

---

## Deployment

`deploy.sh` (local) and `deploy-prod.sh` (remote) are env-driven templates. Production
host/SSH-key/domain are read from environment variables (`DEPLOY_HOST`, `DEPLOY_SSH_KEY`,
`DEPLOY_REMOTE_PATH`, `PUBLIC_DOMAIN`) — no infrastructure is committed to the repo.
`docker-compose.prod.yml` runs only the worker + frontend, expecting shared/managed
Temporal, Redis, and Postgres.
