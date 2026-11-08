"""ATMS con memoria bitemporal derivada: soporte lógico, nunca verdad empírica.

Diseño: el ledger es la fuente canónica. Cada corte autorizado se recompone desde
revisiones; se conserva el linaje y no se mutan snapshots anteriores. El cálculo de
etiquetas es un punto fijo grounded, con antichains y límites explícitos.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from itertools import product
from hashlib import sha256
import json
from typing import Any, Iterable


ENGINE_VERSION = "igc-arena-atms/0.1"
# Preserve historical S/P/B0 replays while admitting the current D/B/M arms.
MEMORY_LANES = frozenset({"D", "B", "M", "S", "P", "B0"})
KINDS = frozenset({"assumption", "fact", "justification", "nogood"})
MAX_ENVIRONMENTS = 2000
MAX_COMBINATIONS = 20000
MAX_STEPS = 100000


class ATMSError(ValueError):
    pass


class ATMSLimitError(ATMSError):
    def __init__(self, kind: str, processed: int):
        super().__init__(f"COMBINATORIAL_LIMIT_REACHED:{kind}:{processed}")
        self.kind, self.processed = kind, processed


def canonical(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def digest(obj: Any) -> str:
    return sha256(canonical(obj)).hexdigest()


def _utc(timestamp: str) -> datetime:
    if not isinstance(timestamp, str):
        raise ATMSError("timestamp with timezone required")
    try:
        value = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ATMSError("invalid timestamp") from exc
    if value.tzinfo is None or value.utcoffset() is None:
        raise ATMSError("timestamp with timezone required")
    return value.astimezone(timezone.utc)


def _minimize(items: Iterable[frozenset[str]]) -> set[frozenset[str]]:
    result: set[frozenset[str]] = set()
    for env in sorted(set(items), key=lambda x: (len(x), tuple(sorted(x)))):
        if not any(item <= env for item in result):
            result.add(env)
    return result


def _ordered_envs(items: Iterable[frozenset[str]]) -> list[list[str]]:
    return [sorted(x) for x in sorted(items, key=lambda x: (len(x), tuple(sorted(x))))]


@dataclass(frozen=True)
class Rule:
    id: str
    antecedents: tuple[str, ...]
    consequent: str
    source_id: str | None = None


@dataclass
class ATMS:
    assumptions: set[str]
    facts: set[str]
    justifications: list[Rule]
    nogoods: set[frozenset[str]]
    max_environments: int = MAX_ENVIRONMENTS
    max_combinations: int = MAX_COMBINATIONS
    max_steps: int = MAX_STEPS
    labels: dict[str, set[frozenset[str]]] = field(default_factory=dict, init=False)
    witnesses: dict[tuple[str, frozenset[str]], tuple[str, tuple[tuple[str, frozenset[str]], ...]]] = field(
        default_factory=dict, init=False)
    stats: dict[str, int] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        if (min(self.max_environments, self.max_combinations, self.max_steps) < 1):
            raise ATMSError("positive computation budgets required")
        if not self.assumptions.isdisjoint(self.facts):
            raise ATMSError("assumption and fact IDs overlap")
        for n in self.nogoods:
            if not n or not n <= self.assumptions:
                raise ATMSError("nogood must contain known assumptions")
        self.nogoods = _minimize(self.nogoods)
        seen: set[str] = set()
        for rule in self.justifications:
            if not rule.id or rule.id in seen or not rule.consequent:
                raise ATMSError("rule IDs must be unique and conclusion non-empty")
            seen.add(rule.id)
            if rule.consequent in self.assumptions or rule.consequent in self.facts:
                raise ATMSError("assumption/fact seeds cannot be derived by a justification")
            if len(set(rule.antecedents)) != len(rule.antecedents) or any(not x for x in rule.antecedents):
                raise ATMSError("repeated or empty rule antecedent")
        self.compute()

    def _consistent(self, env: frozenset[str]) -> bool:
        return not any(ng <= env for ng in self.nogoods)

    def compute(self) -> None:
        self.labels = {}
        self.witnesses = {}
        steps = combos = 0
        for node in sorted(self.assumptions):
            env = frozenset((node,))
            self.labels[node] = {env} if self._consistent(env) else set()
            if self.labels[node]:
                self.witnesses[(node, env)] = ("assumption", ())
        for node in sorted(self.facts):
            env = frozenset()
            self.labels[node] = {env}
            self.witnesses[(node, env)] = ("fact", ())
        if sum(map(len, self.labels.values())) > self.max_environments:
            raise ATMSLimitError("environments", sum(map(len, self.labels.values())))
        rules = sorted(self.justifications, key=lambda r: r.id)
        change = True
        while change:
            change = False
            for rule in rules:
                steps += 1
                if steps > self.max_steps:
                    raise ATMSLimitError("steps", steps)
                options = [sorted(self.labels.get(n, set()),
                                  key=lambda x: (len(x), tuple(sorted(x))))
                           for n in rule.antecedents]
                if any(not group for group in options):
                    continue
                for combination in product(*options):
                    combos += 1
                    if combos > self.max_combinations:
                        raise ATMSLimitError("combinations", combos)
                    merged = frozenset().union(*combination)
                    if not self._consistent(merged):
                        continue
                    prior = self.labels.get(rule.consequent, set())
                    if any(old <= merged for old in prior):
                        continue
                    updated = _minimize(prior | {merged})
                    removed = prior - updated
                    self.labels[rule.consequent] = updated
                    for obsolete in removed:
                        self.witnesses.pop((rule.consequent, obsolete), None)
                    self.witnesses[(rule.consequent, merged)] = (
                        rule.id, tuple(zip(rule.antecedents, combination)))
                    if sum(map(len, self.labels.values())) > self.max_environments:
                        raise ATMSLimitError("environments", sum(map(len, self.labels.values())))
                    change = True
        self.stats = {"steps": steps, "combinations": combos,
                      "environments": sum(map(len, self.labels.values())),
                      "nodes": len(self.labels), "rules": len(rules)}

    def supported_in(self, node: str, context: Iterable[str]) -> bool:
        selected = frozenset(context)
        if not selected <= self.assumptions:
            raise ATMSError("unknown context assumption")
        return any(e <= selected for e in self.labels.get(node, set()))

    def explain(self, node: str, *, max_depth: int = 40) -> dict[str, Any]:
        """Return all surviving minimal supports and one grounded witness per support."""
        def trace(n: str, env: frozenset[str], seen: frozenset[tuple[str, frozenset[str]]], depth: int) -> dict:
            key = (n, env)
            if depth <= 0 or key in seen:
                raise ATMSError("witness chain is cyclic or too deep")
            rule_id, premises = self.witnesses[key]
            rule = next((r for r in self.justifications if r.id == rule_id), None)
            return {"node": n, "environment": sorted(env), "via": rule_id,
                    "source_id": rule.source_id if rule is not None else None,
                    "premises": [trace(p, support, seen | {key}, depth - 1)
                                 for p, support in premises]}
        environments = _ordered_envs(self.labels.get(node, set()))
        return {"node": node, "supported": bool(environments),
                "minimal_environments": environments,
                "paths": [trace(node, frozenset(e), frozenset(), max_depth) for e in environments]}


    def what_if(self, *, disable_assumptions: Iterable[str] = (),
                disable_rules: Iterable[str] = (),
                add_nogoods: Iterable[Iterable[str]] = ()) -> dict[str, Any]:
        """Ephemeral branch; canonical history and this engine remain unmodified."""
        gone = set(disable_assumptions)
        rule_ids = set(disable_rules)
        if not gone <= self.assumptions:
            raise ATMSError("unknown assumption to disable")
        if not rule_ids <= {r.id for r in self.justifications}:
            raise ATMSError("unknown rule to disable")
        extra = {frozenset(x) for x in add_nogoods}
        remaining = self.assumptions - gone
        if any(not x or not x <= remaining for x in extra):
            raise ATMSError("new nogoods require live, known assumptions")
        branched = ATMS(remaining, set(self.facts),
                        [r for r in self.justifications if r.id not in rule_ids],
                        {ng for ng in self.nogoods if ng <= remaining} | extra,
                        self.max_environments, self.max_combinations, self.max_steps)
        changed = {}
        for node in sorted(set(self.labels) | set(branched.labels)):
            before = _ordered_envs(self.labels.get(node, set()))
            after = _ordered_envs(branched.labels.get(node, set()))
            if before != after:
                changed[node] = {"before": before, "after": after}
        return {"status": "WHAT_IF_ONLY", "changed_nodes": changed,
                "changed_count": len(changed), "canonical_mutated": False,
                "branch_hash": digest(branched.to_report())}

    def to_report(self) -> dict[str, Any]:
        return {"engine": ENGINE_VERSION, "labels": {
            node: _ordered_envs(label) for node, label in sorted(self.labels.items())
        }, "nogoods": _ordered_envs(self.nogoods), "stats": self.stats}


def _authorized(policy: str, lane: str) -> bool:
    # Fail closed; never expose private/evaluator material to a constructor.
    return policy == "construction-visible" or policy == "lane:" + lane


def project(events: Iterable[dict[str, Any]], *, as_known_at: str, lane: str,
            investigation_id: str | None = None,
            max_environments: int = MAX_ENVIRONMENTS,
            max_combinations: int = MAX_COMBINATIONS,
            max_steps: int = MAX_STEPS) -> tuple[ATMS, dict[str, Any]]:
    """Rebuild from versioned events, filtering visibility BEFORE ATMS propagation."""
    if lane not in MEMORY_LANES:
        raise ATMSError("unknown lane")
    cut = _utc(as_known_at)
    latest: dict[tuple[str, str], tuple[datetime, int, dict]] = {}
    for position, raw in enumerate(events):
        event = dict(raw)
        if investigation_id is not None and event.get("investigation_id") != investigation_id:
            continue
        kind, identifier = event.get("kind"), event.get("id")
        if kind not in KINDS or not isinstance(identifier, str) or not identifier:
            raise ATMSError("invalid ATMS event kind or ID")
        when = _utc(event.get("recorded_at"))
        if when > cut:
            continue
        key = (kind, identifier)
        if key not in latest or (when, position) > latest[key][:2]:
            latest[key] = (when, position, event)
    visible = []
    for _, _, event in latest.values():
        if event.get("active", True) is False or not _authorized(event.get("access_policy", ""), lane):
            continue
        visible.append(event)
    visible.sort(key=lambda e: (e["kind"], e["id"]))
    assumptions = {e["id"] for e in visible if e["kind"] == "assumption"}
    facts = {e["id"] for e in visible if e["kind"] == "fact"}
    # A rule referring to a hidden assertion must not reveal its presence, even by ID.
    declared = assumptions | facts | {e["consequent"] for e in visible
                   if e["kind"] == "justification" and isinstance(e.get("consequent"), str)}
    rules = [Rule(e["id"], tuple(e.get("antecedents", [])), e["consequent"], e.get("source_id"))
             for e in visible if e["kind"] == "justification"
             and isinstance(e.get("antecedents"), list)
             and set(e["antecedents"]) <= declared]
    ng = {frozenset(e.get("assumption_ids", [])) for e in visible
          if e["kind"] == "nogood" and isinstance(e.get("assumption_ids"), list)
          and set(e["assumption_ids"]) <= assumptions}
    engine = ATMS(assumptions, facts, rules, ng, max_environments,
                  max_combinations, max_steps)
    manifest = {"schema": "igc-atms-projection/0.1", "engine": ENGINE_VERSION,
                "as_known_at": cut.isoformat(), "lane": lane,
                "investigation_id": investigation_id,
                "visible_event_ids": [e["kind"] + ":" + e["id"] for e in visible],
                "source_snapshot_hash": digest(visible),
                "projection_hash": digest(engine.to_report())}
    return engine, manifest


def events_from_ledger(revisions: Iterable[Any]) -> list[dict[str, Any]]:
    """Adapter for scripts.ledger.Ledger.snapshot(...); never reads inaccessible revisions."""
    records = []
    for revision in revisions:
        data = revision.payload
        if isinstance(data, dict) and data.get("kind") in KINDS:
            event = dict(data)
            event["recorded_at"] = revision.recorded_at
            event["access_policy"] = revision.access_policy
            event["id"] = revision.entity_id
            event["investigation_id"] = revision.case_id
            records.append(event)
    return records
