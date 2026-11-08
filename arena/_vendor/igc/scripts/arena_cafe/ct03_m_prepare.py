"""CT-03 preparation ONLY: all six native Short E1 M parents, no OMC/provider.

This prepares the source-equivalent material/information E1 models for the
fixed aggregate pulse in roadmap v4.0, without seeing any construction or held-
out world observations. Six ASTs are retained; three material projections are
not claimed to be three dynamically proven equivalent models.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from scripts.arena_v0_contract import canonical, digest
from scripts.arena_m_visible_pulse import ROOT, REGISTRY, composer, backend, stimulus_only_replace
from scripts.arena_cafe import r2_observational_contracts as r2
from scripts.arena_cafe import r2_m_six_causal_g2 as provenance
from scripts.arena_cafe.ct03_public import PUBLIC_INPUT

SCHEMA = "igc-ct03-m-original-six-initial-preparation/1.0"



def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def sha_file(p: Path):
    return "sha256:" + hashlib.sha256(p.read_bytes()).hexdigest()


def generated():
    """Original E1 compositor and renderer; only externally stated pulse differs."""
    provenance.source_integrity()
    cfg, classes, _ = composer.load_registry(REGISTRY)
    graphs = composer.enumerate_graphs(cfg, classes)
    require(len(graphs) == 6 and len({k for k, _ in graphs}) == 6,
            "CT03_M_SIX_FULL_AST_EXPECTED")
    groups = {}
    rows = []
    texts = []
    for idx, (key, graph) in enumerate(graphs):
        composer.check_graph(graph, cfg, classes)
        projection = r2._material_projection(graph, composer, cfg, classes)
        material_hash = digest(projection)
        groups.setdefault(material_hash, []).append(key)
        name = "CT03M_" + key[:12]
        original = backend.render_model(name, graph, cfg, classes)
        changed = stimulus_only_replace(original, PUBLIC_INPUT["pulse_rate"],
                                        PUBLIC_INPUT["pulse_end"])
        expected = "    Modelica.Blocks.Sources.RealExpression stimulus(y=if time < 2 then 1.7 else 0);"
        require(changed.count(expected) == 1 and
                "    deliveredTotal=" in changed and
                "    reportedDeliveryRate=" in changed and
                "    connect(stimulus.y," in changed and
                "der(" not in changed and "when " not in changed,
                "CT03_M_RENDER_OR_EXTERNAL_PULSE_DRIFT")
        # A changed native molecular mechanism is forbidden.
        require(changed == original.replace(
            "\n".join([
                "    Modelica.Blocks.Sources.Pulse pulse(amplitude=6,period=4,width=40,startTime=1);",
                "    Modelica.Blocks.Sources.Step step(height=6,startTime=1);",
                "    Modelica.Blocks.Sources.Ramp ramp(height=6,duration=3,startTime=1);",
                "    Modelica.Blocks.Sources.Pulse highPulse(amplitude=14,period=4,width=40,startTime=1);",
                "    Modelica.Blocks.Sources.RealExpression stimulus(",
                "      y=if probe==1 then pulse.y else if probe==2 then step.y else",
                "        if probe==3 then ramp.y else highPulse.y);",
            ]), "    // Only publicly supplied experimental stimulus; molecule internals unchanged.\n" + expected), "CT03_M_NON_STIMULUS_ORIGINAL_CHANGED")
        rows.append({
            "index": idx, "canonical_sha256": key,
            "full_ast_sha256": digest(graph),
            "original_ast": graph,
            "material_only_projection_sha256": material_hash,
            "class_name": name, "csv_prefix": "m" + str(idx).zfill(2),
            "parameters_source": "ORIGINAL_E1_BASE_PRIORS_UNFITTED",
            "modelica_renderer": "experiments/e1/backend.py::render_model",
            "model_revision": "NOT_PERFORMED",
            "G2": "NOT_EXECUTED", "G3": "NOT_EXECUTED"
        })
        texts.append(changed)
    require(len(groups) == 3 and sorted(map(len, groups.values())) == [2, 2, 2],
            "CT03_M_THREE_MATERIAL_PROJECTIONS_REQUIRED")
    modelica = "\n".join([
        "within;", "package ArenaCT03M", "\n\n".join(texts),
        '  annotation(uses(Modelica(version="4.0.0"),SystemDynamics(version="2.1.2")));',
        "end ArenaCT03M;", ""
    ])
    lines = [
        "getVersion();",
        'loadFile("/repo/src/modelica/IGCMolecules.mo");',
        'loadFile("/repo/src/modelica/IGCInformationMolecules.mo");',
        'loadFile("native.mo");',
    ]
    for row in rows:
        cls = "ArenaCT03M." + row["class_name"]
        lines.extend([
            "checkModel(" + cls + ");",
            "print(getErrorString());",
            "simulate(" + cls + ',startTime=0,stopTime=8,numberOfIntervals=64,'
            'method="euler",outputFormat="csv",fileNamePrefix="' +
            row["csv_prefix"] + '");',
            "print(getErrorString());",
        ])
    return rows, groups, modelica, "\n".join(lines) + "\n"


def prepare(output: Path) -> dict:
    output = Path(output)
    require(not output.exists(), "CT03_REFUSE_OVERWRITE")
    # No observed, reserved, secret, evaluator or true-world bytes are inputs.
    rows, groups, modelica, commands = generated()
    output.mkdir(parents=True, exist_ok=False)
    (output / "native.mo").write_text(modelica, encoding="utf-8", newline="\n")
    (output / "simulate.mos").write_text(commands, encoding="utf-8", newline="\n")
    manifest = {
        "schema": SCHEMA, "source": PUBLIC_INPUT,
        "source_definition_sha256": digest(PUBLIC_INPUT),
        "original_e1_registry": "experiments/e1/registry.base.json",
        "candidate_count": 6, "candidate_selection": "NONE",
        "candidates": rows,
        "material_projection_groups": [
            {"projection_sha256": key, "graph_ids": sorted(ids)}
            for key, ids in sorted(groups.items())
        ],
        "material_projection_is_dynamic_equivalence": False,
        "original_molecular_mechanisms_unchanged": True,
        "native_modelica_sha256": sha_file(output / "native.mo"),
        "planned_script_sha256": sha_file(output / "simulate.mos"),
        "planned_new_omc": 6,
        "executed_new_omc": 0,
        "provider_calls": 0, "world_selected": False,
        "world_parameters_read": False,
        "construction_observations_read": False,
        "reserved_truth_read": False,
        "solver_status": "SCRIPT_ONLY_NO_OMC_RUN",
        "scientific_status": "PREPARED_NOT_PHYSICALLY_ADJUDICATED"
    }
    (output / "manifest.json").write_bytes(canonical(manifest) + b"\n")
    return manifest


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    report = prepare(args.out)
    print(json.dumps({"status": report["scientific_status"],
                      "candidate_count": report["candidate_count"],
                      "planned_simulations": report["planned_new_omc"],
                      "executed_simulations": report["executed_new_omc"]}))


if __name__ == "__main__":
    main()
