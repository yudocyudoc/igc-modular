"""CT-02: scoped own-feedback ledger retrieval BEFORE a producer decision.

This is a versioned adapter over F1a Ledger, arena_atms, arena_memory and M2's
original own_policy. It does not run OpenModelica, Buffalo or a new estimator.
It must never use future truth, other arms' models or a missing CSV as zero.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
import base64
import math

from scripts.arena_v0_contract import digest, canonical
from scripts.arena_atms import events_from_ledger, project
from scripts.arena_memory import load_events_from_ledger, retrieve
from scripts.ledger import Ledger

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "migrations/0001_ledger.sql"
SCHEMA = "igc-ct02-scoped-owned-feedback/1.0"
M_POLICY = "M-E1-OWN-FEEDBACK-SET/1.0"
ARMS = ("D", "B", "M")


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def _sha(value):
    return isinstance(value, str) and bool(re.fullmatch(r"sha256:[0-9a-f]{64}", value))


def _utc(value):
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    require(stamp.tzinfo is not None and stamp.utcoffset() is not None,
            "CT02_TIMEZONE_REQUIRED")
    return stamp.astimezone(timezone.utc).isoformat(timespec="microseconds")


def make_context(*, experiment, world, round_id, arm, condition, source_hash):
    for item in (experiment, world, round_id, condition):
        require(isinstance(item, str) and re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", item),
                "CT02_INVALID_SCOPE_PART")
    require(arm in ARMS and _sha(source_hash), "CT02_INVALID_ARM_OR_SOURCE")
    case = f"ct-{experiment}-{world}-{round_id}-{arm}-{condition}"
    return {"experiment": experiment, "world": world, "round": round_id,
            "arm": arm, "condition": condition, "source_hash": source_hash,
            "case_id": case}


def _parent_scope(context, parent_hash):
    """One typed subcase per own full parent hash inside the SAME world/round.

    A full 256-bit hash avoids prefix collisions. This is NOT a new world,
    condition or experimental iteration. Parents can coexist and retract
    independently without changing their historical as-known-at cuts.
    """
    require(_sha(parent_hash), "CT02_PARENT_SHA_REQUIRED")
    base = make_context(experiment=context["experiment"], world=context["world"],
                        round_id=context["round"], arm=context["arm"],
                        condition=context["condition"], source_hash=context["source_hash"])
    require(context.get("case_id") in (base["case_id"],
            base["case_id"] + "-parent-" + parent_hash[7:]),
            "CT02_CROSS_PARENT_CONTEXT")
    return {**base, "base_case_id": base["case_id"],
            "candidate_parent_hash": parent_hash,
            "case_id": base["case_id"] + "-parent-" + parent_hash[7:]}


def _ids(context):
    case = context["case_id"]
    return {role: case + ":" + role.upper()
            for role in ("source", "diagnostic", "rule", "feedback", "decision", "decision_rule")}


def _ledger(db):
    return Ledger(db, MIGRATION)


def record_feedback(db, context, *, parent_hash, diagnostic, recorded_at):
    """Record exact source + own-parent + observed diagnostic. Never invent G2."""
    context = _parent_scope(context, parent_hash)
    require(_sha(parent_hash) and isinstance(diagnostic, dict),
            "CT02_PARENT_OR_DIAGNOSTIC_REQUIRED")
    require(diagnostic.get("arm") == context["arm"] and
            diagnostic.get("condition") == context["condition"] and
            diagnostic.get("source_hash") == context["source_hash"] and
            diagnostic.get("parent_hash") == parent_hash,
            "CT02_OWN_DIAGNOSTIC_BINDING_FAILED")
    require(diagnostic.get("evidence") in ("G1", "G2", "G3"),
            "CT02_UNSUPPORTED_DIAGNOSTIC_GATE")
    require(diagnostic.get("no_future_truth") is True and
            diagnostic.get("own_evidence_only") is True,
            "CT02_FUTURE_OR_RIVAL_EVIDENCE_NOT_ALLOWED")
    obs = diagnostic.get("observations", [])
    require(isinstance(obs, list) and all(type(p) is dict and
            type(p.get("time")) in (int, float) and math.isfinite(p["time"]) and
            0 <= p["time"] <= 4 and
            type(p.get("residual")) in (int, float) and math.isfinite(p["residual"])
            for p in obs),
            "CT02_DIAGNOSTIC_OUTSIDE_CONSTRUCTION")
    require(diagnostic.get("evidence") == "G1" or _sha(diagnostic.get("trace_sha256")),
            "CT02_G2_G3_REQUIRES_TRACE_HASH")
    stamp = _utc(recorded_at)
    ids = _ids(context)
    l = _ledger(db)
    source = {"kind": "assumption", "active": True, "scope": context,
              "source_hash": context["source_hash"], "parent_hash": parent_hash,
              "assumption_type": "OWN_INPUT_AND_PARENT_AUTHENTICATED_NOT_CAUSAL_TRUTH"}
    own = {"kind": "assumption", "active": True, "scope": context,
           "source_hash": context["source_hash"], "parent_hash": parent_hash,
           "diagnostic_hash": digest(diagnostic), "diagnostic": diagnostic,
           "assumption_type": "OWN_FEEDBACK_WITH_VERIFIED_PROVENANCE_NOT_CAUSAL_TRUTH"}
    rule = {"kind": "justification", "active": True, "scope": context,
            "antecedents": [ids["source"], ids["diagnostic"]],
            "consequent": ids["feedback"], "source_id": ids["diagnostic"],
            "interpretation": "SUPPORTED_PROVENANCE_NOT_EMPIRICAL_CORRECTNESS"}
    knowledge = {"kind": "knowledge", "active": True, "scope": context,
                 "node_id": ids["feedback"], "source_id": ids["diagnostic"],
                 "title": "Own feedback diagnostic " + context["arm"],
                 "text": "Own feedback diagnostic scoped construction result",
                 "item_type": "OWN_FEEDBACK", "epistemic_status": "CONSTRUCTION_ONLY",
                 "source_revision": 1,
                 "diagnostic_hash": digest(diagnostic), "parent_hash": parent_hash}
    for role, typ, payload in (
        ("source", "ATMSNode", source), ("diagnostic", "ATMSNode", own),
        ("rule", "ATMSNode", rule), ("feedback", "KnowledgeItem", knowledge)
    ):
        l.append_revision(entity_id=ids[role], entity_type=typ,
            case_id=context["case_id"], actor_id="ct02-own-feedback",
            idempotency_key=ids[role] + ":initial",
            payload=payload, recorded_at=stamp, created_at=stamp,
            access_policy="lane:" + context["arm"])
    return {"case_id": context["case_id"], "diagnostic_hash": digest(diagnostic),
            "stored_feedback": True, "decision_executed": False, "provider_calls": 0,
            "new_omc": 0}


def recover_feedback(db, context, *, parent_hash, as_known_at):
    """Retrieve supported own feedback from ledger before policy invocation."""
    context = _parent_scope(context, parent_hash)
    require(_sha(parent_hash), "CT02_PARENT_SHA_REQUIRED")
    at = _utc(as_known_at)
    ids = _ids(context)
    l = _ledger(db)
    revs = l.snapshot(case_id=context["case_id"], as_known_at=at)
    expected = {ids[k] for k in ("source", "diagnostic", "rule", "feedback")}
    require(expected.issubset({x.entity_id for x in revs}),
            "CT02_NO_CURRENT_FEEDBACK")
    require(all(x.case_id == context["case_id"] and
                x.access_policy == "lane:" + context["arm"] and
                l.verify_integrity(entity_id=x.entity_id, revision=x.revision)
                for x in revs), "CT02_SCOPE_OR_INTEGRITY_VIOLATION")
    d = next(x.payload for x in revs if x.entity_id == ids["diagnostic"])
    require(d.get("active") is True and d.get("scope") == context and
            d.get("parent_hash") == parent_hash and
            d.get("source_hash") == context["source_hash"] and
            digest(d.get("diagnostic")) == d.get("diagnostic_hash"),
            "CT02_WITHDRAWN_OR_MISMATCHED_FEEDBACK")
    knowledge, atms = load_events_from_ledger(Path(db), context["case_id"], at)
    result = retrieve(investigation_id=context["case_id"], lane=context["arm"],
                      as_known_at=at, query="own feedback diagnostic",
                      top_k=5, knowledge_records=knowledge, atms_events=atms)
    allowed = [x for x in result["items"]
               if x["node_id"] == ids["feedback"] and x["logical_support"]["supported"]]
    require(len(allowed) == 1, "CT02_FEEDBACK_NOT_CURRENTLY_SUPPORTED")
    return {"context": context, "parent_hash": parent_hash,
            "diagnostic": d["diagnostic"], "diagnostic_hash": d["diagnostic_hash"],
            "retrieval": {"item_id": allowed[0]["id"],
                          "projection_hash": result["atms"]["projection_hash"],
                          "as_known_at": at},
            "source": "LEDGER_ATMS_RETRIEVAL_BEFORE_POLICY"}


def retract_feedback(db, context, *, parent_hash, at):
    """Append-only retraction requires the exact parent (never infer it)."""
    context = _parent_scope(context, parent_hash)
    ids = _ids(context)
    timestamp = _utc(at)
    ledger = _ledger(db)
    current = ledger.snapshot(case_id=context["case_id"], as_known_at=timestamp)
    old = next((x for x in current if x.entity_id == ids["diagnostic"] and
                x.payload.get("active") is True), None)
    require(old is not None, "CT02_NO_ACTIVE_OWN_FEEDBACK_TO_RETRACT")
    require(old.payload.get("scope") == context, "CT02_RETRACT_SCOPE_MISMATCH")
    ledger.append_revision(entity_id=ids["diagnostic"], entity_type="ATMSNode",
        case_id=context["case_id"], actor_id="ct02-feedback-retraction",
        idempotency_key=ids["diagnostic"] + ":withdraw:" + timestamp,
        recorded_at=timestamp, created_at=timestamp,
        access_policy="lane:" + context["arm"],
        payload={"kind": "assumption", "active": False, "scope": context,
                 "reason": "SOURCE_OR_DIAGNOSTIC_WITHDRAWN",
                 "superseded_diagnostic_hash": old.payload["diagnostic_hash"]})
    return {"status": "FEEDBACK_RETRACTED_APPEND_ONLY", "case_id": context["case_id"]}


def own_m_decision(db, context, *, parent_graph, as_known_at, classes=None):
    """M2's original own_policy over new authenticated parent; never use M2.revise replay."""
    require(context["arm"] == "M" and isinstance(parent_graph, dict),
            "CT02_NOT_M_OR_NO_PARENT_GRAPH")
    parent_hash = digest(parent_graph)
    memory = recover_feedback(db, context, parent_hash=parent_hash,
                              as_known_at=as_known_at)
    from scripts.arena_m2_feedback import own_policy
    if classes is None:
        from experiments.e1 import composer
        cfg, classes, _ = composer.load_registry(ROOT / "experiments/e1/registry.base.json")
        composer.check_graph(parent_graph, cfg, classes)
    verified = {"observations": memory["diagnostic"].get("observations", [])}
    choice, reason = own_policy(verified, parent_graph, classes)
    if choice is None:
        disposition = ("RATIFIED" if reason ==
                       "NO_CONSISTENT_LATE_OVERSHOOT_OVER_THRESHOLD" else "ABSTAINED")
        return {"status": disposition, "reason": reason, "policy": M_POLICY,
                "parent_hash": parent_hash, "feedback_hash": memory["diagnostic_hash"],
                "retrieved_before_policy": memory["retrieval"], "new_model": None,
                "provider_calls": 0, "new_omc": 0}
    graph, edits = choice
    require(digest(graph) != parent_hash and len(edits) == 2,
            "CT02_M_POLICY_INVALID_EDIT")
    return {"status": "REVISED", "policy": M_POLICY, "parent_hash": parent_hash,
            "new_graph_hash": digest(graph), "new_model": graph,
            "parameter_edits": edits, "feedback_hash": memory["diagnostic_hash"],
            "retrieved_before_policy": memory["retrieval"],
            "provider_calls": 0, "new_omc": 0}


