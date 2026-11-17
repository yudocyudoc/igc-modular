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
OPERATOR_PAIRS = (("E030", "E062", 48.0),
                  ("E032", "E064", 104.006))


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
    for left, right, t in OPERATOR_PAIRS:
        a,b=operations[left],operations[right]
        need(a["actor"]=="B02" and b["actor"]=="B01" and
             a["type"]==b["type"]=="preparacion_visible" and
             a["confidence"]==b["confidence"]=="observado" and
             all(e["observed_window_video_seconds"][0]<=t<=
                 e["observed_window_video_seconds"][1]
                 for e in (a,b)) and
             "puesto_izquierdo" in a["resources"] and
             "puesto_derecho" in b["resources"],
             "OPERATOR_SAMPLED_EVIDENCE_" + left + "_" + right)
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


def check(view, historical_dossier, *, source_bytes_verified=False):
    episodes,operations=inspect(view)
    reference.config_gate(historical_dossier)
    d=historical_dossier
    need(d["policy"]=="B0" and
         d["resources"]["barista"]["units"]==1 and
         d["resources"]["prep_space"]["units"]==1 and
         d["durations"]["espresso_auto_min"]["value"]==1.5,
         "EXPECTED_UNCHANGED_HISTORICAL_BASELINE")
    def outcome(key,status,why,condition,held_out,refs,assumptions):
        return {"question":key,"status":status,"explanation":why,
                "conditioning_evidence":condition,
                "tested_observation_or_structural_rule":held_out,
                "evidence_refs":refs,
                "fixed_assumptions":assumptions,
                "independent_validation":False}

    reports=[
        outcome("two_operators_vs_single_global_barista","CONTRADICTED",
                "Two anonymized operators are visible working at sampled instants with different stations. One globally exclusive barista and one prep space cannot encode this. Windows do NOT prove continuous activity or permanent staffing.",
                ["Astra reviewed image operadores.jpg: frames 48.000 and 104.006",
                 "paired source windows hold these sample instants"],
                "historical B0 one barista and one prep_space resource",
                ["E030","E062","E032","E064","operadores.jpg"],
                ["one globally serial manual prep resource in historical B0",
                 "visual review samples, not uninterrupted work intervals"]),
        outcome("counter_90s_as_timer_elapsed","CONTRADICTED",
                "Conditional semantic test ONLY: if historical 90s espresso_auto is asserted to equal the displayed counter elapsed time for every drink, the independently reviewed 32s T33 is incompatible. It does NOT establish the real group busy/reuse duration.",
                ["T31 establishes that timer display is an elapsed counter with estimated final 29s; it is NOT fitted as a new model parameter"],
                "historical automatic counter-time hypothesis 90s versus held-out T33 estimated final 32s",
                ["T31","T33","E115","E116"],
                ["90s explicitly interpreted as counter elapsed time",
                 "T33 visually reviewed estimate is not subsecond measurement"]),
        outcome("machine_vs_operator_overlap","COMPATIBLE",
                "An espresso-group task and an auxiliary B02 task can overlap under the existing resource separation. This is feasibility only: the observed schedule was not predicted, and the tasks are not tied to a synthetic order.",
                ["E115 machine group G03 window 13.002–41.014",
                 "E149 B02 observed auxiliary window 14.005–24.000"],
                "existing model permits automatic espresso and independent operator tasks",
                ["E115","E149"],["different resources","no same-drink identity"]),
        outcome("probable_purge_exclusion","COMPATIBLE",
                "Probable T28 purge is excluded from beverage extraction estimates; its true classification remains probabilistic. No extra drink or completed cycle is inferred.",
                ["T28 reviewed G02 at 642.003 without portafilter/cup",
                 "original timer pair G02 counter 0→2"],
                "filter excludes probable purge from drink-extraction sample",
                ["T28"],["purge classification probable, not certain"]),
        outcome("portafilter_remains_after_timer_stop","NOT_REPRESENTED",
                "T31 counter final persists to 48s with portafilter still attached after first final reading at 41.014s. Baseline has no separate mounted/release state: no group reuse time can be computed.",
                ["T31 sampled portafilter state and counter-final readings"],
                "group release after counter stop is a different observable, absent from baseline",
                ["T31"],["presence does not prove every intervening second occupied"]),
        outcome("initial_backlog_and_hidden_task_identity","INDETERMINATE",
                "Observed clips may begin during unfinished work; no complete initial queue, order identity or operator calendars are supplied. Do not import the synthetic initial zero-backlog assumption.",
                ["source operations are partial windows with no linked order"],
                "real backlog or delay attribution at window start",
                ["E030","E062","E032","E064"],
                ["unknown observation state remains unknown"]),
    ]
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
        "possible_purges_excluded_from_extraction":["T28"],
        "real_order_id_links":0,
        "full_service_durations_measured":0,
        "group_release_times_measured":0,
        "checks":reports,
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
                  "",
                  "Condicionamiento: "+"; ".join(row["conditioning_evidence"])+".",
                  "Regla/contraste: "+row["tested_observation_or_structural_rule"]+".",
                  "Supuestos: "+"; ".join(row["fixed_assumptions"])+"."]
    lines += ["",
        "La incompatibilidad de dos operadores es ESTRUCTURAL en la",
        "representación globalmente serial, no estimación de plantilla.",
        "La incompatibilidad de 90 s aplica SÓLO a su interpretación",
        "como segundos del contador; los tiempos de liberación del",
        "grupo NO están medidos y no se han cambiado en el modelo.",
        "COMPATIBLE significa posibilidad, nunca validación predictiva.",
        "Las ventanas parciales NO son tiempos de trabajo continuo.",
        "No se usaron los datos condicionantes para calificar una",
        "predicción del mismo horario. Las revisiones son de construcción",
        "conocida, no validación ciega ni independiente.",
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
    p.add_argument("--out",required=True)
    args=p.parse_args(argv)
    view=read_json(args.view)
    inspect(view)
    verified=authenticate_original_zip(args.source_zip,view) if args.source_zip else False
    export(check(view,read_json(args.historical_dossier),
                 source_bytes_verified=verified),args.out)


if __name__=="__main__":
    main()
