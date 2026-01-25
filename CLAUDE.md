# CLAUDE.md — Internship Application Assistant (Greenhouse + Lever) — Summer 2026

## 0) Purpose of This Document
This file defines the **project specification**, **constraints**, **architecture**, **module interfaces**, and **implementation plan** for an internship-finding and application-assistance system.

The goal is to make it straightforward for an AI coding agent (Claude Code) to implement the project end-to-end, while keeping the system cleanly modular so planned extensions can be added later with minimal refactoring.

---

## 1) High-Level Goal (MVP)
Build a **generalizable** Python program (CLI-first) that:

1. **Discovers internships** from **public job listings** on:
   - Greenhouse (public job boards)
   - Lever (public job boards)

2. Filters for **Summer 2026 internships** relevant to the user’s interests:
   - **Software Engineering** (broad net: backend/frontend/full-stack/ML/systems, etc.)
   - **Quant** (broad net: research/trading/dev, etc.)
   - **Operations Research / Optimization / Analytics** (broad net)

3. Normalizes postings into a unified schema, stores them in a **local SQLite DB**.

4. Uses **AI** (multi-provider supported) to:
   - classify/validate internship eligibility (internship, Summer 2026)
   - extract structured fields from job descriptions
   - compute a relevance score for ranking

5. Provides a CLI workflow to:
   - list jobs, shortlist jobs, mark statuses
   - generate an “application packet” per shortlisted job
   - open application links and optionally assist with autofill (but **NOT** submit)

6. Syncs the current job/application tracker to **Google Sheets** as a **mirror/dashboard** (one-way sync from local DB → Sheets).

### Explicit MVP Non-Goals (Do Not Implement Yet)
- Auto-submit the application (“click submit”) anywhere.
- Bypass logins, CAPTCHAs, anti-bot systems, or gated portals.
- Resume tailoring / rewriting / 1-page targeted resume generation.
- ATS question-answer generation at scale.
- Full web UI (web app planned later; start with CLI).
- Two-way Google Sheets sync (Sheets is mirror only in MVP).

---

## 2) Hard Constraints and Decisions (Locked)
These constraints must be enforced by the implementation.

### 2.1 Internship Relevance Constraints
- Include only **internships**, not full-time jobs.
- Include only **Summer internships for upcoming Summer 2026**.
- Location: include **anywhere in the US** and **any remote** roles.
- Work authorization: assume user has **US work authorization** (no filter needed).
- Industry: include **any industry** if role fits SWE/Quant/OR.
- Compensation: **prioritize paid**, but **do not exclude unpaid**.

### 2.2 Sources
- MVP sources are **ONLY**:
  - Greenhouse public job boards
  - Lever public job boards
- No LinkedIn/Indeed/Handshake scraping in MVP.

### 2.3 Application Behavior (MVP)
- The system may:
  - open links
  - prefill fields where feasible
  - prepare materials
- The system must **pause before submission** (user manually submits).

### 2.4 Tracking
- Source of truth: **local SQLite database**
- Google Sheets: **one-way mirror** (DB → Sheets)

### 2.5 UX
- MVP is **CLI-first**.
- Architecture must allow a future web UI with minimal change.

### 2.6 AI Providers
- Must support **multiple providers** (OpenAI + Anthropic initially).
- Allow mix-and-match by task.
- Must be configurable via environment variables and config.

### 2.7 Secrets
- Store API keys in `.env` (never committed).
- Google Sheets access via OAuth token file.

### 2.8 Scale Expectations
- Expected applications for Summer 2026: ~**50–150**.

### 2.9 Safety / Compliance
- Do not implement login bypass or CAPTCHA bypass.
- Only scrape public job listings and respect reasonable rate limiting.
- Avoid behavior intended to evade anti-bot protections.

---

## 3) User Workflow (MVP)
### 3.1 Setup
1. User clones repo or runs Docker image.
2. User creates `.env` with API keys.
3. User runs `setup` wizard (CLI) to create a local user profile file.
4. User provides resume PDF path (MVP uses PDF as-is).

### 3.2 Search + Review
1. User runs job search:
   - fetches from configured Greenhouse/Lever boards
   - normalizes and stores into DB
