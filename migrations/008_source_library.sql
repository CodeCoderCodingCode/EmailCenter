CREATE TABLE data_source_profiles (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL COLLATE NOCASE UNIQUE,
    mapping_json TEXT NOT NULL,
    defaults_json TEXT NOT NULL,
    empty_policy TEXT NOT NULL CHECK(empty_policy IN ('fallback','keep')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE data_source_lists (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL COLLATE NOCASE UNIQUE,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE data_source_list_rows (
    id TEXT PRIMARY KEY,
    list_id TEXT NOT NULL REFERENCES data_source_lists(id),
    position INTEGER NOT NULL,
    fields_json TEXT NOT NULL,
    UNIQUE(list_id,position)
);
