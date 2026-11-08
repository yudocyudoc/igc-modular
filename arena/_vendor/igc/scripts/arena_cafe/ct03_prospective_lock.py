"""CT-02/CT-03 prospective prediction lock. No solver, provider or world selection.

The producer-side seal only receives public construction and own trajectories
for t6/t8; it never loads reserved evaluator truth. Matching receipt hashes
are NOT independent proof of execution. The evaluator must verify execution
separately before releasing the withheld outcomes.
"""
from __future__ import annotations
import argparse
import json
import math
from pathlib import Path
import re

from scripts.arena_v0_contract import canonical, digest
from scripts.arena_cafe.ct03_public import PUBLIC_INPUT, validate_construction
from scripts.arena_cafe.ct_feedback_bridge import require
from scripts.arena_cafe.ct03_d_prepare import SCHEMA as D_SCHEMA
from scripts.arena_cafe.ct03_m_prepare import SCHEMA as M_SCHEMA
from scripts.arena_cafe.ct03_world_custody import PUBLIC_SCHEMA as WORLD_SCHEMA

SCHEMA = "igc-ct03-prospective-prediction-lock/1.0"
INPUT_SCHEMA = "igc-ct03-prospective-entries/1.0"
STATES = frozenset(("PREDICTED", "G0_REJECTED", "G1_BLOCKED", "G2_FAILED", "NO_NATIVE", "NOT_EXECUTED"))
DECISIONS = {"D": ("RATIFIED", "NOT_EXECUTED"),
             "M": ("REVISED", "RATIFIED", "ABSTAINED", "NOT_EXECUTED"),
             "B": ("REVISED", "RATIFIED", "ABSTAINED", "NOT_EXECUTED")}
SHA = re.compile(r"sha256:[0-9a-f]{64}\Z")
PROTOCOL = (Path(__file__).resolve().parents[2] /
            "experiments/cafeteria/CT03_PREEXECUTION_PROTOCOL_2026-11-07.json")
M_TOPOLOGY_KEY = re.compile(r"[0-9a-f]{64}\Z")


def sha(value):
    return type(value) is str and SHA.fullmatch(value) is not None


def only(value, names, error):
    require(type(value) is dict and set(value) == set(names), error)


def registry(d_manifest, m_manifest):
    """Expected slots derived from original six D and six complete M graphs."""
    require(type(d_manifest) is dict and d_manifest.get("schema") == D_SCHEMA and
            d_manifest.get("candidate_count") == 6 and
            d_manifest.get("D2") == "NOT_APPLICABLE_MISSING_RESET_TRIAL",
            "CT03_LOCK_D_ORIGINAL_SIX_REQUIRED")
    require(type(m_manifest) is dict and m_manifest.get("schema") == M_SCHEMA and
            m_manifest.get("candidate_count") == 6 and
            m_manifest.get("material_projection_is_dynamic_equivalence") is False,
            "CT03_LOCK_M_ORIGINAL_SIX_REQUIRED")
    require(d_manifest.get("source_definition_sha256") ==
            m_manifest.get("source_definition_sha256") == digest(PUBLIC_INPUT),
            "CT03_LOCK_COMMON_EXOGENOUS_SOURCE_REQUIRED")
    d, m = d_manifest.get("candidates"), m_manifest.get("candidates")
    require(type(d) is list and len(d) == 6 and type(m) is list and len(m) == 6,
            "CT03_LOCK_CANDIDATE_MANIFEST_INCOMPLETE")
    expected = {}
    for candidate in d:
        require(type(candidate) is dict and type(candidate.get("id")) is str and
                sha(candidate.get("structure_hash")) and candidate["id"] ==
                "D-" + candidate["structure_hash"][7:19],
                "CT03_LOCK_D_PARENT_IDENTITY")
        key = ("D", candidate["id"])
        require(key not in expected, "CT03_LOCK_DUPLICATE_D")
        expected[key] = {"parent_hash": candidate["structure_hash"],
                         "group": candidate["structure_hash"]}
    for candidate in m:
        require(type(candidate) is dict and sha(candidate.get("full_ast_sha256")) and
                sha(candidate.get("material_only_projection_sha256")) and
                type(candidate.get("canonical_sha256")) is str and
                M_TOPOLOGY_KEY.fullmatch(candidate["canonical_sha256"]) is not None,
                "CT03_LOCK_M_PARENT_IDENTITY")
        key = ("M", candidate["canonical_sha256"])
        require(key not in expected, "CT03_LOCK_DUPLICATE_M")
        require(digest(candidate["original_ast"]) == candidate["full_ast_sha256"],
                "CT03_LOCK_M_FULL_AST_CHANGED")
        expected[key] = {"parent_hash": candidate["full_ast_sha256"],
                         "group": candidate["material_only_projection_sha256"]}
    require(len({v["group"] for k, v in expected.items() if k[0] == "D"}) == 6 and
            len({v["group"] for k, v in expected.items() if k[0] == "M"}) == 3,
            "CT03_LOCK_EXPECT_SIX_D_AND_THREE_M_MATERIAL_GROUPS")
    expected[("B", "B-original")] = {"parent_hash": None, "group": "B-original"}
    return expected


