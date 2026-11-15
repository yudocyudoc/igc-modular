"""Coffee S5 decision pilot: protect existing support's other work.

This is NOT new sales: it probes whether moving barista handoff work to a
support worker can advance already-paid orders when that worker has other
non-displaceable duties. Exactly same paid demand, barista, equipment and
staff in B0/S5. Source is the authorized CONSTRUCTION producer view from
historical GitHub Arena run 43684660729, not truth or a new synthetic world.
All unobserved availability and timing/cost assumptions remain explicit.
"""
from __future__ import annotations

import argparse
import copy
import csv
import json
import math
from pathlib import Path
import sys

from .common import ArenaError, digest, read_json, write_json
from . import coffee_e2e as e2e
from . import coffee_v2_p11 as p11
from . import coffee_v2_reference as physical
from . import coffee_v2_reference_inputs as inputs
from . import decision_atms as knowledge
from . import decision_atms_gate as gate
from . import coffee_decision_disposition as adjudication
from . import coffee_next_action as actions

SCHEMA = "arena.coffee-v2.s5-support-occupancy/1"
SOURCE_RUN_ID = 43684660729
OCCUPANCY = (0, 50, 100)  # % of peak reserved for other support duties
VALID_MARKERS = ("LOWER_PAID_INPUT_Q25", "HIGHER_PAID_INPUT_Q75")


def need(value, code):
    if not value:
        raise ArenaError("COFFEE_S5_PILOT_"+code)


def assumption_windows(horizon, occupied_percent):
    """Protect other support duties; 50% means first 5 minutes of each 10."""
    physical.num(horizon,"HORIZON",0,180)
    need(horizon>0 and occupied_percent in OCCUPANCY and
         type(occupied_percent) is int, "UNDECLARED_SUPPORT_OCCUPANCY")
    if occupied_percent == 0:
        return []
    if occupied_percent == 100:
        return [(0.0,float(horizon))]
    windows=[]
    for k in range(math.ceil(horizon/10)):
        first=10.0*k
        last=min(first+5.0,float(horizon))
        if first < last:
            windows.append((first,last))
    return physical.support_calendar_gate(windows,horizon)


def fetch_existing_construction_views(out, storage=None):
    """Reuse PREVIOUS run's authorized producer views. Never parse raw ZIP."""
    run_id, commit=e2e.execution_identity()
    need(run_id != SOURCE_RUN_ID,"DO_NOT_REPLACE_SOURCE_RUN")
    storage=storage or e2e.private_storage()
    out=Path(out)
    need(not out.exists(),"VIEWS_OVERWRITE")
    out.mkdir(parents=True,exist_ok=False,mode=0o700)
    for name in sorted(e2e.VIEW_FILES):
        storage.get(e2e.private_run_prefix(SOURCE_RUN_ID)+"views/"+name,
                    out/name)
    selection=p11._verified_load_choices(out)
    return {
        "status":"EXISTING_CONSTRUCTION_VIEWS_VERIFIED_NO_NEW_CORPUS",
        "read_only_source_run_id":SOURCE_RUN_ID,
        "current_github_run_id":run_id,
        "current_code_sha":commit,
        "eligible_days":selection["eligible_nonzero_construction_days"],
        "provider_posts":0,"new_omc":0,"new_worlds":0,
    }


