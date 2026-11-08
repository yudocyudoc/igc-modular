"""Durable run state and transparent consumption, independent of execution backend."""
import json
from pathlib import Path
import sqlite3
from datetime import datetime, timezone

from .common import ArenaError


def now():
    return datetime.now(timezone.utc).isoformat()


class RunStore:
    def __init__(self, root, *, config=None):
        self.root = Path(root).resolve()
        if config is not None:
            self.root.mkdir(parents=True, exist_ok=False)
        elif not (self.root / "run.sqlite").is_file():
            raise ArenaError("Run does not exist.")
        self.db = sqlite3.connect(self.root / "run.sqlite", timeout=10)
        self.db.row_factory = sqlite3.Row
        if config is not None:
            self.db.executescript("""
                CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE stages(name TEXT PRIMARY KEY, state TEXT NOT NULL,
                    run_id INTEGER, detail TEXT NOT NULL, updated TEXT NOT NULL);
                CREATE TABLE events(id INTEGER PRIMARY KEY, at TEXT NOT NULL,
                    stage TEXT NOT NULL, state TEXT NOT NULL);
                CREATE TABLE attempts(key TEXT PRIMARY KEY, kind TEXT NOT NULL,
                    amount INTEGER NOT NULL, state TEXT NOT NULL);
                CREATE TABLE measurements(source TEXT PRIMARY KEY, kind TEXT NOT NULL,
                    amount INTEGER NOT NULL, complete INTEGER NOT NULL);
            """)
            self.db.execute("INSERT INTO meta VALUES('config',?)", (json.dumps(config),))
            self.db.execute("INSERT INTO meta VALUES('created',?)", (now(),))
            self.db.execute("INSERT INTO meta VALUES('status','\"CREATED\"')")
            self.db.commit()

    @property
    def config(self):
        return json.loads(self.db.execute("SELECT value FROM meta WHERE key='config'").fetchone()[0])

    def status(self, value):
        self.db.execute("UPDATE meta SET value=? WHERE key='status'", (json.dumps(value),))
        self.db.commit()

    def authorize(self):
        self.db.execute("INSERT INTO meta VALUES('authorized','true') ON CONFLICT(key) DO UPDATE SET value='true'")
        self.db.commit()

    @property
    def authorized(self):
        row = self.db.execute("SELECT value FROM meta WHERE key='authorized'").fetchone()
        return bool(row and row[0] == 'true')

    def stage(self, name):
        row = self.db.execute("SELECT * FROM stages WHERE name=?", (name,)).fetchone()
        return dict(row) if row else None

    def transition(self, name, state, *, run_id=None, detail=None):
        data = json.dumps(detail or {})
        self.db.execute("""INSERT INTO stages VALUES(?,?,?,?,?)
            ON CONFLICT(name) DO UPDATE SET state=excluded.state,
            run_id=COALESCE(excluded.run_id,stages.run_id),detail=excluded.detail,
            updated=excluded.updated""", (name, state, run_id, data, now()))
        self.db.execute("INSERT INTO events(at,stage,state) VALUES(?,?,?)", (now(), name, state))
        self.db.commit()

    def attempt(self, key, kind, *, amount=1):
        if type(amount) is not int or amount <= 0:
            raise ArenaError("An attempt must consume a positive integer amount.")
        limit = self.config["budget"].get(kind)
        self.db.execute("BEGIN IMMEDIATE")
        try:
            if self.db.execute("SELECT 1 FROM attempts WHERE key=?", (key,)).fetchone():
                raise ArenaError("Attempt already registered; automatic retry refused.")
            used = self.db.execute("SELECT COALESCE(SUM(amount),0) FROM attempts WHERE kind=?", (kind,)).fetchone()[0]
            if limit is None or used + amount > limit:
                raise ArenaError("Budget exhausted or not declared: " + kind)
            self.db.execute("INSERT INTO attempts VALUES(?,?,?,'STARTED')", (key, kind, amount))
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

    def finish_attempt(self, key, *, successful):
        self.db.execute("UPDATE attempts SET state=? WHERE key=?", ("COMPLETED" if successful else "FAILED", key))
        self.db.commit()

    def measure(self, source, kind, amount, *, complete):
        if type(amount) is not int or amount < 0:
            raise ArenaError("Invalid consumption observation.")
        self.db.execute("INSERT INTO measurements VALUES(?,?,?,?) ON CONFLICT(source) DO UPDATE SET amount=excluded.amount,complete=excluded.complete",
                        (source, kind, amount, int(complete)))
        self.db.commit()

    def report(self):
        cfg = self.config
        stages = [dict(row) for row in self.db.execute("SELECT * FROM stages ORDER BY rowid")]
        for stage in stages:
            stage["detail"] = json.loads(stage["detail"])
        usage = {}
        for kind, limit in cfg["budget"].items():
            attempts = list(self.db.execute("SELECT * FROM attempts WHERE kind=?", (kind,)))
            measured = list(self.db.execute("SELECT * FROM measurements WHERE kind=?", (kind,)))
            known = cfg["backend"] == "fixture" or kind == "workflow" or (bool(measured) and all(x["complete"] for x in measured))
            count = sum(x["amount"] for x in attempts) + sum(x["amount"] for x in measured)
            usage[kind] = {"limit": limit, "observed_attempts": count,
                           "complete": known, "remaining": limit-count if known else None,
                           "failed_local_attempts": sum(x["amount"] for x in attempts if x["state"] == "FAILED")}
        return {"schema": "arena.run/1", "experiment": cfg["id"], "backend": cfg["backend"],
                "status": json.loads(self.db.execute("SELECT value FROM meta WHERE key='status'").fetchone()[0]),
                "stages": stages, "consumption": usage,
                "cost": {"estimated": None, "billed": None, "currency": None,
                         "note": "Not inferred from request counts; provider billing unavailable."}}

    def close(self):
        self.db.close()

