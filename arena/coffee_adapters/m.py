"""M coffee adapter: original Short E1 typed compositor and unchanged equations."""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

from arena.common import digest
from .shared import VENDOR_ROOT, case_guard, emit, need, sha_bytes

REGISTRY = Path(__file__).resolve().with_name("registry.coffee.v1.json")


def original():
    e1 = VENDOR_ROOT / "experiments" / "e1"
    need((e1 / "composer.py").is_file() and (e1 / "backend.py").is_file(),
         "M_SOURCE_MISSING")
    if str(VENDOR_ROOT) not in sys.path:
        sys.path.insert(0, str(VENDOR_ROOT))
    if str(e1) not in sys.path:
        sys.path.insert(0, str(e1))
    import composer
    import backend
    from scripts.arena_m_visible_pulse import stimulus_only_replace
    need(Path(composer.__file__).resolve() == (e1 / "composer.py").resolve() and
         Path(backend.__file__).resolve() == (e1 / "backend.py").resolve(),
         "M_ORIGINAL_MODULE_SHADOWED")
    return composer, backend, stimulus_only_replace


def material_projection(graph, composer):
    """Topology-only partition; NEVER claim dynamically equivalent outputs."""
    active = {x["id"] for x in graph["instances"] if x["role"] != "report"}
    return {
        "instances": [x for x in graph["instances"] if x["id"] in active],
        "links": [x for x in graph["links"] if x["adapter"] is None and
                  x["from"].split(".")[0] in active and
                  x["to"].split(".")[0] in active],
    }


def generate(case):
    case_guard(case)
    composer, backend, swap = original()
    cfg, classes, _ = composer.load_registry(REGISTRY)
    p = case["hypotheses"]["parameters"]
    for role in ("preparation", "dispatch"):
        need(cfg["roles"][role]["parameters"] == {
            "maxThroughput": p["service_capacity"]["value"],
            "responseTime": p["response_time"]["value"]},
            "M_PUBLIC_PRIOR_DIFFERS_FROM_PINNED_REGISTRY")
    need(cfg.get("new_classes") == [] and
         cfg["roles"]["transit"]["parameters"] == {"maxThroughput": 100,
                                                      "responseTime": 1.6},
         "M_UNKNOWN_REGISTRY_EXTENSION")
    need(p["response_time"]["value"] >= 0.1,
         "M_MIN_RESPONSE_TIME_IS_SIX_MINUTES")
    graphs = composer.enumerate_graphs(cfg, classes)
    need(len(graphs) == 6 and len({key for key, _ in graphs}) == 6,
         "M_SIX_ORIGINAL_CANDIDATES_REQUIRED")
    files = {"registry-snapshot.json": json.dumps(cfg, sort_keys=True, indent=2) + "\n"}
    rows = []
    groups = defaultdict(list)
    rate = case["input"]["rate_orders_per_hour"]
    duration = case["time"]["horizon_hours"]
    model_text = []
    for index, (key, graph) in enumerate(graphs):
        composer.check_graph(graph, cfg, classes)
        projection = material_projection(graph, composer)
        projection_key = digest(projection)
        groups[projection_key].append(key)
        name = "CoffeeM_" + key[:12]
        rendered = backend.render_model(name, graph, cfg, classes)
        model = swap(rendered, rate, duration)
        need("der(" not in model and "when " not in model and
             model.count("Modelica.Blocks.Sources.RealExpression stimulus(") == 1 and
             "    deliveredTotal=" in model and
             "    reportedDeliveryRate=" in model,
             "M_SOURCE_STIMULUS_OR_EQUATIONS_CHANGED")
        model_text.append(model)
        rows.append({
            "id": "M-" + key[:12], "modelica_class": "ArenaCoffeeM." + name,
            "modelica_file": "native.mo", "csv_prefix": "m" + str(index).zfill(2),
            "canonical_graph_sha256": "sha256:" + key,
            "full_ast_sha256": digest(graph), "full_ast": graph,
            "material_projection_sha256": projection_key,
            "material_projection": projection,
            "preparation_capacity_orders_per_hour": p["service_capacity"]["value"],
            "preparation_response_time_hours": p["response_time"]["value"],
            "physical_counter": "deliveredTotal",
            "informational_signal_not_counter": "reportedDeliveryRate",
            "parametric_status": "PUBLIC_ASSUMPTIONS_NOT_FITTED",
        })
    need(len(groups) == 3 and sorted(map(len, groups.values())) == [2, 2, 2],
         "M_EXPECTED_THREE_MATERIAL_PROJECTIONS")
    files["native.mo"] = "\n".join([
        "within;", "package ArenaCoffeeM", "\n\n".join(model_text),
        '  annotation(uses(Modelica(version="4.0.0"),SystemDynamics(version="2.1.2")));',
        "end ArenaCoffeeM;", ""
    ])
    # Preview plan ONLY: not an OMC attempt. The runner will stage pinned
    # libraries and run this script in a later explicitly budgeted campaign.
    script = ["getVersion();",
              'loadFile("/repo/src/modelica/IGCMolecules.mo");',
              'loadFile("/repo/src/modelica/IGCInformationMolecules.mo");',
              'loadFile("native.mo");']
    for row in rows:
        script.extend(["checkModel(" + row["modelica_class"] + ");",
                       "print(getErrorString());"])
    files["check-only.mos"] = "\n".join(script) + "\n"
    manifest = {
        "arm": "M", "method": "short-e1-original-typed-graph-enumeration",
        "adapter": "coffee-m-native/1", "registry_path": str(REGISTRY.relative_to(VENDOR_ROOT.parent.parent)),
        "registry_sha256": sha_bytes(REGISTRY.read_bytes()),
        "registry_original_catalog": "experiments/e0/catalog.json",
        "candidate_count": 6, "candidates": rows,
        "material_groups": [{"projection_sha256": k, "candidate_ids": sorted(v)}
                            for k, v in sorted(groups.items())],
        "material_projection_is_dynamic_equivalence": False,
        "input_profile": {"kind": "pulse", "rate": rate, "duration": duration,
                          "unit": "orders/hour and hours"},
        "role_semantics": {"Order": "paid order", "ReadyOrder": "prepared aggregate work",
                           "Shipment": "dispatch aggregate work", "Delivered": "picked up order"},
        "physical_counter": "deliveredTotal",
        "informational_counter": "reportedDeliveryRate_NOT_PHYSICAL",
        "changed_modelica": "EXTERNAL_STIMULUS_ONLY_ORIGINAL_BACKEND_RENDERED",
        "native_mechanism_unchanged": True,
        "unsupported": ["post_payment_abandonment", "prepayment_abandonment",
                        "shared_barista_machine_resources", "individual_wait_p90",
                        "S1_to_S5_as_business_policies"],
        "has_measured_pickups_for_calibration": False,
    }
    return files, manifest


def prepare(case, out):
    need(not Path(out).exists(), "REFUSE_OVERWRITE")
    files, manifest = generate(case)
    return emit(out, "M", case, files, manifest)
