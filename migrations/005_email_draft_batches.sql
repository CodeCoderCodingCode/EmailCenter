-- Local draft groups; delivery approval remains a separate step for each job.
CREATE TABLE email_draft_batches (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    template_version_id TEXT NOT NULL REFERENCES template_versions(id),
    created_at TEXT NOT NULL
);
CREATE TABLE email_draft_batch_items (
    batch_id TEXT NOT NULL REFERENCES email_draft_batches(id),
    contact_id TEXT NOT NULL REFERENCES contacts(id),
    draft_id TEXT NOT NULL UNIQUE REFERENCES email_drafts(id),
    recipient_snapshot TEXT NOT NULL,
    name_snapshot TEXT NOT NULL,
    PRIMARY KEY(batch_id, contact_id),
    UNIQUE(batch_id, recipient_snapshot COLLATE NOCASE)
);