def compare(view_dir, dossier, protocol):
    physical.config_gate(dossier)
    p11.protocol_gate(protocol)
    need(dossier["policy"]=="B0","NOMINAL_DOSSIER_B0_ONLY")
    pre=knowledge.scenario_predecision(
        dossier,protocol,recorded_at=knowledge.utc_now())
    decision=gate.gate(pre,dossier,protocol)
    gate.require_executable(decision)
    choice=p11._verified_load_choices(view_dir)
    cases, economic=[],[]
    for selected in choice["selected"]:
        need(selected["load_label"] in VALID_MARKERS,
             "NOT_PREDECLARED_INPUT_SELECTION")
        safe=inputs.select_case_day(
            view_dir,selected["case_id"],selected["day"])
        need(safe["partition"]=="CONSTRUCTION",
             "NONCONSTRUCTION_SOURCE_REJECTED")
        for occupied in OCCUPANCY:
            reservations=assumption_windows(safe["horizon"],occupied)
            intervention=copy.deepcopy(dossier)
            intervention["policy"]=physical.S5
            physical.counterfactual_pair_gate(dossier,intervention)
            b0=physical.simulate(
                safe["positions"],safe["items"],dossier,safe["horizon"],
                support_busy_windows=reservations)
            s5=physical.simulate(
                safe["positions"],safe["items"],intervention,safe["horizon"],
                support_busy_windows=reservations)
            need(b0["synthetic_paid_orders"] == s5["synthetic_paid_orders"]
                 and b0["synthetic_beverage_units"] ==
                 s5["synthetic_beverage_units"] and
                 b0["synthetic_paid_orders"] ==
                 b0["modeled_handoffs_during_halfopen_peak"] +
                 b0["modeled_orders_open_at_peak_cut"] and
                 s5["synthetic_paid_orders"] ==
                 s5["modeled_handoffs_during_halfopen_peak"] +
                 s5["modeled_orders_open_at_peak_cut"],
                 "PAID_MASS_OR_PEAK_BALANCE")
            b0_peak=b0["modeled_handoffs_during_halfopen_peak"]
            s5_peak=s5["modeled_handoffs_during_halfopen_peak"]
            delta=s5_peak-b0_peak
            need(b0["resources"]["existing_support"][
                    "busy_unit_minutes_full_drain"] == 0,
                 "B0_STILL_USING_SUPPORT")
            need(abs(
                 b0["resources"]["barista"]["busy_unit_minutes_full_drain"]-
                 s5["resources"]["barista"]["busy_unit_minutes_full_drain"]-
                 s5["resources"]["existing_support"][
                     "busy_unit_minutes_full_drain"]) < 1e-6,
                 "TRANSFERRED_WORK_NOT_CONSERVED")
            reserved_minutes = round(sum(b-a for a,b in reservations),10)
            receipt={
                "load_label":selected["load_label"],
                "support_other_duties_reserved_pct_assumed":occupied,
                "support_available_pct_assumed":100-occupied,
                "existing_support_busy_minutes_reserved_in_peak_assumed":
                    reserved_minutes,
                "synthetic_paid_orders":b0["synthetic_paid_orders"],
                "synthetic_beverage_units":b0["synthetic_beverage_units"],
                "B0_handoffs_in_peak":b0_peak,
                "S5_handoffs_in_peak":s5_peak,
                "delta_S5_minus_B0_handoffs_in_peak":delta,
                "B0_pending_at_peak_cut":b0["modeled_orders_open_at_peak_cut"],
                "S5_pending_at_peak_cut":s5["modeled_orders_open_at_peak_cut"],
                "B0_p90_full_drain_min":
                    b0["modeled_paid_to_handoff_p90_full_drain_min"],
                "S5_p90_full_drain_min":
                    s5["modeled_paid_to_handoff_p90_full_drain_min"],
                "delta_S5_minus_B0_p90_min":round(
                    s5["modeled_paid_to_handoff_p90_full_drain_min"]-
                    b0["modeled_paid_to_handoff_p90_full_drain_min"],10),
                "support_handoff_minutes_if_S5":
                    s5["resources"]["existing_support"][
                        "busy_unit_minutes_full_drain"],
                "model_service_signal":(
                    "S5_ADVANCES_PEAK_HANDOFFS" if delta>0 else
                    "S5_LOSES_PEAK_HANDOFFS" if delta<0 else
                    "NO_CHANGE_IN_PEAK_HANDOFF_COUNT"),
            }
            cases.append(receipt)
            values=protocol["illustrative_economics"]
            for cost in values[
                    "incremental_support_opportunity_cost_mxn_per_peak"]:
                for benefit in values[
                        "assumed_value_mxn_per_additional_handoff_inside_peak"]:
                    net=round(delta*benefit-cost,10)
                    economic.append({
                        "load_label":selected["load_label"],
                        "support_available_pct_assumed":100-occupied,
                        "delta_earlier_handoffs_not_new_sales":delta,
                        "assumed_cost_of_reassignment_mxn":cost,
                        "assumed_timing_value_mxn_per_handoff":benefit,
                        "net_illustrative_timing_value_mxn":net,
                        "comparison_only":(
                            "S5_IF_ASSUMPTIONS" if net>0 else
                            "B0_IF_ASSUMPTIONS" if net<0 else
                            "TIE_IF_ASSUMPTIONS"),
                        "break_even_value_mxn_per_handoff_if_delta_positive":
                            round(cost/delta,10) if delta>0 else None,
                    })
    need(len(cases)==6 and len(economic)==54,
         "PILOT_FIXED_DESIGN_CHANGED")
    for marker in VALID_MARKERS:
        matching=[x for x in cases if x["load_label"]==marker]
        need(len(matching)==3 and
             len(set(x["synthetic_paid_orders"] for x in matching))==1 and
             len(set(x["B0_handoffs_in_peak"] for x in matching))==1,
             "B0_NOT_CONTROLLED_FOR_SUPPORT_CALENDAR")
    positives={
        marker:sorted(x["support_available_pct_assumed"]
                      for x in cases if x["load_label"]==marker
                      and x["delta_S5_minus_B0_handoffs_in_peak"]>0)
        for marker in VALID_MARKERS
    }
    result={
        "schema":SCHEMA,
        "status":"FIRST_ACTIONABLE_SUPPORT_AVAILABILITY_TEST_CONDITIONAL",
        "source_kind":"EXISTING_GITHUB_SYNTHETIC_CONSTRUCTION_PRODUCER_VIEWS",
        "source_run_id":SOURCE_RUN_ID,
        "atms_execution_gate_sha256":decision["gate_sha256"],
        "dossier_sha256":digest(dossier),
        "protocol_sha256":digest(protocol),
        "source_view_manifest_sha256":safe["manifest_sha256"],
        "selection": {
            "rule":p11.SELECTION,
            "load_labels":list(VALID_MARKERS),
            "no_empirical_saturation_claim":True,
        },
        "comparison_rows":cases,
        "economic_rows":economic,
        "decision_readout":{
            "question":"Does existing support have sufficient free windows to improve peak handoffs without displacing its duties?",
            "first_positive_tested_free_pct_by_load":{
                marker:(values[0] if values else None)
                for marker,values in positives.items()
            },
            "only_grid_points_tested_pct":[0,50,100],
            "not_continuous_threshold_estimation":True,
            "first_real_measurement":"Observe existing support worker availability windows and overlapping duties during comparable peaks",
            "second_real_measurement":"Time manual setup and pickup handoffs with observed parallelism",
            "economic_measurement":"Value of delivery timing and actual cost of displaced tasks",
            "current_business_choice":"MEASURE_FIRST_NOT_REAL_REASSIGNMENT_RECOMMENDATION",
            "do_not_count_earlier_handoffs_as_new_orders":True,
            "no_supplier_cost_or_margin_identified":True,
        },
        "external_consumption":{"provider_POST":0,"new_OMC":0,
                                "new_synthetic_worlds":0,"G3":0},
    }
    # This is a new post-comparison ATMS *decision*, not the old static
    # MEASURE_FIRST string. All six contexts must be present or it fails.
    final = adjudication.disposition(pre, decision, cases)
    result["atms_predecision"] = pre
    result["atms_execution_receipt"] = decision
    result["atms_disposition"] = final
    result["decision_readout"]["current_business_choice"] = final[
        "business_choice"]
    result["next_action"] = actions.compare(
        view_dir, dossier, selection=choice)
    return result


