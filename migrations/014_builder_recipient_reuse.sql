-- Repeated targets need an explicit Builder choice; ordinary groups keep uniqueness.
CREATE TABLE email_draft_batch_items_next (
    batch_id TEXT NOT NULL REFERENCES email_draft_batches(id),
    item_key TEXT NOT NULL,
    contact_id TEXT REFERENCES contacts(id),
    draft_id TEXT NOT NULL UNIQUE REFERENCES email_drafts(id),
    recipient_snapshot TEXT NOT NULL,
    name_snapshot TEXT NOT NULL,
    source_snapshot_json TEXT NOT NULL DEFAULT '{}',
    recipient_reuse_allowed INTEGER NOT NULL DEFAULT 0 CHECK(recipient_reuse_allowed IN (0,1)),
    PRIMARY KEY(batch_id, item_key)
);
INSERT INTO email_draft_batch_items_next(batch_id,item_key,contact_id,draft_id,recipient_snapshot,name_snapshot,source_snapshot_json)
SELECT batch_id,item_key,contact_id,draft_id,recipient_snapshot,name_snapshot,source_snapshot_json FROM email_draft_batch_items;
DROP TABLE email_draft_batch_items;
ALTER TABLE email_draft_batch_items_next RENAME TO email_draft_batch_items;
CREATE UNIQUE INDEX idx_batch_unique_recipient ON email_draft_batch_items(batch_id,recipient_snapshot COLLATE NOCASE) WHERE recipient_reuse_allowed=0;
