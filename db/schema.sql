-- SaRadar SQLite schema
-- Initialise with: saradar.db.init_db() or `sqlite3 data/saradar.db < db/schema.sql`

PRAGMA foreign_keys = ON;

-- User profile (single row: id=1 convention for single-user app)
-- profile_json stores the full Profile Pydantic model JSON; the legacy
-- name/email/skills/experience/education columns are kept for SQL queries.
CREATE TABLE IF NOT EXISTS profile (
    id           INTEGER PRIMARY KEY,
    name         TEXT,
    email        TEXT,
    skills       TEXT,           -- JSON string: flat [] of unique skills (all_skills)
    experience   TEXT,           -- JSON string: Profile.experience (list of objects)
    education    TEXT,           -- JSON string: Profile.education  (list of objects)
    raw_text     TEXT,           -- Full raw resume text for reference
    profile_json TEXT,           -- Full Profile.model_dump_json() (authoritative)
    updated_at   TEXT            -- ISO-8601 UTC timestamp
);

-- If you created profile *before* profile_json existed, run once:
-- ALTER TABLE profile ADD COLUMN profile_json TEXT;

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
