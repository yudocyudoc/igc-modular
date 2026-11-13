"""CLI: prepare a reproducible Buffalo input from the same public case as D/M."""
import argparse
import json
import sys
from pathlib import Path

from arena.coffee_domain import build_case
from arena.coffee_adapters.b import prepare
from arena.common import ArenaError


def main(argv=None):
    ap = argparse.ArgumentParser(description="Buffalo coffee public input, zero provider/solver")
    ap.add_argument("--public-dir", required=True)
    ap.add_argument("--assumptions", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    try:
        case = build_case(args.public_dir, args.assumptions)
        payload = prepare(case, Path(args.out))
        print(json.dumps({"status": "BUFFALO_INPUT_PREPARED_NO_PROVIDER",
                          "case_sha256": payload["case_sha256"],
                          "provider_posts": 0, "scientific_lock_created": False}))
        return 0
    except (ArenaError, KeyError, ValueError, OSError, TypeError) as exc:
        print(json.dumps({"status": "STOPPED", "reason": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
