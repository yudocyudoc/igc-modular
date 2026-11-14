"""V2.1 P01 visual *metadata* audit within the source-owner/custodian boundary.

Only the three explicitly whitelisted visual CSV members are ever opened.
The synthetic truth, generator parameters, observed synthetic POS and private
linkage remain unread, even though this tool verifies the whole archive hash.

CLI runs locally on a trusted source-owner machine. NEVER mount the source
ZIP in producer CI, attach it to Actions, or publish unredacted video rows.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import sys
import zipfile

from .common import ArenaError, write_json, digest
from .coffee_dm_campaign import SOURCE_PACKAGE_SHA256
from .coffee_adapters.shared import sha_bytes

SCHEMA="arena.coffee-v2.p01-visual-coverage/1"
MANIFEST="MANIFIESTO_PAQUETE.json"
CONSOLIDATED="video2/completo_v1/eventos_consolidados.csv"
MASTER="video2/maestro_15m_v2/eventos_maestro.csv"
DETECTIONS="video2/sintetico_pico_v1/revision_fila/personas_clasificadas_1s.csv"
ALLOWED=(CONSOLIDATED,MASTER,DETECTIONS)
SOURCE_COUNTS={CONSOLIDATED:980,MASTER:288,DETECTIONS:53270}
MAX_MEMBER_BYTES={CONSOLIDATED:2_000_000,MASTER:1_000_000,DETECTIONS:12_000_000}
HORIZON_SECONDS=6195
JSON_COLS=("grupos_extraccion_json","recursos_json","relaciones_json",
           "evidencias_json","contexto_actor_json","contexto_receptor_json",
           "contexto_solicitud_json","diagnostico_detector_json",
           "fuentes_registros_json","faltantes_json","revision_lote_json")

def need(test,why):
    if not test:
        raise ArenaError("COFFEE_V2_VISUAL_INVENTORY_"+why)

def _float(x,name):
    try: v=float(x)
    except (ValueError,TypeError): raise ArenaError("COFFEE_V2_VISUAL_INVENTORY_BAD_"+name) from None
    need(math.isfinite(v) and 0<=v<=HORIZON_SECONDS,"INVALID_"+name)
    return v

def _sha(raw):
    return hashlib.sha256(raw).hexdigest()

def _rows(z,name,manifest):
    item=z.getinfo(name)
    need(0<item.file_size<=MAX_MEMBER_BYTES[name],"VISUAL_MEMBER_SIZE")
    raw=z.read(name)  # Three visual files ONLY, never *_truth, POS or generator.
    expected=manifest["files"].get(name)
    need(isinstance(expected,dict) and expected.get("bytes")==len(raw)
         and expected.get("sha256")==_sha(raw),"VISUAL_MEMBER_MANIFEST_HASH")
    reader=csv.DictReader(io.StringIO(raw.decode("utf-8-sig"),newline=""))
    columns=reader.fieldnames
    need(bool(columns) and len(columns)==len(set(columns)),
         "MISSING_OR_REPEATED_CSV_HEADERS")
    data=list(reader)
    need(all(isinstance(r,dict) and None not in r and
             all(v is not None for v in r.values()) for r in data),
         "MALFORMED_CSV_ROW")
    return data,{"file_sha256":"sha256:"+_sha(raw),"bytes":len(raw),
                 "columns":len(columns),"rows":len(data),"column_names":columns}

def _event(rows):
    ids={}
    state=Counter()
    event=Counter()
    windows=Counter()
    time=[]
    flags=Counter()
    nonempty=Counter()
    role=Counter()
    for r in rows:
        rid=r["registro_id"]
        need(bool(rid) and rid not in ids,"DUPLICATE_OR_EMPTY_VISUAL_EVENT_ID")
        ids[rid]=r
        start=_float(r["observado_desde_video_s"],"EVENT_TIME")
        end=_float(r["observado_hasta_video_s"],"EVENT_TIME")
        need(start<=end,"VISUAL_EVENT_TIME_REVERSED")
        time.append(start)
        windows[int(start//900)]+=1
        state[r["estado"]]+=1
        role[r["rol_actor"]]+=1
        event[r["tipo_evento"]]+=1
        for name in ("apto_parametro_servicio_arena","continuidad_verificada",
                     "velocidad_real_verificada","retirada_pase_observada",
                     "recepcion_cliente_confirmada"):
            flag=r[name].strip().casefold()
            need(flag in ("true","false"),"UNDECLARED_VISUAL_BOOLEAN")
            if flag=="true": flags[name]+=1
        for name in ("duracion_servicio_min_s","duracion_servicio_max_s"):
            if r[name].strip():
                _float(r[name],"SERVICE_DURATION")
                nonempty[name]+=1
    return ids, {
        "rows":len(rows),
        "seconds_covered_by_events":[min(time),max(time)],
        "events_per_15min_bin":[windows[k] for k in range(7)],
        "observational_state_counts":dict(sorted(state.items())),
        "top_event_categories":dict(event.most_common(12)),
        "distinct_event_categories":len(event),
        "parameter_service_eligible_rows":flags["apto_parametro_servicio_arena"],
        "continuity_verified_rows":flags["continuidad_verificada"],
        "real_speed_verified_rows":flags["velocidad_real_verificada"],
        "service_duration_min_rows":nonempty["duracion_servicio_min_s"],
        "service_duration_max_rows":nonempty["duracion_servicio_max_s"],
        "observed_pass_removal_event_flags":flags["retirada_pase_observada"],
        "confirmed_customer_reception_event_flags":flags["recepcion_cliente_confirmada"],
        "role_labels_are_event_annotations_not_person_counts":True,
        "no_causal_or_empirical_capacity_identified":True,
    }

def _equivalent(x,y):
    for k in x:
        left=x[k];right=y[k]
        if k in JSON_COLS:
            try:
                if json.loads(left)!=json.loads(right):return False
            except (ValueError,TypeError):return False
        elif left.strip().casefold()!=right.strip().casefold():
            return False
    return True

def _detections(rows):
    sources=Counter()
    labels=Counter()
    windows=Counter()
    seconds=set()
    manual_windows=Counter()
    seen=set()
    missing_label=0
    for r in rows:
        t=_float(r["video_s"],"DETECTION_TIME")
        second=int(_float(r["video_second"],"DETECTION_SECOND"))
        need(second == int(t),"DETECTION_CLOCK_CONFLICT")
        seconds.add(second)
        windows[second//900]+=1
        src=r["label_source"] or "unlabeled"
        sources[src]+=1
        labels[r["label"] or "unlabeled"]+=1
        if src=="manual":manual_windows[second//900]+=1
        need(r["synthetic"].strip().casefold()=="false",
             "SYNTHETIC_DETECTIONS_MISCLASSIFIED_AS_VISUAL")
        key=r["detection_id"]
        need(bool(key) and key not in seen,"DUPLICATE_DETECTION_ID")
        seen.add(key)
    return {
        "detection_rows_not_unique_people":len(rows),
        "distinct_video_seconds":len(seconds),
        "seconds_first_last":[min(seconds),max(seconds)],
        "missing_second_bins":len(set(range(max(seconds)+1))-seconds),
        "detections_per_15min_bin":[windows[k] for k in range(7)],
        "label_source_counts":dict(sorted(sources.items())),
        "manual_labels_per_15min_bin":[manual_windows[k] for k in range(7)],
        "manual_labels_not_independent_persons":True,
        "sample_coverage_not_video_frame_file_verification":True,
    }

def audit(source, *,expected_sha=SOURCE_PACKAGE_SHA256, historical=True):
    """Returns aggregate-only metadata; no raw person IDs, tracks or timings."""
    path=Path(source)
    need(path.is_file() and path.stat().st_size<50_000_000,
         "SOURCE_LOCAL_ZIP_REQUIRED")
    # Digest entire ZIP without opening individual private truth members.
    with path.open("rb") as f:
        hasher=hashlib.sha256()
        for chunk in iter(lambda:f.read(1024*1024),b""):
            hasher.update(chunk)
    need(hasher.hexdigest()==expected_sha,"SOURCE_ARCHIVE_SHA256_MISMATCH")
    with zipfile.ZipFile(path) as z:
        infos=z.infolist()
        names=[i.filename for i in infos]
        need(len(set(names))==len(names) and MANIFEST in names
             and set(ALLOWED)<=set(names) and
             all(not name.startswith("/") and
                 ".." not in name.split("/") and "\\" not in name
                 for name in names),
             "ZIP_MEMBERS_INVALID")
        manifest=json.loads(z.read(MANIFEST))
        need(manifest.get("schema")=="cafeteria.pilot-package/1"
             and set(manifest.get("files",{}))==set(names)-{MANIFEST},
             "MANIFEST_NOT_COMPLETE")
        # Do not read other files: package truth and synthetic generator
        # remain invisible to this auditor, including row counts.
        con,con_meta=_rows(z,CONSOLIDATED,manifest)
        mas,mas_meta=_rows(z,MASTER,manifest)
        det,det_meta=_rows(z,DETECTIONS,manifest)
        images=sum(name.lower().endswith((".jpg",".jpeg",".png",".webp"))
                   for name in names)
        video=sum(name.lower().endswith((".mp4",".webm",".mov",".mkv"))
                  for name in names)
    if historical:
        need({CONSOLIDATED:len(con),MASTER:len(mas),DETECTIONS:len(det)}
             ==SOURCE_COUNTS,"PINNED_VISUAL_ROW_COUNTS_CHANGED")
    con_map,con_status=_event(con)
    mas_map,mas_status=_event(mas)
    need(set(mas_map)<=set(con_map),"MASTER_NOT_INCLUDED_IN_CONSOLIDATED")
    need(all(_equivalent(con_map[k],mas_map[k]) for k in mas_map),
         "MASTER_EVENTS_DIFFER_FROM_CONSOLIDATED")
    detection_status=_detections(det)
    if historical:
        need(con_status["events_per_15min_bin"]==
             [288,149,106,110,97,113,117]
             and mas_status["rows"]==288
             and detection_status["distinct_video_seconds"]==6195
             and detection_status["missing_second_bins"]==0,
             "PINNED_TEMPORAL_COVERAGE_CHANGED")
    need(con_status["parameter_service_eligible_rows"]==0
         and con_status["continuity_verified_rows"]==0
         and con_status["service_duration_min_rows"]==0
         and con_status["service_duration_max_rows"]==0,
         "CANNOT_DECLARE_SERVICE_CALIBRATION_FROM_VISUAL_ROWS")
    # No PII / event rows / source descriptions / frame references returned.
    return {
        "schema":SCHEMA,
        "status":"VISUAL_SOURCE_METADATA_VERIFIED_SERVICE_PARAMS_NOT_IDENTIFIED",
        "source_archive_sha256":"sha256:"+hasher.hexdigest(),
        "source_local_owner_only":True,
        "source_original_video_files_in_archive":video,
        "source_video_frames_in_archive":images,
        "selected_visual_members":{
            "full_events":{**con_meta,"column_names":len(con_meta["column_names"])},
            "first_15min_master":{**mas_meta,"column_names":len(mas_meta["column_names"])},
            "detection_labels":{**det_meta,"column_names":len(det_meta["column_names"])},
        },
        "full_event_coverage":con_status,
        "first15_event_coverage":{
            "rows":mas_status["rows"],
            "master_ids_subset_of_consolidated":True,
            "master_semantically_identical_to_consolidated":True,
            "master_not_independent_new_events":True,
            "additional_consolidated_events_after_first_15min":
               len(con_map)-len(mas_map),
        },
        "detection_coverage":detection_status,
        "semantic_limits":{
            "video_original_missing":video==0,
            "frame_evidence_missing":images==0,
            "cannot_reconfirm_annotations_against_original_frames":True,
            "no_verified_contiguous_service_intervals":True,
            "no_measured_machine_busy_time":True,
            "no_measured_manual_active_time":True,
            "cannot_identify_order_to_pickup_waits":True,
            "cannot_recommend_S2_or_S5_yet":True,
            "observed_events_not_equivalent_to_independent_customers":True,
        },
        "next_measurement":{
            "priority":"MEASURE_FIRST",
            "rival_mechanisms":["MACHINE_BUSY_LIMIT","MANUAL_OPERATOR_TIME_LIMIT"],
            "required_events":["machine_busy_start_end",
                               "operator_manual_task_start_end",
                               "shared_task_id","overlap_and_occlusion",
                               "resource_availability"],
            "rules":"Observe linked intervals; distinguish automated and manual overlap; "
                    "censor off-camera/unknown endpoints; no invented durations.",
        },
        "private_synthetic_truth_members_opened":0,
        "private_generator_members_opened":0,
        "R2_access":False,"provider_posts":0,"omc_invocations":0,
        "scientific_lock_created":False,"reserved_evaluation_access":False,
    }

def export(result,out):
    out=Path(out)
    need(not out.exists(),"OUTPUT_EXISTS")
    out.mkdir(parents=True)
    write_json(out/"p01-visual-coverage.json",result,exclusive=True)
    visual=result["full_event_coverage"]
    tracking=result["detection_coverage"]
    text=(
        "# P01 — Auditoría visual agregada de la fuente local original\n\n"
        f"- Archivo fuente íntegro comprobado por SHA-256: "
        f"\`{result['source_archive_sha256']}\`.\n"
        f"- Eventos consolidados: **{visual['rows']}**, con "
        f"**{result['first15_event_coverage']['rows']}** del maestro incluidos "
        "(NO 288 independientes adicionales).\n"
        f"- Etiquetas/detecciones: **{tracking['detection_rows_not_unique_people']}** "
        f"en **{tracking['distinct_video_seconds']}** segundos distintos; "
        "**no son personas únicas**.\n"
        f"- Ventanas de 15 min (eventos): "
        f"\`{visual['events_per_15min_bin']}\`.\n"
        f"- Registro de aptitud para calibrar servicio: "
        f"**{visual['parameter_service_eligible_rows']}/{visual['rows']}**; "
        "sin continuidad confirmada ni tiempos completos de preparación.\n"
        f"- Marcas de retirada de pase: "
        f"**{visual['observed_pass_removal_event_flags']}**; "
        "marcas de recepción cliente: "
        f"**{visual['confirmed_customer_reception_event_flags']}**. "
        "Estas marcas no son entregas longitudinales vinculadas a POS.\n"
        "- El ZIP no incluye video original ni fotogramas: "
        "imposible revalidar eventos dudosos desde aquí.\n"
        "- **P01 semántico pendiente:** medir intervalos emparejados de "
        "actividad manual y máquina, con oclusiones; no seleccionar S2/S5.\n"
        "- Fuentes privadas sintéticas NO abiertas, sin operaciones R2, "
        "OMC, proveedores o G3. Informe agregado, sin identidades.\n")
    (out/"REVIEW.md").write_text(text,encoding="utf-8")
    files=sorted(out.iterdir())
    receipt={
        "schema":SCHEMA,"status":result["status"],
        "source_archive_sha256":result["source_archive_sha256"],
        "outputs":{p.name:sha_bytes(p.read_bytes()) for p in files},
        "private_rows_opened":0,"r2":False,"posts":0,"omc":0,"lock":False,
    }
    write_json(out/"receipt.json",receipt,exclusive=True)
    return receipt

def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("--source",required=True,type=Path,
        help="Local owner source ZIP; NEVER upload it to GitHub")
    p.add_argument("--out",required=True,type=Path)
    opts=p.parse_args(argv)
    try:
        result=export(audit(opts.source),opts.out)
        print(json.dumps({"status":result["status"],"posts":0,"omc":0,
                          "private_rows_opened":0},sort_keys=True))
        return 0
    except (ArenaError,ValueError,KeyError,TypeError,OSError,
            UnicodeDecodeError,zipfile.BadZipFile) as exc:
        print(json.dumps({"status":"STOPPED_NO_EXTERNAL_CONSUMPTION",
                          "reason":str(exc) if isinstance(exc,ArenaError)
                                   else "INVALID_SOURCE_OR_IMPLEMENTATION"}),
              file=sys.stderr)
        return 2

if __name__=="__main__":
    raise SystemExit(main())
