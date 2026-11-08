"""Minimal, offline contract for three INDEPENDENT IGC Arena arms.

V0.0 only: NO hypothesis generator, no Modelica translation, no ATMS engine,
no privileged holdout custody, no scientific verdict and no LLM inference.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
import re
from typing import Any

ARMS = frozenset({"D", "B", "M"})
FUTURE_ARM = "C"  # Clef requires a separate later authorization/protocol.
INPUT_SCHEMA = "igc-arena-visible-input/0.1"
SUBMISSION_SCHEMA = "igc-arena-arm-submission/0.1"
FEEDBACK_SCHEMA = "igc-arena-arm-feedback/0.1"
EVENT_SCHEMA = "igc-arena-trace-event/0.1"
_FORBIDDEN = frozenset({
    "holdout", "gold", "ground_truth", "hidden_truth", "truth_structure",
    "generator_parameters", "reserve", "reserved_observations", "evaluation_answer",
    "other_arm_submission", "other_arm_result", "other_arm_feedback", "cross_arm_context",
})


class ArenaContractError(ValueError):
    """Input missing, inconsistent, contaminated or outside allowed V0 bounds."""


def require(ok: bool, error: str) -> None:
    if not ok:
        raise ArenaContractError(error)


def canonical(value: Any) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, ensure_ascii=False,
                          separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (ValueError, TypeError) as exc:
        raise ArenaContractError("NON_JSON_OR_NONFINITE_VALUE") from exc


def digest(value: Any) -> str:
    return "sha256:" + sha256(canonical(value)).hexdigest()


def _forbidden_keys(value: Any) -> None:
    if isinstance(value, dict):
        for k, v in value.items():
            require(isinstance(k, str) and k.casefold() not in _FORBIDDEN,
                    "RESERVED_OR_CROSS_ARM_FIELD")
            _forbidden_keys(v)
    elif isinstance(value, list):
        for v in value:
            _forbidden_keys(v)


def _valid_hash(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"sha256:[0-9a-f]{64}", value) is not None


def _valid_id(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and len(value) <= 180


def validate_visible_input(payload: dict[str, Any]) -> str:
    """Hash only PUBLIC construction. Security is a contract, not ACL enforcement."""
    require(isinstance(payload, dict), "INPUT_NOT_OBJECT")
    require(set(payload) == {
        "schema", "investigation_id", "round_id", "question", "construction",
        "observability", "source_snapshot_hash", "iteration_limit", "resources",
    }, "INPUT_FIELDS_MISMATCH")
    _forbidden_keys(payload)
    require(payload["schema"] == INPUT_SCHEMA, "BAD_INPUT_SCHEMA")
    for k in ("investigation_id", "round_id", "question", "source_snapshot_hash"):
        require(_valid_id(payload[k]), "MISSING_INPUT_" + k.upper())
    require(_valid_hash(payload["source_snapshot_hash"]), "BAD_SNAPSHOT_HASH")
    require(isinstance(payload["construction"], dict) and payload["construction"],
            "NO_CONSTRUCTION")
    require(isinstance(payload["observability"], dict) and payload["observability"],
            "NO_OBSERVABILITY")
    require(type(payload["iteration_limit"]) is int and 1 <= payload["iteration_limit"] <= 6,
            "INVALID_ITERATION_LIMIT")
    require(isinstance(payload["resources"], dict), "NO_BUDGET")
    canonical(payload)
    return digest(payload)


def arm_view(payload: dict[str, Any], arm_id: str) -> dict[str, Any]:
    """Same source content for all methods; native adapters may format it later."""
    source_hash = validate_visible_input(payload)
    require(arm_id in ARMS, "ARM_NOT_ACTIVE_IN_V0")
    return {"arm_id": arm_id, "input": deepcopy(payload), "input_hash": source_hash}


def assert_same_evidence(views: list[dict[str, Any]]) -> None:
    require(isinstance(views, list) and len(views) == 3, "EXPECTED_THREE_ARMS")
    require({v.get("arm_id") for v in views} == ARMS, "WRONG_ARM_SET")
    require(len({v.get("input_hash") for v in views}) == 1, "EVIDENCE_DIVERGED")
    for v in views:
        require(validate_visible_input(v.get("input")) == v["input_hash"],
                "EVIDENCE_TAMPERED")


def validate_submission(view: dict[str, Any], submission: dict[str, Any]) -> str:
    """Native output may be PARTIAL. A submission cannot claim simulator success."""
    require(isinstance(submission, dict), "SUBMISSION_NOT_OBJECT")
    require(set(submission) == {
        "schema", "arm_id", "round_id", "iteration", "parent_revision_id",
        "native_artifact_sha256", "method_version", "hypothesis_ids", "status",
        "unknowns", "assumption_ids", "evidence_refs", "notes",
    }, "SUBMISSION_FIELDS_MISMATCH")
    _forbidden_keys(submission)
    require(submission["schema"] == SUBMISSION_SCHEMA, "BAD_SUBMISSION_SCHEMA")
    require(view.get("arm_id") in ARMS and submission["arm_id"] == view["arm_id"],
            "CROSS_ARM_SUBMISSION")
    require(view.get("input_hash") == validate_visible_input(view.get("input")),
            "INPUT_CHANGED")
    require(submission["round_id"] == view["input"]["round_id"], "CROSS_ROUND")
    require(type(submission["iteration"]) is int and
            0 <= submission["iteration"] < view["input"]["iteration_limit"],
            "ITERATION_OUT_OF_BOUNDS")
    require((submission["iteration"] == 0 and submission["parent_revision_id"] is None) or
            (submission["iteration"] > 0 and _valid_id(submission["parent_revision_id"])),
            "BROKEN_REVISION_LINK")
    require(isinstance(submission["status"], str) and
            submission["status"] in {"PROPOSED", "PARTIAL", "ABSTAINED", "BLOCKED"},
            "UNVERIFIED_EXECUTABILITY_CLAIM")
    require(_valid_id(submission["method_version"]), "MISSING_METHOD_VERSION")
    require(_valid_hash(submission["native_artifact_sha256"]), "BAD_NATIVE_HASH")
    for k in ("hypothesis_ids", "unknowns", "assumption_ids", "evidence_refs"):
        require(isinstance(submission[k], list) and
                all(_valid_id(v) for v in submission[k]), "BAD_LIST_" + k.upper())
    require(isinstance(submission["notes"], str), "BAD_NOTES")
    return digest(submission)


def feedback_to_own_arm(view: dict[str, Any], submission: dict[str, Any],
                        *, submission_hash: str, technical_diagnostics: list[dict[str, str]]) -> dict[str, Any]:
    """Only this submission's verifier output. No peer comparisons or hidden holdout."""
    require(validate_submission(view, submission) == submission_hash, "SUBMISSION_HASH_MISMATCH")
    require(isinstance(technical_diagnostics, list) and technical_diagnostics,
            "NO_TECHNICAL_DIAGNOSTICS")
    allowed = {"gate", "status", "details", "source_artifact_hash"}
    cleaned = []
    for diag in technical_diagnostics:
        require(isinstance(diag, dict) and set(diag) == allowed, "INVALID_DIAGNOSTIC_FIELDS")
        _forbidden_keys(diag)
        require(diag["gate"] in {"G0", "G1", "G2", "G3"}, "INVALID_GATE")
        require(diag["status"] in {"PASS", "FAIL", "PARTIAL", "BLOCKED", "NOT_RUN"},
                "INVALID_GATE_STATUS")
        require(all(_valid_id(diag[k]) for k in ("details", "source_artifact_hash")),
                "MISSING_DIAGNOSTIC_PROVENANCE")
        cleaned.append(deepcopy(diag))
    return {"schema": FEEDBACK_SCHEMA, "arm_id": view["arm_id"],
            "round_id": view["input"]["round_id"], "iteration": submission["iteration"],
            "input_hash": view["input_hash"], "submission_hash": submission_hash,
            "diagnostics": cleaned}


