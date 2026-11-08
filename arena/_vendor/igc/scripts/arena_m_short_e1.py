"""Arena M0 shell around unmodified Short E1 molecular composer.

The Short E1 enumerator generates *engineering* candidates from declared roles,
not data-inferred hypotheses. M0 refuses to select one for the common Arena
question before a typed evidence-to-role mapping and parameter calibration exist.
No D/B or hidden-world inputs; no provider calls.
"""
from __future__ import annotations
import argparse
import importlib.util
import json
from pathlib import Path
from scripts.arena_v0_contract import (
    arm_view, canonical, digest, trace_event, SUBMISSION_SCHEMA, validate_submission
)

ROOT = Path(__file__).resolve().parents[1]
E1 = ROOT / "experiments" / "e1"
METHOD = "short-e1-molecular-composition-port/0.1"
REGISTRIES = {
    (E1 / "registry.base.json").resolve(),
    (E1 / "registry.extended.json").resolve(),
}


def get_composer():
    spec = importlib.util.spec_from_file_location("short_e1_composer", E1 / "composer.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def prepare(visible: dict, registry: Path):
    view = arm_view(visible, "M")
    registry = Path(registry).resolve()
    if registry not in REGISTRIES:
        raise ValueError("UNVERIFIED_M_REGISTRY")
    composer = get_composer()
    cfg, classes, catalog = composer.load_registry(registry)
    graphs = composer.enumerate_graphs(cfg, classes)
    # These are enumeration candidates, not evidence-selected proposals.
    native = {
        "schema": "igc-arena-m-e1-engineering-library/0.1",
        "arm_id": "M",
        "method": METHOD,
        "evidence_input_hash": view["input_hash"],
        "registry_variant": registry.name,
        "source_experiment": "short/E1",
        "catalog_schema": catalog["schema_version"],
        "role_config_hash": digest(cfg),
        "candidate_count": len(graphs),
        "candidate_graphs": [{"canonical_sha256": key, "ast": ast}
                             for key, ast in graphs],
        "candidate_origin": "PORT_ENUMERATION_NOT_OBSERVATIONAL_INFERENCE",
        "parameters_origin": "SHORT_E1_REGISTRY_FIXED_NOT_FIT_TO_ARENA",
        "common_stimulus_translation": "NOT_IMPLEMENTED",
        "candidate_selection": "UNRESOLVED",
        "missing": [
            "TYPED_OBSERVABLE_TO_ROLE_MAPPING",
            "DATA_ADMISSIBLE_MOLECULAR_MECHANISM",
            "INDEPENDENT_PARAMETER_ESTIMATION",
            "COMMON_STIMULUS_MODELICA_RUN",
        ],
        "status": "ENGINEERING_ONLY_NOT_AN_ARENA_EXPLANATION"
    }
    submission = {
        "schema": SUBMISSION_SCHEMA,
        "arm_id": "M",
        "round_id": visible["round_id"],
        "iteration": 0,
        "parent_revision_id": None,
        "native_artifact_sha256": digest(native),
        "method_version": METHOD,
        "hypothesis_ids": [],
        "status": "PARTIAL",
        "unknowns": native["missing"],
        "assumption_ids": ["SOURCE_SHORT_E1_ROLE_BINDINGS", "SOURCE_SHORT_E1_FIXED_PARAMETERS"],
        "evidence_refs": [visible["source_snapshot_hash"]],
        "notes": ("Enumerated typed, original Short E1 composition candidates only. "
                  "No hypothesis selected or fitted to shared Arena evidence; "
                  "OpenModelica E1 smoke is independent of Arena G3.")
    }
    validate_submission(view, submission)
    event = trace_event(
        arm_id="M", round_id=visible["round_id"],
        event_type="ABSTENTION_RECORDED", iteration=0,
        source_hash=view["input_hash"], payload_hash=digest(submission))
    return native, submission, event


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input", required=True, type=Path)
    p.add_argument("--registry", required=True, type=Path)
    p.add_argument("--out", required=True, type=Path)
    a=p.parse_args()
    if a.out.exists():
        raise ValueError("OUTPUT_ALREADY_EXISTS")
    native, submission, event = prepare(json.loads(a.input.read_text()), a.registry)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_bytes(canonical({
        "native": native, "submission": submission, "event": event}) + b"\n")
    print(json.dumps({"status": submission["status"], "source": native["source_experiment"],
                      "candidate_count": native["candidate_count"],
                      "hypothesis_ids": submission["hypothesis_ids"],
                      "unresolved": submission["unknowns"],
                      "output_hash": digest(native)}))


if __name__=="__main__":
    main()
