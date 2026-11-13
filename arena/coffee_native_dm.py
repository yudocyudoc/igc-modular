"""CLI-only offline native D/M preparation for coffee, outside the custody workflow.

Does not authorize a scientific lock, truth access, provider or OMC execution.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .common import ArenaError, write_json
from .coffee_domain import build_case
from .coffee_adapters.shared import case_guard


def prepare(public_dir, assumptions_path, out, *, arms=("D", "M"), verify_original=True,
            environment=None):
    if set(arms) != {"D", "M"} or len(arms) != 2:
        raise ArenaError("COFFEE_NATIVE_EXPECTED_D_AND_M")
    out = Path(out)
    if out.exists():
        raise ArenaError("COFFEE_NATIVE_REFUSE_OVERWRITE")
    case = case_guard(build_case(public_dir, assumptions_path, environment=environment))
    if verify_original:
        from .runtime import verify
        result = verify(include_history=False)
        if result.get("unchanged") is not True or result.get("files", 0) <= 0:
            raise ArenaError("COFFEE_NATIVE_UNCHANGED_ORIGINALS_NOT_VERIFIED")
    from .coffee_adapters import d, m
    # Generate both in memory before any output. Neither may read reserved data.
    d_files, d_manifest = d.generate(case)
    m_files, m_manifest = m.generate(case)
    out.mkdir(parents=True, exist_ok=False)
    write_json(out / "public-case.json", case, exclusive=True)
    d_record = d.emit(out / "D", "D", case, d_files, d_manifest)
    m_record = m.emit(out / "M", "M", case, m_files, m_manifest)
    report = {"schema": "arena.coffee-peak.native-dm-preparation/1",
              "status": "ORIGINAL_NATIVE_GENERATED_NOT_SIMULATED",
              "arms": {"D": d_record["candidate_count"],
                       "M": m_record["candidate_count"]},
              "truth_access": False, "provider_posts": 0, "new_omc": 0,
              "scientific_lock_created": False}
    write_json(out / "summary.json", report, exclusive=True)
    return report


def main(argv=None):
    cli = argparse.ArgumentParser(description="Coffee native D/M originals; zero external compute")
    cli.add_argument("--public-dir", required=True)
    cli.add_argument("--assumptions", required=True)
    cli.add_argument("--out", required=True)
    args = cli.parse_args(argv)
    try:
        report = prepare(args.public_dir, args.assumptions, args.out)
        print(json.dumps(report, sort_keys=True))
        return 0
    except (ArenaError, ValueError, OSError, TypeError, KeyError, ImportError) as exc:
        print(json.dumps({"status": "STOPPED", "reason": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
