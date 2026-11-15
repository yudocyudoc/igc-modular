"""Arena ATMS decision projection v1: bounded, versioned, contextual justification.

This is the explicit coffee decision-facing projection; it does NOT replace
the existing historical producer Ledger/ATMS in coffee_feedback/_vendor.
Logical support is NOT empirical truth, probability, causality or business ROI.
Events are append-only records with separate recorded_at / valid_from times;
history is replayed from each authorized prefix, never overwritten.
"""
from __future__ import annotations

from datetime import datetime, timezone
from itertools import product
import re

from .common import ArenaError, digest

SCHEMA = "arena.decision-atms.journal/1"
SNAPSHOT = "arena.decision-atms.snapshot/1"
SCOPE = "COFFEE_CONSTRUCTION_DECISION"
MAX_EVENTS = 160
MAX_ASSUMPTIONS = 24
MAX_LABELS = 256
MAX_ROUNDS = 160
TIME_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z\Z")
SHA_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
IDENTITY = re.compile(r"[A-Z][A-Z0-9_]{0,95}\Z")
ASSUMPTION_STATUSES = {"ASSUMED", "BOUNDED", "SIMULATED", "EVIDENCED"}
OPS = {"assumption", "justification", "nogood", "retract", "restore"}


def need(ok, code):
    if not ok:
        raise ArenaError("COFFEE_ATMS_" + code)


def utc_now():
    return datetime.now(timezone.utc).isoformat(
        timespec="microseconds").replace("+00:00", "Z")


def stamp(value):
    need(isinstance(value, str) and TIME_RE.fullmatch(value),
         "CLOCK_FORMAT_UTC_MICROSECONDS")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ArenaError("COFFEE_ATMS_INVALID_TIMESTAMP") from None
    return parsed


def _id(value):
    need(type(value) is str and IDENTITY.fullmatch(value),
         "INVALID_IDENTIFIER")
    return value


def _source(value):
    need(type(value) is str and SHA_RE.fullmatch(value),
         "MISSING_PROVENANCE_SHA")
    return value


