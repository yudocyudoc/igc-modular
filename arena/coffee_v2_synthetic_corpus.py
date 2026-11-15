"""Arena Coffee V2.1 P01/P02/P05/P12: custody-only census of synthetic corpus.

Audits the full, pre-existing ZIP in a trusted local custodian context.
Hashes every member, but parses ONLY allowed POS, line items, scenario
index and visual profile CSV. Never parses truth rows; never exports raw IDs,
seeds, scenario names, latent parameters, private paths or observed POS rows.
No engine, simulator, provider, R2 or held-out evaluation is invoked.
"""
from __future__ import annotations

from collections import Counter
from contextlib import closing
import copy
import argparse
import csv
import hashlib
import hmac
import io
import json
import math
from pathlib import Path
import secrets
import sqlite3
import stat
import sys
import zipfile

from .common import ArenaError, digest, write_json

SCHEMA = "arena.coffee-v2.synthetic-corpus-census/1"
ROOT = "sintetico_pico_v1/"
OUT = ROOT + "salida/"
MANIFEST = OUT + "manifest.json"
CONFIG = ROOT + "parametros_escenarios.json"
PINNED_ZIP_SHA256 = "dd18a787a1ac3dcd065fe54bff9a2f567d945c60d16e7a646444dacaa6ffbef9"
PINNED_CONTAINER_SHA256 = "4ff97ae4d8fe52a5c1d1701aa713fda09b6730ef63d9cbab23e6af30dfad2a5f"
MANIFEST_SCHEMA = "cafeteria.synthetic-output-manifest/2"
PARTITION_POLICY = "SCENARIO_GROUPED_HMAC_12_3_3/1"
FILES = (
    "acciones_clientes_truth.csv", "eventos_truth.csv",
    "hipotesis_pos_recepciones_video.csv", "ordenes_truth.csv",
    "perfil_carga_video.csv", "pos_line_items.csv", "pos_observed.csv",
    "pos_video_imputaciones.csv", "pos_video_imputaciones_lineas.csv",
    "resumen_escenarios.csv", "acciones_clientes_truth.json",
    "eventos_truth.json", "hipotesis_pos_recepciones_video.json",
    "ordenes_truth.json", "pos_line_items.json", "pos_observed.json",
    "pos_video_imputaciones.json", "pos_video_imputaciones_lineas.json",
    "resumen_escenarios.json",
)
REQUIRED = {MANIFEST, CONFIG, ROOT + "LEEME.md",
            ROOT + "generar_escenarios.py"} | {OUT + x for x in FILES}
CSV_FOR_SEMANTICS = (
    "resumen_escenarios.csv", "pos_observed.csv",
    "pos_line_items.csv", "perfil_carga_video.csv",
)
PARTS = {"CONSTRUCTION": 12, "DEVELOPMENT": 3, "EVALUATION": 3}
# Only private SQL gets exact source paths; public output is aggregated.
CONSUMPTION = (
    ("synthetic_pos", "SYNTHETIC_VIEW", "TIMESTAMP_AND_PAYMENT_TYPE",
     "VALIDATED_NOT_RELEASED", "time-varying paid POS", "not arrivals or deliveries"),
    ("synthetic_line_items", "SYNTHETIC_VIEW", "PAYMENT_ORDER_JOIN",
     "VALIDATED_NOT_RELEASED", "workload archetype candidate",
     "item and recipe load require a separate physical dossier"),
    ("visual_presence_profile", "VIDEO_PROXY", "MINUTE_PROXY_SOURCE_ONLY",
     "CONTEXT_ONLY", "relative time profile", "not arrival count or measured service"),
    ("scenario_summary", "CUSTODY_ONLY", "SCENARIO_REPLICATION_INDEX",
     "USED_FOR_PARTITION_ONLY", "scenario grouped split",
     "seeds and latent factors not disclosed to producer"),
    ("synthetic_truth", "EVALUATOR_ONLY", "BYTES_SHA256_ONLY",
     "RESERVED_NOT_READ_AS_ROWS", "future evaluation", "not model fitting"),
    ("video_pos_imputations", "SYNTHETIC_IMPUTATION", "MANIFEST_AND_HASH",
     "NOT_REAL_POS", "alternative linkage sensitivity", "draws are not independent sales"),
    ("physical_interventions", "NOT_IN_SOURCE", "NONE",
     "NOT_IMPLEMENTED", "B0 vs Sx", "18 input regimes are not S1-S5 treatments"),
    ("commercial_costs", "ASSUMED", "CONFIG_HASH_ONLY",
     "NOT_REAL_PROFIT", "conditional economics", "not verified business accounting"),
)


