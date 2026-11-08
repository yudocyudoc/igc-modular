"""Ingest partial observations without fabricating cases, timing, or continuity."""
import csv
import hashlib
import math
from pathlib import Path

from .common import ArenaError, read_json


def ingest(path, *, time_column="time", value_column="delivered", time_unit="hours"):
    path = Path(path)
    raw = path.read_bytes()
    issues = []
    if path.suffix.lower() == ".csv":
        with path.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.reader(stream)
            headers = next(reader, [])
            values = [row for row in reader if row]
        if len(headers) != len(set(headers)):
            issues.append({"code": "AMBIGUOUS_COLUMNS", "action": "Map unique columns before numeric use."})
            rows = [{"columns": [{"position": i, "name": headers[i] if i < len(headers) else None, "value": value}
                                  for i,value in enumerate(record)]} for record in values]
        else:
            rows = []
            for record in values:
                fields = dict(zip(headers, record))
                if len(record) > len(headers):
                    fields["extra_values"] = record[len(headers):]
                rows.append(fields)
    elif path.suffix.lower() == ".json":
        obj = read_json(path)
        rows = obj if isinstance(obj, list) else obj.get("observations", [])
    else:
        raise ArenaError("Supported observation sources: CSV and JSON. Originals are preserved.")
    if not rows:
        raise ArenaError("Source has no observation records.")
    observations, mapped = [], set()
    for index, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            raise ArenaError(f"Record {index} is not an object.")
        point = {"record": index, "fields": row}
        for target, column in (("time", time_column), ("value", value_column)):
            value = row.get(column)
            if value not in (None, ""):
                try:
                    number = float(value)
                except (TypeError, ValueError):
                    issues.append({"record": index, "field": target, "code": "NOT_NUMERIC"})
                    continue
                if not math.isfinite(number):
                    issues.append({"record": index, "field": target, "code": "NONFINITE"})
                    continue
                point[target] = number
                mapped.add(target)
        observations.append(point)
    capabilities = ["partial_observations"]
    if all("time" in row and "value" in row for row in observations):
        capabilities.append("timed_numeric_observations")
    # IDs merely present in a file are not validated identity or complete trajectories.
    return {"schema": "arena.dataset/1", "source_sha256": hashlib.sha256(raw).hexdigest(),
            "record_count": len(rows), "time_unit": time_unit,
            "capabilities": capabilities, "identity_validated": False,
            "continuity_certified": False, "issues": issues, "observations": observations}


def ct03_public(dataset, *, world, source_hash):
    from .legacy import load
    public = load("ct03_public")
    if dataset["time_unit"] != "hours":
        raise ArenaError("CT03 requires explicitly mapped hours. Source remains admitted as partial data.")
    if "timed_numeric_observations" not in dataset["capabilities"]:
        raise ArenaError("CT03 requires timed numeric cuts; source remains admitted as partial data.")
    observed = {}
    for row in dataset["observations"]:
        time = row["time"]
        if time in observed:
            raise ArenaError("CT03 requires unambiguous cuts; duplicate timestamps need explicit reconciliation.")
        observed[time] = row["value"]
    if set(observed) != {0, 1, 2, 4}:
        raise ArenaError("CT03 public input must contain exactly t0/t1/t2/t4; do not include reserved truth.")
    construction = {"schema": public.OBS_SCHEMA, "world_public_id": world, "condition_id": "C0",
                    "source_snapshot_hash": source_hash, "observable": "cumulative_delivered",
                    "time_unit": "hours", "observations": [
                        {"time": time, "delivered": observed[time]} for time in (0, 1, 2, 4)]}
    public.validate_construction({"source_hash": source_hash, "world": world, "condition": "C0"}, construction)
    return construction