class Journal:
    """Deterministic total-recomputation oracle for small explicit graphs.

    Retraction/restoration is a new recorded event. Cycles without grounded
    assumptions never create labels. No incremental cache can go stale.
    """

    def __init__(self, events=()):
        self.events = []
        for e in events:
            self.append(e)

    def append(self, event):
        need(type(event) is dict and len(self.events) < MAX_EVENTS,
             "EVENT_LIMIT_OR_TYPE")
        op = event.get("op")
        need(op in OPS, "INVALID_EVENT_OP")
        required = {"op", "id", "recorded_at", "valid_from",
                    "scope", "source_sha256"}
        if op == "assumption":
            required |= {"node", "status"}
        elif op == "justification":
            required |= {"conclusion", "premises"}
        elif op == "nogood":
            required |= {"assumptions"}
        else:
            required |= {"target"}
        need(set(event) == required, "EVENT_FIELDS")
        _id(event["id"])
        known = stamp(event["recorded_at"])
        stamp(event["valid_from"])
        need(event["scope"] == SCOPE, "SCOPE_NOT_AUTHORIZED")
        _source(event["source_sha256"])
        if self.events:
            need(known > stamp(self.events[-1]["recorded_at"]),
                 "NOT_APPEND_ONLY_OR_SAME_RECORD_TIME")
        if op == "assumption":
            _id(event["node"])
            need(event["status"] in ASSUMPTION_STATUSES,
                 "ASSUMPTION_STATUS")
            need(sum(e["op"] == "assumption" for e in self.events)
                 < MAX_ASSUMPTIONS, "ASSUMPTION_LIMIT")
        elif op == "justification":
            _id(event["conclusion"])
            need(type(event["premises"]) is list and
                 1 <= len(event["premises"]) <= 12 and
                 len(event["premises"]) == len(set(event["premises"])),
                 "JUSTIFICATION_PREMISES")
            for p in event["premises"]:
                _id(p)
        elif op == "nogood":
            values = event["assumptions"]
            need(type(values) is list and 1 <= len(values) <= 12 and
                 len(values) == len(set(values)), "NOGOOD_CONTRACT")
            known_assumptions = {e["id"] for e in self.events
                                 if e["op"] == "assumption"}
            need(all(_id(x) in known_assumptions for x in values),
                 "NOGOOD_MUST_REFERENCE_ASSUMPTION_IDS")
        else:
            _id(event["target"])
            created = {e["id"] for e in self.events if e["op"] in
                       ("assumption", "justification", "nogood")}
            need(event["target"] in created, "RETRACTION_UNKNOWN_TARGET")
        need(event["id"] not in {e["id"] for e in self.events},
             "DUPLICATE_EVENT_ID")
        # Own clone: callers cannot mutate prior history by retaining a list.
        import copy
        self.events.append(copy.deepcopy(event))
        return len(self.events)

    def snapshot(self, *, as_known_at, valid_at):
        known = stamp(as_known_at)
        valid = stamp(valid_at)
        need(valid <= known, "FUTURE_VALIDITY_QUERY_NOT_AUTHORIZED")
        included = []
        states = {}
        definitions = {}
        for e in self.events:
            if stamp(e["recorded_at"]) > known or stamp(e["valid_from"]) > valid:
                continue
            included.append(e)
            if e["op"] in ("assumption", "justification", "nogood"):
                states[e["id"]] = True
                definitions[e["id"]] = e
            elif e["op"] == "retract":
                # This target must be known at the historical cut, not merely
                # created in an as-yet-unavailable future validity period.
                need(e["target"] in states, "HISTORIC_TARGET_NOT_YET_VISIBLE")
                states[e["target"]] = False
            else:
                need(e["target"] in states, "HISTORIC_TARGET_NOT_YET_VISIBLE")
                states[e["target"]] = True
        active = [definitions[k] for k in sorted(states) if states[k]]
        assumptions = [e for e in active if e["op"] == "assumption"]
        justifications = [e for e in active if e["op"] == "justification"]
        bad = [frozenset(e["assumptions"]) for e in active
               if e["op"] == "nogood"]
        def consistent(env):
            return not any(b.issubset(env) for b in bad)
        def minimal(groups):
            result = []
            for env in sorted(set(groups), key=lambda v:(len(v),tuple(sorted(v)))):
                if consistent(env) and not any(previous <= env for previous in result):
                    result.append(env)
                    need(len(result) <= MAX_LABELS, "COMBINATORIAL_LIMIT_REACHED")
            return frozenset(result)
        labels = {}
        for e in assumptions:
            labels[e["node"]] = minimal(
                set(labels.get(e["node"], frozenset())) |
                {frozenset((e["id"],))})
        for _ in range(MAX_ROUNDS):
            changed = False
            for rule in justifications:
                required = [labels.get(p, frozenset()) for p in rule["premises"]]
                if not all(required):
                    continue
                expansions = []
                for environments in product(*required):
                    joined = frozenset().union(*environments)
                    if consistent(joined):
                        expansions.append(joined)
                    need(len(expansions) <= MAX_LABELS * 4,
                         "COMBINATORIAL_LIMIT_REACHED")
                dest = rule["conclusion"]
                next_label = minimal(set(labels.get(dest, frozenset())) |
                                     set(expansions))
                if next_label != labels.get(dest, frozenset()):
                    labels[dest] = next_label
                    changed = True
            if not changed:
                break
        else:
            raise ArenaError("COFFEE_ATMS_FIXPOINT_LIMIT_REACHED")
        normalized = {
            node: [sorted(env) for env in
                   sorted(sets, key=lambda s:(len(s),tuple(sorted(s))))]
            for node, sets in sorted(labels.items()) if sets
        }
        assumptions_by_id = {e["id"]: {
            "node":e["node"], "status":e["status"],
            "source_sha256":e["source_sha256"]
        } for e in assumptions}
        snapshot = {
            "schema": SNAPSHOT, "scope": SCOPE,
            "as_known_at": as_known_at, "valid_at": valid_at,
            "active_event_ids": sorted(states_id for states_id, enabled in
                                       states.items() if enabled),
            "journal_sha256": digest(included),
            "included_event_prefix_sha256": digest(included),
            "labels": normalized,
            "assumption_provenance": assumptions_by_id,
            "logical_support_is_not_empirical_truth": True,
            "no_reserved_or_rival_lane_evidence": True,
            "engine": "BOUNDED_TOTAL_RECOMPUTATION_ATMS_V1",
        }
        snapshot["snapshot_sha256"] = digest(snapshot)
        return snapshot


    def what_if(self, *, as_known_at, valid_at, candidate_events):
        """Ephemeral branch on an as-known prefix; never edits the journal.

        Future canonical events are not included in the fork. The caller must
        give append-only, later-dated hypothetical operations; resulting
        supports are not committed or treated as measured evidence.
        """
        base = self.snapshot(as_known_at=as_known_at, valid_at=valid_at)
        need(type(candidate_events) is list and
             0 < len(candidate_events) <= 12, "WHAT_IF_EVENT_LIMIT")
        prefix = [e for e in self.events
                  if stamp(e["recorded_at"]) <= stamp(as_known_at)]
        fork = Journal(prefix)
        for e in candidate_events:
            fork.append(e)
        last = candidate_events[-1]["recorded_at"]
        changed = fork.snapshot(as_known_at=last, valid_at=last)
        nodes = sorted(set(base["labels"]) | set(changed["labels"]))
        return {
            "schema":"arena.decision-atms.what-if/1",
            "baseline_snapshot_sha256":base["snapshot_sha256"],
            "hypothetical_snapshot":changed,
            "changed_labels":{
                node:{"before":base["labels"].get(node,[]),
                      "after":changed["labels"].get(node,[])}
                for node in nodes if
                base["labels"].get(node,[]) != changed["labels"].get(node,[])
            },
            "hypothetical_only":True,
            "canonical_journal_sha256_unchanged":digest(self.events),
            "no_empirical_inference_or_business_recommendation":True,
        }

    def explain(self, node, *, as_known_at, valid_at):
        _id(node)
        snap = self.snapshot(as_known_at=as_known_at, valid_at=valid_at)
        active = set(snap["active_event_ids"])
        rules = [e for e in self.events
                 if e["id"] in active and e["op"] == "justification"
                 and e["conclusion"] == node]
        return {
            "node":node,
            "logical_support_environments": snap["labels"].get(node, []),
            "status": ("CONDITIONALLY_SUPPORTED"
                       if snap["labels"].get(node) else "UNSUPPORTED"),
            "available_justifications": [
                {"id":r["id"],"premises":r["premises"],
                 "source_sha256":r["source_sha256"]}
                for r in rules],
            "missing_nodes_by_justification": {
                r["id"]:[p for p in r["premises"]
                         if p not in snap["labels"]]
                for r in rules},
            "snapshot_sha256": snap["snapshot_sha256"],
            "logical_support_is_not_empirical_truth": True,
        }


