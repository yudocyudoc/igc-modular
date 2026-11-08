"""R2 custody adapter. Only custodian/evaluator jobs receive these credentials."""
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import subprocess
import sys

from .common import ArenaError,read_json,write_json
from .connections import public_config
from .runtime import IMAGE,execute

class R2:
    def __init__(self):
        account=os.environ.get("CLOUDFLARE_ACCOUNT_ID") or os.environ.get("CT03_R2_ACCOUNT_ID") or public_config()["cloudflare"]["account_id"]
        key=os.environ.get("CT03_R2_ACCESS_KEY_ID")
        secret=os.environ.get("CT03_R2_SECRET_ACCESS_KEY")
        if not account or not key or not secret:
            raise ArenaError("Custodian requires account ID and its two R2 S3 credential references.")
        self.bucket=os.environ.get("CT03_R2_BUCKET","igc-ct03-private-custody")
        self.endpoint="https://"+account+".r2.cloudflarestorage.com"
        self.env={**os.environ,"AWS_ACCESS_KEY_ID":key,"AWS_SECRET_ACCESS_KEY":secret,
                  "AWS_DEFAULT_REGION":"auto","AWS_EC2_METADATA_DISABLED":"true","AWS_MAX_ATTEMPTS":"1"}

    def call(self,*args):
        result=subprocess.run(["aws","--endpoint-url",self.endpoint,*args],env=self.env,capture_output=True,text=True)
        if result.returncode:
            raise ArenaError("R2 operation failed: "+args[1]+". No solver/provider retry was attempted.")
        return json.loads(result.stdout) if result.stdout.strip() else {}

    def preflight(self):
        self.call("s3api","head-bucket","--bucket",self.bucket)
        objects=self.call("s3api","list-objects-v2","--bucket",self.bucket,"--prefix","ct03/","--max-keys","1")
        if objects.get("Contents"):
            raise ArenaError("A CT03 reservation or world already exists. Preserve it; do not select another world.")
        return {"r2_access":"AVAILABLE","existing_ct03_world":False,"new_omc":0,"provider_posts":0}

    def sync(self,source,prefix):
        self.call("s3","sync",str(source),"s3://"+self.bucket+"/"+prefix,"--only-show-errors")

    def download(self,prefix,target):
        target=Path(target)
        if target.exists():
            raise ArenaError("Refuse to reuse an evaluator private directory.")
        target.mkdir(mode=0o700,parents=True)
        self.call("s3","sync","s3://"+self.bucket+"/"+prefix,str(target),"--only-show-errors")

    def reserve(self,temporary,run_id,sha):
        self.preflight()
        marker=Path(temporary)/"world-reservation.json"
        write_json(marker,{"schema":"arena.single-world-reservation/1","repository":os.environ["GITHUB_REPOSITORY"],
                          "run_id":run_id,"frozen_code_sha":sha,"selected_world":False,
                          "created_at":datetime.now(timezone.utc).isoformat()})
        # Atomic create-once, not a read-then-overwrite. No retry after an uncertain response.
        self.call("s3api","put-object","--bucket",self.bucket,"--key","ct03/unique-world.json",
                  "--body",str(marker),"--if-none-match","*")


def create_world(workspace):
    """Select/simulate exactly one world; never print private configuration or CSV."""
    root=Path(workspace).resolve()
    sys.path.insert(0,str(root))
    from scripts.arena_cafe.ct03_private_choose import choose
    from scripts.arena_cafe.ct03_world_custody import prepare_private
    from scripts.arena_cafe.ct03_minimal_custody import release
    temporary=Path(os.environ["RUNNER_TEMP"])
    private=temporary/"arena-custody-private"
    if private.exists():
        raise ArenaError("Custodian private directory already exists; no automatic restart.")
    old_mask=os.umask(0o077)
    private.mkdir(mode=0o700)
    client=R2()
    run_id=os.environ["GITHUB_RUN_ID"]
    sha=os.environ["GITHUB_SHA"]
    prefix="ct03/igc-modular/run-"+run_id
    selected=False
    attempts=0
    try:
        client.reserve(private,run_id,sha)
        config=choose()
        write_json(private/"world-config.json",config,exclusive=True)
        selected=True
        commitment=prepare_private(config,private/"world-run")
        write_json(private/"world-commitment.json",commitment,exclusive=True)
        selected=True
        # Durable selection before OMC; the attempt is retained even on solver failure.
        (private/"world-run/world-attempt.log").write_text(
            "world attempted; GitHub run "+run_id+"; code "+sha+"\n",encoding="utf-8")
        client.sync(private,prefix)
        args=["docker","run","--rm","--network","none","--user",str(os.getuid())+":"+str(os.getgid()),
              "-v",str(root)+":/repo:ro","-v",str(private/"world-run")+":/private","-w","/private",
              "-v",str(temporary/"e1-home")+":/omhome","-e","HOME=/omhome",
              "-v",str(temporary/"e1-libs")+":/thirdparty:ro",
              "-e","OPENMODELICALIBRARY=/thirdparty/msl:/thirdparty/systemdynamics",IMAGE,"omc","simulate.mos"]
        attempts=1
        execute(root,args,private_log=private/"world-run/world-omc.log")
        release(producer_root=root,private_dir=private/"world-run",
                public_out=root/"artifacts/ct03-public",commitment=commitment)
        client.sync(private,prefix)
        return {"status":"ONE_WORLD_PUBLIC_FOUR_CUTS_RELEASED","world_omc_attempts":1,
                "provider_posts":0,"private_data_uploaded_to_github":False}
    finally:
        write_json(root/"artifacts/native-world-usage.json",{"schema":"arena.world-usage/1","run_id":run_id,
                   "frozen_code_sha":sha,"world_selected":selected,"world_omc_attempts":attempts,"provider_posts":0})
        try:
            if selected:
                # Backup only; never simulate or select again in cleanup.
                client.sync(private,prefix)
        finally:
            os.umask(old_mask)
