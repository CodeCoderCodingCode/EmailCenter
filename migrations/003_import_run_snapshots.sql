-- Run configuration stays fixed even when a reusable profile changes later.
ALTER TABLE import_runs ADD COLUMN configuration_json TEXT NOT NULL DEFAULT '{}';
ALTER TABLE import_runs ADD COLUMN source_file_hash TEXT;
