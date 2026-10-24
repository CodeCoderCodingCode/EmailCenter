-- Persistent delivery control; each draft receives at most one captured job per group.
CREATE TABLE email_bulk_dispatches (
    id TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL UNIQUE REFERENCES email_draft_batches(id),
    provider_account_id TEXT NOT NULL REFERENCES email_provider_accounts(id),
    scheduled_local TEXT,
    timezone_id TEXT NOT NULL,
    interval_seconds INTEGER NOT NULL CHECK(interval_seconds BETWEEN 1 AND 3600),
    status TEXT NOT NULL CHECK(status IN ('Preparing','Ready','Running','Paused','Completed','Cancelled')),
    next_send_at_utc TEXT,
    last_error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE email_bulk_dispatch_items (
    dispatch_id TEXT NOT NULL REFERENCES email_bulk_dispatches(id),
    draft_id TEXT NOT NULL REFERENCES email_drafts(id),
    job_id TEXT UNIQUE REFERENCES email_jobs(id),
    position INTEGER NOT NULL,
    PRIMARY KEY(dispatch_id,draft_id),
    UNIQUE(dispatch_id,position)
);
CREATE INDEX idx_bulk_dispatch_job ON email_bulk_dispatch_items(job_id);