def trace_event(*, arm_id: str, round_id: str, event_type: str, iteration: int,
                source_hash: str, payload_hash: str, previous_event_hash: str | None = None) -> dict[str, Any]:
    """Event envelope for future ledger+ATMS projection; does not implement ATMS."""
    require(arm_id in ARMS and _valid_id(round_id), "BAD_EVENT_SCOPE")
    require(event_type in {"HYPOTHESIS_PROPOSED", "SIMULATION_REPORTED", "FEEDBACK_DELIVERED",
                           "HYPOTHESIS_REVISED", "ABSTENTION_RECORDED"}, "BAD_EVENT_TYPE")
    require(type(iteration) is int and iteration >= 0, "BAD_EVENT_ITERATION")
    for v in (source_hash, payload_hash):
        require(_valid_hash(v), "BAD_EVENT_HASH")
    if previous_event_hash is not None:
        require(_valid_hash(previous_event_hash), "BAD_PREVIOUS_EVENT_HASH")
    event = {"schema": EVENT_SCHEMA, "arm_id": arm_id, "round_id": round_id,
             "event_type": event_type, "iteration": iteration,
             "source_hash": source_hash, "payload_hash": payload_hash,
             "previous_event_hash": previous_event_hash}
    return {**event, "event_hash": digest(event)}
