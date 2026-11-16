"""P39: custodian-released Hydra timer pairs, not extraction durations.

One pinned historical source ZIP, one allowed visual member, no synthetic
truth/generator/POS, no hidden partition or operator identities in output.
A timer pair is a local clock observation, NEVER a complete extraction cycle.
Only in the custodian job may the ZIP be opened. The consumer sees the
versioned, verifiable, minimal machine-view projection.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re
import zipfile

from .common import ArenaError, digest, read_json, write_json
from . import coffee_v2_video_inventory as inventory
from . import coffee_dm_campaign as dm
from .coffee_custody import R2Storage, source_key

SCHEMA="arena.coffee.p39.hydra-timer-projection/1"
SOURCE_SHA=dm.SOURCE_PACKAGE_SHA256
CONSOLIDATED=inventory.CONSOLIDATED
GROUPS=("G01","G02","G03")
EXPECTED={"G01":17,"G02":13,"G03":7}
EXAMPLES={"TM-T12":("G01",640.014,668.010,2.0,30.0),
          "TM-T31":("G03",12.000,40.011,0.0,28.0),
          "TM-T33":("G03",118.012,122.006,28.0,32.0)}
GROUP_PATTERN=re.compile(r"(?<![A-Za-z0-9])G0[123](?![A-Za-z0-9])")


def need(ok,code):
    if not ok:
        raise ArenaError("COFFEE_P39_MACHINE_"+code)


def number(value, label):
    try:
        x=float(value)
    except (ValueError,TypeError):
        raise ArenaError("COFFEE_P39_MACHINE_INVALID_"+label) from None
    need(math.isfinite(x) and 0 <= x <= 10000,"NUMERIC_RANGE_"+label)
    return x


def _group(row):
    raw=row.get("grupos_extraccion_json","")
    try:
        parsed=json.loads(raw)
    except (ValueError,TypeError):
        raise ArenaError("COFFEE_P39_MACHINE_BAD_GROUP_JSON") from None
    ids=set(GROUP_PATTERN.findall(json.dumps(parsed,ensure_ascii=False)))
    if len(ids)==1:
        return next(iter(ids))
    return "UNKNOWN"  # never turn an unknown assignment into G01


def _reader(path, expected_sha=SOURCE_SHA):
    path=Path(path)
    need(path.is_file() and not path.is_symlink() and
         path.stat().st_size < 50_000_000,"BOUNDED_PINNED_ARCHIVE_REQUIRED")
    sha=hashlib.sha256()
    with path.open("rb") as f:
        for piece in iter(lambda:f.read(1024*1024),b""):
            sha.update(piece)
    need(sha.hexdigest()==expected_sha,"PINNED_SOURCE_SHA256_MISMATCH")
    with zipfile.ZipFile(path) as archive:
        names=archive.namelist()
        need(len(names)==len(set(names)) and
             inventory.MANIFEST in names and CONSOLIDATED in names and
             all(not n.startswith("/") and ".." not in n.split("/")
                 and "\\" not in n for n in names),
             "ZIP_MEMBER_ALLOWLIST")
        manifest=json.loads(archive.read(inventory.MANIFEST))
        need(manifest.get("schema")=="cafeteria.pilot-package/1" and
             set(manifest.get("files",{}))==set(names)-{inventory.MANIFEST},
             "SOURCE_MANIFEST_INVALID")
        rows,meta=inventory._rows(archive,CONSOLIDATED,manifest)
    need(len(rows)==980,"CONSOLIDATED_HISTORIC_COUNT")
    return rows,meta


def project_rows(rows,*,source_sha=SOURCE_SHA, member_sha):
    """Projection is explicit: no person IDs, synthetic POS or recipe joins."""
    need(type(rows) is list and len(rows) in (3,980),
         "SOURCE_ROW_COUNT_UNEXPECTED")
    selected=[r for r in rows if r.get("tipo_registro")=="medicion_temporizador"]
    need(len(selected)==37 if len(rows)==980 else len(selected)==3,
         "TIMER_PAIRS_MISSING_OR_UNKNOWN_TYPE")
    events=[]
    counts=Counter()
    for row in selected:
        rid=row.get("registro_id","")
        need(type(rid) is str and re.fullmatch(r"TM-T[0-9]{1,3}",rid),
             "TIMER_ID_OR_SCOPE")
        group=_group(row)
        start=number(row.get("observado_desde_video_s"),"VIDEO_START")
        end=number(row.get("observado_hasta_video_s"),"VIDEO_END")
        need(start<=end and end<=900.5,"TIMER_WINDOW_OUTSIDE_FIRST_15MIN")
        initial=number(row.get("lectura_inicial"),"COUNTER_START")
        final=number(row.get("lectura_final"),"COUNTER_END")
        unit=row.get("unidad_medida","")
        need(unit=="s_mostrados_contador","COUNTER_UNIT_MUST_BE_SECONDS_SHOWN")
        criterion=row.get("criterio_temporal","")
        service_state=row.get("duracion_servicio_estado","")
        # Continuity and full extraction endpoints are not certified by
        # two reads. Local agreement is NOT a complete cycle measurement.
        dt=end-start
        dc=final-initial
        state=("RESET_OR_WRAP_OR_DIFFERENT_ACTIVATION" if dc<0 else
               "LOCAL_COUNTER_DELTA_COMPATIBLE_NOT_FULL_CYCLE"
               if abs(dc-dt)<=2.0 else
               "CLOCK_DELTA_MISMATCH_OR_MISSING_CONTEXT")
        counts[group]+=1
        events.append({
            "registro_id":rid,"grupo":group,
            "grupos_extraccion_json":row.get("grupos_extraccion_json",""),
            "observado_desde_video_s":start,
            "observado_hasta_video_s":end,
            "lectura_inicial":initial,"lectura_final":final,
            "unidad_medida":unit,
            "criterio_temporal":criterion,
            "duracion_servicio_estado":service_state,
            "faltantes_json":row.get("faltantes_json",""),
            "evidencias_json":row.get("evidencias_json",""),
            "fuentes_registros_json":row.get("fuentes_registros_json",""),
            "pair_observation_status":state,
            "video_clock_delta_s":round(dt,4),
            "displayed_counter_delta_s":round(dc,4),
            "complete_extraction_duration_s":None,
            "unknown_full_cycle_endpoints":True,
        })
    need(len({r["registro_id"] for r in events})==len(events),
         "TIMER_ID_DUPLICATE")
    if len(rows)==980:
        need(dict(counts)==EXPECTED,
             "HISTORICAL_GROUP_COUNT_OR_UNKNOWN_GROUP")
        for key,(group,t0,t1,c0,c1) in EXAMPLES.items():
            got=next((x for x in events if x["registro_id"]==key),None)
            need(got is not None and got["grupo"]==group and
                 abs(got["observado_desde_video_s"]-t0)<0.015 and
                 abs(got["observado_hasta_video_s"]-t1)<0.015 and
                 abs(got["lectura_inicial"]-c0)<0.05 and
                 abs(got["lectura_final"]-c1)<0.05,
                 "PINNED_EXAMPLE_TIMER_DISAGREES")
    return {
        "schema":SCHEMA,"source_archive_sha256":"sha256:"+source_sha,
        "consolidated_member_sha256":member_sha,
        "scope":"FIRST_15_MIN_VIDEO2_MACHINE_TIMER_PAIRS",
        "rows":events,
        "count_by_labeled_group":dict(sorted(counts.items())),
        "source_rows_are_not_complete_extraction_cycles":True,
        "all_37_durations_not_established":True,
        "observed_group_presence_not_simultaneous_availability":True,
        "no_synthetic_pos_join_or_reserved_truth":True,
    }


def export(path,out):
    rows,meta=_reader(path)
    result=project_rows(rows,member_sha=meta["file_sha256"])
    out=Path(out)
    need(not out.exists(),"NO_OVERWRITE")
    out.mkdir(parents=True,mode=0o700)
    write_json(out/"machine-timers.json",result,exclusive=True)
    return {"status":"PINNED_MACHINE_TIMER_VIEW_RELEASED",
            "source_member_sha256":meta["file_sha256"],
            "timer_pair_count":len(result["rows"]),
            "groups":result["count_by_labeled_group"],
            "full_cycles_certified":0}


def fetch_and_export(out,*,storage=None):
    """Trusted GitHub custodian only; only digest + sidecar is surfaced."""
    import os
    need(os.environ.get("GITHUB_REPOSITORY")=="yudocyudoc/igc-modular"
         and os.environ.get("GITHUB_REF")=="refs/heads/main"
         and os.environ.get("GITHUB_EVENT_NAME")=="push"
         and os.environ.get("GITHUB_RUN_ATTEMPT")=="1",
         "CUSTODIAN_GITHUB_MAIN_ONLY")
    out=Path(out)
    need(not out.exists(),"NO_OVERWRITE")
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        archive=Path(tmp)/"historical-source.zip"
        (storage or R2Storage()).get(source_key(SOURCE_SHA),archive)
        result=export(archive,out)
    return result


def main(argv=None):
    import argparse
    p=argparse.ArgumentParser()
    cmd=p.add_subparsers(dest="command",required=True)
    cmd.add_parser("schema")
    get=cmd.add_parser("custodian-export")
    get.add_argument("--out",required=True)
    args=p.parse_args(argv)
    if args.command=="custodian-export":
        print(json.dumps(fetch_and_export(args.out),sort_keys=True))
    else:
        print(json.dumps({"schema":SCHEMA,"historical_counts":EXPECTED},
                         sort_keys=True))


if __name__=="__main__":
    main()