def event(op, name, at, source, **values):
    return dict(op=op,id=_id(name),recorded_at=at,valid_from=at,
                scope=SCOPE,source_sha256=_source(source),**values)


def scenario_predecision(dossier, protocol, *, recorded_at):
    """Typed P07 & P11 premises; cannot claim real-world S5 support."""
    from . import coffee_v2_reference as physical
    from . import coffee_v2_p11 as p11
    physical.config_gate(dossier)
    p11.protocol_gate(protocol)
    need(dossier["policy"] == "B0", "P11_PREMATURE_POLICY_SWITCH")
    need(dossier["resources"]["existing_support"]["units"] >= 1,
         "NO_DECLARED_SUPPORT_FOR_S5")
    source = digest({"dossier":dossier,"protocol":protocol})
    journal = Journal()
    # Unique timestamp per append: logical UTC microsecond cut positions
    # rather than invented observation times.
    from datetime import timedelta
    base = stamp(recorded_at)
    def at(i):
        return (base+timedelta(microseconds=i)).isoformat(
            timespec="microseconds").replace("+00:00", "Z")
    concepts = [
        ("A_CONSTRUCTION", "CONSTRUCTION_SCOPE_ONLY", "BOUNDED"),
        ("A_PAIRED", "IDENTICAL_INPUT_AND_RESOURCES", "ASSUMED"),
        ("A_HANDOFF", "HANDOFF_TRANSFERABLE_IN_REFERENCE", "ASSUMED"),
        ("A_SUPPORT", "SUPPORT_PRESENT_IN_DECLARED_DOSSIER", "ASSUMED"),
    ]
    for i,(key,node,status) in enumerate(concepts):
        journal.append(event("assumption",key,at(i),source,
                             node=node,status=status))
    journal.append(event("justification","J_S5_SIM",at(4),source,
                        conclusion="S5_CONDITIONAL_SIMULATABLE",
                        premises=[x[1] for x in concepts]))
    journal.append(event("justification","J_S5_REAL",at(5),source,
                        conclusion="S5_REAL_FEASIBLE",
                        premises=["S5_CONDITIONAL_SIMULATABLE",
                                  "SUPPORT_ACTUALLY_AVAILABLE",
                                  "SERVICE_TIMES_REAL_VALIDATED"]))
    journal.append(event("justification","J_S5_PROFIT",at(6),source,
                        conclusion="S5_REAL_ECONOMIC_BENEFIT",
                        premises=["S5_REAL_FEASIBLE",
                                  "REAL_OPPORTUNITY_COST_VALIDATED",
                                  "EARLY_HANDOFF_REAL_VALUE_VALIDATED",
                                  "CAUSAL_SERVICE_GAIN_VALIDATED"]))
    cut=at(7)
    snap=journal.snapshot(as_known_at=cut,valid_at=cut)
    need(bool(snap["labels"].get("S5_CONDITIONAL_SIMULATABLE")) and
         not snap["labels"].get("S5_REAL_FEASIBLE") and
         not snap["labels"].get("S5_REAL_ECONOMIC_BENEFIT"),
         "PREDECISION_TRUTH_OR_POLICY_LEAK")
    return {
        "schema":"arena.coffee-atms.predecision/1",
        "status":"S5_ONLY_CONDITIONAL_SYNTHETIC_COMPARISON_ADMITTED",
        "dossier_sha256":digest(dossier),
        "protocol_sha256":digest(protocol),
        "source_sha256":source,
        "journal":journal.events,
        "snapshot":snap,
        "admissibility":journal.explain(
            "S5_CONDITIONAL_SIMULATABLE",
            as_known_at=cut,valid_at=cut),
        "real_business_claim":journal.explain(
            "S5_REAL_ECONOMIC_BENEFIT",as_known_at=cut,valid_at=cut),
        "no_real_support_or_economic_assumptions_fabricated":True,
        "no_truth_access":True,
    }


