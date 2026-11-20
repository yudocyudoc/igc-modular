"""Guard regressions for exactly one demonstrated pre-reservation failure."""
import copy
from io import BytesIO
import json
from unittest import TestCase
from unittest.mock import patch
from zipfile import ZipFile

from arena import coffee_q75_buffalo_retry_guard as retry
from arena import coffee_q75_buffalo_initial as buffalo
from arena.common import ArenaError


def fixture():
    old_run = {
        "id":retry.SAFE_PRIOR_RUN, "event":"workflow_dispatch",
        "head_branch":"main","run_attempt":1,"status":"completed",
        "conclusion":"failure", "name":"Coffee Q75 — original Buffalo initial generation (manual only, max 1 POST)",
    }
    current = {
        "id":44680000000,"event":"workflow_dispatch","head_branch":"main",
        "run_attempt":1, "status":"in_progress","conclusion":None,
    }
    jobs = [
        {"name":"offline-contracts","conclusion":"success","steps":[]},
        {"name":retry.LIVE_JOB,"conclusion":"failure","steps":[
            {"name":"Verify original manifests and write new Q75 initial input, NO provider yet",
             "conclusion":"success"},
            {"name":retry.PREFLIGHT_STEP,"conclusion":"failure"},
            {"name":retry.RESERVE_STEP,"conclusion":"skipped"},
            {"name":retry.INVOKE_STEP,"conclusion":"skipped"}]}
    ]
    artifacts = [{"id":retry.SAFE_PRIOR_ARTIFACT,
                  "name":"coffee-q75-original-b-initial-"+str(retry.SAFE_PRIOR_RUN),
                  "expired":False,"workflow_run":{"id":retry.SAFE_PRIOR_RUN}}]
    analysis = {
        "schema":"arena.coffee.q75-buffalo-original-initial-analysis/1",
        "attempt_reserved":False,"actual_or_possible_provider_post":False,
        "provider_posts_reported":None,"raw_provider_archived":False,
        "new_omc":0,"new_private_R2_gets":0,
    }
    dry = {"outbound_provider_posts":0,"Q75_request_sha256":retry.SAFE_REQUEST}
    request={"request_sha256":retry.SAFE_REQUEST,"provider_status":"NOT_SENT"}
    return old_run,current,jobs,artifacts,analysis,dry,request


def zip_for(analysis,dry,request,extra=None):
    bio=BytesIO()
    with ZipFile(bio,"w") as out:
        for name,item in (("analysis.json",analysis),("dry-run.json",dry),
                          ("request.json",request)):
            out.writestr(name,json.dumps(item))
        if extra:
            out.writestr(extra,"forbidden")
    return bio.getvalue()


class RetryEvidence(TestCase):
    def test_real_prior_shape_and_one_reconciled_new_attempt(self):
        old,current,jobs,arts,a,d,r=fixture()
        blob=zip_for(a,d,r)
        self.assertEqual(retry.attest_prior_run(old,jobs,arts,blob)
                         ["prior_possible_provider_posts"],0)
        status=retry.verify_dispatch_history(
            {"total_count":2,"workflow_runs":[current,old]}, current["id"],
            lambda _:jobs,lambda _:arts,lambda _:blob)
        self.assertEqual(status["new_attempt_may_reserve_max_posts"],1)

    def test_any_prior_reservation_or_possible_post_is_never_retried(self):
        old,current,jobs,arts,a,d,r=fixture()
        for field in ("attempt_reserved","actual_or_possible_provider_post"):
            alter=copy.deepcopy(a)
            alter[field]=True
            with self.assertRaises(ArenaError):
                retry.attest_prior_run(old,jobs,arts,zip_for(alter,d,r))
        for step_name in (retry.RESERVE_STEP,retry.INVOKE_STEP):
            altered_jobs=copy.deepcopy(jobs)
            next(x for x in altered_jobs[1]["steps"]
                 if x["name"]==step_name)["conclusion"]="success"
            with self.assertRaises(ArenaError):
                retry.attest_prior_run(old,altered_jobs,arts,zip_for(a,d,r))

    def test_no_second_prior_dispatch_or_improper_archive(self):
        old,current,jobs,arts,a,d,r=fixture()
        blob=zip_for(a,d,r)
        for history in (
            {"total_count":3,"workflow_runs":[current,old,
                dict(old,id=44679999999)]},
            {"total_count":4,"workflow_runs":[current,old]},
            {"total_count":2,"workflow_runs":[current,dict(old,id=12)]},
        ):
            with self.assertRaises(ArenaError):
                retry.verify_dispatch_history(
                    history,current["id"],lambda _:jobs,lambda _:arts,
                    lambda _:blob)
        for changed in (zip_for(a,d,r,"attempt.json"),zip_for(a,d,r,"provider/receipt.json")):
            with self.assertRaises(ArenaError):
                retry.attest_prior_run(old,jobs,arts,changed)
        with self.assertRaises(ArenaError):
            retry.attest_prior_run(old,jobs,arts,zip_for(a,d,dict(r,request_sha256="sha256:"+("0"*64))))

    def test_both_fresh_and_previously_spent_policy(self):
        old,current,jobs,arts,a,d,r=fixture()
        self.assertEqual(retry.verify_dispatch_history(
            {"total_count":1,"workflow_runs":[current]},current["id"],
            lambda _:None,lambda _:None,lambda _:None)
            ["prior_possible_provider_posts"],0)


class WorkersOnlyPreflight(TestCase):
    def test_one_ai_metadata_get_and_no_r2_endpoint(self):
        visited=[]
        class R:
            status=200
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,n):return b'{"success":true,"result":[]}'
        def opener(req,timeout):
            visited.append((req.full_url, req.get_method()))
            return R()
        with patch.object(buffalo,"public_config",return_value={
            "cloudflare":{"account_id":"a"*32}}):
            result=buffalo.provider_ai_only_preflight(
                {"CLOUDFLARE_API_TOKEN":"OFFLINE_FAKE",
                 "CLOUDFLARE_ACCOUNT_ID":"a"*32},opener)
        self.assertEqual(result["provider_posts"],0)
        self.assertEqual(result["r2_requests"],0)
        self.assertEqual(result["token_r2_permission_scope"],
                         "NOT_VERIFIED_DO_NOT_CLAIM_LEAST_PRIVILEGE")
        self.assertEqual(visited,[(
            "https://api.cloudflare.com/client/v4/accounts/"+
            ("a"*32)+"/ai/models/search?per_page=1","GET")])

    def test_reject_bad_metadata_or_credentials(self):
        class R:
            status=200
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,n):return b'{"success":false}'
        with patch.object(buffalo,"public_config",return_value={
            "cloudflare":{"account_id":"a"*32}}):
            for env in (
                {"CLOUDFLARE_API_TOKEN":"X","CLOUDFLARE_ACCOUNT_ID":"b"*32},
                {"CLOUDFLARE_ACCOUNT_ID":"a"*32},
            ):
                with self.assertRaises(ArenaError):
                    buffalo.provider_ai_only_preflight(env,lambda *_:R())
            with self.assertRaises(ArenaError):
                buffalo.provider_ai_only_preflight(
                    {"CLOUDFLARE_API_TOKEN":"X","CLOUDFLARE_ACCOUNT_ID":"a"*32},
                    lambda *_:R())
