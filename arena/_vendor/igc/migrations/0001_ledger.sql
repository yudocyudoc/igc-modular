CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    sha256 TEXT NOT NULL,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ledger_events (
    event_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    occurred_at TEXT,
    recorded_at TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS entity_revisions (
    entity_id TEXT NOT NULL,
    revision INTEGER NOT NULL CHECK (revision > 0),
    entity_type TEXT NOT NULL,
    case_id TEXT NOT NULL,
    event_id TEXT NOT NULL UNIQUE REFERENCES ledger_events(event_id),
    recorded_at TEXT NOT NULL,
    valid_from TEXT,
    valid_to TEXT,
    supersedes_revision INTEGER,
    schema_version TEXT NOT NULL,
    created_at TEXT NOT NULL,
    created_by TEXT NOT NULL,
    access_policy TEXT NOT NULL,
    integrity_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    PRIMARY KEY (entity_id, revision),
    CHECK (valid_from IS NULL OR valid_to IS NULL OR valid_to > valid_from),
    CHECK (supersedes_revision IS NULL OR supersedes_revision = revision - 1)
);

CREATE INDEX IF NOT EXISTS idx_entity_revisions_case_recorded
    ON entity_revisions(case_id, recorded_at, entity_id, revision);

CREATE INDEX IF NOT EXISTS idx_entity_revisions_valid_time
    ON entity_revisions(case_id, valid_from, valid_to);

CREATE TRIGGER IF NOT EXISTS ledger_events_no_update
BEFORE UPDATE ON ledger_events
BEGIN
    SELECT RAISE(ABORT, 'ledger_events is append-only');
END;

CREATE TRIGGER IF NOT EXISTS ledger_events_no_delete
BEFORE DELETE ON ledger_events
BEGIN
    SELECT RAISE(ABORT, 'ledger_events is append-only');
END;

CREATE TRIGGER IF NOT EXISTS entity_revisions_no_update
BEFORE UPDATE ON entity_revisions
BEGIN
    SELECT RAISE(ABORT, 'entity_revisions is append-only');
END;

CREATE TRIGGER IF NOT EXISTS entity_revisions_no_delete
BEFORE DELETE ON entity_revisions
BEGIN
    SELECT RAISE(ABORT, 'entity_revisions is append-only');
END;