def postevaluation(pre, policy, native, *, recorded_at, execution_receipt=None):
    """Append post-seal observations; never mutate pre-decision cut or labels."""
    need(type(pre) is dict and
         pre.get("schema")=="arena.coffee-atms.predecision/1" and
         pre.get("status")=="S5_ONLY_CONDITIONAL_SYNTHETIC_COMPARISON_ADMITTED"
         and pre.get("no_truth_access") is True, "PREDECISION_PROOF_REQUIRED")
    journal=Journal(pre["journal"])
    original=pre["snapshot"]
    need(journal.snapshot(as_known_at=original["as_known_at"],
                          valid_at=original["valid_at"])==original,
         "PREDECISION_SNAPSHOT_CHANGED")
    if execution_receipt is not None:
        from . import decision_atms_gate as contract
        contract.require_executable(execution_receipt)
        need(execution_receipt["predecision_snapshot_sha256"] ==
             original["snapshot_sha256"] and
             policy.get("atms_execution_gate_sha256") ==
             execution_receipt["gate_sha256"],
             "ATMS_EXECUTION_PARENT_MISMATCH")
        for amendment in execution_receipt["revision_events"]:
            journal.append(amendment)
        before=execution_receipt["atms_snapshot"]
        need(journal.snapshot(as_known_at=before["as_known_at"],
                              valid_at=before["valid_at"])==before,
             "ATMS_GATE_REVISION_SNAPSHOT_CHANGED")
    else:
        before=original
    need(type(policy) is dict and
         policy.get("dossier_sha256")==pre["dossier_sha256"] and
         policy.get("protocol_sha256")==pre["protocol_sha256"] and
         policy.get("status")==
         "P11_CONDITIONAL_CONSEQUENCES_NOT_BUSINESS_RECOMMENDATION",
         "P11_RESULT_PARENT_MISMATCH")
    need(type(native) is dict and
         native.get("truth_read_after_archived_lock") is True and
         native.get("policy_support_by_original_arms")=={
             "D":"S5_NOT_REPRESENTABLE","M":"S5_NOT_REPRESENTABLE",
             "B":"S5_NOT_REPRESENTABLE"},
         "POST_LOCK_NATIVE_POLICY_BOUNDARY")
    from datetime import timedelta
    base=stamp(recorded_at)
    need(base>stamp(before["as_known_at"]), "POST_NOT_AFTER_PREDECISION")
    src=digest({"p11_summary":policy["summary"],
                "native_lock_sha256":native.get("lock_sha256")})
    nominal=policy["summary"]["nominal_delta_by_load"]
    need(type(nominal) is dict and len(nominal)==2 and
         all(type(x) is int for x in nominal.values()), "NOMINAL_COUNTS_REQUIRED")
    if any(x>0 for x in nominal.values()):
        journal.append(event(
            "assumption","A_NOMINAL_GAIN_MODEL",recorded_at,src,
            node="NOMINAL_EARLY_HANDOFF_GAIN_IN_MODEL",status="SIMULATED"))
        journal.append(event(
            "justification","J_MODEL_GAIN",
            (base+timedelta(microseconds=1)).isoformat(
                timespec="microseconds").replace("+00:00","Z"),src,
            conclusion="S5_CONDITIONAL_MODEL_GAIN",
            premises=["S5_CONDITIONAL_SIMULATABLE",
                      "NOMINAL_EARLY_HANDOFF_GAIN_IN_MODEL"]))
    journal.append(event(
        "assumption","A_ARMS_NO_S5",
        (base+timedelta(microseconds=2)).isoformat(
            timespec="microseconds").replace("+00:00","Z"),src,
        node="NATIVE_DMB_DO_NOT_REPRESENT_S5",status="EVIDENCED"))
    last=(base+timedelta(microseconds=3)).isoformat(
        timespec="microseconds").replace("+00:00","Z")
    after=journal.snapshot(as_known_at=last,valid_at=last)
    need("NATIVE_DMB_DO_NOT_REPRESENT_S5" in after["labels"]
         and "S5_REAL_ECONOMIC_BENEFIT" not in after["labels"]
         and "S5_REAL_FEASIBLE" not in after["labels"],
         "POST_EVALUATION_UNJUSTIFIED_RECOMMENDATION")
    prior=before["labels"]
    changed=sorted(n for n in set(prior)|set(after["labels"])
                   if prior.get(n)!=after["labels"].get(n))
    return {
        "schema":"arena.coffee-atms.postevaluation/1",
        "status":"POST_SEAL_ATMS_UPDATED_NO_BUSINESS_RECOMMENDATION",
        "predecision_snapshot_sha256":original["snapshot_sha256"],
        "execution_snapshot_sha256":before["snapshot_sha256"],
        "execution_gate_sha256":(
            execution_receipt["gate_sha256"] if execution_receipt else None),
        "post_snapshot":after, "revision_events":journal.events[len(pre["journal"]):],
        "changed_support_nodes":changed,
        "conditionally_model_beneficial":bool(
            after["labels"].get("S5_CONDITIONAL_MODEL_GAIN")),
        "real_business_benefit":journal.explain(
            "S5_REAL_ECONOMIC_BENEFIT",as_known_at=last,valid_at=last),
        "model_limitation":journal.explain(
            "NATIVE_DMB_DO_NOT_REPRESENT_S5",as_known_at=last,valid_at=last),
        "prior_snapshot_remains_reproducible":True,
        "no_new_provider_omc_truth_or_worlds":True,
        "logical_support_is_not_empirical_truth":True,
    }
