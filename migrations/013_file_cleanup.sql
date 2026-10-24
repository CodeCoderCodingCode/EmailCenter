-- Persistent receipts allow retry after a locked file or interrupted cleanup.
CREATE TABLE file_cleanup(id TEXT PRIMARY KEY, file_path TEXT NOT NULL, file_hash TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('Pending','Deleted','Blocked')), last_error TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
