-- Durable recipient collections, dispatch policy and resumable document work.
CREATE TABLE recipient_groups(id TEXT PRIMARY KEY,name TEXT NOT NULL COLLATE NOCASE UNIQUE,created_at TEXT NOT NULL);
CREATE TABLE recipient_group_members(group_id TEXT NOT NULL REFERENCES recipient_groups(id) ON DELETE CASCADE,contact_id TEXT NOT NULL REFERENCES contacts(id),PRIMARY KEY(group_id,contact_id));
CREATE TABLE recipient_filters(id TEXT PRIMARY KEY,name TEXT NOT NULL COLLATE NOCASE UNIQUE,configuration_json TEXT NOT NULL,created_at TEXT NOT NULL);
ALTER TABLE email_bulk_dispatches ADD COLUMN daily_budget INTEGER NOT NULL DEFAULT 100 CHECK(daily_budget BETWEEN 1 AND 10000);
ALTER TABLE email_bulk_dispatches ADD COLUMN window_start TEXT NOT NULL DEFAULT '00:00';
ALTER TABLE email_bulk_dispatches ADD COLUMN window_end TEXT NOT NULL DEFAULT '00:00';
ALTER TABLE email_bulk_dispatches ADD COLUMN background INTEGER NOT NULL DEFAULT 0 CHECK(background IN (0,1));
CREATE TABLE email_account_holds(account_id TEXT PRIMARY KEY REFERENCES email_provider_accounts(id),until_utc TEXT NOT NULL,reason TEXT NOT NULL);
CREATE TABLE application_mail_receipts(application_id TEXT NOT NULL REFERENCES applications(id),job_id TEXT PRIMARY KEY REFERENCES email_jobs(id),status TEXT NOT NULL,updated_at TEXT NOT NULL);
INSERT INTO application_mail_receipts SELECT application_id,id,status,updated_at FROM email_jobs WHERE application_id IS NOT NULL;
CREATE TRIGGER application_mail_created AFTER INSERT ON email_jobs WHEN NEW.application_id IS NOT NULL BEGIN
    INSERT INTO application_mail_receipts VALUES(NEW.application_id,NEW.id,NEW.status,NEW.updated_at);
END;
CREATE TRIGGER application_mail_changed AFTER UPDATE OF status ON email_jobs WHEN NEW.application_id IS NOT NULL BEGIN
    INSERT INTO application_mail_receipts VALUES(NEW.application_id,NEW.id,NEW.status,NEW.updated_at) ON CONFLICT(job_id) DO UPDATE SET status=NEW.status,updated_at=NEW.updated_at;
    UPDATE applications SET status_id=(SELECT id FROM application_statuses WHERE code='sent'),application_date=COALESCE(application_date,substr(NEW.sent_at_utc,1,10)),updated_at=NEW.updated_at
        WHERE id=NEW.application_id AND NEW.status='Sent' AND deleted_at IS NULL AND status_id IN (SELECT id FROM application_statuses WHERE code IN ('draft','preparing'));
END;
CREATE TABLE word_replace_runs(id TEXT PRIMARY KEY,name TEXT NOT NULL,source_path TEXT NOT NULL,source_hash TEXT NOT NULL,configuration_json TEXT NOT NULL,status TEXT NOT NULL CHECK(status IN ('Paused','Running','Completed')),created_at TEXT NOT NULL,updated_at TEXT NOT NULL,owner_token TEXT,owner_pid INTEGER,owner_started TEXT,owner_host TEXT);
CREATE TABLE word_replace_run_items(run_id TEXT NOT NULL REFERENCES word_replace_runs(id),position INTEGER NOT NULL,fields_json TEXT NOT NULL,output_path TEXT NOT NULL,status TEXT NOT NULL CHECK(status IN ('Pending','Publishing','Completed','Failed')),document_id TEXT REFERENCES documents(id),output_hash TEXT,last_error TEXT,PRIMARY KEY(run_id,position));
