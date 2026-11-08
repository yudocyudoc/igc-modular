"""One entry point. No secret values accepted on the command line or printed."""
import argparse
import getpass
import json
import os
from pathlib import Path
import sys

from . import orchestrator
from .common import ArenaError, read_json
from .connections import Connections
from .data import ingest
from .legacy import verify
from .github import GitHub
from .setup import link_github


def _summary(result, root):
    run = result["run"]
    score = result.get("fixture_score", result.get("score", {}))
    return {"status": run["status"], "evidence_kind": result["evidence_kind"],
            "result": str(Path(root).resolve()/"result.json"),
            "candidate_denominator": score.get("candidate_denominator"),
            "paired_available": score.get("paired_available"), "consumption": run["consumption"]}


def parser():
    p = argparse.ArgumentParser(prog="arena", description="Modular experiment coordinator; no credential copies between experiments.")
    p.add_argument("--connections", type=Path, default=Path("connections.toml"))
    commands = p.add_subparsers(dest="command", required=True)
    c = commands.add_parser("check", help="Check data/access before spending compute")
    c.add_argument("experiment", type=Path)
    c = commands.add_parser("run", help="Run the whole experiment through one entry point")
    c.add_argument("experiment", type=Path)
    c.add_argument("--out", required=True, type=Path)
    c.add_argument("--authorize", action="store_true", help="One approval for the complete configured live lot")
    for name in ("resume", "status", "report"):
        c = commands.add_parser(name)
        c.add_argument("run", type=Path)
    c = commands.add_parser("ingest", help="Admit partial CSV/JSON independently of experiment eligibility")
    c.add_argument("source", type=Path)
    c.add_argument("--time-column", default="time")
    c.add_argument("--value-column", default="delivered")
    c.add_argument("--time-unit", default="hours")
    commands.add_parser("verify-upstream")
    c = commands.add_parser("connections", help="Reuse environment/OS-vault/gh connections")
    connection_commands = c.add_subparsers(dest="operation", required=True)
    connection_commands.add_parser("status", help="Show availability and source, never values")
    connection_commands.add_parser("capture", help="Save already supplied environment credentials once in the OS vault")
    c = connection_commands.add_parser("save", help="Store once in the native OS vault")
    c.add_argument("connection")
    c.add_argument("key")
    c.add_argument("--from-env", help="Import an existing variable; its value is never an argument")
    c = connection_commands.add_parser("link-github", help="Reuse existing GitHub secrets; provision only missing bindings once")
    c.add_argument("--repository", required=True)
    c.add_argument("--apply", action="store_true", help="Apply the displayed connection setup; never runs compute")
    return p


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    p = parser()
    args = p.parse_args(argv)
    try:
        # Offline fixture and data operations do not even open a credential store.
        connections = Connections.load(args.connections) if args.connections.exists() else Connections({})
        if args.command == "check":
            result = orchestrator.check(args.experiment, connections)
        elif args.command == "run":
            result = _summary(orchestrator.run(args.experiment, args.out, connections, authorize=args.authorize), args.out)
        elif args.command == "resume":
            result = _summary(orchestrator.resume(args.run, connections), args.run)
        elif args.command == "status":
            result = orchestrator.status(args.run)
        elif args.command == "report":
            print((args.run/"report.md").read_text(encoding="utf-8"))
            return 0
        elif args.command == "verify-upstream":
            result = verify()
        elif args.command == "ingest":
            data = ingest(args.source, time_column=args.time_column, value_column=args.value_column, time_unit=args.time_unit)
            result = {key: value for key,value in data.items() if key != "observations"}
        elif args.operation == "status":
            result = {"scope": "LOCAL_CONNECTIONS_ONLY", "github_actions_secrets": "NOT_QUERIED",
                      "note": "A missing local Buffalo/R2 credential does not mean the existing GitHub secret is missing.",
                      "connections": connections.check()}
        elif args.operation == "capture":
            result = connections.capture_environment()
        elif args.operation == "link-github":
            import re
            if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", args.repository):
                raise ArenaError("Invalid GitHub repository.")
            result = link_github(GitHub(args.repository, connections.resolve("github", "token")), connections, apply=args.apply)
        else:
            if args.from_env:
                value = os.environ.get(args.from_env)
            else:
                if not sys.stdin.isatty():
                    raise ArenaError("Use an existing environment variable or an interactive hidden prompt, not a secret in argv.")
                value = getpass.getpass("Credential (hidden): ")
            if not value:
                raise ArenaError("No credential supplied; nothing stored.")
            connections.store(args.connection, args.key, value)
            result = {"stored": True, "connection": args.connection, "key": args.key, "backend": "OS_VAULT"}
        print(json.dumps(result, indent=2, allow_nan=False))
        return 0
    except (ArenaError, ValueError, OSError) as error:
        print(json.dumps({"status": "STOPPED", "reason": str(error)}), file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("Monitoring interrupted. Use resume for this recorded run; do not dispatch a replacement.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
