"""RF-02M · Original Short E1: six-graph OpenModelica engineering G2.

Preserves the six ASTs of registry.base.json in full; never invokes
choose_one(), changes original numerical parameters, or reports G3. Only
the external source stimulus is replaced with the same predeclared causal
event kernel used for D, converted exactly from minutes to hours and
orders/minute to orders/hour. The R2M OMC invocation is a separate CI job.

The material audit uses the original backend's inTransit + deliveredTotal
ports, never reportedDeliveryRate (an information-only signal).\nNOTE: original backend inTransit only sums STATE<Shipment> (transit) stocks;\nthe verified mass operator sums ALL typed bounded-queue waiting ports, including\npreparation and dispatch, plus deliveredTotal. No E1 equation is modified.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from fractions import Fraction as Q
from pathlib import Path

from scripts.arena_v0_contract import canonical, digest
from scripts.arena_cafe.native_handoff import need, validate_a1_visible
from scripts.arena_cafe import r2_causal_pos_signal as causal
from scripts.arena_cafe import r2_observational_contracts as r2
from scripts.arena_cafe import observation_eval as oe
from scripts.arena_m_short_e1 import get_composer
from scripts.arena_m_visible_pulse import backend, stimulus_only_replace

SCHEMA="igc-arena-rf02-m-six-causal-g2-engineering/0.1"
REPORT_SCHEMA="igc-arena-rf02-m-six-causal-g2-audit/0.1"
TOLERANCE_ORDERS=0.08  # fixed before observing any M six-graph trace
SIGNAL_GROUP_TOLERANCE_ORDERS=0.05 # numerical end-state-only probe, not G3
ORIGINAL_BLOBS={
    "experiments/e1/composer.py":"27d9fe2e65db924f204423f9660a576e723bfd9b",
    "experiments/e1/backend.py":"cc854a0f29399a8299146271fbe3c56c7c5347b3",
    "experiments/e1/registry.base.json":"956eb9636046165b827275a822f37f3643dc1e59",
    "src/modelica/IGCMolecules.mo":"2f83de72d38d0b8f5e866295b806d19067c5194d",
    "src/modelica/IGCInformationMolecules.mo":"36d97a7e9de4d7ee80bf884beec6094a9bb1cf98",
}
ROOT=Path(__file__).resolve().parents[2]
PULSE_STIMULUS="    Modelica.Blocks.Sources.RealExpression stimulus(y=if time < 1 then 1 else 0);"


def sha_file(path):
    return "sha256:"+hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_integrity():
    for relative,expected in ORIGINAL_BLOBS.items():
        need(r2._blob(ROOT/relative)==expected,
             "RF02M_ORIGINAL_SOURCE_CHANGED:"+relative)
    return True


def _expression_hours(signal):
    """Retain exact causal half-open event support; native E1 uses hours."""
    need(signal["policy"]==causal.POLICY and
         signal["width_minutes_exact"]=="1/2" and
         signal["no_lookahead_in_mathematical_kernel"] is True,
         "RF02M_SIGNAL_POLICY_UNAUTHORIZED")
    width=Q(signal["width_minutes_exact"])
    times=[Q(t) for t in signal["event_times_minutes_exact"]]
    need(times==sorted(times),"RF02M_EVENT_ORDER_CHANGED")
    parts=[]
    for t in times:
        parts.append("(if time >= "+causal._real(t/60)+
                     " and time < "+causal._real((t+width)/60)+
                     " then "+causal._real(60/width)+" else 0.0)")
    return " + ".join(parts) if parts else "0.0"


def _original_models(visible,condition):
    """Compute six exact backend originals and replace ONLY the source block."""
    source_integrity()
    validate_a1_visible(visible,condition)
    signal=causal.from_visible(visible,condition)["signal"]
    inventory=r2.m_base_universe(visible,condition)
    c=get_composer()
    cfg,classes,catalog=c.load_registry(r2.BASE_PATH)
    graphs=c.enumerate_graphs(cfg,classes)
    need(len(graphs)==inventory["graph_count"]==6 and
         inventory["material_projection_group_count"]==3,
         "RF02M_MUST_ENUMERATE_SIX_NATIVE_GRAPHS")
    expr=_expression_hours(signal)
    rows=[]
    texts=[]
    for i,(key,graph) in enumerate(graphs):
        original=inventory["candidate_graphs"][i]
        need(original["canonical_sha256"]==key and
             original["full_ast_sha256"]==digest(graph) and
             original["ast"]==graph,
             "RF02M_ORIGINAL_AST_IDENTITY_DRIFT")
        c.check_graph(graph,cfg,classes)
        name="E1R2_"+key[:12]
        rendered=backend.render_model(name,graph,cfg,classes)
        # Original legacy wrapper only removes original synthetic probe
        # sources, without touching native graph or molecular mechanisms.
        baseline=stimulus_only_replace(rendered,1.0,1.0)
        need(baseline.count(PULSE_STIMULUS)==1,
             "RF02M_NATIVE_STIMULUS_ANCHOR_DRIFT")
        adapted=baseline.replace(PULSE_STIMULUS,
            "    Modelica.Blocks.Sources.RealExpression stimulus(y="+expr+");")
        need(adapted.count("    connect(stimulus.y,")==1 and
             "der(" not in adapted and "when " not in adapted and
             "    reportedDeliveryRate=" in adapted and
             "    deliveredTotal=" in adapted and "    inTransit=" in adapted,
             "RF02M_NATIVE_GRAPH_OR_STATE_MECHANISM_CHANGED")
        # Strip only the replaced one-line external stimulus from both
        # renderings. The entire remaining source must be byte-identical.
        before=[x for x in baseline.splitlines()
                if x!=PULSE_STIMULUS]
        after=[x for x in adapted.splitlines()
               if not x.startswith("    Modelica.Blocks.Sources.RealExpression stimulus(y=")]
        need(before==after,"RF02M_NON_STIMULUS_EQUATION_CHANGED")
        row={
            "index":i,"canonical_sha256":key,
            "full_ast_sha256":digest(graph),
            "material_only_projection_sha256":
                original["material_only_projection_sha256"],
            "original_ast":graph,
            "model_name":name,
            "csv_prefix":"m"+str(i).zfill(2),
            "parameters_origin":"E1_BASE_REGISTRY_FIXED_NOT_POS_ESTIMATES",
            "original_backend_renderer":"experiments/e1/backend.py::render_model",
            "adaptation":"SINGLE_EXTERNAL_STIMULUS_REPLACEMENT_ONLY",
            "native_material_equations_untouched":True,
            "native_information_branch_preserved":True,
            "G2":"NOT_RUN","G3":"NOT_RUN",
        }
        rows.append(row)
        texts.append(adapted)
    package="\n".join([
        "within;","package ArenaR2M","\n\n".join(texts),
        '  annotation(uses(Modelica(version="4.0.0"),SystemDynamics(version="2.1.2")));',
        "end ArenaR2M;","",
    ])
    return signal,inventory,rows,package


def _script(rows,cutoff_hour):
    lines=[
        "getVersion();",
        'loadFile("/repo/src/modelica/IGCMolecules.mo");',
        'loadFile("/repo/src/modelica/IGCInformationMolecules.mo");',
        'loadFile("native.mo");',
    ]
    for row in rows:
        name="ArenaR2M."+row["model_name"]
        lines.extend([
            "checkModel("+name+");",
            "print(getErrorString());",
            "simulate("+name+",startTime=0,stopTime="+
            causal._real(cutoff_hour)+
            ',numberOfIntervals=2000,method="dassl",tolerance=1e-9,'+
            'outputFormat="csv",fileNamePrefix="'+row["csv_prefix"]+'");',
            "print(getErrorString());",
        ])
    return "\n".join(lines)+"\n"


def prepare(visible,condition,out):
    signal,inventory,rows,source=_original_models(visible,condition)
    out=Path(out)
    need(not out.exists(),"RF02M_REFUSE_OVERWRITE")
    out.mkdir(parents=True,exist_ok=False)
    model=out/"native.mo"
    model.write_text(source,encoding="utf-8",newline="\n")
    cutoff=Q(signal["cutoff_minutes_exact"])/60
    commands=_script(rows,cutoff)
    (out/"simulate.mos").write_text(commands,encoding="utf-8",newline="\n")
    manifest={
        "schema":SCHEMA,"condition_id":condition,
        "track":"ENGINEERING_G2_ONLY_SIX_NATIVE_E1_GRAPHS",
        "source_snapshot_hash":visible["source_snapshot_hash"],
        "public_input_sha256":digest(visible),
        "source_events_count":signal["events_count"],
        "source_events_hash":causal.from_visible(visible,condition)["events_hash"],
        "causal_stimulus":signal,
        "identical_input_policy_as_D":True,
        "time_unit":"hour","rate_unit":"orders/hour",
        "modelica_sha256":sha_file(model),
        "script_sha256":sha_file(out/"simulate.mos"),
        "original_source_git_blobs":dict(ORIGINAL_BLOBS),
        "registry_variant":"registry.base.json",
        "registry_sha256":inventory["registry_sha256"],
        "candidate_count":6,"original_candidate_universe_count":6,
        "candidate_selection_owner":"NONE",
        "candidates":rows,
        "material_projection_groups":inventory["material_projection_groups"],
        "material_projection_is_dynamic_equivalence":False,
        "preparation_dispatch_mandatory_roles_are_priors":True,
        "original_E1_parameters_fixed_not_fit_to_POS":True,
        "original_E1_component_enumeration_complete":True,
        "G2":"NOT_RUN_UNTIL_REAL_CSV",
        "G3":"NOT_RUN","G4":"NOT_RUN","G5":"NOT_RUN",
        "A3":"PARTIAL","method_complete":False,
        "scientific_adequacy":"NOT_ESTABLISHED",
        "no_EV01_parameter_inference":True,
        "no_comparison_with_observed_deliveries":True,
        "provider_calls":0,
    }
    (out/"manifest.json").write_bytes(canonical(manifest)+bytes([10]))
    return manifest



def _all_material_queue_stock_ports(candidate):
    """Use ALL typed queue stock outputs, not the restricted 'inTransit' tap.

    The original E1 backend's 'inTransit' is the sum of STATE<Shipment>
    outputs only; preparation/dispatch have different typed states.
    Therefore that display variable CANNOT be used for global conservation.
    """
    c=get_composer()
    cfg,classes,_=c.load_registry(r2.BASE_PATH)
    graph=candidate["original_ast"]
    c.check_graph(graph,cfg,classes)
    result=[]
    for node in graph["instances"]:
        if node["role"] not in ("preparation","dispatch","transit"):
            continue
        need(node["class_id"]=="bounded-queue",
             "RF02M_UNEXPECTED_NATIVE_MATERIAL_QUEUE_CLASS")
        resolved=c.ports(classes[node["class_id"]],node["role"])
        waiting=[p for p in resolved
                 if p["name"]=="waiting" and p["direction"]=="out" and
                 p["type"].startswith("STATE<") and p["unit"]=="units"]
        need(len(waiting)==1,"RF02M_MATERIAL_STOCK_PORT_NOT_TYPED")
        result.append(node["id"]+".waiting")
    need(2<=len(result)<=4 and len(result)==len(set(result)) and
         any(x.startswith("preparation") for x in result) and
         any(x.startswith("dispatch") for x in result),
         "RF02M_MATERIAL_PATH_STOCKS_NOT_COMPLETE")
    return result


def verify(visible,root):
    root=Path(root)
    need((root/"manifest.json").is_file(),"RF02M_MISSING_MANIFEST")
    manifest=json.loads((root/"manifest.json").read_text(encoding="utf-8"))
    condition=manifest["condition_id"]
    validate_a1_visible(visible,condition)
    signal,inventory,rows,expected_source=_original_models(visible,condition)
    need(manifest["schema"]==SCHEMA and
         manifest["source_snapshot_hash"]==visible["source_snapshot_hash"] and
         manifest["public_input_sha256"]==digest(visible) and
         manifest["candidate_count"]==6 and
         manifest["original_candidate_universe_count"]==6 and
         manifest["candidate_selection_owner"]=="NONE" and
         manifest["registry_variant"]=="registry.base.json" and
         manifest["registry_sha256"]==inventory["registry_sha256"] and
         manifest["original_source_git_blobs"]==ORIGINAL_BLOBS and
         manifest["candidates"]==rows and
         manifest["material_projection_groups"]==
           inventory["material_projection_groups"] and
         manifest["causal_stimulus"]==signal and
         manifest["original_E1_parameters_fixed_not_fit_to_POS"] is True and
         manifest["material_projection_is_dynamic_equivalence"] is False and
         manifest["no_comparison_with_observed_deliveries"] is True and
         manifest["G2"]=="NOT_RUN_UNTIL_REAL_CSV" and
         manifest["G3"]==manifest["G4"]==manifest["G5"]=="NOT_RUN" and
         manifest["A3"]=="PARTIAL" and
         manifest["method_complete"] is False,
         "RF02M_CANDIDATE_OR_SCIENCE_CLAIM_TAMPERED")
    need((root/"native.mo").is_file() and
         (root/"simulate.mos").is_file() and
         sha_file(root/"native.mo")==manifest["modelica_sha256"] and
         sha_file(root/"simulate.mos")==manifest["script_sha256"] and
         (root/"native.mo").read_text(encoding="utf-8")==expected_source and
         (root/"simulate.mos").read_text(encoding="utf-8")==
           _script(rows,Q(signal["cutoff_minutes_exact"])/60),
         "RF02M_MODELICA_OR_SCRIPT_DRIFT")
    need((root/"INVOCATION_STARTED").is_file() and
         (root/"exit_code.txt").is_file() and
         (root/"INVOCATION_STARTED").read_text().strip()=="INVOCATION_STARTED" and
         (root/"exit_code.txt").read_text().strip()=="0",
         "RF02M_NO_REAL_SOLVER_SUCCESS")
    cutoff=Q(signal["cutoff_minutes_exact"])
    width=Q(signal["width_minutes_exact"])
    times=[Q(x) for x in signal["event_times_minutes_exact"]]
    samples=[]
    audited=[]
    for candidate in rows:
        csv=root/(candidate["csv_prefix"]+"_res.csv")
        need(csv.is_file() and csv.stat().st_size>500,
             "RF02M_MISSING_NATIVE_SOLVER_CSV")
        data=oe._rows(csv)
        need(len(data)>=1000,"RF02M_INSUFFICIENT_REAL_SAMPLES")
        # E1 inTransit is a restricted STATE<Shipment> display, not an
        # aggregate of preparation + dispatch + transit work-in-progress.
        # Bind all native material queue ports by typed AST, not by a guessed
        # 'inTransit' label or a manually imposed two-stage topology.
        stock_ports=_all_material_queue_stock_ports(candidate)
        prev=-1.0
        prev_delivered=-1.0
        residual=0.0
        first=None
        last=None
        for row in data:
            hour=oe._column(row,"time")
            minute=hour*60
            delivered=oe._column(row,"deliveredTotal")
            stock_levels=[oe._column(row,name) for name in stock_ports]
            total_stocks=sum(stock_levels)
            partial_in_transit=oe._column(row,"inTransit")
            need(minute+1e-8>=prev and -1e-8<=minute<=float(cutoff)+1e-7,
                 "RF02M_TIME_OR_CUTOFF_DRIFT")
            need(delivered>=prev_delivered-1e-6 and
                 min([delivered,partial_in_transit]+stock_levels)>=-1e-6 and
                 partial_in_transit<=total_stocks+1e-6,
                 "RF02M_NEGATIVE_OR_DECREASING_MATERIAL")
            injected=float(causal.event_mass_until(times,width,Q(str(minute))))
            residual=max(residual,abs(total_stocks+delivered-injected))
            if first is None:
                first=(minute,delivered,total_stocks,partial_in_transit)
            last=(minute,delivered,total_stocks,partial_in_transit)
            prev,prev_delivered=minute,delivered
        need(abs(first[0])<=1e-7 and
             abs(last[0]-float(cutoff))<=1e-6,
             "RF02M_TRUNCATED_NATIVE_TRAJECTORY")
        need(residual<=TOLERANCE_ORDERS,"RF02M_MATERIAL_BALANCE_FAILED")
        samples.append({"group":candidate["material_only_projection_sha256"],
                        "delivered":last[1],"all_material_stocks":last[2]})
        audited.append({
            "canonical_sha256":candidate["canonical_sha256"],
            "full_ast_sha256":candidate["full_ast_sha256"],
            "material_only_projection_sha256":
                candidate["material_only_projection_sha256"],
            "solver_csv_sha256":sha_file(csv),
            "rows":len(data),
            "material_stock_ports":stock_ports,
            "mass_balance_operator":"SUM_ALL_TYPED_BOUNDED_QUEUE_WAITING_PLUS_DELIVERED_TOTAL",
            "inTransit_is_shipment_only_subset_not_total_WIP":True,
            "max_material_residual_orders":residual,
            "delivered_final_engineering":last[1],
            "all_material_stocks_final_engineering":last[2],
            "shipment_only_inTransit_final_engineering":last[3],
            "G2":"PASS_ENGINEERING_MASS_CONSERVATION",
            "G3":"NOT_RUN",
        })
    groups={}
    for member in samples:
        groups.setdefault(member["group"],[]).append(member)
    need(len(groups)==3 and all(len(v)==2 for v in groups.values()),
         "RF02M_STRUCTURAL_GROUPS_CHANGED")
    checks=[]
    for key,items in sorted(groups.items()):
        delta_delivery=abs(items[0]["delivered"]-items[1]["delivered"])
        delta_stocks=abs(items[0]["all_material_stocks"]-
                         items[1]["all_material_stocks"])
        need(delta_delivery<=SIGNAL_GROUP_TOLERANCE_ORDERS and
             delta_stocks<=SIGNAL_GROUP_TOLERANCE_ORDERS,
             "RF02M_INFORMATION_BRANCH_CHANGED_PHYSICAL_ENDSTATE")
        checks.append({"material_group_sha256":key,
                       "pair_count":len(items),
                       "delivery_end_difference_orders":delta_delivery,
                       "all_stock_end_difference_orders":delta_stocks,
                       "end_state_parity_is_not_dynamic_equivalence":True})
    return {
        "schema":REPORT_SCHEMA,"condition_id":condition,
        "source_snapshot_hash":visible["source_snapshot_hash"],
        "original_molecule_count":6,
        "balance_operator":"SUM_ALL_TYPED_BOUNDED_QUEUE_WAITING_PLUS_DELIVERED_TOTAL",
        "inTransit_is_not_complete_WIP_across_E1_roles":True,
        "source_graphs":"ORIGINAL_SHORT_E1_BASE_FULL_AST",
        "native_source":"ORIGINAL_E1_COMPOSER_AND_BACKEND_WITH_EXTERNAL_INPUT_ONLY",
        "same_causal_signal_hash_as_D":signal["event_rate_signal_sha256"],
        "signal_units_on_M":"orders/hour; time in hours",
        "input_mass_cutoff_orders_exact":
            signal["mass_before_cutoff_orders_exact"],
        "input_mass_deferred_after_cutoff_orders_exact":
            signal["mass_deferred_after_cutoff_orders_exact"],
        "modelica_sha256":sha_file(root/"native.mo"),
        "script_sha256":sha_file(root/"simulate.mos"),
        "source_original_git_blobs":dict(ORIGINAL_BLOBS),
        "original_fixed_E1_registry_parameters":True,
        "no_empirical_parameter_estimation":True,
        "real_solver_invocation_recorded_by_CI":True,
        "solver_exit_code":0,"candidate_count":6,
        "candidates":audited,
        "material_group_endstate_checks":checks,
        "material_parity_tolerance_orders_predeclared":SIGNAL_GROUP_TOLERANCE_ORDERS,
        "balance_tolerance_orders_predeclared":TOLERANCE_ORDERS,
        "G2":"PASS_REAL_OMC_ENGINEERING_ONLY",
        "G3":"NOT_RUN","G4":"NOT_RUN","G5":"NOT_RUN",
        "A3":"PARTIAL","scientific_adequacy":"NOT_ESTABLISHED",
        "selection_owner":"NONE","provider_calls":0,
        "no_comparison_with_observed_deliveries":True,
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("prepare","verify"))
    p.add_argument("--visible",required=True,type=Path)
    p.add_argument("--condition",required=True,choices=("O0","O1"))
    p.add_argument("--native-dir",required=True,type=Path)
    p.add_argument("--out",type=Path)
    args=p.parse_args()
    view=json.loads(args.visible.read_text(encoding="utf-8"))
    if args.action=="prepare":
        report=prepare(view,args.condition,args.native_dir)
    else:
        need(args.out is not None and not args.out.exists(),
             "RF02M_REPORT_REFUSE_OVERWRITE")
        report=verify(view,args.native_dir)
        args.out.write_bytes(canonical(report)+bytes([10]))
    print(json.dumps({"candidate_count":report["candidate_count"],
                      "G2":report["G2"],"G3":report["G3"],
                      "condition":report["condition_id"]},sort_keys=True))


if __name__=="__main__":
    main()
