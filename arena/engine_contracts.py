"""Exercise original Buffalo SDK + own-memory revision with offline transport only."""
import base64
import json
import os
from pathlib import Path
import subprocess
import sys

from .common import ArenaError, read_json, write_json
from .runtime import execute

STAMP = "2026-11-07T12:00:00+00:00"


def run(workspace):
    root=Path(workspace).resolve()
    os.chdir(root)
    sys.path.insert(0,str(root))
    from scripts.arena_cafe.ct03_b_visible import view
    from scripts.arena_cafe.ct03_public import OBS_SCHEMA
    from scripts.arena_cafe.ct_feedback_bridge import make_context,record_feedback,recover_feedback
    from scripts.arena_v0_contract import canonical,digest
    folder=root/"artifacts/engine-contracts"
    folder.mkdir(parents=True,exist_ok=False)
    source="sha256:"+"a"*64
    public={"schema":OBS_SCHEMA,"source_snapshot_hash":source,"world_public_id":"W1",
            "condition_id":"C0","time_unit":"hours","observable":"cumulative_delivered",
            "observations":[{"time":t,"delivered":y} for t,y in ((0,0),(1,.1),(2,.2),(4,.4))]}
    for phase in ("initial","revision"):
        (folder/(phase+".json")).write_bytes(canonical(view(public,world="W1",round_kind=phase))+b"\n")
    environment={**os.environ,"SDAI_ROOT":str(root/"upstream/sd-ai"),"BUFFALO_MODE":"mock",
                 "BUFFALO_VISIBLE_INPUT":str(folder/"initial.json"),"BUFFALO_OUTPUT":str(folder/"initial"),
                 "BUFFALO_ROUND_KIND":"initial"}
    for name in ("CLOUDFLARE_API_TOKEN","CT03_R2_ACCESS_KEY_ID","CT03_R2_SECRET_ACCESS_KEY"):
        environment.pop(name,None)
    execute(root,["node","scripts/arena_b_ct03_native_runner.mjs"],env=environment)
    initial=read_json(folder/"initial/receipt.json")
    assert initial["status"]=="ORIGINAL_ENGINE_OFFLINE_PATH_PASS"
    assert initial["provider_calls"]==0 and initial["proxy_requests"]==1
    context=make_context(experiment="CT03",world="W1",round_id="R0",arm="B",condition="C0",source_hash=source)
    parent=initial["result_sha256"]
    diagnostic={"arm":"B","condition":"C0","source_hash":source,"parent_hash":parent,
                "evidence":"G1","observations":[],"own_evidence_only":True,"no_future_truth":True,
                "diagnostic_origin":"MOCK_CI_PROTOCOL_ONLY_NOT_EMPIRICAL"}
    db=folder/"mock-only-ledger.sqlite"
    record_feedback(db,context,parent_hash=parent,diagnostic=diagnostic,recorded_at=STAMP)
    memory=recover_feedback(db,context,parent_hash=parent,as_known_at="2026-11-07T12:00:01+00:00")
    packet={"schema":"igc-ct03-b-own-feedback/1.0","arm":"B","world_public_id":"W1",
            "condition_id":"C0","source_snapshot_hash":source,"parent_result_sha256":parent,
            "own_diagnostic_sha256":memory["diagnostic_hash"],
            "own_diagnostic_canonical_base64":base64.b64encode(canonical(memory["diagnostic"])).decode(),
            "retrieved_before_policy":memory["retrieval"],"own_diagnostic":memory["diagnostic"]}
    feedback=folder/"mock-feedback.json"
    feedback.write_bytes(canonical(packet)+b"\n")
    environment.update(BUFFALO_VISIBLE_INPUT=str(folder/"revision.json"),BUFFALO_OUTPUT=str(folder/"revision"),
                       BUFFALO_ROUND_KIND="revision",BUFFALO_PARENT_NATIVE=str(folder/"initial/native-engine-result.json"),
                       BUFFALO_PARENT_RECEIPT=str(folder/"initial/receipt.json"),BUFFALO_OWN_FEEDBACK=str(feedback))
    execute(root,["node","scripts/arena_b_ct03_native_runner.mjs"],env=environment)
    final=read_json(folder/"revision/receipt.json")
    assert final["status"]=="ORIGINAL_ENGINE_OFFLINE_PATH_PASS"
    assert final["provider_calls"]==0 and final["proxy_requests"]==1
    assert final["parent_native_sha256"]==parent and final["parent_as_original_currentModel"] is True
    assert final["own_feedback_sha256"]==digest(packet)
    assert final["request_sha256"]!=initial["request_sha256"]
    # Prove unapproved live cannot reach the SDK or provider. No credentials.
    denied={**environment,"BUFFALO_MODE":"live","BUFFALO_ROUND_KIND":"initial",
            "BUFFALO_VISIBLE_INPUT":str(folder/"initial.json"),"BUFFALO_OUTPUT":str(folder/"live-denied")}
    denied.pop("BUFFALO_LIVE_AUTH",None)
    denied.pop("BUFFALO_CT03_LIVE_AUTH",None)
    result=subprocess.run(["node","scripts/arena_b_ct03_native_runner.mjs"],cwd=root,env=denied,capture_output=True,text=True)
    assert result.returncode!=0
    receipt=read_json(folder/"live-denied/receipt.json")
    assert receipt["provider_calls"]==receipt["proxy_requests"]==0
    assert receipt["runner_error"]=="CT03_LIVE_ONE_ROUND_AUTH_REQUIRED"
    summary={"status":"ORIGINAL_BUFFALO_INITIAL_AND_OWN_REVISION_VERIFIED_MOCK",
             "evidence_kind":"OFFLINE_TRANSPORT_CONTRACT","provider_posts":0,"new_omc":0,
             "upstream_source_modified":False,"cloudflare_transport":"ORIGINAL_PROVEN_ADAPTER",
             "old_repository_network_reads":0}
    write_json(folder/"summary.json",summary)
    return summary


if __name__=="__main__":
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument("--workspace",type=Path,required=True)
    arguments=parser.parse_args()
    print(json.dumps(run(arguments.workspace),indent=2))
