"""Minimal append-only SQLite ledger with bitemporal snapshots for synthetic F1a fixtures."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterator


class LedgerError(ValueError):
    """Invalid ledger command or temporal value."""


class IdempotencyConflict(LedgerError):
    """An idempotency key was reused for a different command."""


@dataclass(frozen=True)
class Revision:
    entity_id: str
    revision: int
    entity_type: str
    case_id: str
    event_id: str
    recorded_at: str
    valid_from: str | None
    valid_to: str | None
    supersedes_revision: int | None
    schema_version: str
    created_at: str
    created_by: str
    access_policy: str
    integrity_hash: str
    payload: dict[str, Any]


def _timestamp(value: str | None, *, field: str, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    if not isinstance(value, str) or not value:
        raise LedgerError(f"{field} must be a non-empty ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise LedgerError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise LedgerError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class Ledger:
    def __init__(self, db_path: str | Path, migration_path: str | Path):
        self.db_path = str(db_path)
        self.migration_path = Path(migration_path)
        migration_sql = self.migration_path.read_text(encoding="utf-8")
        migration_version = self.migration_path.stem
        migration_sha256 = _digest(migration_sql)
        with self._connect() as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS schema_migrations (
                    version TEXT PRIMARY KEY,
                    sha256 TEXT NOT NULL,
                    applied_at TEXT NOT NULL
                )"""
            )
            applied = connection.execute(
                "SELECT sha256 FROM schema_migrations WHERE version = ?",
                (migration_version,),
            ).fetchone()
            if applied:
                if applied["sha256"] != migration_sha256:
                    raise LedgerError(f"applied migration {migration_version} was modified")
                return
            try:
                migration_script = (
                    "BEGIN IMMEDIATE;" + chr(10)
                    + migration_sql
                    + chr(10)
                    + "INSERT INTO schema_migrations(version, sha256, applied_at) "
                    + f"VALUES ('{migration_version}', '{migration_sha256}', "
                    + "strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));"
                    + chr(10)
                    + "COMMIT;"
                )
                connection.executescript(migration_script)
            except Exception:
                if connection.in_transaction:
                    connection.rollback()
                raise

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.db_path, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
        finally:
            connection.close()

    def append_revision(
        self,
        *,
        entity_id: str,
        entity_type: str,
        case_id: str,
        actor_id: str,
        idempotency_key: str,
        payload: dict[str, Any],
        recorded_at: str,
        created_at: str,
        valid_from: str | None = None,
        valid_to: str | None = None,
        occurred_at: str | None = None,
        schema_version: str = "0.1.0",
        access_policy: str = "case-private",
    ) -> Revision:
        for name, value in {
            "entity_id": entity_id,
            "entity_type": entity_type,
            "case_id": case_id,
            "actor_id": actor_id,
            "idempotency_key": idempotency_key,
            "access_policy": access_policy,
        }.items():
            if not isinstance(value, str) or not value.strip():
                raise LedgerError(f"{name} must be a non-empty string")
        if not isinstance(payload, dict):
            raise LedgerError("payload must be a JSON object")
        recorded = _timestamp(recorded_at, field="recorded_at")
        created = _timestamp(created_at, field="created_at")
        valid_start = _timestamp(valid_from, field="valid_from", optional=True)
        valid_end = _timestamp(valid_to, field="valid_to", optional=True)
        occurred = _timestamp(occurred_at, field="occurred_at", optional=True)
        if valid_start and valid_end and valid_end <= valid_start:
            raise LedgerError("valid_to must be later than valid_from")
        payload_json = _canonical(payload)
        payload_hash = _digest(payload_json)
        event_body = _canonical({
            "entity_id": entity_id,
            "entity_type": entity_type,
            "case_id": case_id,
            "actor_id": actor_id,
            "recorded_at": recorded,
            "created_at": created,
            "valid_from": valid_start,
            "valid_to": valid_end,
            "occurred_at": occurred,
            "schema_version": schema_version,
            "access_policy": access_policy,
            "payload_hash": payload_hash,
        })
        event_hash = _digest(event_body)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            previous_event = connection.execute(
                "SELECT event_id, payload_hash FROM ledger_events WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
            if previous_event:
                existing = connection.execute(
                    "SELECT * FROM entity_revisions WHERE event_id = ?",
                    (previous_event["event_id"],),
                ).fetchone()
                if previous_event["payload_hash"] != event_hash or existing is None:
                    connection.rollback()
                    raise IdempotencyConflict("idempotency key already belongs to a different command")
                connection.commit()
                return self._from_row(existing)
            current = connection.execute(
                "SELECT revision, case_id, recorded_at FROM entity_revisions WHERE entity_id = ? ORDER BY revision DESC LIMIT 1",
                (entity_id,),
            ).fetchone()
            if current and current["case_id"] != case_id:
                connection.rollback()
                raise LedgerError("an entity cannot change case_id across revisions")
            if current and recorded < current["recorded_at"]:
                connection.rollback()
                raise LedgerError("recorded_at cannot precede the prior revision for this entity")
            revision = (current["revision"] + 1) if current else 1
            supersedes = revision - 1 if revision > 1 else None
            event_id = f"urn:igc:event:{_digest(idempotency_key)[:24]}"
            connection.execute(
                """INSERT INTO ledger_events
                   (event_id, case_id, event_type, actor_id, idempotency_key, occurred_at,
                    recorded_at, schema_version, payload_hash, payload_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (event_id, case_id, "entity_revision_recorded", actor_id, idempotency_key,
                 occurred, recorded, schema_version, event_hash, event_body),
            )
            integrity_body = _canonical({
                "entity_id": entity_id, "revision": revision, "event_id": event_id,
                "entity_type": entity_type, "case_id": case_id, "recorded_at": recorded,
                "valid_from": valid_start, "valid_to": valid_end, "supersedes_revision": supersedes,
                "schema_version": schema_version, "created_at": created, "created_by": actor_id,
                "access_policy": access_policy, "payload_hash": payload_hash,
            })
            integrity_hash = _digest(integrity_body)
            connection.execute(
                """INSERT INTO entity_revisions
                   (entity_id, revision, entity_type, case_id, event_id, recorded_at,
                    valid_from, valid_to, supersedes_revision, schema_version, created_at,
                    created_by, access_policy, integrity_hash, payload_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (entity_id, revision, entity_type, case_id, event_id, recorded,
                 valid_start, valid_end, supersedes, schema_version, created, actor_id,
                 access_policy, integrity_hash, payload_json),
            )
            row = connection.execute(
                "SELECT * FROM entity_revisions WHERE entity_id = ? AND revision = ?",
                (entity_id, revision),
            ).fetchone()
            connection.commit()
            return self._from_row(row)

    def snapshot(
        self,
        *,
        case_id: str,
        as_known_at: str,
        valid_during: tuple[str, str] | None = None,
    ) -> list[Revision]:
        system_cut = _timestamp(as_known_at, field="as_known_at")
        window: tuple[str, str] | None = None
        if valid_during:
            start = _timestamp(valid_during[0], field="valid_during.start")
            end = _timestamp(valid_during[1], field="valid_during.end")
            if end <= start:
                raise LedgerError("valid_during end must be later than start")
            window = (start, end)
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT * FROM entity_revisions
                   WHERE case_id = ? AND recorded_at <= ?
                   ORDER BY entity_id, recorded_at DESC, revision DESC""",
                (case_id, system_cut),
            ).fetchall()
        latest: dict[str, sqlite3.Row] = {}
        for row in rows:
            latest.setdefault(row["entity_id"], row)
        result = [self._from_row(row) for row in latest.values()]
        if window:
            result = [
                item for item in result
                if (item.valid_from is None or item.valid_from < window[1])
                and (item.valid_to is None or item.valid_to > window[0])
            ]
        return sorted(result, key=lambda item: item.entity_id)

    def verify_integrity(self, *, entity_id: str, revision: int) -> bool:
        """Check a stored revision digest against its canonical metadata and payload."""
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM entity_revisions WHERE entity_id = ? AND revision = ?",
                (entity_id, revision),
            ).fetchone()
        if row is None:
            raise LedgerError("revision does not exist")
        payload = json.loads(row["payload_json"])
        payload_hash = _digest(_canonical(payload))
        body = _canonical({
            "entity_id": row["entity_id"],
            "revision": row["revision"],
            "event_id": row["event_id"],
            "entity_type": row["entity_type"],
            "case_id": row["case_id"],
            "recorded_at": row["recorded_at"],
            "valid_from": row["valid_from"],
            "valid_to": row["valid_to"],
            "supersedes_revision": row["supersedes_revision"],
            "schema_version": row["schema_version"],
            "created_at": row["created_at"],
            "created_by": row["created_by"],
            "access_policy": row["access_policy"],
            "payload_hash": payload_hash,
        })
        return _digest(body) == row["integrity_hash"]

    @staticmethod
    def _from_row(row: sqlite3.Row) -> Revision:
        return Revision(
            entity_id=row["entity_id"],
            revision=row["revision"],
            entity_type=row["entity_type"],
            case_id=row["case_id"],
            event_id=row["event_id"],
            recorded_at=row["recorded_at"],
            valid_from=row["valid_from"],
            valid_to=row["valid_to"],
            supersedes_revision=row["supersedes_revision"],
            schema_version=row["schema_version"],
            created_at=row["created_at"],
            created_by=row["created_by"],
            access_policy=row["access_policy"],
            integrity_hash=row["integrity_hash"],
            payload=json.loads(row["payload_json"]),
        )
