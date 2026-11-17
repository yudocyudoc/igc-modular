"""P42: inspect authenticated P39 results, without R2/video/solver access.

Make deductions from explicitly assumed scheduler parameters; never convert
timer pairs into observed complete extractions. No new model worlds.
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path

from .common import ArenaError, read_json, write_json
from . import coffee_hydra_p39 as p39
from . import coffee_hydra_timers_p39 as timers
from . import coffee_v2_reference as reference

SCHEMA="arena.coffee.p42.structural-review/1"
SOURCE_RUN=43965403016
SOURCE_ARTIFACT_ID=14275986824
REVIEW_IDS=("TM-T31","TM-T33","TM-T12")


def need(ok,code):
    if not ok:
        raise ArenaError("COFFEE_P42_"+code)


def analyze(data,dossier):
    need(data.get("schema")==p39.SCHEMA and
         data.get("status")=="THREE_GROUP_HYDRA_SCENARIO_CONDITIONAL_NOT_CALIBRATED",
         "AUTHENTIC_P39_SCHEMA")
    machine=data.get("machine_evidence_consumer",{})
    need(machine.get("timer_pairs")==37 and
         machine.get("group_presence_counts")==timers.EXPECTED and
         machine.get("identifiable_complete_auto_extraction_cycles")==0 and
         data.get("timer_pairs_used_to_calibrate_auto_time")==0 and
         data.get("manual_load_remove_clean_explicitly_modeled") is False and
         data.get("simultaneous_availability_observed") is False and
         data.get("no_real_business_capacity_or_roi_inferred") is True,
         "OBSERVATION_UNCERTAINTY_LOST")
    reference.config_gate(dossier)
    setup=dossier["durations"]["manual_setup_min"]["value"]
    extraction=dossier["durations"]["espresso_auto_min"]["value"]
    need(dossier["policy"]=="B0" and
         dossier["resources"]["barista"]["units"]==1 and
         dossier["resources"]["espresso_group"]["units"]==1 and
         setup==0.5 and extraction==1.5 and
         data["automatic_extraction_time_minutes_used"]==extraction,
         "HISTORICAL_90_30_NOT_VERIFIED")
    enough=math.ceil(extraction/setup-1e-10)
    need(enough==3,"STRUCTURAL_RATIO_CHANGED")
    cases=data.get("scenarios")
    need(type(cases) is list and len(cases)==2 and
         {r.get("load_label") for r in cases}==set(p39.SELECTED),
         "ORIGINAL_TWO_LOADS_MISSING")
    outputs=[]
    for row in sorted(cases,key=lambda r:p39.SELECTED.index(r["load_label"])):
        pairs=row.get("comparison")
        need(type(pairs) is list and len(pairs)==2,"ORIGINAL_ARMS_MISSING")
        a,b=pairs
        need(a.get("case")=="HISTORICAL_ONE_ENABLED" and
             b.get("case")=="HYDRA_THREE_ENABLED_ASSUMED" and
             a.get("assumed_enabled_group_count")==1 and
             b.get("assumed_enabled_group_count")==3 and
             a.get("assumed_automatic_extraction_min")==extraction and
             b.get("assumed_automatic_extraction_min")==extraction and
             a.get("paid_orders")==b.get("paid_orders") and
             a.get("beverage_units")==b.get("beverage_units") and
             row.get("same_paid_orders_and_beverage_mix") is True and
             row.get("change_only_one_to_three_assumed_enabled_groups") is True,
             "ARMS_NOT_ONE_FACTOR")
        d0,d3=a["diagnostics"],b["diagnostics"]
        required=("espresso_tasks_blocked_by_group_count",
                  "espresso_auto_queued_minutes_before_cut",
                  "espresso_group_busy_unit_minutes_before_cut",
                  "espresso_group_busy_fraction_of_capacity_before_cut",
                  "manual_setup_queued_minutes_before_cut",
                  "milk_finish_queued_minutes_before_cut",
                  "handoff_queued_minutes_before_cut")
        for diag,groups in ((d0,1),(d3,3)):
            need(diag.get("schema")=="arena.coffee-v2.stage-wait-diagnostic/1" and
                 diag.get("espresso_group_assumed_units")==groups and
                 diag.get("diagnostic_does_not_modify_scheduling") is True and
                 all(type(diag.get(k)) in (int,float) and
                     math.isfinite(diag[k]) and diag[k]>=0 for k in required),
                 "ORIGINAL_STAGE_METRICS_UNTRUSTED")
        need(d3["espresso_tasks_blocked_by_group_count"]==0 and
             d3["espresso_auto_queued_minutes_before_cut"]==0,
             "CLAIMED_ZERO_ESPRESSO_QUEUE_UNTRUE")
        need(abs(d3["espresso_group_busy_unit_minutes_before_cut"]-
                 d0["espresso_group_busy_unit_minutes_before_cut"])<1e-6 and
             abs(d3["espresso_group_busy_unit_minutes_before_cut"]-
                 extraction*b["beverage_units"])<1e-6,
             "BUSY_MINUTES_CONSERVATION")
        need(abs(d3["espresso_group_busy_fraction_of_capacity_before_cut"]-
                 d0["espresso_group_busy_fraction_of_capacity_before_cut"]/3)<1e-8,
             "OCCUPANCY_MEAN_NOT_CONSISTENT")
        delta=b["p90_paid_to_handoff_full_drain_min"]-a["p90_paid_to_handoff_full_drain_min"]
        need(abs(delta-row["delta_p90_min"])<1e-6 and
             b["handoffs_before_cut"]-a["handoffs_before_cut"]==
             row["delta_handoffs_at_cut"],
             "PUBLISHED_P39_DIFFERENCES_NOT_REPRODUCED")
        outputs.append({
            "load_label":row["load_label"],
            "source_horizon_min":row["source_horizon_minutes"],
            "paid_orders":a["paid_orders"],
            "beverage_units":a["beverage_units"],
            "handoffs_before_cut_1_to_3":[a["handoffs_before_cut"],
                                         b["handoffs_before_cut"]],
            "p90_full_drain_min_1_to_3":[
                a["p90_paid_to_handoff_full_drain_min"],
                b["p90_paid_to_handoff_full_drain_min"]],
            "espresso_blocked_tasks_1_to_3":[
                d0["espresso_tasks_blocked_by_group_count"],
                d3["espresso_tasks_blocked_by_group_count"]],
            "espresso_wait_minutes_task_1_to_3":[
                d0["espresso_auto_queued_minutes_before_cut"],
                d3["espresso_auto_queued_minutes_before_cut"]],
            "espresso_occupancy_percent_1_to_3":[
                round(100*d0["espresso_group_busy_fraction_of_capacity_before_cut"],4),
                round(100*d3["espresso_group_busy_fraction_of_capacity_before_cut"],4)],
            "three_group_remaining_wait_task_minutes":{
                "manual_setup":d3["manual_setup_queued_minutes_before_cut"],
                "milk_finish":d3["milk_finish_queued_minutes_before_cut"],
                "handoff":d3["handoff_queued_minutes_before_cut"],
            },
            "espresso_busy_group_minutes_in_peak":
                d3["espresso_group_busy_unit_minutes_before_cut"],
        })
    episodes=[]
    for rid in REVIEW_IDS:
        group,start,end,t0,t1=timers.EXAMPLES[rid]
        episodes.append({
            "record_id":rid,"video_group_annotation":group,
            "source_file_expected":"video2/videoplayback.webm",
            "anchor_video_s":[start,end],
            "counter_readings_seconds_shown":[t0,t1],
            "video_delta_s":round(end-start,3),
            "counter_delta_s":t1-t0,
            "verified_visual_activation_type":None,
            "complete_extraction_start_s":None,
            "complete_extraction_end_s":None,
            "group_occupied_duration_s":None,
            "barista_load_remove_clean_duration_s":None,
            "simultaneous_other_groups_available":None,
            "censored_or_unknown":True,
            "frames_reviewed":False,
            "review_instruction":"Inspect source frames around anchor; extend only until same activation starts/ends or censor. Distinguish extraction vs purge, operator loading/removing, other group availability. Do not join to synthetic orders.",
        })
    return {
        "schema":SCHEMA,"status":"AUTHENTIC_P39_REINTERPRETED_NO_NEW_RUN",
        "source_run":SOURCE_RUN,"source_artifact_id":SOURCE_ARTIFACT_ID,
        "assumed_serial_setup_seconds":30,
        "assumed_auto_espresso_seconds":90,
        "sufficient_group_count_in_this_scheduler":enough,
        "structural_reason":"One serial barista setup takes 30s and each auto-extraction takes 90s; a fourth extraction-ready task cannot arrive sooner than 90s after the first; its group is already released under current rules.",
        "structural_assumptions":[
            "barista cannot prepare two drinks concurrently",
            "manual setup precedes auto extraction",
            "auto extraction releases group after 90s, does not require barista",
            "group loading, removal and cleaning do not separately hold operator/group",
            "milk and handoff can delay setup, not accelerate it"],
        "evidence_level":"MODEL_CONSEQUENCE_NOT_REAL_MACHINE_CALIBRATION",
        "scenarios":outputs,
        "targeted_video_review":episodes,
        "actual_video_frames_available":False,
        "reviewed_video_episodes":0,
        "timer_pairs_are_not_completed_extractions":True,
        "no_real_bottleneck_identified":True,
        "new_simulations":0,"new_OMC":0,"R2_reads":0,"provider_POST":0,
    }


def export(result,out):
    out=Path(out)
    need(not out.exists(),"OUTPUT_EXISTS")
    out.mkdir(parents=True,exist_ok=False)
    write_json(out/"structural-review.json",result,exclusive=True)
    lines=[
        "# P42 | P39: mecanismo estructural, colas y revisión de evidencia",
        "",
        "**Fuente:** artifact P39 original, run "+str(SOURCE_RUN)+
        ", artifact "+str(SOURCE_ARTIFACT_ID)+".",
        "**Cómputo:** sólo posprocesamiento; 0 nuevas simulaciones, 0 OMC, 0 R2.",
        "",
        "## Deducción que no requiere otra simulación",
        "",
        "**Supuestos:** preparación manual serial 30 s por bebida, extracción",
        "automática 90 s, un barista, tres grupos hipotéticamente habilitados.",
        "Con un solo barista, dos preparaciones no terminan con menos de",
        "30 s de separación. Tras tres inicios separados 30 s, cuando",
        "la cuarta bebida queda lista, el primer grupo ha terminado.",
        "**90 / 30 = 3 grupos.** Bajo estas reglas el flujo de preparación",
        "no puede producir una cola sostenida en extracción con tres grupos.",
        "Esta relación es consecuencia de los supuestos, NO comprobación",
        "de la capacidad instalada real de una Synesso Hydra.",
        "Cargar, retirar y limpiar no ocupan simultáneamente barista/grupo",
        "como fases propias; ese mecanismo físico aún no se representa.",
        "",
        "## Comparación existente de uno contra tres grupos",
        "",
        "| Carga | Entregas 1→3 | P90 pago-entrega 1→3 (min) | Bloqueos espresso 1→3 | Espera espresso 1→3 (min-tarea) | Ocupación espresso 1→3 |",
        "|---|---|---|---|---|---|",
    ]
    for row in result["scenarios"]:
        u,v=row["handoffs_before_cut_1_to_3"]
        p,q=row["p90_full_drain_min_1_to_3"]
        b,c=row["espresso_blocked_tasks_1_to_3"]
        w,z=row["espresso_wait_minutes_task_1_to_3"]
        o,t=row["espresso_occupancy_percent_1_to_3"]
        lines.append(f"| {row['load_label']} | {u}→{v} | {p:.5f}→{q:.5f} | {b}→{c} | {w:.4f}→{z:.4f} | {o:.2f}%→{t:.2f}% |")
    lines+=["",
        "**P90:** calculado sobre todos los pedidos hasta terminar el",
        "drenaje, no sólo sobre las entregas anteriores al corte.",
        "**Ocupación:** minutos-grupo ocupados / (grupos habilitados × horizonte).",
        "El tiempo total de extracción no cambia; se divide entre más grupos.",
        "",
        "## Esperas de tareas manuales con tres grupos habilitados",
        "",
        "| Carga | Preparación (min-tarea) | Leche/acabado (min-tarea) | Entrega (min-tarea) |",
        "|---|---:|---:|---:|",
    ]
    for row in result["scenarios"]:
        d=row["three_group_remaining_wait_task_minutes"]
        lines.append(f"| {row['load_label']} | {d['manual_setup']:.4f} | {d['milk_finish']:.4f} | {d['handoff']:.4f} |")
    lines+=["",
        "Todas las tareas de estas etapas requieren barista en el modelo.",
        "Son minutos-tarea acumulados, no espera media de clientes ni",
        "minutos ocupados del empleado. No justifican contratar personal.",
        "",
        "## Verificación pendiente de tres episodios de video2",
        "",
        "| ID | Grupo anotado | Reloj video, s | Lectura de contador, s |",
        "|---|---|---|---|",
    ]
    for e in result["targeted_video_review"]:
        a,b=e["anchor_video_s"];c,d=e["counter_readings_seconds_shown"]
        lines.append(f"| {e['record_id']} | {e['video_group_annotation']} | {a:.3f}–{b:.3f} | {c:g}→{d:g} |")
    lines+=["",
        "**Estado:** SIN FOTOGRAMAS VERIFICADOS. Estas son dos lecturas",
        "por registro, no tiempos completos de servicio. El ZIP histórico",
        "no contiene los fotogramas o el video HD; la copia local no",
        "está accesible para esta ejecución. No se ha inferido inicio, fin,",
        "purga, trabajo manual ni ocupación simultánea.",
        "Examinar sólo las ventanas indicadas, ampliándolas para buscar",
        "extremos y conservando censura donde no sean visibles.",
        "Si la evidencia lo permite, aislar después un tiempo o regla",
        "del ciclo de barista/grupo con tres grupos y el mismo POS sintético.",
    ]
    (out/"P42_MECHANISM_REVIEW.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print("P42 READ_ONLY_REANALYSIS_OK",SOURCE_RUN,"CASES",len(result["scenarios"]),
          "VIDEO_FRAMES_REVIEWED",0)


def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("--source",required=True)
    p.add_argument("--dossier",required=True)
    p.add_argument("--out",required=True)
    args=p.parse_args(argv)
    export(analyze(read_json(args.source),read_json(args.dossier)),args.out)


if __name__=="__main__":
    main()