def d_fixed_decision(db, context, *, parent_hash, as_known_at):
    require(context["arm"] == "D", "CT02_NOT_D")
    memory = recover_feedback(db, context, parent_hash=parent_hash,
                              as_known_at=as_known_at)
    return {"status": "RATIFIED", "policy": "D-CT03-EXPLICIT-FIXED-SET/1.0",
            "d2": "NOT_APPLICABLE_MISSING_RESET_TRIAL", "parent_hash": parent_hash,
            "feedback_hash": memory["diagnostic_hash"],
            "retrieved_before_policy": memory["retrieval"],
            "model_revision": False, "provider_calls": 0, "new_omc": 0}


def b_review_envelope(db, context, *, original_native, authenticated_receipt=None,
                      as_known_at):
    """Prepare currentModel only when the original Buffalo result has a bound receipt.

    This adapter does not authenticate provider bytes by itself. A separate
    source verifier must assert the receipt and original raw model match before
    moving READY_NOT_SENT into a real live runner. Missing evidence fails closed.
    """
    require(context["arm"] == "B", "CT02_NOT_B")
    if not isinstance(original_native, dict) or not original_native:
        return {"status": "NOT_EXECUTED_NO_AUTHENTIC_PARENT", "provider_calls": 0}
    model = original_native.get("model")
    receipt = authenticated_receipt
    if (not isinstance(model, dict) or not isinstance(model.get("variables"), list)
            or not isinstance(model.get("relationships"), list)
            or not isinstance(receipt, dict)
            or receipt.get("model_returned") is not True
            or receipt.get("round_kind") != "initial"
            or receipt.get("world_public_id") != context["world"]
            or receipt.get("condition_id") != context["condition"]
            or receipt.get("source_snapshot_hash") != context["source_hash"]
            or receipt.get("provider_calls") != 1
            or receipt.get("mode") != "live"
            or receipt.get("upstream_sha") != "5199f7b45f3a7ae4a773cb0dd8542940aabe9edc"
            or receipt.get("transport") != "CLOUDFLARE_WORKERS_AI_DIRECT_REST_JSON_SCHEMA"
            or receipt.get("proxy_requests") != 1
            or receipt.get("horizon_matches_case") is not True
            or receipt.get("output_horizon_hours") != 8
            or receipt.get("upstream_source_modified") is not False
            or not isinstance(receipt.get("result_sha256"), str)):
        return {"status": "NOT_EXECUTED_UNAUTHENTICATED_B_NATIVE_OR_RECEIPT",
                "provider_calls": 0}
    from scripts.arena_cafe.e02_b_feedback import _model_sha
    parent_hash = _model_sha(original_native)
    if receipt.get("result_sha256") != parent_hash or\
       receipt.get("case_id") != "CT-03" or\
       receipt.get("status") != "ORIGINAL_ENGINE_LIVE_OUTPUT_RETURNED":
        return {"status": "NOT_EXECUTED_UNAUTHENTICATED_B_NATIVE_OR_RECEIPT",
                "provider_calls": 0}
    memory = recover_feedback(db, context, parent_hash=parent_hash,
                              as_known_at=as_known_at)
    return {"status": "READY_NOT_SENT_RECEIPT_REQUIRES_EXTERNAL_BYTE_VERIFICATION",
            "method": "UB-IAD/sd-ai::Engine.generate",
            "route": "OPEN_ROUTER_SDK_CLOUDFLARE_PROTOCOL_REUSE",
            "currentModel": model,
            "own_feedback": memory["diagnostic"],
            "revision_feedback_packet": {
                "schema": "igc-ct03-b-own-feedback/1.0",
                "arm": "B", "world_public_id": context["world"],
                "condition_id": context["condition"],
                "source_snapshot_hash": context["source_hash"],
                "parent_result_sha256": parent_hash,
                "own_diagnostic_sha256": memory["diagnostic_hash"],
                # Canonical Python bytes and hash travel together. JS checks
                # these exact bytes, their hash, and the transmitted object.
                "own_diagnostic_canonical_base64": base64.b64encode(
                    canonical(memory["diagnostic"])).decode("ascii"),
                "retrieved_before_policy": memory["retrieval"],
                "own_diagnostic": memory["diagnostic"],
            },
            "parent_hash": parent_hash,
            "provider_receipt_result_sha256": receipt["result_sha256"],
            "retrieved_before_policy": memory["retrieval"],
            "provider_calls": 0, "new_omc": 0,
            "warning": "NO_LIVE_UNTIL_ORIGINAL_RECEIPT_BYTES_AND_NEW_CASE_ADAPTER_VERIFIED"}


