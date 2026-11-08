"""Arena memory: authorized lexical retrieval enriched by ATMS support paths.

The retrieval layer finds *candidates*. ATMS explains dependencies; it does not
turn retrieval relevance or logical support into empirical truth.
Vector/RDF/KGE backends are explicit follow-on adapters, not silently emulated.
"""
from __future__ import annotations

import argparse
from datetime import timezone
from hashlib import sha256
import json
from pathlib import Path
import re
import sqlite3
import unicodedata
from typing import Any, Iterable

from .arena_atms import ATMSError, MEMORY_LANES, canonical, digest, project, _utc, events_from_ledger


MEMORY_VERSION = "igc-arena-memory/0.1"


def _terms(value: str) -> set[str]:
    folded = unicodedata.normalize("NFKD", value.casefold())
    ascii_text = "".join(ch for ch in folded if not unicodedata.combining(ch))
    return set(re.findall(r"[a-z0-9]{2,}", ascii_text))


def _permit(policy: str, lane: str) -> bool:
    return policy in ("construction-visible", "lane:" + lane)


def _fts5_scores(eligible: list[dict[str, Any]], query: str) -> dict[str, float]:
    """Index ONLY post-permission, post-as-of objects in transient SQLite FTS5."""
    terms = sorted(_terms(query))
    if not terms or not eligible:
        return {}
    expression = " OR ".join('"' + token + '"' for token in terms)
    try:
        with sqlite3.connect(":memory:") as conn:
            conn.execute("CREATE VIRTUAL TABLE candidate_memory USING fts5("
                         "object_id UNINDEXED, title, body, "
                         "tokenize='unicode61 remove_diacritics 2')")
            conn.executemany("INSERT INTO candidate_memory VALUES (?, ?, ?)", [
                (item["id"], item["title"], item["text"]) for item in eligible])
            matches = conn.execute(
                "SELECT object_id, bm25(candidate_memory,0.0,4.0,1.0) "
                "FROM candidate_memory WHERE candidate_memory MATCH ?",
                (expression,)).fetchall()
    except sqlite3.OperationalError as exc:
        raise ATMSError("FTS5_UNAVAILABLE_OR_INVALID_QUERY") from exc
    return {identifier: round(-float(score), 10) for identifier, score in matches}


def visible_knowledge(records: Iterable[dict[str, Any]], *, at: str, lane: str,
                      investigation_id: str) -> list[dict[str, Any]]:
    """As-of and access filters run before ranking/indexing or ATMS references."""
    cut = _utc(at)
    latest: dict[str, tuple[Any, int, dict]] = {}
    for index, data in enumerate(records):
        if data.get("kind") != "knowledge" or not isinstance(data.get("id"), str):
            raise ATMSError("knowledge record kind/ID invalid")
        when = _utc(data["recorded_at"])
        if when > cut or data.get("investigation_id") != investigation_id:
            continue
        identifier = data["id"]
        if identifier not in latest or (when, index) > latest[identifier][:2]:
            latest[identifier] = (when, index, dict(data))
    results = []
    for _, _, item in latest.values():
        if item.get("active", True) is False or not _permit(item.get("access_policy", ""), lane):
            continue
        if not isinstance(item.get("title"), str) or not isinstance(item.get("text"), str):
            raise ATMSError("knowledge items require title/text")
        if not isinstance(item.get("node_id"), str) or not item["node_id"]:
            raise ATMSError("knowledge items require node_id")
        if not isinstance(item.get("source_id"), str) or not item["source_id"]:
            raise ATMSError("knowledge items require source_id")
        results.append(item)
    return sorted(results, key=lambda item: item["id"])