def validate_state(state, role):
    only(state, ("status", "native_sha256", "trace_sha256", "receipt_sha256", "forecast"),
         "CT03_LOCK_UNTYPED_" + role)
    require(state["status"] in STATES, "CT03_LOCK_UNKNOWN_" + role)
    if state["status"] == "PREDICTED":
        require(all(sha(state[k]) for k in
                    ("native_sha256", "trace_sha256", "receipt_sha256")),
                "CT03_LOCK_PREDICTION_REQUIRES_OWN_NATIVE_TRACE_RECEIPT")
        points = state["forecast"]
        require(type(points) is list and len(points) == 2,
                "CT03_LOCK_TWO_PREDICTIONS_REQUIRED")
        prev = -1e-8
        for time, point in zip((6, 8), points):
            only(point, ("time", "delivered"), "CT03_LOCK_UNKNOWN_FORECAST_FIELDS")
            value = point["delivered"]
            require(type(point["time"]) in (int, float) and point["time"] == time and
                    type(value) in (int, float) and math.isfinite(value) and
                    -1e-8 <= value <= 3.4 + 1e-8 and value >= prev - 1e-8,
                    "CT03_LOCK_INVALID_FORECAST_OR_TIME")
            prev = value
    else:
        require(state["forecast"] is None and state["trace_sha256"] is None and
                (state["native_sha256"] is None or sha(state["native_sha256"])) and
                (state["receipt_sha256"] is None or sha(state["receipt_sha256"])),
                "CT03_LOCK_MISSING_TRACE_MUST_NOT_BE_ZERO")
        if state["status"] in ("G0_REJECTED", "G1_BLOCKED", "G2_FAILED"):
            require(sha(state["receipt_sha256"]),
                    "CT03_LOCK_FAILED_RUN_REQUIRES_OWN_RECEIPT")
        if state["status"] == "G0_REJECTED":
            require(sha(state["native_sha256"]),
                    "CT03_LOCK_G0_REJECTED_REQUIRES_EXISTING_NATIVE")
        if state["status"] in ("NO_NATIVE", "NOT_EXECUTED"):
            require(state["native_sha256"] is None,
                    "CT03_LOCK_NO_NATIVE_MUST_BE_EXPLICIT")
        if state["status"] == "NOT_EXECUTED":
            require(state["receipt_sha256"] is None,
                    "CT03_LOCK_UNEXECUTED_HAS_NO_ATTEMPT_RECEIPT")