2. System runs AI enrichment:
   - extracts structured fields
   - verifies internship + Summer 2026
   - assigns relevance score
3. User views ranked results and shortlists.

### 3.3 Application Packet + Assisted Apply
1. User generates an application packet for a job:
   - job details JSON
   - resume copy (PDF for MVP)
   - optionally a short AI summary of “why relevant” and key requirements
2. User runs assist apply:
   - opens application link
   - optionally prefills basic fields if possible (not required in MVP)
   - stops for user to manually submit

### 3.4 Tracking + Sync
- Status changes are stored in DB and mirrored to Google Sheets.

---

## 4) Project Structure (Recommended)
```
internship-assistant/
  app/
    __init__.py
    cli.py                 # entrypoint (Typer recommended)
    config.py              # config loader (env + user profile + defaults)
    logging_config.py
    models.py              # pydantic schemas (JobPosting, etc.)
    db/
      __init__.py
      schema.sql
      sqlite.py            # DB access layer + migrations
      repositories.py      # CRUD operations for Jobs, Applications, Runs
    sources/
      __init__.py
      base.py              # Source interface
      greenhouse.py        # Greenhouse board ingestion
      lever.py             # Lever board ingestion
    ai/
      __init__.py
      base.py              # AIProvider interface + common utilities
      openai_provider.py   # OpenAI implementation
      anthropic_provider.py# Anthropic implementation
      prompts/
        job_extract.md
        job_score.md
    pipeline/
      __init__.py
      discover.py          # orchestrates source fetch + store
      enrich.py            # AI extraction + scoring
      rank.py              # ranking logic + filters
      dedupe.py            # dedupe heuristics
    apply/
      __init__.py
      packet.py            # generate packet folder & artifacts
      assist.py            # open link; optional Playwright scaffold
    sync/
      __init__.py
      sheets.py            # one-way sync DB → Google Sheets
    utils/
      http.py              # rate limiting, retry/backoff, caching
      text.py              # normalization, cleaning
  storage/
    (created at runtime)
    applications.db
    packets/
      <job_id>/
  tests/
  .env.example
  pyproject.toml
  CLAUDE.md
  README.md
```

---

## 5) Core Data Model (DB + In-Memory Schemas)
Use Pydantic (recommended) or dataclasses with validation.

### 5.1 JobPosting (Normalized)
Required fields:
- `job_id` (string, stable internal UUID or deterministic hash)
- `source` ("greenhouse" | "lever")
- `source_job_id` (string; the id in the source system if available)
- `company` (string)
- `title` (string)
- `location` (string or null)
- `is_remote` (bool)
- `apply_url` (string)
- `posting_url` (string; often same as apply_url)
- `description_html` (string; raw)
- `description_text` (string; cleaned)
- `date_posted` (date or null if unknown)
- `scraped_at` (timestamp)

AI-enriched fields:
- `role_family` ("SWE" | "QUANT" | "OR" | "OTHER")
- `is_internship` (bool)
- `season` ("Summer" | "Fall" | "Spring" | "Other" | null)
- `year` (int or null)
- `is_summer_2026` (bool)  # strict MVP filter
- `paid_flag` ("PAID" | "UNPAID" | "UNKNOWN")
- `requirements` (list[str])
- `preferred_skills` (list[str])
- `keywords` (list[str])
- `relevance_score` (float 0–100)
- `ai_confidence` (float 0–1)
- `ai_model_used` (string)

### 5.2 ApplicationStatus (Enum)
- DISCOVERED
- SHORTLISTED
- PACKET_READY
- APPLIED (manual user sets after submitting)
- REJECTED
- FOLLOW_UP_DUE
- ARCHIVED

### 5.3 ApplicationAttempt
- `job_id`
- `status`
- `packet_path` (nullable)
- `notes` (nullable)
- `created_at`
- `updated_at`

### 5.4 Run Metadata
Track each run for observability:
- run_id, started_at, ended_at, source_count, new_jobs, enriched_jobs, errors

---

## 6) Key Modules and Interfaces (Must Be Stable)
### 6.1 Source Interface
**`Source.fetch(criteria: SearchCriteria) -> list[RawJob]`**

**`Source.normalize(raw: RawJob) -> JobPosting`**

