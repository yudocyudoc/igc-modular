"""Cloud execution workspace for byte-preserved D/M/B originals.

No source clone from IGC or sd-ai at runtime. Scientific source and historical
consequences live in this package; only standard libraries/npm/image are fetched.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from .common import ArenaError, read_json, write_json

VENDOR = Path(__file__).resolve().parent / "_vendor"
IMAGE = "openmodelica/openmodelica@sha256:8993c8273224aeacbc018f351c00d60879c5aec386c77a58019318c44c938c9b"
MSL = ("https://github.com/modelica/ModelicaStandardLibrary.git", "6626538a236a34a390655b55d5e8c906bfe31772")
SD = ("https://github.com/modelica-3rdparty/SystemDynamics.git", "b986a2ea354ab550d627a392f857ad7c9997d961")
OLD_REF = "refs/heads/experiment/arena-ct00-ct02-20261107"
ADAPTER_FILES = (
    "scripts/arena_cafe/ct03_dm_execute_ten_once.sh",
    "scripts/arena_cafe/ct03_m_revision_execute_once.sh",
    "scripts/arena_cafe/ct03_b_producer_rounds_once.sh",
    "scripts/arena_cafe/ct03_b_physical_execute_once.sh",
    "scripts/arena_b_ct03_native_runner.mjs",
)


def verify(*, include_history=True):
    manifest = read_json(VENDOR/"ENGINES_MANIFEST.json")
    count = 0
    for row in manifest["files"]:
        relative = Path(row["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ArenaError("Invalid engine manifest path.")
        if not include_history and relative.parts[0] == "ct02":
            continue
        path = VENDOR/relative
        if not path.is_file() or path.is_symlink():
            raise ArenaError("Missing original engine resource: "+row["path"])
        raw = path.read_bytes()
        blob = hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()
        if blob != row["git_blob"]:
            raise ArenaError("Original engine resource changed: "+row["path"])
        count += 1
    return {"schema":"arena.engines-verification/1", "files":count, "unchanged":True,
            "history_checked":include_history, "igc_commit":manifest["igc_commit"],
            "buffalo_commit":manifest["buffalo_commit"], "new_omc":0, "provider_posts":0}


def prepare(out, *, role="contracts"):
    if role not in ("contracts","custodian","dm","b","lock","evaluator"):
        raise ArenaError("Unknown runtime role.")
    verify(include_history=role in ("contracts","dm"))
    out = Path(out).resolve()
    if out.exists():
        raise ArenaError("Refuse to overwrite an execution workspace.")
    shutil.copytree(VENDOR/"igc", out, ignore=shutil.ignore_patterns("__pycache__","*.pyc","tests"))
    if role in ("contracts","b"):
        shutil.copytree(VENDOR/"buffalo", out/"upstream/sd-ai")
    if role in ("contracts","dm"):
        shutil.copytree(VENDOR/"ct02", out/"artifacts/ct03-reuse/original")
    patched = []
    for name in ADAPTER_FILES:
        target = out/name
        text = target.read_text(encoding="utf-8")
        if text.count(OLD_REF) != 1:
            raise ArenaError("Operational guard relocation differs from frozen source: "+name)
        target.write_text(text.replace(OLD_REF,"refs/heads/main"),encoding="utf-8",newline="\n")
        patched.append(name)
    info = {"schema":"arena.runtime-workspace/1","role":role,
            "scientific_sources_modified":False,
            "operational_guard_relocation":{"from":OLD_REF,"to":"refs/heads/main","files":patched},
            "historical_initials_copied":role in ("contracts","dm"),
            "buffalo_source_copied":role in ("contracts","b"),
            "external_engine_repositories_read":False}
    write_json(out/"runtime.json",info)
    return info


def execute(workspace, argv, *, env=None, private_log=None):
    """Argument arrays only. Secrets stay in the job environment, never argv."""
    options = {"cwd":str(workspace),"env":os.environ.copy() if env is None else env}
    if private_log:
        with Path(private_log).open("wb") as log:
            code = subprocess.run(argv,stdout=log,stderr=subprocess.STDOUT,**options).returncode
    else:
        code = subprocess.run(argv,**options).returncode
    if code:
        raise ArenaError("Execution command failed; attempt retained, no automatic retry.")
    return code


def module(workspace, name, *args, env=None):
    return execute(workspace,[sys.executable,"-m","scripts.arena_cafe."+name,*map(str,args)],env=env)


def libraries():
    base = Path(os.environ["RUNNER_TEMP"])/"e1-libs"
    base.mkdir(parents=True,exist_ok=True)
    (base.parent/"e1-home").mkdir(exist_ok=True)
    for folder,(repository,commit) in (("msl",MSL),("systemdynamics",SD)):
        target = base/folder
        if target.exists():
            raise ArenaError("Refuse to reuse an unverified preexisting library checkout.")
        target.mkdir()
        for args in (["git","init","-q"],["git","remote","add","origin",repository],
                     ["git","fetch","--quiet","--depth","1","origin",commit],
                     ["git","checkout","--quiet","--detach","FETCH_HEAD"]):
            execute(target,args)
        actual = subprocess.check_output(["git","rev-parse","HEAD"],cwd=target,text=True).strip()
        if actual != commit:
            raise ArenaError("Standard library identity differs from pinned runtime.")
    execute(base,["docker","pull",IMAGE])
    return {"image":IMAGE,"msl_commit":MSL[1],"systemdynamics_commit":SD[1]}


def verify_ct02(workspace):
    root = Path(workspace)
    dest = root/"artifacts/ct03-reuse/reused-original-two.json"
    module(root,"ct03_reuse_ct02","--original-artifact-dir",
           "artifacts/ct03-reuse/original","--out",dest)
    result = read_json(dest)
    if result["new_omc"] != 0 or len(result["items"]) != 2:
        raise ArenaError("Historical reuse did not verify the two original consequences.")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command",required=True)
    commands.add_parser("verify")
    item=commands.add_parser("prepare")
    item.add_argument("--out",type=Path,required=True)
    item.add_argument("--role",default="contracts")
    item=commands.add_parser("ct02")
    item.add_argument("--workspace",type=Path,required=True)
    commands.add_parser("libraries")
    args=parser.parse_args(argv)
    if args.command=="verify": result=verify()
    elif args.command=="prepare": result=prepare(args.out,role=args.role)
    elif args.command=="ct02": result=verify_ct02(args.workspace)
    else: result=libraries()
    print(json.dumps(result,indent=2))


if __name__=="__main__":
    main()
