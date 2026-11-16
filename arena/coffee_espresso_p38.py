"""PR38: why a second espresso group helps reference but not aggregate M?

Fixed previously published CONSTRUCTION loads. Replay ONLY B0 versus +1
espresso group in the deterministic physical reference, with opt-in stage
queue diagnostics. Read original native M CSV and result.json; no new OMC.
The two models have DIFFERENT input profiles/units, so this diagnoses
their own mechanisms, not a physical causal reconciliation.
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

from .common import ArenaError, digest, read_json, write_json
from .coffee_adapters.shared import sha_bytes
from . import coffee_m_p08 as m
from . import coffee_next_action as actions
from . import coffee_v2_p11 as p11
from . import coffee_v2_reference as reference
from . import coffee_v2_reference_inputs as views

SCHEMA="arena.coffee.p38.espresso-mechanism/1"
QUESTION="WHY_ESPRESSO_GROUP_HELPS_REFERENCE_BUT_NOT_AGGREGATE_M"
ACTION="ONE_ADDITIONAL_ESPRESSO_GROUP"
LOADS=m.INPUT_LABELS


def need(ok,code):
    if not ok:
        raise ArenaError("COFFEE_P38_ESPRESSO_"+code)


def native_m_stage_diagnostic(root,load,paid):
    """Use authenticated prior M CSV, no reinterpretation as discrete orders."""
    manifest=read_json(Path(root)/"manifest.json")
    results=read_json(Path(root)/"result.json")
    need(manifest.get("schema")==m.SCHEMA and
         results.get("schema")==m.SCHEMA and
         results.get("status")=="NATIVE_M_P08_SIX_SIMS_SUCCEEDED" and
         results.get("new_omc_attempted")==6 and
         results.get("failed_models")==[],"M_PRIOR_RUN_NOT_AUTHENTIC")
    records=manifest.get("models",[])
    need(type(records) is list and len(records)==6,"M_MANIFEST_NOT_SIX_MODELS")
    subset=[r for r in records if r.get("load_label")==load]
    need(len(subset)==3 and
         {r["variant"] for r in subset}==set(m.VARIANTS),
         "M_PAIRS_MISSING")
    base=next(r for r in subset if r["variant"]=="BASE")
    extra=next(r for r in subset if r["variant"]=="ESPRESSO_CAPACITY_X2")
    need(base.get("input_paid_orders")==extra.get("input_paid_orders")==paid
         and base["model_parameter_changes"]=={
             "preparation_max_throughput_orders_per_hour":12,
             "espresso_stage_max_throughput_orders_per_hour":15,
             "dispatch_max_throughput_orders_per_hour":100}
         and extra["model_parameter_changes"]=={
             "preparation_max_throughput_orders_per_hour":12,
             "espresso_stage_max_throughput_orders_per_hour":30,
             "dispatch_max_throughput_orders_per_hour":100},
         "M_NOT_SAME_INPUT_OR_STAGE_PARAMETER")
    source=Path(root)/base["csv"]
    checked=m.audit_csv(source,base)
    with source.open(encoding="utf-8",newline="") as stream:
        reader=csv.DictReader(stream)
        need({"espresso0.waiting","preparation0.waiting","time"}.issubset(
             set(reader.fieldnames or [])),
             "M_NATIVE_ESPRESSO_STOCK_COLUMN_MISSING")
        rows=[(float(x["time"]),float(x["espresso0.waiting"]),
               float(x["preparation0.waiting"])) for x in reader]
    considered=[(espresso,prep) for t,espresso,prep in rows if
                0 <= t <= m.INPUT_HORIZON_MIN/60+1e-7]
    need(len(considered)>100 and
         min(min(v) for v in considered)>=-0.001 and all(
             all(z < 100000 for z in v) for v in considered),
         "M_ESPRESSO_STOCK_NOT_PHYSICAL")
    response=m.ROLE_ASSUMPTIONS["espresso"]["responseTime"]
    cap=m.ROLE_ASSUMPTIONS["espresso"]["maxThroughput"]
    theoretical_uncapped=max(x[0] for x in considered)/response
    preparation_uncapped=max(x[1] for x in considered)/(
        m.ROLE_ASSUMPTIONS["preparation"]["responseTime"])
    epsilon=0.001
    # The native model saturates when its stock/responseTime >= maxThroughput.
    # Here that is 1.5 abstract orders queued at espresso, NOT a physical
    # number of drinks waiting for an espresso machine.
    aggregate_capacity_binding=theoretical_uncapped>=cap-epsilon
    comparisons=[r for r in results.get("pairwise_comparisons",[]) if
                 r.get("load_label")==load and
                 r.get("variant")=="ESPRESSO_CAPACITY_X2"]
    need(len(comparisons)==1 and
         comparisons[0]["B0_paid_orders_from_existing_artifact"]==paid and
         abs(comparisons[0]["native_M_B0_continuous_handoffs_at_cut"]-
             checked["modeled_delivered_continuous_at_cut"])<1e-5,
         "M_PREVIOUS_CSV_AND_RESULT_DIFFER")
    delta=comparisons[0]["delta_continuous_handoffs_at_cut"]
    return {
        "paid_count_unchanged":paid,
        "M_B0_continuous_delivered_at_cut":
            comparisons[0]["native_M_B0_continuous_handoffs_at_cut"],
        "M_espresso_x2_delta_continuous_at_cut":delta,
        "M_preparation_limit_assumed_orders_per_hour":12,
        "M_espresso_limit_assumed_orders_per_hour":15,
        "M_stage_max_stock_abstract_orders":round(
            max(x[0] for x in considered),8),
        "M_max_uncapped_preparation_release_per_hour":round(
            preparation_uncapped,8),
        "M_preparation_capacity_binding_in_sample":
            preparation_uncapped >=
            m.ROLE_ASSUMPTIONS["preparation"]["maxThroughput"]-epsilon,
        "M_max_uncapped_espresso_release_per_hour":round(
            theoretical_uncapped,8),
        "M_espresso_capacity_bound_active_in_sample":aggregate_capacity_binding,
        "M_espresso_stage_cap_not_hit":not aggregate_capacity_binding,
        "M_method":"GENERIC_ORDER_STOCK_NOT_MACHINE_RESOURCE_OR_BEVERAGE",
        "no_p90_per_paid_order":True,
        "native_csv_read_only_reused":True,
    }


def compare(view_dir,source_path,mroot,dossier):
    source_path=Path(source_path)
    source=read_json(source_path)
    receipt=read_json(source_path.parent/"receipt.json")
    need(receipt.get("outputs",{}).get("NEXT_ACTION.json")==
         sha_bytes(source_path.read_bytes()),
         "SOURCE_DIGEST_NOT_MATCHING_PRIOR_RECEIPT")
    counts=m.input_cases(source,receipt)
    reference.config_gate(dossier)
    need(dossier["policy"]=="B0" and
         digest(dossier)==source["dossier_sha256"],
         "REFERENCE_ASSUMPTIONS_CHANGED")
    selection=p11._verified_load_choices(view_dir)
    need(len(selection["selected"])==2 and
         {row["load_label"] for row in selection["selected"]}==set(LOADS),
         "CONSTRUCTION_LOADS_CHANGED")
    results=[]
    for item in selection["selected"]:
        label=item["load_label"]
        safe=views.select_case_day(
            view_dir,item["case_id"],item["day"])
        need(safe["partition"]=="CONSTRUCTION","NOT_CONSTRUCTION")
        alternative=actions._candidate(dossier,ACTION)
        base,_,_=reference._engine(
            safe["positions"],safe["items"],dossier,safe["horizon"],
            diagnose_stage_waits=True)
        changed,_,_=reference._engine(
            safe["positions"],safe["items"],alternative,safe["horizon"],
            diagnose_stage_waits=True)
        need(base["synthetic_paid_orders"]==changed["synthetic_paid_orders"]==
             counts[label] and
             base["synthetic_beverage_units"]==
             changed["synthetic_beverage_units"],
             "PAID_ORDERS_OR_RECIPES_NOT_FIXED")
        expected_b=[r for r in source["baseline"] if
                    r["load_label"]==label]
        expected_a=[r for r in source["rows"] if
                    r["load_label"]==label and r["mechanism"]==ACTION]
        need(len(expected_b)==len(expected_a)==1,
             "PUBLISHED_BASELINE_OR_ACTION_MISSING")
        b,a=expected_b[0],expected_a[0]
        need(base["modeled_handoffs_during_halfopen_peak"]==
             b["B0_peak_handoffs"]==a["B0_peak_handoffs"] and
             changed["modeled_handoffs_during_halfopen_peak"]==
             a["intervention_peak_handoffs"] and
             abs(base["modeled_paid_to_handoff_p90_full_drain_min"]-
                 b["B0_p90_full_drain_min"])<1e-6 and
             abs(changed["modeled_paid_to_handoff_p90_full_drain_min"]-
                 a["intervention_p90_min"])<1e-6,
             "NEW_TRACE_CHANGED_PUBLISHED_REFERENCE_RESULTS")
        diag0=base["mechanism_diagnostics"]
        diag1=changed["mechanism_diagnostics"]
        agg=native_m_stage_diagnostic(mroot,label,counts[label])
        p90gain=(changed["modeled_paid_to_handoff_p90_full_drain_min"] <
                 base["modeled_paid_to_handoff_p90_full_drain_min"]-1e-6)
        # Two model-local hypotheses. Do not claim they settle the cross-model
        # difference, because arrivals, recipes and units differ.
        conditions={
            "H_AGGREGATE_ESPRESSO_CAPACITY_NOT_BINDING":{
                "support":bool(agg["M_espresso_stage_cap_not_hit"] and
                              abs(agg["M_espresso_x2_delta_continuous_at_cut"])<1e-6),
                "test":"M espresso native stock/responseTime remains below 15/h; "
                       "doubling its cap changes no deliveries",
            },
            "H_AGGREGATE_PREPARATION_CAPACITY_BINDING":{
                "support":bool(agg.get(
                    "M_preparation_capacity_binding_in_sample",False)),
                "test":"M native preparation stock/responseTime reaches 12/h "
                       "within the 105-min pulse (not inferred from espresso alone)",
            },
            "H_REFERENCE_ESPRESSO_RESOURCE_CONGESTION":{
                "support":bool(diag0["espresso_tasks_blocked_by_group_count"]>0
                               and diag0["espresso_auto_queued_minutes_before_cut"]>0
                               and diag1["espresso_auto_queued_minutes_before_cut"] <
                               diag0["espresso_auto_queued_minutes_before_cut"]-1e-6
                               and p90gain),
                "test":"A second group reduces ready-task waiting for occupied "
                       "espresso resources and reduces modeled P90",
            },
            "H_CROSS_MODEL_DISAGREEMENT_EXPLAINED_ENTIRELY":{
                "support":False,
                "test":"NOT TESTED: align temporal POS profile, order/beverage "
                       "unit and same intervention semantics",
            },
        }
        results.append({
            "load_label":label,
            "paid_orders":counts[label],
            "beverage_units_reference":base["synthetic_beverage_units"],
            "reference_B0_peak_handoffs":
                base["modeled_handoffs_during_halfopen_peak"],
            "reference_plus_group_peak_handoffs":
                changed["modeled_handoffs_during_halfopen_peak"],
            "reference_p90_B0_min":
                base["modeled_paid_to_handoff_p90_full_drain_min"],
            "reference_p90_plus_group_min":
                changed["modeled_paid_to_handoff_p90_full_drain_min"],
            "reference_B0_stage":diag0,
            "reference_plus_group_stage":diag1,
            "aggregate_M_stage":agg,
            "hypotheses":conditions,
            "not_independent_validation_or_revenue":True,
        })
    need(len(results)==2,"TWO_DIAGNOSTIC_CASES_REQUIRED")
    return {
        "schema":SCHEMA,
        "status":"MODEL_LOCAL_ESPRESSO_DIAGNOSTIC_NOT_PHYSICAL_VALIDATION",
        "question":QUESTION,
        "cases":results,
        "physical_reference_uses_discrete_recipes_events_and_shared_barista":True,
        "M_uses_flattened_105_min_paid_order_pulse":True,
        "D_equivalent_to_M_in_this_P08_configuration":True,
        "remaining_unresolved": [
            "INPUT_TEMPORAL_ALIGNMENT",
            "ORDER_VERSUS_BEVERAGE_WORK_UNIT",
            "ESPRESSO_GROUP_PLUS_ONE_VERSUS_AGGREGATE_CAPACITY_X2",
            "PARAMETER_CALIBRATION",
        ],
        "decision":"DO_NOT_BUY_MACHINE_FROM_SYNTHETIC_DIAGNOSTIC",
        "suggested_next_experiment":"ALIGN_ONE_FACTOR_AT_A_TIME_ONLY_IF_CROSS_MODEL_EXPLANATION_NEEDED",
        "source_github_runs":{"reference":43697007653,"M":43702148041},
        "new_omc":0,"provider_posts":0,"new_worlds":0,"reserved_truth_read":False,
    }


def export(result,out):
    out=Path(out)
    need(not out.exists(),"RESULT_ALREADY_EXISTS")
    out.mkdir(parents=True,exist_ok=False)
    write_json(out/"mechanism.json",result,exclusive=True)
    lines=[
        "# PR38 — ¿Por qué espresso ayuda en referencia y no en M/D?",
        "",
        "Pregunta estrecha; dos días sintéticos CONSTRUCTION, mismos pagos/recetas",
        "entre B0 y espresso +1 de la referencia. M usa CSV ORIGINAL sin OMC.",
        "",
        "| Carga | Ref espresso bloqueadas B0 → +1 | Ref espera espresso antes del corte (min) B0 → +1 | Ref P90 B0 → +1 | M máximo flujo espresso sin tope (h⁻¹) / límite (h⁻¹) |",
        "|---|---:|---:|---:|---:|",
    ]
    for r in result["cases"]:
        b=r["reference_B0_stage"]
        a=r["reference_plus_group_stage"]
        M=r["aggregate_M_stage"]
        lines.append(
            f"| {r['load_label']} | "
            f"{b['espresso_tasks_blocked_by_group_count']} → "
            f"{a['espresso_tasks_blocked_by_group_count']} | "
            f"{b['espresso_auto_queued_minutes_before_cut']:.3f} → "
            f"{a['espresso_auto_queued_minutes_before_cut']:.3f} | "
            f"{r['reference_p90_B0_min']:.3f} → "
            f"{r['reference_p90_plus_group_min']:.3f} | "
            f"{M['M_max_uncapped_espresso_release_per_hour']:.3f} / "
            f"{M['M_espresso_limit_assumed_orders_per_hour']} |")
    lines += ["","## Hipótesis comprobadas dentro de cada simulador"]
    for r in result["cases"]:
        lines.append("### "+r["load_label"])
        for name,data in r["hypotheses"].items():
            lines.append("- "+name+": "+
                         ("SUPPORTED_IN_THIS_MODEL_AND_LOAD" if data["support"]
                          else "NOT_SUPPORTED_OR_NOT_TESTED")+
                         " — "+data["test"])
    lines += [
        "",
        "**Diagnóstico, no validación física:** la referencia modela recursos",
        "y tareas de bebida discretos; M considera pedidos agregados con",
        "una tasa rectangular. D no aporta una segunda dinámica independiente.",
        "Una diferencia de signo en entregas no equivale a ausencia de",
        "mejora de P90 cuando la métrica individual no existe en M.",
        "",
        "**Pregunta todavía abierta:** qué porcentaje del desacuerdo se",
        "explica sólo por entradas, unidades e intervenciones no equivalentes.",
        "No simular más mundos ni comprar máquina; si hace falta reconciliar",
        "las representaciones, alinear un factor por experimento.",
        "",
        "Cálculo: sólo GitHub Actions; OMC 0, POST 0, nuevos mundos 0.",
    ]
    (out/"DECISION.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    # Writing UTF-8 report files remains lossless; Windows cp1252 CI
    # consoles cannot encode the Delta/arrow characters used in tables.
    import sys
    report="\n".join(lines)
    encoding=sys.stdout.encoding or "utf-8"
    print(report.encode(encoding,errors="backslashreplace").decode(encoding))


def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("--views",required=True)
    p.add_argument("--reference",required=True)
    p.add_argument("--native-M",required=True)
    p.add_argument("--dossier",required=True)
    p.add_argument("--out",required=True)
    args=p.parse_args(argv)
    export(compare(args.views,args.reference,args.native_M,
                   read_json(args.dossier)),args.out)


if __name__=="__main__":
    main()
