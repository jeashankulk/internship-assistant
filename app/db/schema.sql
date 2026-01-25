-- SQLite schema for Internship Assistant (MVP)
-- Keep migrations simple: if schema changes, add new migration scripts later.

PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS jobs (
  job_id TEXT PRIMARY KEY,
  source TEXT NOT NULL,
  source_job_id TEXT,
  company TEXT NOT NULL,
  title TEXT NOT NULL,
  location TEXT,
  is_remote INTEGER NOT NULL DEFAULT 0,
  apply_url TEXT NOT NULL,
  posting_url TEXT NOT NULL,
  description_html TEXT,
  description_text TEXT,
  date_posted TEXT,
  scraped_at TEXT NOT NULL,

  -- AI enriched
  role_family TEXT,
  is_internship INTEGER,
  season TEXT,
  year INTEGER,
  is_summer_2026 INTEGER,
  paid_flag TEXT,
  requirements_json TEXT,
  preferred_skills_json TEXT,
  keywords_json TEXT,
  relevance_score REAL,
  ai_confidence REAL,
  ai_model_used TEXT,

  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_jobs_source ON jobs(source);
CREATE INDEX IF NOT EXISTS idx_jobs_company_title ON jobs(company, title);
CREATE INDEX IF NOT EXISTS idx_jobs_relevance ON jobs(relevance_score);

CREATE TABLE IF NOT EXISTS applications (
  job_id TEXT PRIMARY KEY,
  status TEXT NOT NULL,
  packet_path TEXT,
  notes TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY(job_id) REFERENCES jobs(job_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_applications_status ON applications(status);

CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY,
  started_at TEXT NOT NULL,
  ended_at TEXT,
  source_count INTEGER,
  new_jobs INTEGER,
  enriched_jobs INTEGER,
  errors_json TEXT
);
