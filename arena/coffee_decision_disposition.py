"""Post-comparison ATMS: outcomes change the admissible S5 conclusions.

No model refitting, no causal inference or ROI. Compare ALL six preregistered
CONSTRUCTION cells, then derive statements from the complete grid. A favorable
single cell is not admissible evidence for a general recommendation.
"""
from __future__ import annotations

from datetime import timedelta

from .common import ArenaError, digest
from . import decision_atms as atms
from . import decision_atms_gate as execution_gate

SCHEMA = "arena.coffee.atms-disposition/1"
LOADS = ("LOWER_PAID_INPUT_Q25", "HIGHER_PAID_INPUT_Q75")
FREE = (0, 50, 100)
BROAD = "S5_BROAD_SYNTHETIC_SERVICE_IMPROVEMENT"
P90_SOME = "S5_P90_IMPROVES_SOME_TESTED_CONTEXTS"
NO_PEAK_GAIN = "S5_NO_PEAK_GAIN_ANY_TESTED_CONTEXT"
HARM = "S5_HARMS_SOME_TESTED_CONTEXT"
NEXT = "INVESTIGATE_PREPARATION_AND_MACHINE_CAPACITY"


def need(test, code):
    if not test:
        raise ArenaError("COFFEE_ATMS_DISPOSITION_" + code)


def validate_rows(rows):
    need(type(rows) is list and len(rows) == 6, "SIX_CONTEXTS_REQUIRED")
    observed = set()
    for r in rows:
        need(type(r) is dict and r.get("load_label") in LOADS and
             type(r.get("support_available_pct_assumed")) is int and
             r["support_available_pct_assumed"] in FREE,
             "INVALID_CONTEXT_LABEL")
        context = (r["load_label"],r["support_available_pct_assumed"])
        need(context not in observed,"DUPLICATE_CONTEXT")
        observed.add(context)
        fields = ("synthetic_paid_orders","B0_handoffs_in_peak",
                  "S5_handoffs_in_peak","B0_pending_at_peak_cut",
                  "S5_pending_at_peak_cut",
                  "delta_S5_minus_B0_handoffs_in_peak")
        need(all(type(r.get(x)) is int for x in fields),
             "INVALID_PEAK_COUNTER")
        paid = r["synthetic_paid_orders"]
        b0 = r["B0_handoffs_in_peak"]
        s5 = r["S5_handoffs_in_peak"]
        need(paid >= 0 and 0 <= b0 <= paid and 0 <= s5 <= paid
             and b0 + r["B0_pending_at_peak_cut"] == paid
             and s5 + r["S5_pending_at_peak_cut"] == paid
             and s5-b0 == r["delta_S5_minus_B0_handoffs_in_peak"],
             "BROKEN_MASS_OR_DELTA")
        a = r.get("B0_p90_full_drain_min")
        b = r.get("S5_p90_full_drain_min")
        d = r.get("delta_S5_minus_B0_p90_min")
        need(all(type(x) in (float,int) for x in (a,b,d)) and
             all(0 <= x < 1000000 for x in (a,b)) and
             abs((b-a)-d) < 1e-6,
             "BROKEN_P90_DELTA")
    need(observed == {(a,b) for a in LOADS for b in FREE},
         "NOT_COMPLETE_PREREGISTERED_GRID")
    return rows


