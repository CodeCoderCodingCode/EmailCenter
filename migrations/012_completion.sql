ALTER TABLE contacts ADD COLUMN address_json TEXT NOT NULL DEFAULT '{}';
CREATE TABLE record_archive(entity_type TEXT NOT NULL, entity_id TEXT NOT NULL, archived_at TEXT NOT NULL, PRIMARY KEY(entity_type,entity_id));
CREATE TABLE export_history(id TEXT PRIMARY KEY, kind TEXT NOT NULL, file_path TEXT NOT NULL, file_hash TEXT NOT NULL, file_size_bytes INTEGER NOT NULL, row_count INTEGER NOT NULL DEFAULT 0, configuration_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL);
CREATE TABLE builder_groups(id TEXT PRIMARY KEY, name TEXT NOT NULL COLLATE NOCASE UNIQUE, graph_json TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