def validate_row(row, expected, world):
    only(row, ("arm", "candidate_id", "parent_hash", "material_group", "initial",
               "decision", "final"), "CT03_LOCK_UNKNOWN_ROW_FIELDS")
    arm, candidate_id = row["arm"], row["candidate_id"]
    require((arm, candidate_id) in expected, "CT03_LOCK_WRONG_ARM_OR_CANDIDATE")
    binding = expected[(arm, candidate_id)]
    require(row["material_group"] == binding["group"] and
            (row["parent_hash"] == binding["parent_hash"] if arm != "B"
             else row["parent_hash"] is None or sha(row["parent_hash"])),
            "CT03_LOCK_PARENT_OR_GROUP_NOT_ORIGINAL")
    validate_state(row["initial"], "INITIAL")
    validate_state(row["final"], "FINAL")
    decision = row["decision"]
    only(decision, ("status", "policy", "feedback_hash", "retrieved_item_id",
                    "new_model_sha256"), "CT03_LOCK_UNKNOWN_DECISION_FIELDS")
    status = decision["status"]
    require(status in DECISIONS[arm] and type(decision["policy"]) is str and
            1 <= len(decision["policy"]) <= 120,
            "CT03_LOCK_DECISION_NOT_OWN_POLICY")
    if status in ("REVISED", "RATIFIED", "ABSTAINED"):
        parent = row["parent_hash"]
        item = ("ct-CT03-" + world + "-R0-" + arm + "-C0-parent-" +
                parent[7:] + ":FEEDBACK") if sha(parent) else None
        require(sha(decision["feedback_hash"]) and
                decision["retrieved_item_id"] == item,
                "CT03_LOCK_DECISION_WITHOUT_OWN_RETRIEVAL")
    else:
        require(decision["feedback_hash"] is None and
                decision["retrieved_item_id"] is None,
                "CT03_LOCK_UNEXECUTED_DECISION_CANNOT_HAVE_FEEDBACK")
    if status == "REVISED":
        require(sha(decision["new_model_sha256"]) and
                decision["new_model_sha256"] == row["final"]["native_sha256"] and
                row["initial"]["native_sha256"] is not None and
                decision["new_model_sha256"] != row["initial"]["native_sha256"],
                "CT03_LOCK_REVISION_NOT_AN_OWN_CHANGED_NATIVE")
    else:
        require(decision["new_model_sha256"] is None and
                row["final"] == row["initial"],
                "CT03_LOCK_UNREVISED_CANDIDATE_MUST_REUSE_TRACE")
    if arm != "B":
        require(row["initial"]["status"] != "G0_REJECTED" and
                row["final"]["status"] != "G0_REJECTED",
                "CT03_LOCK_G0_HORIZON_ONLY_BUFFALO")
    if arm == "D":
        require(decision["policy"] == "D-CT03-EXPLICIT-FIXED-SET/1.0",
                "CT03_LOCK_D2_CANNOT_BE_USED")
    if arm == "M":
        require(decision["policy"] == "M-E1-OWN-FEEDBACK-SET/1.0",
                "CT03_LOCK_WRONG_M_POLICY")
    if arm == "B":
        require(decision["policy"] == "UB-IAD/sd-ai::Engine.generate" and
                (row["parent_hash"] == row["initial"]["native_sha256"] or
                 (row["parent_hash"] is None and
                  row["initial"]["native_sha256"] is None)),
                "CT03_LOCK_B_CURRENT_MODEL_PARENT_MISMATCH")
    return arm, candidate_id


