"""RF-02 / R2: strictly additive POS observation contracts, no numerical run.

D-B is a NEW, versioned observational boundary bound to the untouched D
grammar. It does not call D.generate with fabricated pulses, choose D2, estimate
nominal parameters, or translate POS events into a rate silently.

M inventory uses the original Short E1 six-graph BASE registry, preserves the
full AST and fixed parameters, and records material-only projection groups as
structural observations, NOT claims of dynamic equivalence.

This module must never import an evaluator DES, OpenModelica or any LLM client.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import defaultdict
from fractions import Fraction
from pathlib import Path

from scripts.arena_v0_contract import ArenaContractError, canonical, digest
from scripts.arena_cafe.native_handoff import validate_a1_visible, need
from scripts.arena_d_v01 import (
    generate as legacy_generate, lint_structure, modelica as legacy_modelica,
    topology,
)
from scripts.arena_m_short_e1 import E1, get_composer

SCHEMA="igc-arena-r2-observational-contracts/0.1"
D_SCHEMA="igc-arena-d-observed-pos-extension/0.1"
M_SCHEMA="igc-arena-m-base-universe/0.1"
HJ_SCHEMA="igc-arena-r2-comparability-matrix/0.1"
D_RANGES={"max_stocks":(1,3),"max_candidates":(1,6),"max_simulations":(0,6)}
D_PARAMETERS={
    "capacity":"orders/minute",
    "response_time":"minute",
    "loss_time":"minute",
}
EVENT_KIND="PUBLIC_POS_PEDIDO_CREADO_BEFORE_CUTOFF"
NO_SIGNAL="POLICY_NOT_SELECTED_NO_RATE_INFERRED"
NO_NOMINAL="NO_PARAMETERS_DECLARED"
BASE_PATH=E1/"registry.base.json"
REGISTRY_GIT_BLOB="956eb9636046165b827275a822f37f3643dc1e59"
D_GIT_BLOB="9dcab2bf1ee3a3c7430595385f381d89ba023a6d"


def _blob(path):
    data=Path(path).read_bytes()
    return hashlib.sha1(b"blob "+str(len(data)).encode()+bytes([0])+data).hexdigest()


def original_source_checks():
    need(_blob(Path(__file__).resolve().parents[1]/"arena_d_v01.py")==D_GIT_BLOB,
         "R2_D_ORIGINAL_CHANGED")
    need(_blob(BASE_PATH)==REGISTRY_GIT_BLOB,"R2_M_BASE_REGISTRY_CHANGED")
    return True


def _budget(resources):
    need(type(resources) is dict and
         set(resources)=={"max_stocks","allow_loss","max_candidates","max_simulations"},
         "R2_D_RESOURCE_SCHEMA")
    need(all(type(resources[k]) is int and low<=resources[k]<=high
             for k,(low,high) in D_RANGES.items()) and
         type(resources["allow_loss"]) is bool, "R2_D_OUT_OF_ORIGINAL_BUDGET")
    return {k:resources[k] for k in
            ("max_stocks","allow_loss","max_candidates","max_simulations")}


def _grammar(resources):
    """D original topology and linter, without supplying synthetic pulse data."""
    r=_budget(resources)
    rows=[]
    for n in range(1,r["max_stocks"]+1):
        for loss in ((False,True) if r["allow_loss"] else (False,)):
            structure=topology(n,loss)
            lint=lint_structure(structure)
            key=digest(structure)
            rows.append({
                "id":"D-"+key[7:19],
                "structure":structure,
                "structure_hash":key,
                "lint":lint,
            })
    rows=rows[:r["max_candidates"]]
    need(len(rows)==len({row["structure_hash"] for row in rows}),
         "R2_D_DUPLICATE_STRUCTURE")
    return rows


def _declared_params(params):
    """Only explicit external provenance is representable; never derive from E1."""
    if params is None:
        return None
    need(type(params) is dict and set(params)==set(D_PARAMETERS),
         "R2_D_NOMINAL_COMPLETE_SCHEMA_REQUIRED")
    result={}
    for name,unit in D_PARAMETERS.items():
        item=params[name]
        need(type(item) is dict and
             set(item)=={"value","unit","status","actor","source_kind","source_ref"},
             "R2_D_NOMINAL_PROVENANCE_REQUIRED")
        value=item["value"]
        need(type(value) in (int,float) and math.isfinite(value) and value>0,
             "R2_D_NOMINAL_NONPOSITIVE")
        need(item["unit"]==unit and
             item["status"] in ("ASSUMED","EXTERNALLY_ESTIMATED") and
             item["actor"] in ("INVESTIGATOR","EXTERNAL_ESTIMATOR") and
             item["source_kind"] in ("EXPLICIT_UNVALIDATED_ASSUMPTION",
                                     "INDEPENDENT_OPERATIONAL_MEASUREMENT") and
             type(item["source_ref"]) is str and
             2<=len(item["source_ref"])<=150 and
             all(x not in item["source_ref"].lower()
                 for x in ("e1_registry","other_arm","private_des","holdout")),
             "R2_D_NOMINAL_NOT_INDEPENDENT_OR_UNATTRIBUTED")
        need((item["status"]=="ASSUMED" and
              item["source_kind"]=="EXPLICIT_UNVALIDATED_ASSUMPTION" and
              item["actor"]=="INVESTIGATOR") or
             (item["status"]=="EXTERNALLY_ESTIMATED" and
              item["source_kind"]=="INDEPENDENT_OPERATIONAL_MEASUREMENT" and
              item["actor"]=="EXTERNAL_ESTIMATOR"),
             "R2_D_NOMINAL_STATUS_INCONSISTENT")
        result[name]=dict(item)
    return result


def d_pos_contract(visible,condition,*,resources,nominal=None):
    """Enumerate ALL D grammar alternatives; return no executable rate/model.

    The public event list is bound exactly but an input-rate profile is withheld
    until a future, pre-authorized policy is approved and versioned.
    """
    original_source_checks()
    validate_a1_visible(visible,condition)
    budget=_budget(resources)
    parameters=_declared_params(nominal)
    events=visible["construction"]["pos_arrival_events"]
    cutoff=Fraction(visible["observability"]["cutoff_minutes_exact"])
    times=[Fraction(row["t_minutes_exact"]) for row in events]
    need(all(0<=t<cutoff for t in times),
         "R2_D_POS_AFTER_CUTOFF")
    members=_grammar(budget)
    declared={
        "schema":D_SCHEMA,
        "method":"D_OBSERVED_POS_EXTENSION/0.1",
        "legacy_method":"generic-conservative-chain-search/0.1",
        "legacy_source_git_blob":D_GIT_BLOB,
        "legacy_generate_called_with_pos":False,
        "legacy_grammar_functions_used":["topology","lint_structure"],
        "arm_id":"D","condition_id":condition,
        "public_view_sha256":digest(visible),
        "public_source_snapshot_hash":visible["source_snapshot_hash"],
        "observational_boundary":{
            "event_kind":EVENT_KIND,
            "source":"construction.pos_arrival_events",
            "event_times_minutes_exact":[str(t) for t in times],
            "event_ids_hash":digest(events),
            "events_n":len(events),
            "total_input_orders":len(events),
            "cutoff_minutes_exact":str(cutoff),
            "observed_instants_are_not_continuous_rate":True,
            "delivery_observation_used_to_construct_arrival_signal":False,
            "arrival_signal_hash":None,
            "rate_conversion_policy":NO_SIGNAL,
            "candidate_reference_only":"A1_UNIFORM_0_5_MIN_PARITY_NOT_AUTHORIZED_FOR_D_B",
            "retrocausal_bin_leak_risk":"UNIFORM_BIN_MAY_PREDATE_EVENT",
        },
        "original_resources":budget,
        "candidate_count":len(members),
        "candidates":[{
            **row,
            "selection_owner":"NONE",
            "parameter_values":({key:parameters[key]["value"]
                                 for key in D_PARAMETERS} if parameters else None),
            "modelica_sha256":None,
            "G0":"ORIGINAL_GRAMMAR_ENUMERATED",
            "G1":"ORIGINAL_LINTER_PASS",
            "G2":"NOT_RUN","G3":"NOT_RUN",
        } for row in members],
        "nominal_parameters_provenance":parameters,
        "nominal_parameters_state":(
            "EXPLICIT_EXTERNAL_VALUES_NOT_FITTED_BY_D"
            if parameters is not None else NO_NOMINAL),
        "parameter_inference_by_original_D":False,
        "candidate_selection_by_original_D":False,
        "modelica_emission":"NOT_RUN_SIGNAL_POLICY_MISSING",
        "solver_invocations":0,"provider_calls":0,
        "g4":"NOT_RUN","g5":"NOT_RUN",
        "method_component_execution":"ORIGINAL_GRAMMAR_ENUMERATION_VIA_VERSIONED_EXTENSION",
        "arena_task_complete":False,
        "method_complete":False,
        "simulation_authorized":False,
        "decision_required":[
            "PROSPECTIVE_TEMPORAL_SIGNAL_POLICY_AND_CAUSALITY_BOUND",
            "INDEPENDENT_PARAMETER_PROVENANCE_FOR_EV01",
            "SCIENTIFIC_APPROVAL_FOR_EQUATION_EMISSION_OR_G2",
        ],
    }
    return declared


def legacy_intersection_conformance(legacy_visible):
    """D-A: compare native D-generated candidates to an independent grammar path.

    This accepts ONLY an already valid D pulse fixture, not EV-01. Original
    generated Modelica text is compared byte-for-byte for every candidate.
    Neither version is simulated. This does not establish POS temporal validity.
    """
    from scripts.arena_d_v01 import validate_case
    original_source_checks()
    validate_case(legacy_visible)  # native original must admit this control
    result=legacy_generate(legacy_visible)
    expected=_grammar(legacy_visible["resources"])
    got=result["candidates"]
    need(len(got)==len(expected) and len(got)>0,
         "R2_D_LEGACY_UNIVERSE_MISMATCH")
    nominal=legacy_visible["construction"]["nominal_parameters"]
    profile=legacy_visible["construction"]["input_profile"]
    checked=[]
    for old,new in zip(got,expected):
        need(old["id"]==new["id"] and
             old["structure"]==new["structure"] and
             old["structure_hash"]==new["structure_hash"] and
             old["lint"]==new["lint"] and
             old["nominal_parameters"]==nominal and
             old["parameter_status"]=="PUBLIC_ASSUMPTIONS_NOT_FITTED",
             "R2_D_LEGACY_TOPOLOGY_OR_ORDER_CHANGED")
        independent={**new,"nominal_parameters":dict(nominal),
                     "parameter_status":"PUBLIC_ASSUMPTIONS_NOT_FITTED"}
        # The shared original renderer is called with two independently built
        # candidate payloads. This tests payload and bytes, not 2 renderers.
        actual=legacy_modelica(old,profile)
        expect=legacy_modelica(independent,profile)
        need(actual==expect,"R2_D_LEGACY_RENDER_DIFFERS")
        checked.append({"candidate_id":old["id"],
                        "structure_sha256":old["structure_hash"],
                        "modelica_sha256":"sha256:"+hashlib.sha256(actual.encode()).hexdigest()})
    return {
        "schema":"igc-r2-d-legacy-intersection-conformance/0.1",
        "scope":"VALID_ORIGINAL_D_PULSE_FIXTURE_NOT_EV01",
        "legacy_generate_invoked":True,
        "d_pos_extension_accepts_event_data_in_this_test":False,
        "candidate_count":len(checked),
        "candidates":checked,
        "order_structure_and_modelica_bytes":"MATCH",
        "solver_invocations":0,"scientific_equivalence_for_POS":"NOT_PROVEN",
    }


def _material_projection(graph,composer,cfg,classes):
    """Remove signal-only instances and edges; preserve material provenance."""
    items={node["id"]:node for node in graph["instances"]}
    material_ids=set()
    for node in graph["instances"]:
        ports=composer.ports(classes[node["class_id"]],node["role"])
        if any(p["type"].startswith("FLOW<") for p in ports) or (
            node["role"] in (cfg["endpoints"]["source"]["role"],
                             cfg["endpoints"]["receipt"]["role"])):
            material_ids.add(node["id"])
    nodes=[node for node in graph["instances"] if node["id"] in material_ids]
    links=[edge for edge in graph["links"]
           if edge["adapter"] is None and
           edge["from"].split(".")[0] in material_ids and
           edge["to"].split(".")[0] in material_ids]
    need(len(nodes)>=4 and len(links)==len(nodes)-1,
         "R2_M_MATERIAL_PROJECTION_INVALID")
    return {"instances":nodes,"links":links}


def m_base_universe(visible,condition):
    """Read all six original E1 base ASTs, no selection or G2 simulation."""
    original_source_checks()
    validate_a1_visible(visible,condition)
    c=get_composer()
    cfg,classes,catalog=c.load_registry(BASE_PATH)
    graphs=c.enumerate_graphs(cfg,classes)
    need(len(graphs)==6 and len({k for k,_ in graphs})==6,
         "R2_M_BASE_SIX_ORIGINAL_GRAPHS_DRIFT")
    rows=[]
    groups=defaultdict(list)
    for key,ast in graphs:
        c.check_graph(ast,cfg,classes)
        projection=_material_projection(ast,c,cfg,classes)
        group=digest(projection)
        groups[group].append(key)
        rows.append({
            "canonical_sha256":key,
            "full_ast_sha256":digest(ast),
            "ast":ast,
            "material_only_projection_sha256":group,
            "native_registry_parameters_preserved":True,
            "observational_selection":"NOT_RUN",
            "simulation":"NOT_RUN",
            "semantic_observable_equivalence":"NOT_PROVEN",
        })
    need(len(groups)==3 and sorted(map(len,groups.values()))==[2,2,2],
         "R2_M_MATERIAL_PROJECTION_GROUPS_DRIFT")
    return {
        "schema":M_SCHEMA,
        "arm_id":"M","condition_id":condition,
        "source_public_sha256":digest(visible),
        "source_snapshot_hash":visible["source_snapshot_hash"],
        "original_composer":"experiments/e1/composer.py",
        "source_registry":"experiments/e1/registry.base.json",
        "registry_git_blob":REGISTRY_GIT_BLOB,
        "registry_sha256":digest(cfg),
        "catalog_schema":catalog["schema_version"],
        "mandatory_roles_are_priors":list(cfg["mandatory_roles"]),
        "graph_count":6,"candidate_graphs":rows,
        "material_projection_group_count":3,
        "material_projection_groups":[{"projection_sha256":k,
                                      "graph_ids":sorted(v)}
                                     for k,v in sorted(groups.items())],
        "material_projection_is_dynamic_equivalence":False,
        "extended_registry_not_used":True,
        "registry_parameters_fixed_not_estimated_from_POS":True,
        "original_component_complete":True,
        "arena_task_complete":False,
        "selection_actor":"NONE",
        "abstention":"M0_SELECTION_UNRESOLVED_NOT_ENUMERATOR_FAILURE",
        "g2":"NOT_RUN","g3":"NOT_RUN",
    }


def comparable_observables(visible,condition):
    """Strict per-arm semantics; common availability ≠ forced representability."""
    validate_a1_visible(visible,condition)
    specs=[]
    def add(obs,role,arms,hj,limit):
        specs.append({"observable":obs,"role":role,"per_arm":arms,
                      "H_j":hj,"semantic_limit":limit})
    add("orders_created_cumulative","INPUT_NOT_SCORED",
        {"D":"ENTRY_OBSERVED_NO_RATE_POLICY",
         "B":"INPUT_AVAILABLE_LIVE_USE_NOT_VERIFIED",
         "M":"INPUT_AVAILABLE_TYPED_SOURCE_PORT_UNRUN"},
        "integral(input_rate,0,t) if and only if justified",
        "Never score supplied arrivals as model prediction.")
    add("delivered_cumulative","POTENTIAL_PRIMARY_OUTPUT",
        {"D":"CANDIDATE_AFTER_PARAMS_SIGNAL_AND_G2",
         "B":"PENDING_REAL_NATIVE_MODEL_AND_TRANSLATION",
         "M":"CANDIDATE_TYPED_RECEIPT_STATE_HJ_NOT_CALIBRATED"},
        "delivered(t) with same material, boundary, units and observation window",
        "No common metric until each trajectory passes semantic admission.")
    add("orders_minus_delivered","OBSERVED_BALANCE_NOT_WIP_BY_DEFAULT",
        {"D":"MAY_INCLUDE_STOCKS_AND_LOST",
         "B":"UNDETERMINED_NATIVE_MECHANISM",
         "M":"UNRESOLVED_MATERIAL_CORRESPONDENCE"},
        "A(t)-delivered(t)",
        "If losses exist, A-D includes losses; not just in-process stocks.")
    if condition=="O1":
        add("n_completed_stage_services","O1_STAGE_EVIDENCE",
            {"D":"NO_IDENTIFIED_PREPARATION_STAGE",
             "B":"UNKNOWN_NATIVE_STAGE",
             "M":"TYPED_PORT_PROPOSED_SEMANTIC_EQUIVALENCE_NOT_PROVEN"},
            "integral(preparation.completed) only if operational unit correspondence passes",
            "Discrete-v-continuous not automatically excluded; semantic mapping missing.")
        for name in ("mean_wait_minutes_exact","mean_service_minutes_exact"):
            add(name,"O1_CENSORED_STAGE_EVIDENCE",
                {"D":"NOT_COMPARABLE","B":"NOT_COMPARABLE",
                 "M":"NOT_COMPARABLE"},
                "NO_ADMISSIBLE_OPERATOR",
                "Completed intervals only; neither a stock nor a responseTime estimate.")
    return {
        "schema":HJ_SCHEMA,"condition_id":condition,
        "source_snapshot_hash":visible["source_snapshot_hash"],
        "view_sha256":digest(visible),
        "primary_policy":"DELIVERED_CUMULATIVE_CONDITIONAL_ON_PER_ARM_SEMANTIC_GATE",
        "same_evidence_not_same_method":True,
        "no_native_stage_forced":True,
        "no_scoring_absent_observables":True,
        "source_event_count":len(visible["construction"]["pos_arrival_events"]),
        "source_event_type":EVENT_KIND,
        "operator_admission":"NOT_RUN",
        "operators":specs,
    }


def build(visible,condition,resources,nominal=None):
    d=d_pos_contract(visible,condition,resources=resources,nominal=nominal)
    m=m_base_universe(visible,condition)
    hj=comparable_observables(visible,condition)
    need(d["public_source_snapshot_hash"]==
         m["source_snapshot_hash"]==hj["source_snapshot_hash"],
         "R2_SOURCE_CROSS_ARM_MISMATCH")
    return {
        "schema":SCHEMA,
        "condition_id":condition,
        "public_snapshot":visible["source_snapshot_hash"],
        "public_view_sha256":digest(visible),
        "D":d,"M":m,"Hj":hj,
        "D_A":"LEGACY_CONFORMANCE_SEPARATE_FIXTURE",
        "D_B":"VERSIONED_OBSERVATIONAL_CONTRACT_ONLY",
        "D_C":"NEW_EXPERIMENT_NOT_STARTED",
        "temporal_input_policy":"NOT_SELECTED",
        "nominal_ev01_origin":"NOT_AUTHORIZED_WHEN_MISSING",
        "R2":"PARTIAL_CONTRACT_AND_GRAMMAR_NO_NUMERICAL_POLICY",
        "R3":"NOT_RUN","A3":"PARTIAL","G4":"NOT_RUN","G5":"NOT_RUN",
        "provider_calls":0,"solver_invocations":0,
        "independent_scientific_review":"PENDING",
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input",required=True,type=Path)
    p.add_argument("--condition",required=True,choices=("O0","O1"))
    p.add_argument("--out",required=True,type=Path)
    p.add_argument("--budget",type=Path)
    p.add_argument("--nominal-provenance",type=Path)
    args=p.parse_args()
    need(not args.out.exists(),"R2_REFUSE_OVERWRITE")
    view=json.loads(args.input.read_text(encoding="utf-8"))
    # Explicit, prospective complete legacy budget; not a selection among
    # evaluated candidates. To narrow it, provide a reviewed budget file.
    resources=(json.loads(args.budget.read_text(encoding="utf-8"))
               if args.budget else {"max_stocks":3,"allow_loss":True,
                                    "max_candidates":6,"max_simulations":0})
    nominal=(json.loads(args.nominal_provenance.read_text(encoding="utf-8"))
             if args.nominal_provenance else None)
    report=build(view,args.condition,resources,nominal)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_bytes(canonical(report)+bytes([10]))
    print(json.dumps({"R2":report["R2"],
                      "D_candidates":report["D"]["candidate_count"],
                      "M_candidates":report["M"]["graph_count"],
                      "G4":report["G4"],"G5":report["G5"]},
                     sort_keys=True))


if __name__=="__main__":
    main()
