-- Preserve existing contact groups and allow import rows / manual rows without creating contacts.
CREATE TABLE email_draft_batch_items_next (
    batch_id TEXT NOT NULL REFERENCES email_draft_batches(id),
    item_key TEXT NOT NULL,
    contact_id TEXT REFERENCES contacts(id),
    draft_id TEXT NOT NULL UNIQUE REFERENCES email_drafts(id),
    recipient_snapshot TEXT NOT NULL,
    name_snapshot TEXT NOT NULL,
    source_snapshot_json TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY(batch_id, item_key),
    UNIQUE(batch_id, recipient_snapshot COLLATE NOCASE)
);
INSERT INTO email_draft_batch_items_next(batch_id,item_key,contact_id,draft_id,recipient_snapshot,name_snapshot)
SELECT batch_id,contact_id,contact_id,draft_id,recipient_snapshot,name_snapshot FROM email_draft_batch_items;
DROP TABLE email_draft_batch_items;
ALTER TABLE email_draft_batch_items_next RENAME TO email_draft_batch_items;