def seal(construction, commitment, d_manifest, m_manifest, entries):
    """Hash all 13 slots, never importing evaluator-only private values."""
    only(commitment, ("schema", "world_public_id", "source_definition_sha256",
                      "private_commitment_sha256", "protocol_sha256", "status",
                      "evaluator_boundary", "omc_executed", "provider_calls"),
         "CT03_LOCK_CUSTODY_COMMITMENT_FIELDS")
    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    require(protocol.get("schema") == "igc-ct03-preexecution-protocol/1.0" and
            protocol["world"]["construction_times_hours"] == [0, 1, 2, 4] and
            protocol["world"]["heldout_times_hours"] == [6, 8] and
            protocol["cost"]["currently_authorized_new_provider_post"] == 0 and
            protocol["cost"]["currently_authorized_new_omc"] == 0,
            "CT03_LOCK_PREEXECUTION_PROTOCOL_DRIFT")
    require(commitment["schema"] == WORLD_SCHEMA and
            sha(commitment["private_commitment_sha256"]) and
            sha(commitment["protocol_sha256"]) and
            commitment["protocol_sha256"] == digest(protocol) and
            commitment["source_definition_sha256"] == digest(PUBLIC_INPUT),
            "CT03_LOCK_CUSTODY_COMMITMENT_INVALID")
    require(type(construction) is dict and
            construction.get("world_public_id") == commitment["world_public_id"],
            "CT03_LOCK_CROSS_WORLD_CONSTRUCTION")
    context = {"source_hash": construction.get("source_snapshot_hash"),
               "world": commitment["world_public_id"], "condition": "C0"}
    validate_construction(context, construction)
    only(entries, ("schema", "world_public_id", "source_snapshot_hash",
                   "condition_id", "rows"), "CT03_LOCK_ENTRIES_FIELDS")
    require(entries["schema"] == INPUT_SCHEMA and
            entries["world_public_id"] == context["world"] and
            entries["source_snapshot_hash"] == context["source_hash"] and
            entries["condition_id"] == "C0" and type(entries["rows"]) is list,
            "CT03_LOCK_ENTRIES_CASE_MISMATCH")
    expected, seen = registry(d_manifest, m_manifest), set()
    for row in entries["rows"]:
        key = validate_row(row, expected, context["world"])
        require(key not in seen, "CT03_LOCK_DUPLICATE_CANDIDATE")
        seen.add(key)
    require(seen == set(expected), "CT03_LOCK_ALL_THIRTEEN_SLOTS_REQUIRED")
    body = {
        "schema": SCHEMA,
        "status": "BYTE_LOCK_ONLY_NOT_INDEPENDENT_EXECUTION_PROOF",
        "world_public_id": context["world"], "condition_id": "C0",
        "source_snapshot_hash": context["source_hash"],
        "world_commitment_sha256": commitment["private_commitment_sha256"],
        "protocol_sha256": commitment["protocol_sha256"],
        "construction_sha256": digest(construction),
        "d_manifest_sha256": digest(d_manifest),
        "m_manifest_sha256": digest(m_manifest),
        "candidate_count": len(seen),
        "material_groups": {"D": 6, "M": 3, "B": 1},
        "rows": sorted(entries["rows"], key=lambda r: (r["arm"], r["candidate_id"])),
        "authentic_solver_runs_proven": False,
        "reserved_truth_opened": False,
        "provider_calls_triggered": 0, "omc_runs_triggered": 0,
    }
    return {**body, "lock_sha256": digest(body)}


def verify_locked(lock):
    require(type(lock) is dict and sha(lock.get("lock_sha256")),
            "CT03_LOCK_MISSING_DIGEST")
    body = {key: value for key, value in lock.items() if key != "lock_sha256"}
    require(digest(body) == lock["lock_sha256"] and
            lock.get("status") == "BYTE_LOCK_ONLY_NOT_INDEPENDENT_EXECUTION_PROOF" and
            lock.get("reserved_truth_opened") is False and
            lock.get("authentic_solver_runs_proven") is False,
            "CT03_LOCK_SEAL_TAMPERED_OR_OVERCLAIMED")
    return lock["lock_sha256"]


def main():
    parser = argparse.ArgumentParser()
    for label in ("construction", "commitment", "d-manifest", "m-manifest", "entries"):
        parser.add_argument("--" + label, required=True, type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    require(not args.out.exists(), "CT03_LOCK_REFUSE_OVERWRITE")
    def read(file):
        return json.loads(file.read_text(encoding="utf-8"))
    result = seal(read(args.construction), read(args.commitment),
                  read(args.d_manifest), read(args.m_manifest), read(args.entries))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x", encoding="utf-8") as output:
        output.write(canonical(result).decode("utf-8") + "\n")
    print(json.dumps({"status": result["status"], "lock": result["lock_sha256"],
                      "rows": result["candidate_count"], "provider_calls": 0,
                      "new_omc": 0}))


if __name__ == "__main__":
    main()
