-- Immutable, project-local builder versions. Existing drafts and jobs stay intact.
CREATE TABLE email_builders (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE email_builder_versions (
    id TEXT PRIMARY KEY,
    builder_id TEXT NOT NULL REFERENCES email_builders(id),
    version_number INTEGER NOT NULL CHECK(version_number > 0),
    graph_json TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(builder_id,version_number)
);
