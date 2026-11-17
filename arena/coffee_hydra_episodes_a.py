"""A-only episode constraints for the known video2 construction observations.

Consumes a small reviewed layer separately from P39's 37 historical pairs.
This is a feasibility/representation checker, not an order reconstruction,
a simulator, an optimiser, a calibration distribution, or an independent
visual audit. No media, personal images or synthetic truth are opened.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import zipfile

from .common import ArenaError, read_json, write_json
from . import coffee_v2_reference as reference

SCHEMA = "arena.coffee.p43.episode-review-layer/1"
REPORT_SCHEMA = "arena.coffee.p43.observed-episode-constraints/1"
REVIEW = "evidencia/episodios_revisados.csv"
OPERATIONS = "evidencia/operaciones_existentes.csv"
MANIFEST = "evidencia/manifest.json"
HISTORIC = {"T31": ("G03", 12, 40.011, 0, 28),
            "T33": ("G03", 118.012, 122.006, 28, 32),
            "T12": ("G01", 640.014, 668.010, 2, 30)}
REVIEW_IDS = {"T31", "T33", "T12", "T28"}


def need(ok, code):
    if not ok:
        raise ArenaError("COFFEE_P43_A_" + code)


def finite(x):
    return type(x) in (float, int) and math.isfinite(x)


def by_id(rows):
    need(type(rows) is list and all(type(x) is dict and
         type(x.get("id")) is str for x in rows), "INVALID_ROWS")
    result = {x["id"]: x for x in rows}
    need(len(result) == len(rows), "DUPLICATE_ROW")
    return result


def inspect(view):
    """Validate curated layer before any scientific checks."""
    need(type(view) is dict and view.get("schema") == SCHEMA,
         "SOURCE_SCHEMA")
    need(view.get("scope") == "KNOWN_CONSTRUCTION_VIDEO2_EPISODES_NOT_POS_LINKED"
         and view.get("synthetic_order_joins") == 0 and
         view.get("source_operation_rows") == 36 and
         view.get("historical_timer_rows_unchanged") == 37 and
         view.get("historical_timer_group_counts") ==
             {"G01": 17, "G02": 13, "G03": 7} and
         view.get("manual_stage_durations_calibrated") == 0 and
         view.get("group_reuse_times_measured") == 0,
         "SOURCE_PROVENANCE_OR_SCOPE")
    for label, n in (("new_review_package_zip_sha256",64),
                     ("manifest_member_sha256",64),
                     ("review_csv_sha256",64),
                     ("existing_operations_csv_sha256",64)):
        raw = view.get(label)
        need(type(raw) is str and len(raw) == n and
             all(ch in "0123456789abcdef" for ch in raw),
             "SHA_FIELD_" + label)
    need(view.get("historical_source_sha256") ==
         "4ff97ae4d8fe52a5c1d1701aa713fda09b6730ef63d9cbab23e6af30dfad2a5f",
         "UNRECOGNIZED_P39_SOURCE")
    episodes = by_id(view.get("reviewed_episodes"))
    operations = by_id(view.get("selected_operations"))
    need(set(episodes) == REVIEW_IDS and len(operations) == 12,
         "EPISODE_OR_OPERATION_COVERAGE")
    for rid, (group, t0, t1, c0, c1) in HISTORIC.items():
        e = episodes[rid]
        need(e.get("group") == group and
             e.get("linked_historic_timer_id") == "TM-" + rid and
             e.get("old_pair") ==
                {"video_s": [t0,t1], "counter_s": [c0,c1]},
             "OLD_TIMER_PAIR_CHANGED_" + rid)
    for rid in ("T31", "T33", "T12"):
        e = episodes[rid]
        need(e.get("type") in
             ("extraction_to_cup", "probable_extraction_to_cup") and
             finite(e.get("counter_elapsed_seconds")) and
             e["counter_elapsed_seconds"] > 0 and
             e.get("complete_service_seconds") is None and
             e.get("group_released_video_s") is None and
             e.get("confidence") in
             ("estimated_from_counter_and_visual_context",
              "estimated_with_occlusions"),
             "EXTRACTION_MUST_REMAIN_ESTIMATE_" + rid)
    purge=episodes["T28"]
    need(purge.get("type") == "probable_purge" and
         purge.get("confidence") == "probable_visual_without_portafilter_or_cup"
         and purge.get("counter_elapsed_seconds") is None and
         purge.get("complete_service_seconds") is None and
         purge.get("group_released_video_s") is None,
         "PURGE_NOT_EXCLUSION")
    for op in operations.values():
        w=op.get("observed_window_video_seconds")
        need(type(w) is list and len(w)==2 and
             all(finite(v) for v in w) and 0 <= w[0] <= w[1] <= 900 and
             op.get("window_is_full_task_duration") is False and
             op.get("order_id") is None and
             op.get("confidence") in ("observado","probable") and
             type(op.get("resources")) is list and
             type(op.get("source_row")) is str and
             op["source_row"] == OPERATIONS + "#" + op["id"],
             "WINDOW_IS_NOT_TASK_DURATION_" + op["id"])
    # Reviewed point samples are evidence assertions separate from windows.
    # The windows only bound where a sample is plausible; they DO NOT
    # establish uninterrupted activity or sample simultaneity on their own.
    samples=by_id(view.get("operator_activity_samples", []))
    need(len(samples)<=12, "SAMPLE_COUNT")
    for sample in samples.values():
        instant=sample.get("video_s")
        actors=sample.get("actors")
        need(finite(instant) and 0<=instant<=900 and
             type(sample.get("reviewer_observed_simultaneous_activity")) is bool and
             sample.get("confidence")=="reviewer_visual_assertion" and
             sample.get("full_continuous_intervals_observed") is False and
             type(sample.get("visual_evidence_ref")) is str and
             sample["visual_evidence_ref"].endswith(".jpg") and
             type(sample.get("provenance")) is str and
             "Astra" in sample["provenance"] and
             type(actors) is list and 1<=len(actors)<=3,
             "SAMPLE_PROVENANCE_OR_TYPE")
        ids=[]
        for observed in actors:
            need(type(observed) is dict and
                 observed.get("operation_id") in operations,
                 "SAMPLE_UNREFERENCED_OPERATION")
            op=operations[observed["operation_id"]]
            window=op["observed_window_video_seconds"]
            need(observed.get("actor")==op["actor"] and
                 observed.get("activity")==op["type"] and
                 observed.get("station") in op["resources"] and
                 window[0]<=instant<=window[1],
                 "SAMPLE_NOT_IN_DECLARED_WINDOW")
            ids.append(observed["actor"])
        need(len(ids)==len(set(ids)),"SAMPLE_DUPLICATE_ACTOR")
    need(operations["E115"]["type"]=="extraccion_en_curso" and
         operations["E115"]["resources"]==["G03"] and
         operations["E149"]["actor"]=="B02" and
         operations["E149"]["observed_window_video_seconds"][0]>=
         operations["E115"]["observed_window_video_seconds"][0] and
         operations["E149"]["observed_window_video_seconds"][1]<=
         operations["E115"]["observed_window_video_seconds"][1],
         "MACHINE_MANUAL_CONTEXT")
    need(episodes["T31"]["first_final_seen_video_s"] <
         episodes["T31"]["final_still_seen_video_s"] and
         episodes["T31"]["visual_state_note"]==
             "portafilter_still_attached_after_counter_stops",
         "AFTER_COUNTER_STOP_EVIDENCE")
    return episodes,operations


def authenticate_original_zip(path,view):
    """Optional local source-byte verification; never extracts or reads JPGs."""
    data=Path(path).read_bytes()
    need(hashlib.sha256(data).hexdigest() ==
         view["new_review_package_zip_sha256"],"ZIP_DIGEST_MISMATCH")
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names=archive.namelist()
        need(len(names)==len(set(names)) and
             all(not name.startswith("/") and "\\" not in name and
                 ".." not in name.split("/") for name in names),
             "UNSAFE_ZIP_PATH")
        blobs={p:archive.read(p) for p in (REVIEW,OPERATIONS,MANIFEST)}
    for key,name in (("review_csv_sha256",REVIEW),
                     ("existing_operations_csv_sha256",OPERATIONS),
                     ("manifest_member_sha256",MANIFEST)):
        need(hashlib.sha256(blobs[name]).hexdigest()==view[key],
             "SOURCE_MEMBER_SHA_" + key)
    meta=json.loads(blobs[MANIFEST])
    need(meta.get("existing_operation_rows")==36 and
         meta["files"]["episodios_revisados.csv"]==view["review_csv_sha256"]
         and meta["files"]["operaciones_existentes.csv"]==
             view["existing_operations_csv_sha256"],
         "ASTRA_MANIFEST_MISMATCH")
    def parse(member):
        records=list(csv.DictReader(io.StringIO(blobs[member].decode("utf-8-sig"))))
        need(len(records)==(4 if member==REVIEW else 36),
             "ORIGINAL_CSV_ROW_COUNT")
        return records
    originals={x["id"]:x for x in parse(REVIEW)}
    original_ops={x["event_id"]:x for x in parse(OPERATIONS)}
    for e in view["reviewed_episodes"]:
        raw=originals[e["id"]]
        need(raw["grupo"]==e["group"] and
             (float(raw["contador_final_s"]) if raw["contador_final_s"]
              else None)==e["counter_elapsed_seconds"] and
             (float(raw["duracion_automatica_estimada_s"])
              if raw["duracion_automatica_estimada_s"] else None)==
                  e["counter_elapsed_seconds"] and
             raw["duracion_servicio_completo_s"]=="" and
             raw["evidencia"].split(";")==e["evidence_refs"] and
             raw["clasificacion"] == {
                 "extraction_to_cup":"extraccion_hacia_vaso_papel",
                 "probable_extraction_to_cup":"extraccion_hacia_vaso_papel_probable",
                 "probable_purge":"purga_probable_sin_portafiltro",
             }[e["type"]],
             "REVIEW_PROJECTION_DISAGREES_" + e["id"])
        for key,src in (("first_final_seen_video_s","primer_final_visible_video_s"),
                        ("final_still_seen_video_s","final_persiste_video_s"),
                        ("estimated_activation_start_video_s",
                         "inicio_activacion_estimado_video_s")):
            need((float(raw[src]) if raw[src] else None)==e[key],
                 "REVIEW_TIMES_DISAGREE_" + e["id"])
    for o in view["selected_operations"]:
        raw=original_ops[o["id"]]
        need(raw["actor_id"]==o["actor"] and
             raw["event_type"]==o["type"] and
             raw["status"]==o["confidence"] and
             float(raw["start_lower_video_s"])==
                 o["observed_window_video_seconds"][0] and
             abs(float(raw["end_upper_video_s"])-
                 o["observed_window_video_seconds"][1])<1e-9 and
             json.loads(raw["resources"])==o["resources"] and
             raw["arena_service_parameter_eligible"]=="False" and
             raw["duration_lower_s"]==raw["duration_upper_s"]=="",
             "OPERATION_PROJECTION_DISAGREES_"+o["id"])
    return True


# Explicit test policy, NOT a calibrated sensor-error model. Reporting a match
# within two seconds does not imply sub-second measurement accuracy.
COUNTER_COMPATIBLE_WITHIN_SECONDS = 2.0
COUNTER_UNCERTAINTY_GUARD_SECONDS = 4.0
COUNTER_HYPOTHESIS = "automatic_duration_equals_counter_elapsed"


def evaluate_cases(view, episodes, operations, caps, automatic_min, *,
                   timer_semantics=COUNTER_HYPOTHESIS):
    """Pure constraint evaluation; accepts alternative representation fixtures.

    Source authentication and pinned historic pairs are separate from this
    function. In particular a future B dossier can change resource units.
    """
    need(timer_semantics in (COUNTER_HYPOTHESIS, "not_established"),
         "COUNTER_SEMANTICS_NOT_EXPLICIT")
    need(finite(automatic_min) and automatic_min>0,
         "MODEL_AUTOMATIC_DURATION_INVALID")
    units=caps["resource_units"]
    req=caps["stage_requirements"]
    manual=req["manual_setup"]
    auto=req["espresso_auto"]
    need(set(manual) <= set(units) and set(auto) <= set(units) and
         type(caps["post_counter_mounted_state_supported"]) is bool,
         "CAPABILITIES_NOT_RESOLVED")

    def outcome(key,status,rule,observed,modeled,uncertainty,why,refs):
        return {
            "question":key,
            "status":status,
            "rule":rule,
            "observed":observed,
            "model":modeled,
            "uncertainty":uncertainty,
            "explanation":why,
            "evidence_refs":refs,
            "conditioning_evidence":refs,
            "tested_observation_or_structural_rule":rule,
            "fixed_assumptions":[uncertainty],
            "independent_validation":False,
        }

    results=[]
    samples=view.get("operator_activity_samples", [])
    reviewed=[]
    for sample in samples:
        if not sample["reviewer_observed_simultaneous_activity"]:
            continue
        actors=[x for x in sample["actors"]
                if x["activity"]=="preparacion_visible"]
        if len({a["actor"] for a in actors})>=2 and len({
             a["station"] for a in actors})>=2:
            reviewed.append(sample)
    max_simultaneous=max((len(x["actors"]) for x in reviewed),default=None)
    manual_caps={r:units[r] for r in manual}
    manual_capacity=min(manual_caps.values())
    if max_simultaneous is None:
        concurrency_status="INDETERMINATE"
        note=("No reviewer-verified simultaneous preparation sample is "
              "available. Overlapping operation windows alone do not "
              "establish concurrent work.")
    else:
        deficits={r:limit for r,limit in manual_caps.items()
                  if max_simultaneous>limit}
        concurrency_status=("CONTRADICTED" if deficits else "COMPATIBLE")
        note=(f"Reviewed distinct-operator/station samples require "
              f"{max_simultaneous} concurrent manual setups; model "
              f"capacity is {manual_capacity} from {manual_caps}. "
              + (f"Insufficient resources: {deficits}." if deficits else
                 "This requirement is representable, not a scheduling prediction."))
    results.append(outcome(
        "two_operators_vs_single_global_barista",concurrency_status,
        "max observed simultaneous independent preparations <= each required stage resource capacity",
        {"reviewed_samples":[{"id":x["id"],"video_s":x["video_s"],
             "actor_ids":[a["actor"] for a in x["actors"]],
             "stations":[a["station"] for a in x["actors"]]}
             for x in reviewed],
         "required_simultaneous_preparations":max_simultaneous},
        {"stage":"manual_setup","required_resources":manual,
         "capacities":manual_caps,"concurrent_capacity":manual_capacity},
        "Two still-frame assertions from Astra; not continuously tracked intervals or permanent staffing.",
        note,[x["id"] for x in reviewed]+
             [a["operation_id"] for x in reviewed for a in x["actors"]]))

    # T31 supplies independent semantic context; T33 is the held-out
    # observable. Neither is a complete group-occupation duration.
    t33=episodes["T33"]
    measured=t33["counter_elapsed_seconds"]
    predicted=automatic_min*60.0
    diff=abs(predicted-measured)
    if timer_semantics=="not_established":
        time_status="INDETERMINATE"
        reason="Automatic model duration has not been mapped to displayed counter elapsed time."
    elif diff<=COUNTER_COMPATIBLE_WITHIN_SECONDS:
        time_status="COMPATIBLE"
        reason=("Counter interpretation is not contradicted at the declared "
                "whole-second tolerance; this does not prove real group occupancy.")
    elif diff<=COUNTER_UNCERTAINTY_GUARD_SECONDS:
        time_status="INDETERMINATE"
        reason="Difference lies in the explicit uncertainty guard band."
    else:
        time_status="CONTRADICTED"
        reason=("Under the counter-elapsed semantic hypothesis, the model "
                "automatic duration is incompatible with T33's estimated final counter.")
    results.append(outcome(
        "counter_90s_as_timer_elapsed",time_status,
        "compare held-out T33 elapsed counter estimate to model espresso_auto_min * 60 ONLY under declared semantic equivalence",
        {"episode":"T33","estimated_counter_elapsed_s":measured,
         "class":t33["type"],"context_episode":"T31",
         "absolute_difference_s":round(diff,6)},
        {"espresso_auto_min":automatic_min,"seconds":predicted,
         "timer_semantics":timer_semantics},
        f"Estimates rounded to seconds; compatible ≤{COUNTER_COMPATIBLE_WITHIN_SECONDS}s, "
        f"undetermined up to {COUNTER_UNCERTAINTY_GUARD_SECONDS}s, otherwise incompatible. "
        "These are operational guard bands, NOT calibrated sensor precision.",
        f"{reason} Model {predicted:g}s vs T33 {measured:g}s "
        f"(difference {diff:g}s); mapping={timer_semantics}.",
        ["T31","T33"]))

    machine=operations["E115"]
    auxiliary=operations["E149"]
    win1=machine["observed_window_video_seconds"]
    win2=auxiliary["observed_window_video_seconds"]
    potential=(max(win1[0],win2[0])<=min(win1[1],win2[1]))
    shared=sorted(set(auto)&set(manual))
    if not potential:
        machine_status="INDETERMINATE"
        reason="The annotated windows do not overlap, so they do not test concurrency."
    elif shared:
        machine_status="INDETERMINATE"
        reason=("A shared model resource could block simultaneous actions, "
                "but partial windows alone do not prove a common active instant.")
    else:
        machine_status="COMPATIBLE"
        reason=("The model permits automatic extraction and a separate "
                "manual action to overlap; this is possible resource "
                "compatibility, NOT proof they occurred continuously together.")
    results.append(outcome(
        "machine_vs_operator_overlap",machine_status,
        "potentially simultaneous stages are permitted when their required resource sets are disjoint",
        {"operations":["E115","E149"],
         "windows_video_s":[win1,win2],
         "window_intersection_possible":potential},
        {"auto_stage_required_resources":auto,
         "manual_stage_required_resources":manual,
         "shared_resources":shared},
        "Partial annotated windows, no certified same-instant machine/operator identity or paid-order join.",
        reason,["E115","E149"]))

    purge=episodes["T28"]
    excluded=[x["id"] for x in episodes.values()
              if x["type"]=="probable_purge"]
    purge_status=("COMPATIBLE" if purge["id"] in excluded else
                  "INDETERMINATE")
    results.append(outcome(
        "probable_purge_exclusion",purge_status,
        "a probable purge is excluded from beverage counter-duration examples",
        {"T28_type":purge["type"],"T28_confidence":purge["confidence"],
         "excluded_as_probable_purge":excluded},
        {"drink_counter_sample_ids":[rid for rid,e in episodes.items()
              if e["type"] in ("extraction_to_cup",
                               "probable_extraction_to_cup")]},
        "Probable, not a confirmed purge; excluded only from drink-extraction estimation.",
        ("The classification of T28 is reflected in the exclusion set."
         if purge_status=="COMPATIBLE" else
         "T28 does not provide a usable probable-purge exclusion."),
        ["T28"]))

    t31=episodes["T31"]
    has_sample=(t31.get("visual_state_note")==
                "portafilter_still_attached_after_counter_stops" and
                finite(t31.get("first_final_seen_video_s")) and
                finite(t31.get("final_still_seen_video_s")) and
                t31["final_still_seen_video_s"]>
                t31["first_final_seen_video_s"])
    supported=caps["post_counter_mounted_state_supported"]
    post_status=("INDETERMINATE" if not has_sample else
                 "COMPATIBLE" if supported else "NOT_REPRESENTED")
    results.append(outcome(
        "portafilter_remains_after_timer_stop",post_status,
        "representation must have an explicit post-counter group-mounted/release state to express the observed state",
        {"episode":"T31","post_counter_state_sample_exists":has_sample,
         "first_counter_final_visible_s":t31.get("first_final_seen_video_s"),
         "counter_final_persists_s":t31.get("final_still_seen_video_s"),
         "portafilter_note":t31.get("visual_state_note")},
        {"post_counter_mounted_state_supported":supported,
         "model_capabilities_from":caps.get("stage_source")},
        "Portafilter in still images does NOT prove continuously occupied time or a release timestamp.",
        ("No confirmed after-counter mounted-state sample to test." if not has_sample
         else "The model can express a post-counter mounted state (not its duration)." if supported
         else "The model releases the group after the automatic stage; it cannot express post-counter mounted state."),
        ["T31"]))

    unknown_backlog=view.get("unknown_starting_backlog") is True
    unlinked=all(x.get("order_id") is None for x in operations.values())
    missing_calendar=view.get(
        "operator_presence_beyond_sampled_windows_unknown") is True
    backlog_status=("INDETERMINATE" if
                    unknown_backlog or unlinked or missing_calendar
                    else "COMPATIBLE")
    results.append(outcome(
        "initial_backlog_and_hidden_task_identity",backlog_status,
        "real initial pending work and task-to-order relationships require independently observed state, not synthetic assumptions",
        {"initial_backlog_unknown":unknown_backlog,
         "no_order_links":unlinked,
         "operator_calendar_unknown":missing_calendar},
        {"initial_open_orders":None,
         "real_backlog_fitted":False},
        "No real initial state or continuous operator calendar was measured.",
        ("Observed source lacks one or more required fields for backlog "
         "or delay attribution." if backlog_status=="INDETERMINATE"
         else "Observed state/links are declared known; requires separate factual audit."),
        ["E030","E062","E032","E064"]))
    return results


def historical_baseline_gate(dossier):
    """Identity check for the ORIGINAL historical report, not for candidates."""
    reference.config_gate(dossier)
    need(dossier["policy"]=="B0" and
         dossier["resources"]["barista"]["units"]==1 and
         dossier["resources"]["prep_space"]["units"]==1 and
         dossier["durations"]["espresso_auto_min"]["value"]==1.5,
         "EXPECTED_UNCHANGED_HISTORICAL_BASELINE")


def check(view, dossier, *, source_bytes_verified=False,
          timer_semantics=COUNTER_HYPOTHESIS):
    episodes,operations=inspect(view)
    capabilities=reference.episode_model_capabilities(dossier)
    results=evaluate_cases(view,episodes,operations,capabilities,
                           dossier["durations"]["espresso_auto_min"]["value"],
                           timer_semantics=timer_semantics)
    return {
        "schema":REPORT_SCHEMA,
        "scope":"OBSERVED_EPISODE_FEASIBILITY_AND_REPRESENTATION_ONLY",
        "source_zip_digest_verified_in_this_execution":bool(source_bytes_verified),
        "source_review_file_digest":view["review_csv_sha256"],
        "source_operations_file_digest":view["existing_operations_csv_sha256"],
        "historical_timers_preserved":37,
        "new_annotated_episodes":len(episodes),
        "operations_in_small_review_layer":len(operations),
        "original_operations_in_source":view["source_operation_rows"],
        "reviewed_estimated_counter_seconds":{
            k:episodes[k]["counter_elapsed_seconds"] for k in
            ("T31","T33","T12")},
        "possible_purges_excluded_from_extraction":[
            e["id"] for e in episodes.values()
            if e["type"]=="probable_purge"],
        "model_capabilities":capabilities,
        "model_counter_semantic_hypothesis":timer_semantics,
        "model_automatic_extraction_seconds":
            dossier["durations"]["espresso_auto_min"]["value"]*60,
        "real_order_id_links":0,
        "full_service_durations_measured":0,
        "group_release_times_measured":0,
        "checks":results,
        "no_model_parameter_changes":True,
        "no_new_reference_simulations":True,
        "no_OMC_or_provider":True,
    }


def export(report, out):
    out=Path(out)
    need(not out.exists(),"OUTPUT_EXISTS")
    out.mkdir(parents=True,exist_ok=False)
    write_json(out/"episode-checks.json",report,exclusive=True)
    lines=[
        "# P43 · Entrega A: episodios observados vs reglas representadas",
        "",
        "Fuente: revisión visual previa de Astra, no observación nueva.",
        "ZIP autenticado contra bytes en esta ejecución: **"+
        ("sí" if report["source_zip_digest_verified_in_this_execution"]
         else "no; sólo proyección comprometida en Git") + "**.",
        "Registros históricos P39 preservados: **37**. Revisiones: **4**.",
        "Operaciones revisadas: **12 de las 36** disponibles.",
        "No se enlazaron pedidos sintéticos ni se midieron servicios completos.",
        "",
        "| Pregunta | Resultado | Registros |",
        "|---|---|---|",
    ]
    for row in report["checks"]:
        lines.append("| "+row["question"]+" | **"+row["status"]+
                     "** | "+", ".join(row["evidence_refs"])+" |")
    for row in report["checks"]:
        lines += ["", "## "+row["question"], "",
                  "**"+row["status"]+"** — "+row["explanation"],
                  "", "Regla: "+row["rule"],
                  "Observado: "+json.dumps(row["observed"],
                                            ensure_ascii=False,sort_keys=True),
                  "Modelo: "+json.dumps(row["model"],
                                         ensure_ascii=False,sort_keys=True),
                  "Incertidumbre: "+row["uncertainty"],
                  "Referencias: "+", ".join(row["evidence_refs"])]
    lines += ["",
        "## Alcance y condición de falsabilidad", "",
        "Los estados del informe se calculan de entradas de los episodios y",
        "capacidades del motor, no de etiquetas estáticas de resultados.",
        "Cambiar el dossier a dos baristas y dos espacios puede resolver",
        "la incompatibilidad de concurrencia, sin validar la intervención.",
        "La comparación del contador es condicional a semántica explícita.",
        "La liberación del grupo permanece sin medición física.",
        "COMPATIBLE sólo significa factibilidad bajo reglas y observaciones.",
        "Ventanas superpuestas no certifican operación continua.",
        "Las muestras son afirmaciones de revisión de Astra, no una nueva",
        "auditoría visual ni validación externa independiente.",
    ]
    (out/"A_EPISODE_FINDINGS.md").write_text(
        "\n".join(lines)+"\n", encoding="utf-8")
    print("P43_A_CHECKS",len(report["checks"]),
          "AUTHENTIC_ZIP_BYTES",report["source_zip_digest_verified_in_this_execution"],
          "NEW_REFERENCE_RUNS",0)


def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("--view",required=True)
    p.add_argument("--historical-dossier",required=True)
    p.add_argument("--source-zip",help="Optional exact local Astra ZIP, read-only; never uploads images")
    p.add_argument("--timer-semantics",choices=(COUNTER_HYPOTHESIS,"not_established"),
                   default=COUNTER_HYPOTHESIS,
                   help="Declared counter comparison hypothesis, not established empirical equivalence")
    p.add_argument("--out",required=True)
    args=p.parse_args(argv)
    view=read_json(args.view)
    inspect(view)
    verified=authenticate_original_zip(args.source_zip,view) if args.source_zip else False
    export(check(view,read_json(args.historical_dossier),
                 source_bytes_verified=verified,
                 timer_semantics=args.timer_semantics),args.out)


if __name__=="__main__":
    main()