def disposition(pre, execution_receipt, rows):
    """Deterministically create two later knowledge cuts, never edit history."""
    execution_gate.require_executable(execution_receipt)
    need(execution_receipt["predecision_snapshot_sha256"] ==
         pre["snapshot"]["snapshot_sha256"] and
         execution_receipt["dossier_sha256"] == pre["dossier_sha256"] and
         execution_receipt["protocol_sha256"] == pre["protocol_sha256"],
         "WRONG_PREDECISION_OR_PROTOCOL_PARENT")
    need(execution_receipt["revision_events"] == [] and
         execution_receipt["atms_snapshot"]["snapshot_sha256"] ==
         pre["snapshot"]["snapshot_sha256"],
         "UNSUPPORTED_POSTHOC_REVISION")
    validate_rows(rows)
    journal=atms.Journal(pre["journal"])
    cut=pre["snapshot"]["as_known_at"]
    need(journal.snapshot(as_known_at=cut,valid_at=cut)==pre["snapshot"],
         "PREDECISION_NOT_REPLAYABLE")
    source=digest({"six_full_context_rows":sorted(
        rows,key=lambda r:(r["load_label"],r["support_available_pct_assumed"])),
        "gate_sha256":execution_receipt["gate_sha256"]})
    now=atms.stamp(cut)
    def tick(i):
        return (now+timedelta(microseconds=i)).isoformat(
            timespec="microseconds").replace("+00:00","Z")
    facts = [("A_SIX_CONTEXTS","S5_COMPLETE_PREREGISTERED_GRID")]
    if all(r["delta_S5_minus_B0_handoffs_in_peak"] >= 0 for r in rows):
        facts.append(("A_NO_PEAK_LOSS","S5_NO_PEAK_LOSS_ALL_TESTED"))
    if all(r["delta_S5_minus_B0_p90_min"] <= 0 for r in rows):
        facts.append(("A_NO_P90_LOSS","S5_NO_P90_LOSS_ALL_TESTED"))
    if any(r["delta_S5_minus_B0_handoffs_in_peak"] > 0 or
           r["delta_S5_minus_B0_p90_min"] < 0 for r in rows):
        facts.append(("A_SOME_SERVICE_GAIN","S5_SOME_TESTED_SERVICE_GAIN"))
    if any(r["delta_S5_minus_B0_p90_min"] < 0 for r in rows):
        facts.append(("A_P90_BETTER","S5_SOME_TESTED_P90_GAIN"))
    if all(r["delta_S5_minus_B0_handoffs_in_peak"] <= 0 for r in rows):
        facts.append(("A_NO_PEAK_GAIN","S5_NO_TESTED_PEAK_GAIN"))
    if any(r["delta_S5_minus_B0_handoffs_in_peak"] < 0 or
           r["delta_S5_minus_B0_p90_min"] > 0 for r in rows):
        facts.append(("A_SOME_HARM","S5_SOME_TESTED_SERVICE_HARM"))
    for i,(eid,node) in enumerate(facts,1):
        journal.append(atms.event(
            "assumption",eid,tick(i),source,node=node,status="SIMULATED"))
    evidence_end=tick(len(facts))
    rules = [
        ("J_BROAD",BROAD,[
            "S5_CONDITIONAL_SIMULATABLE","S5_COMPLETE_PREREGISTERED_GRID",
            "S5_NO_PEAK_LOSS_ALL_TESTED","S5_NO_P90_LOSS_ALL_TESTED",
            "S5_SOME_TESTED_SERVICE_GAIN"]),
        ("J_P90_SOME",P90_SOME,[
            "S5_CONDITIONAL_SIMULATABLE","S5_COMPLETE_PREREGISTERED_GRID",
            "S5_SOME_TESTED_P90_GAIN"]),
        ("J_NO_PEAK_GAIN",NO_PEAK_GAIN,[
            "S5_CONDITIONAL_SIMULATABLE","S5_COMPLETE_PREREGISTERED_GRID",
            "S5_NO_TESTED_PEAK_GAIN"]),
        ("J_CONTEXT_HARM",HARM,[
            "S5_CONDITIONAL_SIMULATABLE","S5_COMPLETE_PREREGISTERED_GRID",
            "S5_SOME_TESTED_SERVICE_HARM"]),
        ("J_NEXT",NEXT,[
            "S5_COMPLETE_PREREGISTERED_GRID","S5_NO_TESTED_PEAK_GAIN"]),
    ]
    for i,(eid,conclusion,premises) in enumerate(rules,len(facts)+1):
        journal.append(atms.event(
            "justification",eid,tick(i),source,
            conclusion=conclusion,premises=premises))
    end=tick(len(facts)+len(rules))
    before=pre["snapshot"]
    evidence=journal.snapshot(as_known_at=evidence_end,valid_at=evidence_end)
    after=journal.snapshot(as_known_at=end,valid_at=end)
    need(journal.snapshot(as_known_at=cut,valid_at=cut)==before and
         not after["labels"].get("S5_REAL_ECONOMIC_BENEFIT"),
         "PREDECISION_OR_REAL_BENEFIT_CHANGED")
    supported=lambda name:bool(after["labels"].get(name))
    claims={
        name:{
            "supported":supported(name),
            "support_environments":after["labels"].get(name,[]),
            "missing_premises_by_rule":journal.explain(
                name,as_known_at=end,valid_at=end)[
                    "missing_nodes_by_justification"],
        }
        for name in (BROAD,P90_SOME,NO_PEAK_GAIN,HARM,NEXT)
    }
    business = (
        "CONDITIONAL_SERVICE_IMPROVEMENT_WORTH_MEASURING"
        if supported(BROAD) else
        "MEASURE_FIRST_NOT_REAL_REASSIGNMENT_RECOMMENDATION")
    # These are *scoped* simulated claims. Absence of support is not a
    # measured physical impossibility outside the six test contexts.
    result={
        "schema":SCHEMA,
        "status":"CONTEXT_COMPLETE_S5_POSTCOMPARISON_DISPOSITION",
        "predecision_snapshot_sha256":before["snapshot_sha256"],
        "execution_gate_sha256":execution_receipt["gate_sha256"],
        "results_source_sha256":source,
        "cuts":{"predecision_T":cut,
                "evidence_T_plus_microseconds":evidence_end,
                "disposition_T_plus_microseconds":end},
        "snapshots":{
            "predecision":before["snapshot_sha256"],
            "evidence":evidence["snapshot_sha256"],
            "disposition":after["snapshot_sha256"],
        },
        "postdecision_events":journal.events[len(pre["journal"]):],
        "claims":claims,
        "business_choice":business,
        "not_a_real_business_recommendation":True,
        "no_measured_incomes_or_profit":True,
        "condition_scope":"EXACTLY_TWO_CONSTRUCTION_LOADS_TIMES_THREE_SUPPORT_AVAILABILITIES",
        "would_not_be_admissible_without_all_six_contexts":True,
        "prevented_claim_example":{
            "unsafe_claim":"S5_IMPROVES_SERVICE_IN_GENERAL",
            "unsafe_method":"SELECT_BEST_P90_CELL_AND_GENERALIZE_TO_ALL",
            "tempting_positive_case_exists":supported(P90_SOME),
            "admissible_as_general":supported(BROAD),
            "classification":(
                "REJECTED_CHERRY_PICK_GENERALIZATION"
                if supported(P90_SOME) and not supported(BROAD)
                else "NO_CHERRY_PICK_CONFLICT_DEMONSTRATED"),
            "what_unsafe_rule_would_say":(
                "APPROVE_GENERAL_S5" if supported(P90_SOME)
                else "NO_GENERAL_S5_FROM_BEST_CELL"),
            "counterfactual_is_a_DEFINED_BAD_HEURISTIC_NOT_A_REAL_SYSTEM_RUN":True,
        },
    }
    need(result["claims"][BROAD]["supported"] ==
         (all(r["delta_S5_minus_B0_handoffs_in_peak"] >= 0 and
              r["delta_S5_minus_B0_p90_min"] <= 0 for r in rows) and
          any(r["delta_S5_minus_B0_handoffs_in_peak"] > 0 or
              r["delta_S5_minus_B0_p90_min"] < 0 for r in rows)),
         "BROAD_CLAIM_NOT_SUPPORTED_BY_COMPLETE_GRID")
    result["disposition_sha256"]=digest(result)
    return result
