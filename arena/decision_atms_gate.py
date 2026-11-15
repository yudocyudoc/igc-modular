"""ATMS → Arena execution gate, not merely an annotation on a P11 report.

The baseline decision is conditional and synthetic. Loss of an essential
logical support MUST prevent invoking P11. Hypothetical revision branches
are only for isolated fixtures / future trusted-ledger adaptation: the CLI
does not ingest untrusted amendment files and this module is not a substitute
for the canonical IGC ledger authorization boundary.
"""
from __future__ import annotations

from .common import ArenaError, digest
from . import decision_atms as atms

SCHEMA = "arena.coffee-atms.execution-gate/1"
POLICY = "S5_CONDITIONAL_SIMULATABLE"
EXECUTE = "ADMIT_CONDITIONAL_P11_NOT_BUSINESS_RECOMMENDATION"
ABSTAIN = "ABSTAIN_MEASURE_FIRST_NO_P11_SIMULATION"
MAX_REVISIONS = 12

# Existing assumptions and one justification belong to the sealed P11
# premises; unknown revisions or new supporting claims cannot be injected.
REVISION_TARGETS = frozenset({
    "A_CONSTRUCTION", "A_PAIRED", "A_HANDOFF", "A_SUPPORT", "J_S5_SIM"})
NOGOOD_TARGETS = frozenset({
    "A_CONSTRUCTION", "A_PAIRED", "A_HANDOFF", "A_SUPPORT"})


def need(value, error):
    if not value:
        raise ArenaError("COFFEE_ATMS_GATE_" + error)


def trusted_predecision(pre, dossier, protocol):
    """Reject a fabricated/modified initial journal even with self-consistent hashes."""
    need(type(pre) is dict and pre.get("schema") ==
         "arena.coffee-atms.predecision/1" and
         type(pre.get("journal")) is list and bool(pre["journal"]),
         "PREDECISION_MISSING")
    original_cut = pre["journal"][0].get("recorded_at")
    expected = atms.scenario_predecision(
        dossier, protocol, recorded_at=original_cut)
    need(pre == expected, "PREDECISION_NOT_DERIVED_FROM_DECLARED_INPUTS")
    return expected


def gate(pre, dossier, protocol, *, revision_events=()):
    """Compute an operational admission decision from actual ATMS labels.

    revision_events only accepts retractions/restorations/conflicts affecting
    the original premisses. It cannot create an unobserved fact, add rules,
    grant authorization, read truth, or silently turn simulated support into
    measured evidence. The production CLI does NOT accept injected revisions.
    """
    trusted_predecision(pre, dossier, protocol)
    need(type(revision_events) in (list, tuple) and
         len(revision_events) <= MAX_REVISIONS,
         "REVISION_COUNT_OR_TYPE")
    journal = atms.Journal(pre["journal"])
    for revision in revision_events:
        need(type(revision) is dict, "REVISION_RECORD_REQUIRED")
        operation = revision.get("op")
        need(operation in {"retract", "restore", "nogood"},
             "NO_ARBITRARY_NEW_PREMISES_OR_JUSTIFICATIONS")
        if operation in ("retract", "restore"):
            need(revision.get("target") in REVISION_TARGETS,
                 "REVISION_OUTSIDE_P11_PREMISES")
        else:
            values = revision.get("assumptions")
            need(type(values) is list and
                 1 <= len(values) <= len(NOGOOD_TARGETS) and
                 set(values).issubset(NOGOOD_TARGETS),
                 "NOGOOD_OUTSIDE_P11_PREMISES")
        need(atms.stamp(revision["recorded_at"]) >
             atms.stamp(pre["snapshot"]["as_known_at"]),
             "REVISION_BEFORE_SEALED_PREDECISION")
        need(revision["valid_from"] == revision["recorded_at"],
             "NO_RETROACTIVE_AUTHORING_IN_THIS_GATE")
        journal.append(revision)
    cut = (revision_events[-1]["recorded_at"] if revision_events
           else pre["snapshot"]["as_known_at"])
    candidate = journal.snapshot(as_known_at=cut, valid_at=cut)
    support = candidate["labels"].get(POLICY, [])
    missing_real = (not candidate["labels"].get("S5_REAL_FEASIBLE")
                    and not candidate["labels"].get("S5_REAL_ECONOMIC_BENEFIT"))
    need(missing_real, "SIMULATION_CANNOT_PROVE_REAL_FEASIBILITY")
    need(journal.snapshot(
        as_known_at=pre["snapshot"]["as_known_at"],
        valid_at=pre["snapshot"]["valid_at"]) == pre["snapshot"],
        "HISTORICAL_PREDECISION_CHANGED")
    from_pre = pre["snapshot"]["labels"]
    to_next = candidate["labels"]
    changed = {
        node: {"before": from_pre.get(node, []), "after": to_next.get(node, [])}
        for node in sorted(set(from_pre) | set(to_next))
        if from_pre.get(node, []) != to_next.get(node, [])
    }
    result = {
        "schema": SCHEMA,
        "status": EXECUTE if support else ABSTAIN,
        "action": "RUN_P11_CONDITIONAL_REFERENCE" if support
                  else "DO_NOT_RUN_P11_MEASURE_OR_REVISIT_PREMISES",
        "predecision_snapshot_sha256": pre["snapshot"]["snapshot_sha256"],
        "dossier_sha256": pre["dossier_sha256"],
        "protocol_sha256": pre["protocol_sha256"],
        "atms_snapshot": candidate,
        "revision_events": list(revision_events),
        "revision_interpretation": (
            "HYPOTHETICAL_OR_LEDGER_ADAPTER_NOT_YET_WIRED"
            if revision_events else "SEALED_DECLARED_CONSTRUCTION_PREMISES"),
        "changed_support": changed,
        "policy_support_environments": support,
        "blocked_support_explanation": journal.explain(
            POLICY, as_known_at=cut, valid_at=cut),
        "requested_measurement_if_blocked": (
            "VERIFY_DECLARED_RESOURCES_AND_SUPPORT_AVAILABILITY"
            if not support else None),
        "allowed_simulations": 52 if support else 0,
        "refuses_empirical_claims_or_paid_runs": True,
        "requires_private_truth": False,
        "no_provider_post_r2_omc_new_worlds": True,
    }
    result["gate_sha256"] = digest(result)
    return result


def require_executable(receipt):
    """Used in the Arena producer path BEFORE any reference/P11 call."""
    need(type(receipt) is dict and
         receipt.get("schema") == SCHEMA,
         "MISSING_GATE_RECEIPT")
    proof = {k: v for k, v in receipt.items() if k != "gate_sha256"}
    need(receipt.get("gate_sha256") == digest(proof),
         "GATE_RECEIPT_MUTATED")
    need(receipt.get("status") == EXECUTE and
         receipt.get("action") == "RUN_P11_CONDITIONAL_REFERENCE" and
         bool(receipt.get("policy_support_environments")) and
         receipt.get("allowed_simulations") == 52,
         "ABSTAIN_MEASURE_FIRST_NO_SIMULATOR")
    need(receipt.get("atms_snapshot", {}).get("labels", {}).get(POLICY) ==
         receipt["policy_support_environments"], "SUPPORT_LABEL_MISMATCH")
    return receipt["atms_snapshot"]["snapshot_sha256"]
