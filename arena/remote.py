"""One native GitHub workflow, durable monitoring, no intermediate admin writes."""
import json
import re
import time

from .common import ArenaError,read_json,write_json
from .reporting import write_report

class GitHubBackend:
    stages=("experiment",)
    workflow="arena-run.yml"

    def __init__(self,api,*,sleep=None,timeout_seconds=4*60*60):
        self.api=api
        self.sleep=sleep or time.sleep
        self.timeout_seconds=timeout_seconds

    def _detail(self,store):
        return json.loads(store.stage("experiment")["detail"])

    def _verify_run(self,record,store):
        detail=self._detail(store)
        if (record.get("head_sha")!=detail["frozen_code_sha"] or record.get("head_branch")!=store.config["github"]["ref"] or
            record.get("event")!="workflow_dispatch" or record.get("run_attempt",0)<1 or
            record.get("path")!=".github/workflows/"+self.workflow):
            raise ArenaError("Remote run does not match this frozen native experiment.")

    def execute(self,store,*,authorize=False):
        if authorize: store.authorize()
        stage=store.stage("experiment")
        if stage and stage["state"] in ("DISPATCHING","DISPATCH_UNCERTAIN","FAILED"):
            raise ArenaError("Uncertain or failed paid execution is recorded; automatic retry refused. Inspect its GitHub run.")
        if stage is None:
            if not store.authorized:
                raise ArenaError("Authorize the complete lot once with --authorize.")
            checked=self.api.inspect(store.config["github"],configure=False)
            sha=checked["frozen_code_sha"]
            if not re.fullmatch("[0-9a-f]{40}",sha):
                raise ArenaError("GitHub did not resolve a full frozen SHA.")
            detail={"frozen_code_sha":sha}
            store.attempt("dispatch:experiment","workflow")
            store.transition("experiment","DISPATCHING",detail=detail)
            try:
                run_id=self.api.dispatch(self.workflow,store.config["github"]["ref"],{
                    "mode":"live","authorized":"yes","freeze_sha":sha,
                    "max_new_omc":"19","max_provider_posts":"2"})
            except Exception:
                store.finish_attempt("dispatch:experiment",successful=False)
                store.transition("experiment","DISPATCH_UNCERTAIN",detail=detail)
                store.status("NEEDS_RECONCILIATION")
                raise
            store.finish_attempt("dispatch:experiment",successful=True)
            detail["url"]=f"https://github.com/{self.api.repository}/actions/runs/{run_id}"
            store.transition("experiment","RUNNING",run_id=run_id,detail=detail)
            stage=store.stage("experiment")
        store.status("RUNNING")
        started=time.monotonic()
        while stage["state"]!="COMPLETED":
            record=self.api.run(stage["run_id"])
            self._verify_run(record,store)
            if record["status"]=="completed":
                detail=self._detail(store)
                success=record["conclusion"]=="success"
                detail.update(url=record.get("html_url"),conclusion=record["conclusion"])
                store.transition("experiment","COMPLETED" if success else "FAILED",run_id=stage["run_id"],detail=detail)
                if not success:
                    store.status("FAILED")
                    self._diagnostic(store)
                    raise ArenaError("Native workflow failed or stopped; no new dispatch: "+str(detail.get("url")))
                break
            if time.monotonic()-started>=self.timeout_seconds:
                store.status("WAITING_REMOTE")
                raise ArenaError("Local monitoring limit reached. Resume this recorded run; do not dispatch another lot.")
            self.sleep(store.config["github"]["poll_seconds"])
            stage=store.stage("experiment")
        return self._result(store)

    def _measure(self,store,resources):
        for kind,maximum in (("omc",19),("provider_posts",2)):
            item=resources[kind]
            if (item.get("limit")!=maximum or type(item.get("observed_attempts")) is not int or
                not 0<=item["observed_attempts"]<=maximum or type(item.get("complete")) is not bool):
                raise ArenaError("Invalid consumption report from native workflow.")
            store.measure("native:"+kind,kind,item["observed_attempts"],complete=item["complete"])

    def _diagnostic(self,store):
        try:
            run_id=store.stage("experiment")["run_id"]
            files=self.api.artifact(run_id,"arena-native-diagnostic-"+str(run_id))
            if set(files)!={"result.json","report.md"}:
                return
            result=json.loads(files["result.json"])
            if result.get("frozen_code_sha")!=self._detail(store)["frozen_code_sha"]:
                return
            self._measure(store,result["run"]["consumption"])
            write_json(store.root/"diagnostic.json",result)
            write_report(result,store.root)
        except (ArenaError,KeyError,ValueError):
            # Preserve a failed execution and unknown usage; never replace it by zero.
            return

    def _result(self,store):
        run_id=store.stage("experiment")["run_id"]
        files=self.api.artifact(run_id,"arena-native-result-"+str(run_id))
        expected={"result.json","report.md","consumption.json","score-post-lock.json","archive-record.json"}
        if set(files)!=expected:
            raise ArenaError("Unexpected public result artifact files.")
        result=json.loads(files["result.json"])
        score=json.loads(files["score-post-lock.json"])
        ack=json.loads(files["archive-record.json"])
        usage=json.loads(files["consumption.json"])
        provenance=result.get("provenance",{})
        sha=self._detail(store)["frozen_code_sha"]
        if (result.get("schema")!="arena.result/1" or result.get("evidence_kind")!="PHYSICAL_NATIVE_WORKFLOW" or
            provenance.get("repository")!=self.api.repository or provenance.get("run_id")!=str(run_id) or
            provenance.get("frozen_code_sha")!=sha or score.get("candidate_denominator")!=13 or
            score.get("schema")!="igc-ct03-paired-prospective-evaluation/1.0" or
            ack.get("github_run_id")!=run_id or ack.get("frozen_code_sha")!=sha or
            ack.get("lock_sha256")!=score.get("lock_sha256") or result.get("score")!=score or
            result["run"].get("consumption")!=usage):
            raise ArenaError("Native result does not match the frozen closed experiment.")
        self._measure(store,usage)
        for name in ("score-post-lock.json","archive-record.json","consumption.json"):
            write_json(store.root/"results"/name,json.loads(files[name]))
        store.status("COMPLETED")
        result["controller"]=store.report()
        write_json(store.root/"result.json",result)
        return result
