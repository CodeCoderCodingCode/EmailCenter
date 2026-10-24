-- Mutable editor checkpoint, separate from immutable named builder versions.
CREATE TABLE email_builder_workspace (
    id INTEGER PRIMARY KEY CHECK(id = 1),
    revision INTEGER NOT NULL CHECK(revision > 0),
    state_json TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
UPDATE project_metadata SET value='10' WHERE key='schema_version';
