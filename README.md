# Temporal Agentic Application Pipeline

[![CI](https://github.com/joshs444/temporal-agentic-application-pipeline/actions/workflows/ci.yml/badge.svg)](https://github.com/joshs444/temporal-agentic-application-pipeline/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

A **durable, human-in-the-loop job-application pipeline** built on
[Temporal](https://temporal.io). Long-running workflows discover roles, score them
against a candidate profile with an LLM, draft tailored outreach, **pause for human
approval**, send via Gmail, and then run a multi-week follow-up sequence on durable
timers — all crash-safe, resumable, and observable. The interesting engineering isn't
"a bot that applies to jobs"; it's the orchestration substrate: signals, queries,
retries with backoff, idempotent activities, deterministic workflow IDs, and a
provider-agnostic LLM layer wired to pluggable external-API connectors.

> **What this is, honestly:** an application pipeline used as a vehicle to build
> production-shaped agentic orchestration. The Temporal layer (signals/queries/timers/
> retries/HITL gate/child workflows) is complete and real, and the discover → draft →
> approve → send → follow-up path runs end to end (outbound email is gated by
> `EMAIL_SENDING_ENABLED`, default off, so it runs safely in demo mode). A few
> enrichment activities are explicit placeholders — see
> [Status: implemented vs roadmap](#status-implemented-vs-roadmap).

---

## Architecture

```mermaid
flowchart TB
    subgraph client["Client"]
        UI["Dashboard (vanilla JS / nginx)"]
        API["FastAPI<br/>REST + workflow control"]
    end

    subgraph temporal["Temporal"]
        TS["Temporal Server<br/>durable workflow state + timers"]
    end

    subgraph worker["job-worker (Temporal worker, task queue: jobhunt-worker)"]
        direction TB
        WF["Workflows<br/>Discovery · Enrichment · Application · FollowUp · InterviewPrep"]
        ACT["Activities<br/>discover · parse · score · generate · send · classify"]
        POLLER["Email poller (opt-in)<br/>Gmail reply detection"]
    end

    subgraph ext["External APIs (pluggable connectors)"]
        LLM["LLM<br/>OpenAI-compatible (default: xAI Grok)"]
        SEARCH["Job search<br/>SerpAPI · SearchAPI · Grok web-search"]
        APOLLO["Apollo.io<br/>company + contact enrichment"]
        GMAIL["Gmail API<br/>OAuth send + reply polling"]
    end

    subgraph data["Data stores"]
        PG[("PostgreSQL<br/>+ pgvector")]
        REDIS[("Redis")]
        MINIO[("MinIO / S3")]
    end

    UI <--> API
    API -- "start / signal / query" --> TS
    TS <--> WF
    WF -- "execute_activity (retry + timeout)" --> ACT
    ACT --> LLM & SEARCH & APOLLO & GMAIL
    ACT <--> PG
    API <--> PG
    ACT -.-> REDIS
    ACT -.-> MINIO
    GMAIL -. "reply detected" .-> POLLER
    POLLER -. "reply_received signal (opt-in)" .-> TS
```

The **email poller** (opt-in: `RUN_EMAIL_POLLER=true`, needs Gmail OAuth) watches Gmail
for replies and signals the running `FollowUpWorkflow` (`reply_received`) so the sequence
stops the moment a human responds. Independently, the follow-up loop re-checks the database
after every durable timer, so replies are honored even when the poller isn't running.

---

## How it works (end-to-end lifecycle)

1. **Discover** — `JobDiscoveryWorkflow` runs from a saved search config (or synthesizes
   one from the candidate's resume), queries the job connectors, **dedupes** against
   existing rows (`ON CONFLICT`), and persists new postings.
2. **Enrich** — `JobEnrichmentWorkflow` adds company data + hiring contacts (Apollo) and
   computes a detailed fit score. It **skips already-enriched jobs** unless `force_refresh`.
3. **Match** — an LLM scores each job against the profile (0–100) with matched/missing
   skills and reasoning; a cheap keyword pre-filter gates the expensive LLM call.
4. **Draft** — `ApplicationWorkflow` generates a cover letter + outreach email, finds the
   best contact, saves a draft, and **notifies the user**.
5. **Approve (human-in-the-loop)** — the workflow blocks on
   `await workflow.wait_condition(... , timeout=7 days)` until the user sends an
   `approve_send(approved, edits)` signal (or `cancel_application`). It can apply the
   user's edits before sending. `auto_send=True` bypasses the gate.
6. **Send** — the approved email is sent via Gmail (when `EMAIL_SENDING_ENABLED=true`;
   otherwise stubbed in demo mode) and an application record is created — both under a
   tighter retry policy to avoid duplicate sends.
7. **Follow up** — `ApplicationWorkflow` spawns a `FollowUpWorkflow` child
   (`followup-{application_id}`) that uses **durable timers** to run a day-5 / day-12 /
   day-21 cadence, exiting early on `reply_received`, `stop_sequence`, or a job-closed check.
8. **Prep** — `InterviewPrepWorkflow` researches the company + interviewers and generates
   likely questions and talking points.

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant API as FastAPI
    participant WF as ApplicationWorkflow
    participant ACT as Activities
    participant FU as FollowUpWorkflow

    API->>WF: start (job_id)
    WF->>ACT: generate cover letter + email (LLM)
    ACT-->>WF: draft
    WF->>API: notify "draft ready"
    Note over WF: wait_condition(approval, timeout=7d)
    User->>API: review draft
    API->>WF: signal approve_send(approved, edits)
    WF->>ACT: send email (Gmail, retry x2)
    WF->>FU: start child (durable timers)
    loop day 5 / 12 / 21
        FU->>FU: workflow.sleep(timer)
        FU->>ACT: check reply / job active
        FU->>ACT: send follow-up
    end
    API-->>FU: signal reply_received (stops sequence)
```

---

## Why these design decisions

- **Why Temporal?** The work is inherently long-running and human-gated: an application can
  sit for *days* awaiting approval, and follow-ups span *weeks*. Encoding that as durable
  workflows means a worker crash, redeploy, or restart loses nothing — timers, approval
  state, and progress are persisted by Temporal, not held in memory or a fragile cron + DB
  flag. A 21-day follow-up is just `await workflow.sleep(timedelta(days=...))`.
- **Why human-in-the-loop?** Outreach is irreversible and reputational. The approval gate
  (`wait_condition` + signal) makes "draft, then a human approves/edits, then send" a
  first-class state rather than a hopeful `if` check, with a 7-day timeout so abandoned
  drafts expire cleanly.
- **How retries & idempotency are handled:**
  - Activities run under a `RetryPolicy` (exponential backoff, capped attempts); email
    sends use a tighter policy (2 attempts) to avoid duplicate outreach.
  - **Deterministic workflow IDs** (`application-{job_id}`, `followup-{application_id}`)
    make starts idempotent — the same job can't spawn duplicate pipelines.
  - DB writes use `ON CONFLICT` upserts (jobs by `external_id`, companies by `domain`,
    contacts by `email`); enrichment is skipped when `enriched_at` is set.
  - **Belt-and-suspenders reply detection:** the follow-up loop re-checks the database
    after every timer (always on) *and* honors a `reply_received` signal from the opt-in
    email poller for a near-instant stop — so a missed or disabled signal still can't
    cause an unwanted follow-up.
- **Why a provider-agnostic LLM layer?** All model config lives in
  [`utils/llm_config.py`](job-worker/utils/llm_config.py). It targets any
  OpenAI-compatible endpoint (default: xAI Grok) via `LLM_BASE_URL` / `LLM_MODEL` /
  `LLM_API_KEY` — swap to OpenAI or a local server with env vars, no code changes.
- **Why config-driven identity?** The candidate's name, contact info, background, and
  resume live in a YAML profile ([`profile.example.yaml`](profile.example.yaml)), never in
  code — so the repo is shareable and prompts/signatures are built at runtime from config.

---

## The workflows

| Workflow | Signals | Queries | Durability mechanics |
|---|---|---|---|
| **JobDiscoveryWorkflow** | `cancel_discovery` | `get_progress` | retry policy on every activity; dedupe via DB upsert; resume-driven synthesis |
| **JobEnrichmentWorkflow** | — | `get_status` | idempotent skip on `enriched_at`; company cache by domain; `force_refresh` |
| **ApplicationWorkflow** | `approve_send(approved, edits)`, `cancel_application` | `get_draft`, `get_status` | **HITL approval gate** (`wait_condition`, 7-day timeout); spawns follow-up child |
| **FollowUpWorkflow** | `reply_received`, `stop_sequence`, `pause_sequence`, `resume_sequence` | `get_status` | **durable timers** (5/12/21-day cadence); signal + DB reply checks |
| **InterviewPrepWorkflow** | — | `get_status` | per-interviewer research with graceful degradation |

---

## Tech stack

- **Orchestration:** Temporal (Python SDK) — workflows, activities, signals, queries, timers
- **API:** FastAPI + Uvicorn
- **LLM:** any OpenAI-compatible endpoint via the OpenAI SDK (default: xAI Grok)
- **Connectors:** SerpAPI / SearchAPI (Google Jobs), Apollo.io, Gmail API (OAuth2)
- **Data:** PostgreSQL + pgvector, Redis, MinIO (S3-compatible)
- **Frontend:** dependency-free vanilla JS dashboard served by nginx
- **Infra:** Docker Compose (local) / Compose over shared infra (prod)

---

## Quickstart

```bash
# 1. Configure environment (all keys are optional for a first boot)
cp .env.example .env

# 2. (Optional) Customize the candidate profile used in prompts + matching.
#    Without this, generic placeholder defaults are used.
cp profile.example.yaml data/profile.yaml   # gitignored; edit with your details

# 3. Bring up the full stack
docker compose up -d

# Dashboard:    http://localhost:8084
# API + docs:   http://localhost:8080/docs
# Temporal UI:  http://localhost:8088
```

To actually run discovery/enrichment/outreach you'll need API keys in `.env`
(`LLM_API_KEY`/`XAI_API_KEY`, `SERPAPI_KEY`, `APOLLO_API_KEY`, and Gmail OAuth). The stack
boots and the dashboard/API/Temporal UI are usable without them.

### Configuration

| Concern | Where | Notes |
|---|---|---|
| LLM provider | `LLM_BASE_URL` / `LLM_MODEL` / `LLM_API_KEY` | OpenAI-compatible; defaults to xAI Grok |
| Candidate identity | `profile.yaml` / `PROFILE_PATH` | name, contact, background, resume — never in code |
| Job search | `SERPAPI_KEY` / `SEARCHAPI_KEY` | Google Jobs connectors |
| Enrichment | `APOLLO_API_KEY` | company + contact data |
| Email | `GOOGLE_CLIENT_ID/SECRET`, `OAUTH_MASTER_KEY` | Gmail OAuth; tokens encrypted at rest |
| Outbound email | `EMAIL_SENDING_ENABLED` | off by default (sends stubbed); set `true` to send for real |
| Reply detection | `RUN_EMAIL_POLLER`, `ENABLE_TEMPORAL_SIGNALS`, `POLL_INTERVAL_SECONDS` | opt-in Gmail inbox poller; signals the follow-up workflow on reply (the workflow's DB re-check is always-on) |
| API auth | `JOBHUNT_API_KEY`, `ENVIRONMENT` | required in production; dev is open only when `ENVIRONMENT=development` and no key set |

### Tests

```bash
pip install -r job-worker/requirements.txt
pytest          # unit tests + Temporal workflow tests (time-skipping)
ruff check job-worker
```

The suite includes **Temporal workflow tests** that drive `ApplicationWorkflow` and
`FollowUpWorkflow` end to end on Temporal's in-memory time-skipping test server (no real
cluster needed): they assert the approval gate blocks then proceeds / rejects / cancels /
times out, that the 5/12/21-day durable timers fire, and that a reply — via signal or the
DB re-check — short-circuits the sequence. CI (GitHub Actions) runs `ruff` + `pytest` on
every push/PR.

---

## Project structure

```
.
├── job-worker/                  # FastAPI app + Temporal worker
│   ├── workflows/               # 5 Temporal workflows (the orchestration layer)
│   ├── activities/              # Temporal activities (discover, score, generate, send)
│   ├── clients/                 # External API connectors (SerpAPI, Apollo, Gmail, Grok)
│   ├── routes/                  # FastAPI endpoints (jobs, applications, workflows, ...)
│   ├── utils/                   # llm_config, profile, matching, content formatting
│   ├── prompts/                 # LLM prompt templates (candidate details injected at runtime)
│   ├── tests/                   # Unit tests + Temporal workflow tests (time-skipping)
│   ├── worker.py                # Registers workflows + activities on the task queue
│   └── main.py                  # FastAPI entry point
├── frontend/                    # Vanilla-JS dashboard (nginx)
├── db/migrations/               # Numbered SQL migrations
├── .github/workflows/ci.yml     # CI: ruff + pytest
├── profile.example.yaml         # Candidate profile template (copy to profile.yaml)
├── docker-compose.yml           # Local dev stack
└── .env.example                 # Environment template (no secrets)
```

---

## Status: implemented vs roadmap

**Fully implemented**

- The entire Temporal orchestration layer: 5 workflows, signals, queries, the HITL
  approval gate, durable timers, child workflows, retry policies, deterministic IDs.
- The full discover → enrich → score → draft → approve → send → follow-up path,
  wired end to end against the database schema (17 migrations).
- Job discovery (SerpAPI / SearchAPI / Grok web-search), parsing, dedupe.
- LLM fit-scoring, cover-letter / outreach-email / resume-bullet generation.
- Gmail send via `activities.email.send_outreach_email`; the workflow send activities
  delegate to it when `EMAIL_SENDING_ENABLED=true`, otherwise return a stubbed success
  so the orchestration completes in demo mode without sending.
- Reply polling + sentiment classification, application + follow-up tracking.
- FastAPI surface, the dashboard, and a test suite — unit tests plus Temporal workflow
  tests (time-skipping) that exercise the approval gate, rejection/cancel/timeout paths,
  and the follow-up timers — with CI (ruff + pytest).

**Placeholders / roadmap** (clearly marked in code with structured stub returns)

- Interview/company deep-research activities (`research_company_recent`,
  `research_interviewer`, `research_company_culture`) return `pending_integration`
  stubs pending an external research/search integration.
- Outbound email defaults to stubbed (`EMAIL_SENDING_ENABLED=false`); flip it on with
  Gmail OAuth configured to send for real.

---

## Why I built this

I wanted a real, production-shaped system to reason about **durable agentic
orchestration** — not a toy. Job applications turned out to be a perfect forcing
function: the work is long-running (weeks of follow-ups), human-gated (you must approve
outreach), failure-prone (third-party APIs, email), and only useful if it's *exactly
once* and crash-safe. That maps cleanly onto Temporal's primitives, so building it end to
end — workflows, signals, durable timers, idempotent activities, a provider-agnostic LLM
layer, and pluggable connectors — was a way to practice the patterns that matter for
agentic platforms in general, with honest tradeoffs and clear proofs.

## License

[MIT](LICENSE)