### 6.2 AI Provider Interface
Minimum interface:
- `extract_job_fields(job: JobPosting, user_profile: UserProfile) -> ExtractedJobFields`
- `score_job(job: JobPosting, user_profile: UserProfile) -> JobScoreResult`

### 6.3 Pipeline Orchestrator
- `discover.run(criteria)`
- `enrich.run(job_ids|query)`
- `rank.list(criteria)`

### 6.4 Packet Generator
- `packet.create(job_id) -> packet_path`

### 6.5 Apply Assist
- open application URL in browser
- optional Playwright integration scaffold
- always pause before submit

### 6.6 Sheets Sync
One-way DB → Sheets:
- `sync_sheets.run(sheet_id, worksheet_name)`

---

## 7) CLI Commands (MVP)
Use Typer for structured CLI.

- `python -m app.cli setup`
- `python -m app.cli discover --sources greenhouse lever`
- `python -m app.cli enrich --new-only`
- `python -m app.cli list --top 50`
- `python -m app.cli shortlist --job-id <id>`
- `python -m app.cli status --job-id <id> --set SHORTLISTED`
- `python -m app.cli packet --job-id <id>`
- `python -m app.cli assist --job-id <id>`
- `python -m app.cli sync-sheets --sheet-id <id> --tab "Summer2026"`

---

## 8) Setup Wizard (User Profile)
The setup wizard must create a profile for MVP + extensions.

Profile fields:
- Name, Email, Phone
- Location (city/state)
- School + expected graduation year
- Work authorization (US authorized)
- Links: LinkedIn, GitHub, personal site
- Target role families (SWE/Quant/OR)
- Resume path (PDF for MVP)
- (Optional) Master resume DOCX path (future tailoring)

Store in JSON: `storage/profile.json`

---

## 9) AI Usage Details (MVP)
Must use AI for:
- Internship vs not
- Summer/year classification (Summer 2026)
- Extract requirements/skills
- Relevance scoring

Multi-provider configurable:
- `AI_EXTRACT_PROVIDER=openai|anthropic`
- `AI_SCORE_PROVIDER=openai|anthropic`

Extraction must produce strict JSON.

---

## 10) Ingestion Approach (Greenhouse + Lever)
Prefer structured endpoints when possible.
Implement rate limiting, retries, caching.

---

## 11) Google Sheets Sync (One-Way Mirror)
Rows include:
- job_id, company, title, role_family, location, remote, paid_flag
- relevance_score, status, apply_url, source, date_posted
- discovered_at, notes, updated_at

Upsert by job_id; do not delete rows.

---

## 12) Testing Requirements (Minimum)
- Greenhouse parsing normalization
- Lever parsing normalization
- Dedupe heuristics
- AI JSON parsing + repair fallback

---

## 13) Implementation Milestones
0) Skeleton
1) Sources ingestion
2) AI enrichment
3) CLI shortlist/status
4) Packet generator
5) Sheets sync
6) Assist apply (minimal)

---

## 14) Planned Extensions (Design Hooks)
### 14.1 Resume Tailoring (Truthful)
- Master resume DOCX → tailored 1-page → output PDF
- `python-docx` + PDF render (LibreOffice in Docker)

### 14.2 ATS Question Answering
- Draft answers constrained by truthfulness, saved to packet

### 14.3 Auto-Submit Plugins (Opt-in, cautious)
- Only public/no-login flows; never bypass CAPTCHAs/logins

### 14.4 Additional Sources
- Workday (hard), custom sites, search discovery, job boards (ToS cautious)

### 14.5 Web UI
- FastAPI + thin frontend over DB

### 14.6 Two-Way Sheets Sync
- Not MVP; requires conflict resolution

---

## 15) Guardrails
- Keep modules decoupled.
- Avoid brittle selectors.
- Handle partial failures.
- Never commit secrets.
- Never bypass logins/CAPTCHAs.
- Always pause before submit (MVP).

---

## 16) Environment Variables (.env)
See `.env.example`.

---

## 17) Done Definition (MVP Acceptance Criteria)
MVP complete when:
1) setup works
2) discover ingests Greenhouse/Lever to SQLite
3) enrich adds classification + scoring
4) list/shortlist/status works
5) packet generation works
6) sheets sync works (one-way)
7) assist opens link and pauses before submit
