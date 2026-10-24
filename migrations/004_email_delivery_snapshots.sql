-- Identity and local payload are fixed before any provider call.
ALTER TABLE email_jobs ADD COLUMN sender_snapshot TEXT;
ALTER TABLE email_jobs ADD COLUMN message_id_snapshot TEXT;
ALTER TABLE email_jobs ADD COLUMN payload_file_path TEXT;
ALTER TABLE email_jobs ADD COLUMN payload_hash TEXT;
ALTER TABLE email_jobs ADD COLUMN approval_snapshot_json TEXT NOT NULL DEFAULT '{}';
ALTER TABLE email_jobs ADD COLUMN requires_overdue_confirmation INTEGER NOT NULL DEFAULT 0 CHECK(requires_overdue_confirmation IN (0,1));
ALTER TABLE email_drafts ADD COLUMN provider_draft_id TEXT;
ALTER TABLE email_drafts ADD COLUMN synced_hash TEXT;
CREATE UNIQUE INDEX idx_email_jobs_message_identity ON email_jobs(message_id_snapshot) WHERE message_id_snapshot IS NOT NULL;
CREATE TRIGGER email_jobs_preserve_snapshot
BEFORE UPDATE OF provider_account_id,recipients_snapshot_json,subject_snapshot,body_snapshot,body_format,
                 scheduled_at_utc,timezone_id,sender_snapshot,message_id_snapshot,payload_file_path,payload_hash
ON email_jobs WHEN OLD.message_id_snapshot IS NOT NULL
BEGIN
    SELECT RAISE(ABORT, 'Delivery snapshots are immutable; prepare a new job.');
END;