def retrieve(*, investigation_id: str, lane: str, as_known_at: str, query: str,
             knowledge_records: Iterable[dict[str, Any]],
             atms_events: Iterable[dict[str, Any]], top_k: int = 10,
             max_environments: int = 500, backend: str = "lexical") -> dict[str, Any]:
    if not isinstance(query, str) or not query.strip():
        raise ATMSError("query must be non-empty")
    if not (1 <= top_k <= 100):
        raise ATMSError("top_k out of bounds")
    if lane not in MEMORY_LANES:
        raise ATMSError("unknown lane")
    engine, atms_manifest = project(atms_events, as_known_at=as_known_at,
                                     lane=lane, investigation_id=investigation_id,
                                     max_environments=max_environments)
    eligible = visible_knowledge(knowledge_records, at=as_known_at, lane=lane,
                                 investigation_id=investigation_id)
    if backend not in ("lexical", "fts5"):
        raise ATMSError("unknown retrieval backend")
    query_terms = _terms(query)
    fts_scores = _fts5_scores(eligible, query) if backend == "fts5" else {}
    matched = []
    for item in eligible:
        if backend == "fts5":
            if item["id"] not in fts_scores:
                continue
            score = fts_scores[item["id"]]
        else:
            title_hits = len(query_terms & _terms(item["title"]))
            body_hits = len(query_terms & _terms(item["text"]))
            score = title_hits * 3 + body_hits
            if not score:
                continue
        node = item["node_id"]
        explanation = engine.explain(node)
        matched.append({
            "id": item["id"], "kind": item.get("item_type", "UNCLASSIFIED"),
            "title": item["title"], "text": item["text"],
            "source_id": item["source_id"], "source_revision": item.get("source_revision"),
            "node_id": node, "relevance_score": score,
            "logical_support": explanation,
            "epistemic_status": item.get("epistemic_status", "UNASSESSED"),
            "truth_status": "NOT_DETERMINED_BY_ATMS"
        })
    matched.sort(key=lambda x: (-x["relevance_score"], x["id"]))
    payload = {
        "schema": MEMORY_VERSION,
        "investigation_id": investigation_id, "lane": lane,
        "as_known_at": _utc(as_known_at).astimezone(timezone.utc).isoformat(),
        "query": query, "retrieval_backend": "FTS5_V0" if backend == "fts5" else "LEXICAL_V0",
        "vector_backend_status": "NOT_IMPLEMENTED",
        "rdf_backend_status": "NOT_CONNECTED",
        "atms": atms_manifest, "items": matched[:top_k],
        "coverage": {"authorized_knowledge_items": len(eligible),
                     "matching_items": len(matched),
                     "lexically_matching_items": len(matched),
                     "returned_items": min(len(matched), top_k)},
        "truncation_reason": "TOP_K" if len(matched) > top_k else None,
        "permissions_applied": ["construction-visible", "lane:" + lane],
        "holdout_accessed": False,
    }
    payload["reproducibility_hash"] = digest(payload)
    return payload


def load_events_from_ledger(db: Path, case_id: str, as_known_at: str) -> tuple[list[dict], list[dict]]:
    """Use F1a append-only bitemporal ledger as source, never mix later revisions."""
    from .ledger import Ledger
    root = Path(__file__).resolve().parents[1]
    ledger = Ledger(db, root / "migrations/0001_ledger.sql")
    revisions = ledger.snapshot(case_id=case_id, as_known_at=as_known_at)
    atms = events_from_ledger(revisions)
    knowledge = []
    for revision in revisions:
        data = revision.payload
        if revision.entity_type != "KnowledgeItem" or not isinstance(data, dict):
            continue
        item = dict(data)
        item.update(kind="knowledge", id=revision.entity_id,
                    recorded_at=revision.recorded_at, access_policy=revision.access_policy,
                    investigation_id=revision.case_id)
        knowledge.append(item)
    return knowledge, atms


def main() -> int:
    parser = argparse.ArgumentParser(description="IGC Arena memory/ATMS retrieval")
    parser.add_argument("--events", type=Path, help="JSON fixture with knowledge[] and atms[]")
    parser.add_argument("--db", type=Path, help="F1a SQLite ledger (instead of --events)")
    parser.add_argument("--case", required=True)
    parser.add_argument("--as-known-at", required=True)
    parser.add_argument("--lane", choices=sorted(MEMORY_LANES), required=True)
    parser.add_argument("--query", required=True)
    parser.add_argument("--backend", choices=("lexical", "fts5"), default="lexical")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if (args.events is None) == (args.db is None):
        parser.error("specify exactly one of --events and --db")
    if args.events is not None:
        data = json.loads(args.events.read_text(encoding="utf-8"))
        knowledge, atms = data["knowledge"], data["atms"]
    else:
        knowledge, atms = load_events_from_ledger(args.db, args.case, args.as_known_at)
    result = retrieve(investigation_id=args.case, lane=args.lane,
                      as_known_at=args.as_known_at, query=args.query,
                      knowledge_records=knowledge, atms_events=atms,
                      backend=args.backend)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical(result) + b"\n")
    print(json.dumps({"status": "PASS_FTS5_ATMS" if args.backend == "fts5" else "PASS_LEXICAL_ATMS",
                      "items": len(result["items"]), "hash": result["reproducibility_hash"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
