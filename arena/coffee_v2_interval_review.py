"""V2.1 P07: local, video-grounded review of manual/machine intervals.

This is an observation instrument, NOT a service-time estimator. The
original media stays with its owner. No POS, synthetic truth, G3, provider,
solver or private case is opened. Outputs are aggregate-only.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import json
import math
from pathlib import Path
import re
import sys

from .common import ArenaError, write_json

SCHEMA = "arena.coffee-v2.p07-directed-interval-review/1"
PHASES = {"MANUAL_ACTIVE": "OPERATOR", "MACHINE_BUSY": "MACHINE"}
BOUNDARIES = {"OBSERVED", "CENSORED"}
REVIEW_STATES = {"DRAFT", "DUAL_CONFIRMED", "DISPUTED"}
SOURCES = {"VIDEO_DIRECT", "LEGACY_ANNOTATION"}
FIELDS = (
    "event_id", "window_id", "task_id", "resource_id", "resource_type",
    "phase", "start_s", "end_s", "start_boundary", "end_boundary",
    "source", "review_state", "primary_reviewer", "second_reviewer",
    "confidence", "evidence_ref",
)
HEX_SHA = re.compile(r"^sha256:[a-f0-9]{64}$")
CLOCK = "ORIGINAL_VIDEO_SECONDS"
MAX_WINDOWS = 200
MAX_ROWS = 10000


def need(ok, reason):
    if not ok:
        raise ArenaError("COFFEE_V2_INTERVAL_" + reason)


def number(value, label):
    try:
        x = float(value)
    except (ValueError, TypeError):
        raise ArenaError("COFFEE_V2_INTERVAL_INVALID_" + label) from None
    need(math.isfinite(x), "NONFINITE_" + label)
    return x


def sha_file(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def create_template(out):
    """No fabricated observations: creates an empty private review worksheet."""
    out = Path(out)
    need(not out.exists(), "OUTPUT_EXISTS")
    out.mkdir(parents=True)
    manifest = {
        "schema": SCHEMA, "clock": CLOCK,
        "media_sha256": "REPLACE_WITH_SHA256_OF_ORIGINAL_MEDIA",
        "media_duration_s": None,
        "review_scope": "EXPLORATORY_DESCRIPTIVE_NO_G3",
        "study_question": "S2_MACHINE_BUSY_LIMIT_VS_S5_MANUAL_WORK_LIMIT",
        "windows": [],
    }
    write_json(out / "manifest.template.json", manifest, exclusive=True)
    with (out / "intervals.template.csv").open("x", encoding="utf-8", newline="") as f:
        csv.writer(f).writerow(FIELDS)
    (out / "INSTRUCTIONS.md").write_text(
        "# Revisión dirigida P07 — plantilla privada\n\n"
        "1. Conservar el video original localmente; obtener su SHA-256 y "
        "duración real en segundos. Completar manifest y declarar ventanas "
        "ANTES de codificar eventos (incluye intervalos tranquilos y activos).\n"
        "2. Cada ventana: id, start_s, end_s, stratum (ACTIVITY/QUIET/UNCERTAIN) "
        "y selection_reason. No convertir proxies de presencia o pagos POS "
        "sintéticos en duración de servicio.\n"
        "3. Una fila por intervalo visible de MANUAL_ACTIVE (OPERATOR) o "
        "MACHINE_BUSY (MACHINE); vincular la misma tarea mediante task_id "
        "opaco cuando sea defendible. Registrar inicio/fin exactos en reloj "
        "del video y marcar CENSORED si ocurrió fuera del campo o ventana.\n"
        "4. Un DUAL_CONFIRMED exige dos revisores distintos, cotejo directo "
        "contra el video, evidencia_ref local y confianza HIGH; el programa "
        "comprueba declaraciones y coherencia, no puede certificar revisión humana.\n"
        "5. Usar --media-file al evaluar: se comprueba SHA, pero nunca se "
        "sube ni modifica el video. No subir manifest, CSV ni video a GitHub.\n"
        "6. Salida: JSON y REVIEW.md con agregados, jamás IDs/filas/frames. "
        "Aunque haya intervalos elegibles, NO se infiere automáticamente "
        "capacidad, cuello de botella, rentabilidad ni recomendación S2/S5.\n",
        encoding="utf-8",
    )
    return out


def validate_manifest(manifest):
    need(type(manifest) is dict and manifest.get("schema") == SCHEMA
         and manifest.get("clock") == CLOCK
         and manifest.get("review_scope") == "EXPLORATORY_DESCRIPTIVE_NO_G3"
         and manifest.get("study_question") ==
         "S2_MACHINE_BUSY_LIMIT_VS_S5_MANUAL_WORK_LIMIT",
         "MANIFEST_CONTRACT")
    need(type(manifest.get("media_sha256")) is str and
         HEX_SHA.fullmatch(manifest["media_sha256"]) is not None,
         "MEDIA_SHA256_REQUIRED")
    duration = number(manifest.get("media_duration_s"), "MEDIA_DURATION")
    need(0 < duration <= 86400, "MEDIA_DURATION_RANGE")
    windows = manifest.get("windows")
    need(type(windows) is list and 0 < len(windows) <= MAX_WINDOWS,
         "WINDOWS_REQUIRED")
    out = {}
    for w in windows:
        need(type(w) is dict and
             type(w.get("id")) is str and bool(w["id"].strip()) and
             w["id"] not in out and
             type(w.get("selection_reason")) is str and
             len(w["selection_reason"].strip()) >= 12 and
             w.get("stratum") in {"ACTIVITY", "QUIET", "UNCERTAIN"},
             "WINDOW_PROVENANCE")
        start = number(w.get("start_s"), "WINDOW_START")
        end = number(w.get("end_s"), "WINDOW_END")
        need(0 <= start < end <= duration, "WINDOW_BOUNDS")
        out[w["id"]] = (start, end, w["stratum"])
    ordered = sorted((start, end) for start, end, _ in out.values())
    need(all(ordered[i][0] >= ordered[i-1][1]
             for i in range(1, len(ordered))), "WINDOWS_OVERLAP")
    return out


def parse_rows(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        need(reader.fieldnames == list(FIELDS), "CSV_COLUMNS")
        rows = []
        for row in reader:
            need(len(rows) < MAX_ROWS and None not in row and
                 all(value is not None for value in row.values()),
                 "CSV_MALFORMED_OR_TOO_LARGE")
            rows.append(row)
    return rows


def analyze(manifest, rows, *, media_file):
    """Media SHA attestation; qualified rows still need scientific review."""
    windows = validate_manifest(manifest)
    need(media_file is not None and Path(media_file).is_file(),
         "ORIGINAL_VIDEO_FILE_REQUIRED")
    need(sha_file(media_file) == manifest["media_sha256"],
         "MEDIA_HASH_MISMATCH")
    need(type(rows) is list and len(rows) <= MAX_ROWS, "INVALID_ROWS")
    seen = set()
    counts = Counter()
    strata = Counter()
    qualified = []
    for row in rows:
        need(type(row) is dict and set(row) == set(FIELDS)
             and all(type(v) is str for v in row.values()),
             "INVALID_ROW_SHAPE")
        eid = row["event_id"]
        need(bool(eid.strip()) and eid not in seen, "DUPLICATE_EVENT_ID")
        seen.add(eid)
        need(row["window_id"] in windows and row["phase"] in PHASES
             and row["resource_type"] == PHASES[row["phase"]]
             and row["start_boundary"] in BOUNDARIES
             and row["end_boundary"] in BOUNDARIES
             and row["source"] in SOURCES
             and row["review_state"] in REVIEW_STATES
             and row["confidence"] in {"HIGH", "MEDIUM", "LOW"}
             and all(row[k].strip() for k in
                     ("task_id", "resource_id", "primary_reviewer")),
             "INVALID_INTERVAL_CONTRACT")
        a, b, stratum = windows[row["window_id"]]
        start = number(row["start_s"], "EVENT_START")
        end = number(row["end_s"], "EVENT_END")
        need(a <= start < end <= b, "INTERVAL_OUTSIDE_WINDOW")
        if row["start_boundary"] == "CENSORED":
            need(math.isclose(start, a, abs_tol=1e-9), "LEFT_CENSOR_BOUNDARY")
        if row["end_boundary"] == "CENSORED":
            need(math.isclose(end, b, abs_tol=1e-9), "RIGHT_CENSOR_BOUNDARY")
        if row["review_state"] == "DUAL_CONFIRMED":
            need(row["second_reviewer"].strip()
                 and row["second_reviewer"] != row["primary_reviewer"]
                 and row["evidence_ref"].strip() and
                 row["source"] == "VIDEO_DIRECT",
                 "DUAL_REVIEW_PROVENANCE")
        counts["interval_rows"] += 1
        counts[row["phase"]] += 1
        strata[stratum] += 1
        if row["start_boundary"] == "CENSORED" or row["end_boundary"] == "CENSORED":
            counts["censored_intervals"] += 1
        eligible = (row["review_state"] == "DUAL_CONFIRMED"
                    and row["confidence"] == "HIGH"
                    and row["start_boundary"] == "OBSERVED"
                    and row["end_boundary"] == "OBSERVED")
        if eligible:
            qualified.append((row["window_id"], row["resource_id"],
                              row["task_id"], row["phase"], start, end))
            counts["qualified_" + row["phase"]] += 1
            counts["qualified_" + row["phase"] + "_seconds"] += end - start
        else:
            counts["not_qualified"] += 1
    # A single exclusive resource cannot run two qualified incompatible tasks.
    for i, left in enumerate(qualified):
        for right in qualified[i+1:]:
            if left[0] != right[0] or left[1] != right[1]:
                continue
            overlap = min(left[5], right[5]) - max(left[4], right[4])
            need(overlap <= 1e-9, "EXCLUSIVE_RESOURCE_OVERLAP")
    overlaps = []
    for i, left in enumerate(qualified):
        if left[3] != "MANUAL_ACTIVE":
            continue
        for right in qualified:
            if right[0] != left[0] or right[3] != "MACHINE_BUSY":
                continue
            intersection = max(0.0, min(left[5], right[5]) -
                               max(left[4], right[4]))
            if intersection > 1e-9:
                overlaps.append((intersection, left[2] == right[2]))
    counts["overlap_pairs_manual_machine"] = len(overlaps)
    counts["overlap_pair_seconds_not_union"] = sum(x for x, _ in overlaps)
    counts["same_task_overlap_pairs"] = sum(1 for _, same in overlaps if same)
    status = ("MEASURE_FIRST" if not qualified else
              "INTERVAL_CANDIDATES_NEED_IDENTIFIABILITY_REVIEW")
    return {
        "schema": SCHEMA,
        "status": status,
        "question": "S2 versus S5; NO causal bottleneck selected",
        "source_verified_by_sha256": True,
        "source_sha256": manifest["media_sha256"],
        "review_scope": manifest["review_scope"],
        "window_count": len(windows),
        "reviewed_window_seconds": sum(b-a for a, b, _ in windows.values()),
        "window_strata": dict(sorted(Counter(w[2] for w in windows.values()).items())),
        "rows_by_window_stratum": dict(sorted(strata.items())),
        "aggregate": dict(sorted(counts.items())),
        "eligible_definition": "dual-asserted direct-video HIGH confidence with two observed endpoints",
        "dual_review_is_self_attested_not_machine_verified": True,
        "censored_and_legacy_rows_never_calibrate": True,
        "overlap_pair_seconds_not_distinct_occupancy": True,
        "service_capacity_not_identified": True,
        "demand_not_observed_from_video_proxies": True,
        "no_S2_S5_recommendation": True,
        "no_POS_or_reserved_truth_access": True,
        "no_lock_or_G3": True,
        "external_consumption": {"R2": 0, "OMC": 0, "provider_POST": 0},
    }


def export(result, out):
    out = Path(out)
    need(not out.exists(), "OUTPUT_EXISTS")
    out.mkdir(parents=True)
    write_json(out / "p07-interval-summary.json", result, exclusive=True)
    report = (
        "# P07 — intervalos manuales/máquina, resultado agregado\n\n"
        f"- Estado: **{result['status']}**.\n"
        f"- Ventanas: {result['window_count']}; "
        f"duración total revisada: {result['reviewed_window_seconds']:.3f} s.\n"
        f"- Intervalos registrados: {result['aggregate'].get('interval_rows', 0)}; "
        f"elegibles manuales: {result['aggregate'].get('qualified_MANUAL_ACTIVE', 0)}; "
        f"elegibles máquina: {result['aggregate'].get('qualified_MACHINE_BUSY', 0)}.\n"
        f"- Pares de solapamiento: "
        f"{result['aggregate'].get('overlap_pairs_manual_machine', 0)} "
        "(un par no equivale a ocupación total ni productividad).\n"
        "- La doble revisión está declarada, no demostrada por software. "
        "No se asignan tiempos a intervalos censurados.\n"
        "- No se identifica aún cuello de botella S2/S5, demanda, "
        "capacidad física, espera ni rentabilidad. Requiere contraste "
        "de identificabilidad y representatividad antes de B0/Sx.\n"
        "- CERO acceso a POS, verdad reservada, R2, provider, OMC, G3.\n"
    )
    (out / "REVIEW.md").write_text(report, encoding="utf-8")
    return result["status"]


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--init", action="store_true",
                   help="Create blank private review sheet; no media needed")
    p.add_argument("--manifest", type=Path)
    p.add_argument("--intervals", type=Path)
    p.add_argument("--media-file", type=Path)
    p.add_argument("--out", required=True, type=Path)
    options = p.parse_args(argv)
    try:
        if options.init:
            need(not any((options.manifest, options.intervals,
                          options.media_file)), "INIT_EXCLUSIVE")
            create_template(options.out)
            status = "EMPTY_PRIVATE_REVIEW_TEMPLATE"
        else:
            need(options.manifest is not None and
                 options.intervals is not None, "INPUTS_REQUIRED")
            data = analyze(json.loads(options.manifest.read_text(encoding="utf-8")),
                           parse_rows(options.intervals),
                           media_file=options.media_file)
            status = export(data, options.out)
        print(json.dumps({"status": status, "paid_consumption": 0}, sort_keys=True))
        return 0
    except (ArenaError, ValueError, TypeError, KeyError, OSError,
            UnicodeDecodeError, json.JSONDecodeError) as exc:
        print(json.dumps({
            "status": "STOPPED_NO_EXTERNAL_CONSUMPTION",
            "reason": str(exc) if isinstance(exc, ArenaError) else "INVALID_PRIVATE_INPUT",
        }), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