def need(condition, code):
    if not condition:
        raise ArenaError("COFFEE_V2_CORPUS_" + code)


def sha_file(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha_member(z, name):
    h = hashlib.sha256()
    with z.open(name, "r") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def member_class(name):
    if "_truth." in name:
        return "EVALUATOR_TRUTH"
    if name in ("pos_observed.csv", "pos_observed.json"):
        return "SYNTHETIC_POS"
    if name in ("pos_line_items.csv", "pos_line_items.json"):
        return "SYNTHETIC_LINE_ITEMS"
    if name.startswith("pos_video_imputaciones") or name.startswith("hipotesis_pos"):
        return "ALTERNATIVE_IMPUTATION"
    if name == "perfil_carga_video.csv":
        return "VISUAL_PROXY"
    if name.startswith("resumen_escenarios"):
        return "CUSTODY_SCENARIO_INDEX"
    return "PRIVATE_OTHER"


def read_csv(z, basename, must_have, max_rows):
    with z.open(OUT + basename) as stream:
        text_stream = io.TextIOWrapper(stream, encoding="utf-8-sig", newline="")
        reader = csv.DictReader(text_stream)
        headers = reader.fieldnames
        need(bool(headers) and len(headers) == len(set(headers))
             and set(must_have) <= set(headers), "CSV_HEADER_CONTRACT")
        result = []
        for row in reader:
            need(len(result) < max_rows and None not in row and
                 all(value is not None for value in row.values()),
                 "CSV_ROW_MALFORMED")
            result.append(row)
    return result


def integer(v, low, high, name):
    try:
        n = int(v)
    except (TypeError, ValueError):
        raise ArenaError("COFFEE_V2_CORPUS_BAD_" + name) from None
    need(str(n) == str(v) and low <= n <= high, "BAD_" + name)
    return n


def floating(v, low, high, name):
    try:
        n = float(v)
    except (TypeError, ValueError):
        raise ArenaError("COFFEE_V2_CORPUS_BAD_" + name) from None
    need(math.isfinite(n) and low <= n <= high, "BAD_" + name)
    return n


def stable_id(key, tag, value):
    return hmac.new(key, (tag + "\0" + value).encode("utf-8"),
                    hashlib.sha256).hexdigest()[:32]


def allocate(scenarios, key):
    need(type(key) is bytes and len(key) >= 32, "PRIVATE_KEY_REQUIRED")
    need(len(scenarios) == sum(PARTS.values()), "18_SCENARIOS_REQUIRED")
    ranked = sorted(scenarios, key=lambda s: (stable_id(key, "partition", s), s))
    out = {}
    offset = 0
    for part, amount in PARTS.items():
        for scenario in ranked[offset:offset + amount]:
            out[scenario] = part
        offset += amount
    need(len(out) == len(scenarios), "SPLIT_INCOMPLETE")
    return out


class SourceArchive:
    """Canonical names over either pinned archive; original bytes stay intact.

    The historical documentation package contains the same corpus under video2/.
    Expose only its 23 corpus members, never other observations or private files.
    This changes the container adapter, not source hashes or generated records.
    """
    def __init__(self, source, source_sha):
        self.archive = zipfile.ZipFile(source)
        self.prefix = "video2/" if source_sha == PINNED_CONTAINER_SHA256 else ""

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.archive.close()

    def infolist(self):
        if not self.prefix:
            return self.archive.infolist()
        result = []
        for info in self.archive.infolist():
            if info.filename.startswith(self.prefix) and info.filename[len(self.prefix):] in REQUIRED:
                item = copy.copy(info)
                item.filename = info.filename[len(self.prefix):]
                result.append(item)
        return result

    def getinfo(self, name):
        return self.archive.getinfo(self.prefix + name)

    def open(self, name, mode="r"):
        return self.archive.open(self.prefix + name, mode)

    def read(self, name):
        return self.archive.read(self.prefix + name)


def audit(source, *, key, expected_sha=None):
    """Return private catalog data and a sanitized public review.

    A matching ZIP checksum and 19 verified output digests attest bytes.
    Truth files are hashed, not interpreted or used for selection.
    """
    source = Path(source)
    need(source.is_file() and 0 < source.stat().st_size < 40_000_000,
         "LOCAL_SOURCE_ZIP_REQUIRED")
    actual = sha_file(source)
    need(actual == expected_sha if expected_sha is not None else
         actual in (PINNED_ZIP_SHA256, PINNED_CONTAINER_SHA256), "ZIP_SHA256_MISMATCH")
    try:
        with SourceArchive(source, actual) as z:
            infos = z.infolist()
            names = [i.filename for i in infos]
            need(len(names) == len(set(names)) and set(names) == REQUIRED
                 and all(not n.startswith("/") and "\\" not in n
                         and ".." not in n.split("/") for n in names),
                 "ZIP_MEMBERS_UNEXPECTED")
            need(all(not ((i.external_attr >> 16) & 0o170000 == 0o120000)
                     and i.file_size < 160_000_000
                     and i.compress_size > 0
                     for i in infos), "ZIP_LINK_OR_SIZE_UNSAFE")
            raw_manifest = z.read(MANIFEST)
            raw_config = z.read(CONFIG)
            manifest = json.loads(raw_manifest)
            config = json.loads(raw_config)
            need(manifest.get("schema") == MANIFEST_SCHEMA and
                 set(manifest.get("outputs", {})) == set(FILES)
                 and manifest.get("config_sha256") ==
                 hashlib.sha256(raw_config).hexdigest(),
                 "MANIFEST_VERSION_OR_CONFIG_HASH")
            need(config.get("schema") == "cafeteria.synthetic-scenario/1"
                 and config.get("interpretation", {}).get("parameters_are_observations")
                 is False and
                 config.get("interpretation", {}).get("generated_records_are_synthetic")
                 is True, "GENERATOR_PROVENANCE")
            design = config["design"]
            factors = (len(design["peak_arrivals_per_minute_scenarios"]) *
                       len(design["offpeak_load_factor_scenarios"]) *
                       len(design["queue_abandonment_patience_scenarios_minutes"]))
            nreps = integer(design["replications_per_combination"], 1, 20, "REPLICAS")
            need(factors == 18 and nreps == 3 and
                 manifest.get("scenario_combinations") == factors and
                 manifest.get("replications_per_combination") == nreps and
                 manifest.get("weekly_runs") == factors * nreps,
                 "FACTORIAL_COUNTS_MISMATCH")
            verified = []
            for basename in FILES:
                i = z.getinfo(OUT + basename)
                meta = manifest["outputs"][basename]
                need(type(meta) is dict and
                     meta.get("bytes") == i.file_size and
                     type(meta.get("sha256")) is str and
                     len(meta["sha256"]) == 64 and
                     sha_member(z, OUT + basename) == meta["sha256"],
                     "OUTPUT_SHA256_MISMATCH")
                verified.append({
                    "path": OUT + basename,
                    "class": member_class(basename),
                    "sha256": meta["sha256"],
                    "bytes": i.file_size,
                    "verification": "FULL_BYTE_SHA256",
                    "semantic_rows_read": basename in CSV_FOR_SEMANTICS,
                })
            scenario_rows = read_csv(
                z, "resumen_escenarios.csv",
                {"scenario_id", "replication", "seed", "synthetic",
                 "net_profit_mxn"}, 100)
            pos_rows = read_csv(
                z, "pos_observed.csv",
                {"scenario_id", "replication", "day_of_week", "pos_record_id",
                 "order_id", "pos_record_type", "sale_status", "synthetic",
                 "source_class", "timestamp_min_from_peak_start"}, 20000)
            item_rows = read_csv(
                z, "pos_line_items.csv",
                {"scenario_id", "replication", "day_of_week", "pos_record_id",
                 "order_id", "pos_line_id", "quantity", "synthetic",
                 "source_class"}, 20000)
            profile = read_csv(
                z, "perfil_carga_video.csv",
                {"minute_from_peak_start", "sample_seconds", "source_class",
                 "synthetic"}, 200)
    except (KeyError, ValueError, TypeError, RuntimeError, zipfile.BadZipFile,
            UnicodeDecodeError, csv.Error) as exc:
        raise ArenaError("COFFEE_V2_CORPUS_INVALID_SOURCE_STRUCTURE") from exc

    need(len(scenario_rows) == manifest["weekly_runs"],
         "SUMMARY_RUN_COUNT_CHANGED")
    case_keys, seeds, scenarios = set(), set(), set()
    for row in scenario_rows:
        sc = row["scenario_id"]
        need(bool(sc) and row["synthetic"].casefold() == "true"
             and not row["net_profit_mxn"].strip(), "SUMMARY_IS_NOT_SYNTHETIC_PROFIT_UNKNOWN")
        rep = integer(row["replication"], 1, nreps, "REPLICATION")
        seed = integer(row["seed"], 1, 2**63 - 1, "SEED")
        case = (sc, rep)
        need(case not in case_keys and seed not in seeds, "DUPLICATE_CASE_OR_SEED")
        case_keys.add(case)
        seeds.add(seed)
        scenarios.add(sc)
    need(len(scenarios) == factors and
         all({rep for sc, rep in case_keys if sc == scenario} ==
             set(range(1, nreps + 1)) for scenario in scenarios),
         "SCENARIO_REPLICA_COVERAGE")
    split = allocate(scenarios, key)

    horizon = floating(config["source"]["synthetic_peak_window_minutes"],
                       60, 180, "PEAK_HORIZON")
    pc = Counter()
    ic = Counter()
    paid = Counter()
    pos_index = {}
    seen_lines = set()
    after_horizon_pos = 0
    for row in pos_rows:
        sc = row["scenario_id"]
        rep = integer(row["replication"], 1, nreps, "POS_REP")
        day = integer(row["day_of_week"], 1, 7, "POS_DAY")
        case = (sc, rep)
        need(case in case_keys and row["synthetic"].casefold() == "true"
             and row["source_class"] == "synthetic_pos_view",
             "POS_CASE_OR_PROVENANCE")
        t = floating(row["timestamp_min_from_peak_start"], 0, 1440,
                     "POS_TIMESTAMP")
        after_horizon_pos += t > horizon + 1e-6
        event_kind = row["pos_record_type"]
        need(event_kind in {"sale", "refund"}, "UNKNOWN_POS_EVENT")
        record_id = row["pos_record_id"]
        need(bool(record_id) and bool(row["order_id"]), "EMPTY_POS_JOIN_ID")
        keypos = (sc, rep, day, record_id)
        need(keypos not in pos_index, "DUPLICATE_POS_ID")
        pos_index[keypos] = (row["order_id"], event_kind)
        pc[case] += 1
        paid[event_kind] += 1
    for row in item_rows:
        sc = row["scenario_id"]
        rep = integer(row["replication"], 1, nreps, "LINE_REP")
        day = integer(row["day_of_week"], 1, 7, "LINE_DAY")
        case = (sc, rep)
        need(case in case_keys and row["synthetic"].casefold() == "true"
             and row["source_class"] == "synthetic_pos_line_item",
             "LINE_CASE_OR_PROVENANCE")
        keypos = (sc, rep, day, row["pos_record_id"])
        need(keypos in pos_index and
             pos_index[keypos] == (row["order_id"], "sale"),
             "LINE_NOT_JOINED_TO_PAID_POS")
        line = (keypos, row["pos_line_id"])
        need(bool(row["pos_line_id"]) and line not in seen_lines,
             "DUPLICATE_LINE_ID")
        seen_lines.add(line)
        integer(row["quantity"], 1, 30, "ITEM_QUANTITY")
        ic[case] += 1
    profile_minutes = set()
    for row in profile:
        minute = integer(row["minute_from_peak_start"], 0, 110, "PROFILE_MINUTE")
        need(minute not in profile_minutes and
             integer(row["sample_seconds"], 1, 60, "SAMPLED_SECONDS") >= 1 and
             row["synthetic"].casefold() == "false" and
             row["source_class"] == "video_customer_presence_proxy_not_arrival_count",
             "PROFILE_NOT_VISUAL_PROXY")
        profile_minutes.add(minute)
    need(profile_minutes == set(range(manifest["video_proxy_minutes"])),
         "PROFILE_MINUTES_GAPPED")
    need(len(pos_rows) == manifest["pos_rows_synthetic"] and
         len(item_rows) == manifest["pos_line_items_synthetic"],
         "POS_MANIFEST_COUNTS_CHANGED")
    # Declare supplementary sources by their manifest cardinalities only,
    # not by treating video-derived link hypotheses as independent sales.
    need(manifest["video_receipt_linkage_hypothesis_rows"] == 4 and
         manifest["video_anchor_pos_imputation_rows"] == 300 and
         manifest["video_anchor_pos_imputation_line_rows"] == 400,
         "ALTERNATIVE_IMPUTATION_COUNTS_CHANGED")
    case_records = []
    for sc, rep in sorted(case_keys):
        case_records.append({
            "scenario_private": sc,
            "replication_private": rep,
            "partition": split[sc],
            "opaque_case_id": stable_id(key, "case", f"{sc}\0{rep}"),
            "weekly_source_rows": 1,
            "pos_rows": pc[(sc, rep)],
            "line_rows": ic[(sc, rep)],
        })
    need(len({x["opaque_case_id"] for x in case_records}) == len(case_records),
         "OPAQUE_CASE_COLLISION")
    counts = Counter(x["partition"] for x in case_records)
    need(dict(counts) == {k: v * nreps for k, v in PARTS.items()},
         "PARTITION_COUNTS_INCORRECT")
    public = {
        "schema": SCHEMA,
        "status": "FULL_SYNTHETIC_CORPUS_CENSUSED_NOT_INTERVENTION_EVALUATED",
        "source_zip_sha256": "sha256:" + actual,
        "synthetic_manifest_version": MANIFEST_SCHEMA,
        "archive_members_verified": len(REQUIRED),
        "output_member_sha256_verified": len(FILES),
        "truth_bytes_hashed_but_truth_rows_not_interpreted": True,
        "visual_proxy_semantics": "RELATIVE_INTENSITY_SHAPE_NOT_ARRIVAL_COUNTS",
        "generator_source": "SYNTHETIC_BEHAVIOR_WITH_UNVALIDATED_PHYSICAL_RATES",
        "scenario_conditions": factors,
        "replications_per_condition": nreps,
        "synthetic_weekly_runs": len(case_records),
        "days_per_synthetic_week": 7,
        "pos_synthetic_rows": len(pos_rows),
        "pos_paid_records": paid["sale"],
        "pos_refund_records": paid["refund"],
        "pos_line_item_rows": len(item_rows),
        "pos_rows_after_declared_peak_horizon": after_horizon_pos,
        "video_proxy_minute_rows": len(profile),
        "alternate_video_pos_imputation_rows_not_sales":
            manifest["video_anchor_pos_imputation_rows"],
        "alternative_linkage_hypotheses_not_sales":
            manifest["video_receipt_linkage_hypothesis_rows"],
        "source_has_distinct_B0_S1_to_S5_treatments": False,
        "real_coffee_service_times_identified": False,
        "business_net_profit_validated": False,
        "partition_policy": PARTITION_POLICY,
        "partition_units": "ENTIRE_SCENARIO_WITH_3_REPLICATIONS_AND_7_DAYS_EACH",
        "partition_case_counts": dict(sorted(counts.items())),
        "partition_seed_and_latent_labels_never_published": True,
        "independent_real_world_evidence": False,
        "status_of_V1_historical_holdout": "FROZEN_NOT_REUSED_AS_NEW_INDEPENDENT_G3",
        "native_provider_calls": 0,
        "omc_runs": 0,
        "new_synthetic_worlds": 0,
    }
    need(not any(s in json.dumps(public) for s in scenarios),
         "PRIVATE_SCENARIO_NAME_LEAK")
    return {"public": public,
            "cases": case_records, "files": verified,
            "key_fingerprint": hashlib.sha256(key).hexdigest()}


def export(result, *, private_out, public_out, key):
    private_out = Path(private_out).resolve()
    public_out = Path(public_out).resolve()
    need(not private_out.exists() and not public_out.exists() and
         private_out != public_out and
         private_out not in public_out.parents and
         public_out not in private_out.parents,
         "PRIVATE_PUBLIC_OUTPUT_COLLISION")
    private_out.mkdir(parents=True, mode=0o700)
    (private_out / "custody-key.bin").write_bytes(key)
    (private_out / "custody-key.bin").chmod(0o600)
    database = private_out / "catalog.sqlite"
    with closing(sqlite3.connect(database)) as conn:
        conn.executescript("""
            CREATE TABLE source_files(
                path TEXT PRIMARY KEY, class TEXT NOT NULL, sha256 TEXT NOT NULL,
                bytes INTEGER NOT NULL, verification TEXT NOT NULL,
                semantic_rows_read INTEGER NOT NULL
            );
            CREATE TABLE synthetic_cases(
                scenario_private TEXT NOT NULL, replication_private INTEGER NOT NULL,
                partition TEXT NOT NULL, opaque_case_id TEXT UNIQUE NOT NULL,
                weekly_source_rows INTEGER NOT NULL,
                pos_rows INTEGER NOT NULL, line_rows INTEGER NOT NULL,
                PRIMARY KEY(scenario_private, replication_private)
            );
            CREATE TABLE private_meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        """)
        conn.executemany("INSERT INTO source_files VALUES (:path,:class,:sha256,:bytes,:verification,:semantic_rows_read)",
                         result["files"])
        conn.executemany(
            """INSERT INTO synthetic_cases
               VALUES (:scenario_private,:replication_private,:partition,
                       :opaque_case_id,:weekly_source_rows,:pos_rows,:line_rows)""",
            result["cases"])
        conn.execute("INSERT INTO private_meta VALUES (?, ?)",
                     ("key_fingerprint", result["key_fingerprint"]))
        conn.execute("INSERT INTO private_meta VALUES (?, ?)",
                     ("source_zip_sha256", result["public"]["source_zip_sha256"]))
        conn.commit()
    database.chmod(0o600)
    public_out.mkdir(parents=True, mode=0o700)
    write_json(public_out / "corpus-coverage.json", result["public"], exclusive=True)
    with (public_out / "consumption-to-decision.csv").open("x", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(("group", "source_class", "operator", "consumption",
                         "intended_use", "limit"))
        writer.writerows(CONSUMPTION)
    msg = (
        "# Arena V2.1 — P01/P02 corpus sintético, inventario completo\n\n"
        f"Archivo ZIP fijado y {result['public']['output_member_sha256_verified']} "
        "salidas verificadas por SHA-256; las filas de truth NO se interpretaron.\n\n"
        f"{result['public']['scenario_conditions']} regímenes × "
        f"{result['public']['replications_per_condition']} réplicas = "
        f"{result['public']['synthetic_weekly_runs']} semanas sintéticas; "
        "no son tratamientos de personal/máquina.\n\n"
        f"POS {result['public']['pos_synthetic_rows']} filas; partidas "
        f"{result['public']['pos_line_item_rows']}; minutos proxy "
        f"{result['public']['video_proxy_minute_rows']}.\n\n"
        "La asignación por régimen sintético completo es "
        "CONSTRUCTION/DEVELOPMENT/EVALUATION = 36/9/9 semanas.\n"
        "La reserva sirve para evaluación interna de este generador, no para "
        "validación empresarial ni un G3 histórico restaurado.\n"
        "Ningún valor de parámetro oculto, semilla, nombre de escenario, "
        "ID de cliente o verdad del mundo se publica.\n"
        "Ninguna política S1-S5 está representada aquí: no comparar ROI.\n"
        "Salida: catálogo privado SQLite y clave bajo custodia; "
        "CSV/JSON públicos AGREGADOS solamente.\n"
    )
    (public_out / "REVIEW.md").write_text(msg, encoding="utf-8")
    write_json(public_out / "receipt.json", {
        "schema": SCHEMA,
        "outputs": {
            p.name: "sha256:" + sha_file(p)
            for p in public_out.iterdir() if p.name != "receipt.json"
        },
        "source_zip_sha256": result["public"]["source_zip_sha256"],
        "private_catalog_file_exported": False,
        "private_key_exported": False,
        "external_consumption": {"R2": 0, "provider": 0, "OMC": 0},
    }, exclusive=True)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--private-out", type=Path, required=True)
    parser.add_argument("--public-out", type=Path, required=True)
    parser.add_argument("--key-file", type=Path,
                        help="Existing private 32-byte secret for reproducible partition")
    options = parser.parse_args(argv)
    try:
        key = (options.key_file.read_bytes() if options.key_file
               else secrets.token_bytes(32))
        need(len(key) >= 32, "PRIVATE_KEY_REQUIRED")
        result = audit(options.source, key=key)
        export(result, private_out=options.private_out,
               public_out=options.public_out, key=key)
        print(json.dumps({
            "status": result["public"]["status"],
            "corpus_source_hash": result["public"]["source_zip_sha256"],
            "private_catalog_not_published": True,
            "paid_consumption": 0,
        }, sort_keys=True))
        return 0
    except (ArenaError, OSError, ValueError, TypeError, KeyError,
            zipfile.BadZipFile, json.JSONDecodeError, sqlite3.Error) as exc:
        print(json.dumps({
            "status": "STOPPED_NO_EXTERNAL_CONSUMPTION",
            "reason": str(exc) if isinstance(exc, ArenaError) else
                      "INVALID_PRIVATE_INPUT_OR_OUTPUT",
        }), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
