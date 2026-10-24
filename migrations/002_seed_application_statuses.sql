INSERT INTO application_statuses
    (id, code, label, sort_order, is_system, is_terminal, created_at)
VALUES
    ('8a201a74-80b7-4d5f-b7eb-304b182a13b0', 'draft', 'Entwurf', 10, 1, 0, strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('37336252-3301-4304-8c90-efacb3db4608', 'preparing', 'In Vorbereitung', 20, 1, 0, strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('7b4f35fd-bb57-4c15-82e4-ad8d85d335c7', 'sent', 'Versendet', 30, 1, 0, strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('aa893a0e-4417-42fd-95ca-0904d621c602', 'interview', 'Gespräch', 40, 1, 0, strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('5b1f32b2-3405-4b89-9880-991c6951688d', 'offer', 'Angebot', 50, 1, 0, strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('405d5fa0-530d-48cc-8e11-cf91786ace5c', 'accepted', 'Angenommen', 60, 1, 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('f70e6745-bab7-450f-8a89-4fe28ac06b26', 'rejected', 'Abgelehnt', 70, 1, 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('81c3920b-08b4-42d6-817f-6d41bb0a51a1', 'withdrawn', 'Zurückgezogen', 80, 1, 1, strftime('%Y-%m-%dT%H:%M:%fZ','now'));
