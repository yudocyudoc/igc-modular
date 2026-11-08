"""CT-02: render exactly one revision chosen by original M2 own_policy.

The policy already consumed own supported feedback in ct_feedback_bridge.
This adapter only binds that result back to the exact original Short E1 parent,
checks that two responseTime multipliers were the sole change, and renders
through the original E1 backend with the same external pulse. No OMC, provider,
hidden-world truth, fitting, re-ranking or topology repair.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
from pathlib import Path

from scripts.arena_v0_contract import canonical, digest
from scripts.arena_m_visible_pulse import composer, backend, REGISTRY, stimulus_only_replace
from scripts.arena_cafe.ct03_m_prepare import SCHEMA as PREP, PUBLIC_INPUT
from scripts.arena_cafe.ct_feedback_bridge import M_POLICY, require

SCHEMA = "igc-ct03-m-own-policy-revision-native/1.0"


def hashbytes(value: bytes):
    return "sha256:" + hashlib.sha256(value).hexdigest()


def validate_revision(manifest, parent, decision):
    require(type(manifest) is dict and manifest.get("schema") == PREP and
            manifest.get("candidate_count") == 6 and
            type(parent) is dict and
            sum(parent == x for x in manifest["candidates"]) == 1,
            "CT03_M_REVISION_NOT_OWN_SIX_PARENT")
    require(type(decision) is dict and decision.get("status") == "REVISED" and
            decision.get("policy") == M_POLICY and
            decision.get("parent_hash") == digest(parent["original_ast"]) and
            decision.get("new_graph_hash") == digest(decision.get("new_model")) and
            type(decision.get("retrieved_before_policy")) is dict and
            type(decision.get("parameter_edits")) is list and
            len(decision["parameter_edits"]) == 2,
            "CT03_M_REVISION_NO_POLICY_PROVENANCE")
    cfg, classes, _ = composer.load_registry(REGISTRY)
    prior = parent["original_ast"]
    updated = decision["new_model"]
    composer.check_graph(prior, cfg, classes)
    composer.check_graph(updated, cfg, classes)
    require(composer.canonical(updated) == parent["canonical_sha256"],
            "CT03_M_REVISION_TOPOLOGY_CHANGED")
    require(prior.keys() == updated.keys() and prior["links"] == updated["links"] and
            len(prior["instances"]) == len(updated["instances"]),
            "CT03_M_REVISION_CHANGED_EDGES_OR_MEMBERSHIP")
    changes = []
    for before, after in zip(prior["instances"], updated["instances"]):
        require(before.keys() == after.keys() and
                before["id"] == after["id"] and
                before["class_id"] == after["class_id"] and
                before["role"] == after["role"],
                "CT03_M_REVISION_NODE_IDENTITY_CHANGED")
        if before["role"] in ("preparation", "dispatch"):
            original = before["parameters"]["responseTime"]
            current = after["parameters"]["responseTime"]
            bound = classes[before["class_id"]]["parameters"]["responseTime"]
            require(type(original) in (int, float) and
                    current == original*2 and
                    bound["min"] <= current <= bound["max"] and
                    after["parameters"] == {**before["parameters"], "responseTime": current},
                    "CT03_M_REVISION_UNAUTHORIZED_RESPONSE_TIME_EDIT")
            changes.append({
                "instance_id": before["id"], "parameter": "responseTime",
                "before": original, "after": current,
                "catalog_bounds": [bound["min"], bound["max"]],
            })
        else:
            require(before == after, "CT03_M_REVISION_NON_TARGET_CLASS_CHANGED")
    require(len(changes) == 2 and
            changes == decision["parameter_edits"],
            "CT03_M_REVISION_POLICY_EDITS_DIFFER")
    return cfg, classes, updated


def prepare_revision(out: Path, manifest, parent, decision):
    out = Path(out)
    require(not out.exists(), "CT03_M_REVISION_REFUSE_OVERWRITE")
    cfg, classes, graph = validate_revision(manifest, parent, decision)
    model_name = "CT03MR_" + parent["canonical_sha256"][:12] + "_" + digest(graph)[7:15]
    original = backend.render_model(model_name, graph, cfg, classes)
    rendered = stimulus_only_replace(original, PUBLIC_INPUT["pulse_rate"], PUBLIC_INPUT["pulse_end"])
    require(rendered.count("    Modelica.Blocks.Sources.RealExpression stimulus(y=if time < 2 then 1.7 else 0);") == 1 and
            "    deliveredTotal=" in rendered and "    reportedDeliveryRate=" in rendered and
            "der(" not in rendered and "when " not in rendered,
            "CT03_M_REVISION_RENDER_DRIFT")
    text = "\n".join([
        "within;", "package ArenaCT03MR", rendered,
        '  annotation(uses(Modelica(version="4.0.0"),SystemDynamics(version="2.1.2")));',
        "end ArenaCT03MR;", ""
    ])
    commands = "\n".join([
        "getVersion();",
        'loadFile("/repo/src/modelica/IGCMolecules.mo");',
        'loadFile("/repo/src/modelica/IGCInformationMolecules.mo");',
        'loadFile("revision.mo");',
        "checkModel(ArenaCT03MR." + model_name + ");",
        "print(getErrorString());",
        "simulate(ArenaCT03MR." + model_name +
            ',startTime=0,stopTime=8,numberOfIntervals=64,method="euler",'
            'outputFormat="csv",fileNamePrefix="mrev");',
        "print(getErrorString());", ""
    ])
    out.mkdir(parents=True)
    (out/"revision.mo").write_text(text, encoding="utf-8", newline="\n")
    (out/"simulate.mos").write_text(commands, encoding="utf-8", newline="\n")
    report = {
        "schema": SCHEMA, "policy": M_POLICY,
        "parent_full_ast_sha256": parent["full_ast_sha256"],
        "parent_hash": decision["parent_hash"],
        "parent_canonical_topology": parent["canonical_sha256"],
        "revised_full_ast_sha256": digest(graph),
        "parameter_edits": decision["parameter_edits"],
        "material_projection_group": parent["material_only_projection_sha256"],
        "native_modelica_sha256": hashbytes(text.encode()),
        "simulate_script_sha256": hashbytes(commands.encode()),
        "retrieved_before_policy": decision["retrieved_before_policy"],
        "feedback_hash": decision["feedback_hash"],
        "world_parameters_read": False, "reserved_truth_read": False,
        "planned_new_omc": 1, "executed_new_omc": 0,
        "provider_calls": 0,
        "status": "M2_REVISION_RENDERED_NOT_SOLVED_NOT_SCORED"
    }
    (out/"manifest.json").write_bytes(canonical(report)+b"\n")
    return report


def main():
    p=argparse.ArgumentParser()
    for name in ("manifest","parent","decision"):
        p.add_argument("--"+name, required=True, type=Path)
    p.add_argument("--out", required=True, type=Path)
    args=p.parse_args()
    result=prepare_revision(args.out,
        json.loads(args.manifest.read_text()),
        json.loads(args.parent.read_text()),
        json.loads(args.decision.read_text()))
    print(json.dumps({"status":result["status"],
                      "planned_omc":1,"executed_omc":0}))


if __name__ == "__main__":
    main()