def export(result,out):
    out=Path(out)
    need(not out.exists(),"RESULT_OVERWRITE")
    out.mkdir(parents=True,exist_ok=False,mode=0o700)
    for name,rows in (
        ("support-availability-service.csv",result["comparison_rows"]),
        ("support-availability-economics.csv",result["economic_rows"])):
        with (out/name).open("x",encoding="utf-8",newline="") as f:
            writer=csv.DictWriter(f,fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    # Full ATMS proof travels separately, concise disposition in decision.json.
    proof=result["atms_disposition"]
    gate_receipt=result["atms_execution_receipt"]
    pre=result["atms_predecision"]
    need(proof["execution_gate_sha256"]==gate_receipt["gate_sha256"]
         and proof["predecision_snapshot_sha256"]==
         pre["snapshot"]["snapshot_sha256"],
         "ATMS_CHAIN_MISMATCH_BEFORE_EXPORT")
    public={key:value for key,value in result.items()
            if key not in ("comparison_rows","economic_rows",
                           "atms_predecision","atms_execution_receipt",
                           "atms_disposition")}
    public["atms"]={
        "execution_gate_sha256":gate_receipt["gate_sha256"],
        "predecision_snapshot_sha256":pre["snapshot"]["snapshot_sha256"],
        "disposition_sha256":proof["disposition_sha256"],
        "admitted_under_assumptions":gate_receipt["status"],
        "post_comparison_claims":proof["claims"],
        "business_choice":proof["business_choice"],
        "no_real_profit_claim":True,
    }
    write_json(out/"decision.json",public,exclusive=True)
    write_json(out/"ATMS_PREDECISION.json",pre,exclusive=True)
    write_json(out/"ATMS_GATE.json",gate_receipt,exclusive=True)
    write_json(out/"ATMS_DISPOSITION.json",proof,exclusive=True)
    write_json(out/"NEXT_ACTION.json",result["next_action"],exclusive=True)
    with (out/"next-action-service.csv").open(
            "x",encoding="utf-8",newline="") as f:
        rows=result["next_action"]["rows"]
        writer=csv.DictWriter(f,fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    lines=[
        "# ¿Cuándo conviene reasignar la entrega al apoyo?",
        "",
        "**Sólo simulación condicional, no ventas nuevas ni utilidad real.**",
        "Mismos pedidos sintéticos pagados y mismos recursos B0/S5;",
        "S5 respeta las otras tareas del apoyo, que no se desplazan.",
        "",
        "| Carga de pagos | Apoyo disponible (supuesto) | B0 handoffs | S5 handoffs | Diferencia | P90 drenaje B0/S5 |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for r in result["comparison_rows"]:
        lines.append(
            f"| {r['load_label']} | {r['support_available_pct_assumed']}% | "
            f"{r['B0_handoffs_in_peak']} | {r['S5_handoffs_in_peak']} | "
            f"{r['delta_S5_minus_B0_handoffs_in_peak']:+d} | "
            f"{r['B0_p90_full_drain_min']:.2f} / "
            f"{r['S5_p90_full_drain_min']:.2f} min |"
        )
    lines += [
        "",
        "## ATMS: premisas, interpretación y disposición",
        "",
        "| Compuerta | Evidencia / supuesto | Resultado |",
        "|---|---|---|",
        "| Antes de simular | "
        "P07/P11 construcción; soporte y traspaso ASSUMED | "+
        gate_receipt["status"]+" |",
        "| Cobertura de resultados | 2 cargas × 3 disponibilidades, "
        "sin elegir sólo 100% | "
        "COMPLETE_SIX_CONTEXT_GRID |",
        "| Mejoría general del servicio | No empeorar entregas ni P90 "
        "en ninguna condición y mejorar al menos una | "+
        ("CON_SOPORTE" if proof["claims"][
            adjudication.BROAD]["supported"] else
         "SIN_SOPORTE_ATMS") + " |",
        "| Efecto puntual P90 | Sólo en determinados escenarios "
        "sintéticos | "+
        ("CON_SOPORTE_CONDICIONAL" if proof["claims"][
            adjudication.P90_SOME]["supported"] else
         "SIN_SOPORTE") + " |",
        "| Ganancia económica real | Disponibilidad, costes y valor "
        "no medidos | SIN_SOPORTE |",
        "",
        "**Decisión derivada:** "+proof["business_choice"]+".",
        "**Generalización selectiva probada:** "+
        proof["prevented_claim_example"]["classification"]+".",
        "La heurística insegura tomaría únicamente el mejor P90 y "
        "aprobaría S5 para todas las condiciones; el soporte ATMS "
        "exige toda la grilla.",
        "Cadena temporal replayable: "+
        proof["cuts"]["predecision_T"]+" → "+
        proof["cuts"]["evidence_T_plus_microseconds"]+" → "+
        proof["cuts"]["disposition_T_plus_microseconds"]+".",
        "Premisas, eventos, respaldos y SHA se publican junto "
        "a la tabla en ATMS_GATE.json y ATMS_DISPOSITION.json.",
        "",
        "## Próxima decisión: preparación manual vs capacidad de máquina",
        "",
        "| Carga | Intervención física asumida | Entregas B0 → acción "
        "| Cambio de P90 (min) |",
        "|---|---|---|---:|",
    ]
    for r in result["next_action"]["rows"]:
        lines.append(
            "| "+r["load_label"]+" | "+r["assumed_change"]+" | "+
            str(r["B0_peak_handoffs"])+" → "+
            str(r["intervention_peak_handoffs"])+" | "+
            f'{r["delta_p90_min"]:+.2f}'+" |")
    lines += [
        "",
        "Acciones que merecen MEDIR costes y factibilidad (no comprar aún): "+
        (", ".join(result["next_action"]["priority_to_measure"])
         or "ninguna con más entregas en los casos probados")+".",
        "Reducir tiempo manual al límite declarado no es gratis ni "
        "un rendimiento medido; una máquina adicional exige "
        "espacio, energía y trabajo de barista.",
        "",
        "## Decisión práctica pendiente",
        "",
        "Medir 1) ventanas de disponibilidad real del apoyo,",
        "2) duración manual y handoff, 3) coste real de mover tareas.",
        "La tabla muestra sólo tres niveles ilustrativos de disponibilidad:",
        "no establece un umbral continuo ni identifica el margen del negocio.",
        "Más handoffs dentro del pico pueden ser entregas ADELANTADAS,",
        "no nuevos pedidos pagados ni ingresos adicionales.",
        "",
        "Fuente: vistas autorizadas CONSTRUCTION del run GitHub #" +
        str(SOURCE_RUN_ID) + "; nada de EVALUATION, ZIP o truth.",
        "Costo de proveedor, OMC, mundos nuevos y G3: cero.",
    ]
    (out/"DECISION.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    write_json(out/"receipt.json",{
        "schema":SCHEMA,
        "source_run_id":SOURCE_RUN_ID,
        "result_digest_sha256":digest(public),
        "atms_execution_gate_sha256":result["atms_execution_gate_sha256"],
        "no_reserved_truth":True,
        "outputs": {p.name: "sha256:"+inputs.sha_file(p)
                    for p in sorted(out.iterdir()) if p.name!="receipt.json"},
    },exclusive=True)


def main(argv=None):
    parser=argparse.ArgumentParser(description="GitHub-only S5 staff availability business decision pilot")
    subs=parser.add_subparsers(dest="command",required=True)
    a=subs.add_parser("fetch-views")
    a.add_argument("--out",required=True)
    a=subs.add_parser("compare")
    a.add_argument("--views",required=True)
    a.add_argument("--out",required=True)
    args=parser.parse_args(argv)
    try:
        if args.command=="fetch-views":
            print(json.dumps(fetch_existing_construction_views(args.out),
                             sort_keys=True))
        else:
            root=Path(__file__).resolve().parents[1]
            dossier=read_json(root/"experiments/coffee_v2/EXAMPLE_REFERENCE_DOSSIER_ASSUMPTIONS_ONLY.json")
            protocol=read_json(root/"experiments/coffee_v2/P11_INITIAL_CONDITIONAL_PROTOCOL_V1.json")
            result=compare(args.views,dossier,protocol)
            export(result,args.out)
            print(json.dumps({"status":result["status"],
                "service_pairs":len(result["comparison_rows"]),
                "real_business_recommendation":False},sort_keys=True))
        return 0
    except (ArenaError,OSError,ValueError,KeyError,TypeError,
            json.JSONDecodeError) as exc:
        print(json.dumps({"status":"STOPPED","reason":str(exc)
              if isinstance(exc,ArenaError) else "INVALID_SOURCE_OR_CONFIG"}),
              file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
