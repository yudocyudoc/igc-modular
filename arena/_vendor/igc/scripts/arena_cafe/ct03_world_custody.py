"""CT-03 custody-side world factory, NOT activated by ordinary CI or import.

Reuses the existing Short E1 compositor, backend and bounded-queue class.
A custodian supplies one sealed configuration only AFTER method/protocol lock.
The source contains neither a selected world nor a default RNG seed.
No OMC/provider call. Private world bytes must stay in a separate evaluator job.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re

from scripts.arena_v0_contract import canonical, digest
from scripts.arena_m_visible_pulse import composer, backend, stimulus_only_replace, REGISTRY
from scripts.arena_cafe.ct03_public import PUBLIC_INPUT

SCHEMA = "igc-ct03-sealed-evaluator-world-source/1.0"
PUBLIC_SCHEMA = "igc-ct03-world-commitment-only/1.0"
AUTH = "CT03_POST_LOCK_CUSTODIAN_ONLY"


def require(ok, code):
    if not ok:
        raise ValueError(code)


def sha(raw):
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def validate(config):
    require(type(config) is dict and
            set(config) == {"world_public_id", "stage_count", "capacity", "response_time",
                            "custody_nonce", "protocol_sha256"},
            "CT03_WORLD_CONFIG_FIELDS")
    require(type(config["world_public_id"]) is str and
            re.fullmatch(r"[A-Za-z0-9_-]{1,64}",config["world_public_id"]) is not None,
            "CT03_WORLD_PUBLIC_ID")
    require(type(config["stage_count"]) is int and config["stage_count"] in (2,3),
            "CT03_WORLD_ONLY_TWO_OR_THREE_MATERIAL_STAGES")
    for name, lower, upper in (("capacity",1.2,2.8),
                               ("response_time",.5,1.5)):
        x=config[name]
        require(type(x) in (int,float) and lower <= x <= upper,
                "CT03_WORLD_PARAMETER_OUTSIDE_PREREGISTRATION:"+name)
    require(type(config["custody_nonce"]) is str and
            len(config["custody_nonce"]) >= 24 and
            re.fullmatch(r"[A-Za-z0-9_-]+",config["custody_nonce"]) is not None,
            "CT03_WORLD_NONCE_REQUIRED")
    require(type(config["protocol_sha256"]) is str and
            re.fullmatch(r"sha256:[0-9a-f]{64}",config["protocol_sha256"]) is not None,
            "CT03_WORLD_PROTOCOL_LOCK_REQUIRED")
    return config


def make_private_source(config):
    """Original E1 material chain: no reports, loss, buffer or new class."""
    validate(config)
    cfg, classes, _ = composer.load_registry(REGISTRY)
    possible=[]
    for key, graph in composer.enumerate_graphs(cfg,classes):
        mats=[node for node in graph["instances"]
              if node["role"] in ("preparation","dispatch","transit")]
        report=[node for node in graph["instances"] if node["role"]=="report"]
        if len(mats)==config["stage_count"] and not report:
            possible.append((key,graph))
    require(len(possible)==1,"CT03_WORLD_ORIGINAL_E1_MATERIAL_PATH_NOT_UNIQUE")
    original_key, original_graph=possible[0]
    graph=copy.deepcopy(original_graph)
    for instance in graph["instances"]:
        if instance["role"] not in ("preparation","dispatch","transit"):
            continue
        require(instance["class_id"]=="bounded-queue",
                "CT03_WORLD_UNEXPECTED_NATIVE_CLASS")
        original_class=classes[instance["class_id"]]["parameters"]
        for param,value in (("maxThroughput",config["capacity"]),
                            ("responseTime",config["response_time"])):
            bounds=original_class[param]
            require(bounds["min"]<=value<=bounds["max"],
                    "CT03_WORLD_OUTSIDE_ORIGINAL_MOLECULE_BOUNDS")
            instance["parameters"][param]=value
    composer.check_graph(graph,cfg,classes)
    require(composer.canonical(graph)==original_key,
            "CT03_WORLD_TOPOLOGY_CHANGED_BY_PARAMETERIZATION")
    raw=backend.render_model("CT03SealedWorld",graph,cfg,classes)
    rewritten=stimulus_only_replace(raw,PUBLIC_INPUT["pulse_rate"],
                                     PUBLIC_INPUT["pulse_end"])
    require(rewritten.count("    Modelica.Blocks.Sources.RealExpression stimulus(y=if time < 2 then 1.7 else 0);")==1
            and "    deliveredTotal=" in rewritten and "der(" not in rewritten and
            "when " not in rewritten,"CT03_WORLD_RENDER_CHANGED_MECHANISM")
    modelica="\n".join([
        "within;","package ArenaCT03Sealed",rewritten,
        '  annotation(uses(Modelica(version="4.0.0"),SystemDynamics(version="2.1.2")));',
        "end ArenaCT03Sealed;",""
    ])
    cmds="\n".join([
        "getVersion();",
        'loadFile("/repo/src/modelica/IGCMolecules.mo");',
        'loadFile("/repo/src/modelica/IGCInformationMolecules.mo");',
        'loadFile("private_world.mo");',
        "checkModel(ArenaCT03Sealed.CT03SealedWorld);",
        "print(getErrorString());",
        'simulate(ArenaCT03Sealed.CT03SealedWorld,startTime=0,stopTime=8,'
        'numberOfIntervals=64,method="euler",outputFormat="csv",'
        'fileNamePrefix="sealed_world");',
        "print(getErrorString());",""
    ])
    return modelica,cmds,graph,original_key


def prepare_private(config, private_out: Path):
    """Never publish private_model or native world graph as producer artifact."""
    validate(config)
    private_out=Path(private_out)
    require(not private_out.exists(),"CT03_WORLD_PRIVATE_OUTPUT_EXISTS")
    modelica,commands,graph,key=make_private_source(config)
    private_out.mkdir(parents=True)
    (private_out/"private_world.mo").write_text(modelica,encoding="utf-8",newline="\n")
    (private_out/"simulate.mos").write_text(commands,encoding="utf-8",newline="\n")
    private_manifest={
        "schema":SCHEMA,"world_private_config":config,
        "graph":graph,"original_e1_topology_key":key,
        "modelica_sha256":sha(modelica.encode()),
        "script_sha256":sha(commands.encode()),
        "source_definition_sha256":digest(PUBLIC_INPUT),
        "actual_omc_executions":0,
        "planned_omc_executions":1,
        "provider_calls":0,
        "private_bytes_must_not_be_mounted_in_producer":True,
        "status":"PRIVATE_SOURCE_PREPARED_NOT_SIMULATED",
    }
    (private_out/"private-manifest.json").write_bytes(canonical(private_manifest)+b"\n")
    # Commitment-only output: never stage count, true parameter, selected graph
    # or seed. Nor output the secret filename outside the evaluator workspace.
    return {
        "schema": PUBLIC_SCHEMA,
        "world_public_id":config["world_public_id"],
        "source_definition_sha256":digest(PUBLIC_INPUT),
        "private_commitment_sha256":digest(private_manifest),
        "protocol_sha256":config["protocol_sha256"],
        "status":"WORLD_COMMITTED_NOT_EXECUTED_NO_PUBLIC_CONSTRUCTION_YET",
        "evaluator_boundary":"PROCEDURAL_JOB_ISOLATION_NOT_OS_ACL_PROOF",
        "omc_executed":0,"provider_calls":0,
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--sealed-config",type=Path,required=True)
    p.add_argument("--private-out",type=Path,required=True)
    p.add_argument("--public-commitment",type=Path,required=True)
    p.add_argument("--producer-root",type=Path,required=True)
    args=p.parse_args()
    require(os.environ.get("IGC_CT03_CUSTODIAN_AUTH")==AUTH,
            "CT03_WORLD_CUSTODY_NOT_AUTHORIZED")
    require(not args.public_commitment.exists(),"CT03_WORLD_PUBLIC_COMMITMENT_EXISTS")
    # Fail BEFORE reading config or generating private source. Neither the
    # executable checkout nor any producer workspace may contain secrets.
    def overlaps(a, b):
        return a == b or a in b.parents or b in a.parents
    roots=(Path(__file__).resolve().parents[2],
           args.producer_root.resolve(strict=True))
    require(all(root.is_dir() for root in roots),
            "CT03_WORLD_PRODUCER_ROOT_REQUIRED")
    for path in (args.sealed_config.resolve(strict=True),
                 args.private_out.resolve(strict=False)):
        require(all(not overlaps(path, root) for root in roots),
                "CT03_WORLD_PRIVATE_PATH_INSIDE_REPO_OR_PRODUCER")
    require(not overlaps(args.private_out.resolve(strict=False),
                         args.public_commitment.resolve(strict=False)),
            "CT03_WORLD_PUBLIC_PRIVATE_PATHS_OVERLAP")
    config=json.loads(args.sealed_config.read_text(encoding="utf-8"))
    from scripts.arena_cafe.ct03_prospective_lock import PROTOCOL
    protocol=json.loads(PROTOCOL.read_text(encoding="utf-8"))
    require(config.get("protocol_sha256")==digest(protocol),
            "CT03_WORLD_WRONG_FROZEN_PROTOCOL_DIGEST")
    summary=prepare_private(config,args.private_out)
    args.public_commitment.parent.mkdir(parents=True,exist_ok=True)
    args.public_commitment.write_bytes(canonical(summary)+b"\n")
    print(json.dumps({"status":summary["status"],"world_public_id":summary["world_public_id"],
                      "planned_omc":1,"executed_omc":0,"provider_calls":0}))


if __name__=="__main__":
    main()