def persist_disposition(db, context, *, decision, recorded_at):
    """Persist a D/M disposition with a support dependency on recovered feedback.

    A B staging envelope is never accepted as a Buffalo revision. Scientific
    fitness is not conferred by ATMS; revised M models still require new G2/G5.
    """
    require(context["arm"] in ("D", "M") and isinstance(decision, dict),
            "CT02_NOT_AN_EXECUTED_D_M_DISPOSITION")
    require(decision.get("status") in ("REVISED", "RATIFIED", "ABSTAINED") and
            isinstance(decision.get("retrieved_before_policy"), dict),
            "CT02_NOT_AN_OWN_POLICY_DISPOSITION")
    stamp = _utc(recorded_at)
    parent_hash = decision.get("parent_hash")
    context = _parent_scope(context, parent_hash)
    own = recover_feedback(db, context, parent_hash=parent_hash, as_known_at=stamp)
    require(decision["retrieved_before_policy"] == own["retrieval"] or (
        decision["retrieved_before_policy"]["item_id"] == own["retrieval"]["item_id"] and
        decision["retrieved_before_policy"]["projection_hash"] == own["retrieval"]["projection_hash"] and
        decision["retrieved_before_policy"]["as_known_at"] <= stamp),
        "CT02_DECISION_NOT_FROM_RETRIEVED_OWN_FEEDBACK")
    require(decision.get("feedback_hash") == own["diagnostic_hash"] and
            decision.get("provider_calls") == 0 and
            decision.get("new_omc") == 0,
            "CT02_DECISION_FEEDBACK_OR_COST_MISMATCH")
    ids = _ids(context)
    status = decision["status"]
    prepared = {"schema": SCHEMA, "status": status,
                "policy": decision.get("policy"), "parent_hash": parent_hash,
                "feedback_hash": own["diagnostic_hash"],
                "new_graph_hash": decision.get("new_graph_hash") if status == "REVISED" else None,
                "parameter_edits": decision.get("parameter_edits", []),
                "consequences_not_resimulated": True,
                "scientific_status": "METHOD_DISPOSITION_ONLY_NOT_HELDOUT_EVALUATION"}
    rule = {"kind": "justification", "active": True, "scope": context,
            "antecedents": [ids["feedback"]], "consequent": ids["decision"],
            "source_id": ids["feedback"],
            "interpretation": "DECISION_TRACED_TO_OWN_FEEDBACK_NOT_CAUSAL_VERIFICATION"}
    knowledge = {"kind": "knowledge", "active": True, "scope": context,
                 "node_id": ids["decision"], "source_id": ids["feedback"],
                 "title": "Own decision following feedback",
                 "text": "Own policy disposition after retrieval of supported feedback",
                 "item_type": "OWN_POLICY_DISPOSITION",
                 "epistemic_status": "NOT_PREDICTIVELY_VALIDATED", "source_revision": 1,
                 "prepared_disposition": prepared}
    ledger = _ledger(db)
    for role, typ, payload in (("decision_rule", "ATMSNode", rule),
                               ("decision", "KnowledgeItem", knowledge)):
        ledger.append_revision(entity_id=ids[role], entity_type=typ,
            case_id=context["case_id"], actor_id="ct02-own-policy-disposition",
            idempotency_key=ids[role] + ":initial",
            payload=payload, recorded_at=stamp, created_at=stamp,
            access_policy="lane:" + context["arm"])
    revs = ledger.snapshot(case_id=context["case_id"], as_known_at=stamp)
    engine, _ = project(events_from_ledger(revs), as_known_at=stamp,
                        lane=context["arm"], investigation_id=context["case_id"])
    require(engine.explain(ids["decision"])["supported"],
            "CT02_PERSISTED_DECISION_UNSUPPORTED")
    return {"status": "DISPOSITION_RECORDED_WITH_OWN_FEEDBACK_SUPPORT",
            "case_id": context["case_id"], "method_status": status,
            "scientific_status": prepared["scientific_status"],
            "model_change_count": int(status == "REVISED"),
            "provider_calls": 0, "new_omc": 0}
