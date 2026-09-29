-- SaRadar SQLite schema
-- Initialise with: saradar.db.init_db() or `sqlite3 data/saradar.db < db/schema.sql`

PRAGMA foreign_keys = ON;

-- User profile (single row: id=1 convention for single-user app)
CREATE TABLE IF NOT EXISTS profile (
    id          INTEGER PRIMARY KEY,
    name        TEXT,
    email       TEXT,
    skills      TEXT,           -- JSON string: ["Python", "PyTorch", ...]
    experience  TEXT,           -- JSON string: [{company, title, dates, bullets[]}, ...]
    education   TEXT,           -- JSON string: [{school, degree, field, year}, ...]
    raw_text    TEXT,           -- Full raw resume text for reference
    updated_at  TEXT            -- ISO-8601 UTC timestamp
);

-- Jobs sourced from APIs and Gmail alerts
CREATE TABLE IF NOT EXISTS jobs (
    hash        TEXT PRIMARY KEY,          -- Stable content hash for dedupe
    title       TEXT NOT NULL,
    company     TEXT NOT NULL,
    url         TEXT,
    source      TEXT,                      -- e.g. "rapidapi-js", "gmail-alert"
    city        TEXT,
    state       TEXT,
    country     TEXT,
    work_mode   TEXT,                      -- "remote" | "hybrid" | "onsite" | "unknown"
    lat         REAL,
    lng         REAL,
    description TEXT,
    fit         INTEGER,                   -- 0-100 fit score, NULL until scored
    is_new      INTEGER DEFAULT 1,         -- 1 = not yet shown to user
    jd_status   TEXT DEFAULT 'pending',    -- pending | parsed | scored | failed
    created_at  TEXT                       -- ISO-8601 UTC timestamp
);

CREATE INDEX IF NOT EXISTS idx_jobs_fit        ON jobs(fit);
CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at);
CREATE INDEX IF NOT EXISTS idx_jobs_is_new     ON jobs(is_new);

-- Application tracker
CREATE TABLE IF NOT EXISTS applications (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id       TEXT NOT NULL,
    status       TEXT NOT NULL,            -- saved | applied | interview | offer | rejected
    applied_date TEXT,                     -- ISO-8601 date
    notes        TEXT,                     -- User free-text notes
    created_at   TEXT,                     -- ISO-8601 UTC timestamp
    FOREIGN KEY (job_id) REFERENCES jobs(hash) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_applications_job_id ON applications(job_id);
CREATE INDEX IF NOT EXISTS idx_applications_status ON applications(status);
