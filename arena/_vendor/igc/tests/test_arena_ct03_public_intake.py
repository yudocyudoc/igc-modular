"""CT03 public intake rejects truth/private fields; synthetic public release."""
import base64
import copy
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts.arena_v0_contract import canonical,digest
from scripts.arena_cafe.ct03_public_intake import validate,from_b64_environment,FILES
from scripts.arena_cafe.ct03_world_custody import PUBLIC_SCHEMA
from scripts.arena_cafe.ct03_prospective_lock import PROTOCOL
from scripts.arena_cafe.ct03_public import PUBLIC_INPUT,OBS_SCHEMA

def fixture():
    commitment={
        "schema":PUBLIC_SCHEMA,"world_public_id":"W1",
        "source_definition_sha256":digest(PUBLIC_INPUT),
        "private_commitment_sha256":"sha256:"+"c"*64,
        "protocol_sha256":digest(json.loads(PROTOCOL.read_text())),
        "status":"WORLD_COMMITTED_NOT_EXECUTED_NO_PUBLIC_CONSTRUCTION_YET",
        "evaluator_boundary":"PROCEDURAL_JOB_ISOLATION_NOT_OS_ACL_PROOF",
        "omc_executed":0,"provider_calls":0}
    source=digest({
        "world_public_id":"W1",
        "world_commitment_sha256":commitment["private_commitment_sha256"],
        "source_definition_sha256":commitment["source_definition_sha256"],
        "role":"PUBLIC_ONLY_CONSTRUCTION_CUTS"})
    construction={
        "schema":OBS_SCHEMA,"source_snapshot_hash":source,
        "world_public_id":"W1","condition_id":"C0",
        "time_unit":"hours","observable":"cumulative_delivered",
        "observations":[{"time":t,"delivered":v}
                        for t,v in ((0,0.),(1,.2),(2,.4),(4,.6))]}
    status={
        "schema":"igc-ct03-public-four-cuts-release/1.0",
        "status":"PROCEDURAL_CUSTODY_FOUR_CONSTRUCTION_ONLY",
        "construction_sha256":digest(construction),
        "public_world_commitment_sha256":digest(commitment),
        "source_snapshot_hash":source,
        "released_times":[0,1,2,4],"reserved_times_released":[],
        "private_solver_csv_exported":False,"private_source_exported":False,
        "operator_independence_verified":False,
        "new_omc_by_release":0,"provider_posts":0}
    return construction,commitment,status

class PublicIntakeTests(unittest.TestCase):
    def test_only_three_public_files_accepted_without_true_world(self):
        c,k,s=fixture()
        self.assertEqual(validate(c,k,s),c["source_snapshot_hash"])
        with TemporaryDirectory() as tmp:
            env={
                "CT03_PUBLIC_CONSTRUCTION_B64":base64.b64encode(canonical(c)).decode(),
                "CT03_PUBLIC_COMMITMENT_B64":base64.b64encode(canonical(k)).decode(),
                "CT03_PUBLIC_RELEASE_STATUS_B64":base64.b64encode(canonical(s)).decode()
            }
            target=Path(tmp)/"public"
            with patch.dict(os.environ,env):
                self.assertEqual(from_b64_environment(target),c["source_snapshot_hash"])
            self.assertEqual({p.name for p in target.iterdir()},FILES)
            with self.assertRaisesRegex(ValueError,"REFUSE_OVERWRITE"):
                with patch.dict(os.environ,env):
                    from_b64_environment(target)

    def test_future_truth_or_forged_custody_status_is_rejected(self):
        c,k,s=fixture()
        bad=copy.deepcopy(c)
        bad["reserved_y6"]=.5
        with self.assertRaises(ValueError):
            validate(bad,k,s)
        forged=copy.deepcopy(s)
        forged["operator_independence_verified"]=True
        with self.assertRaisesRegex(ValueError,"NONPUBLIC_RELEASE_OR_MISMATCH"):
            validate(c,k,forged)
        corrupted=copy.deepcopy(k)
        corrupted["private_commitment_sha256"]="sha256:"+"f"*64
        with self.assertRaisesRegex(ValueError,"SOURCE_NOT_DERIVED"):
            validate(c,corrupted,s)
        badstatus=copy.deepcopy(s)
        badstatus["reserved_times_released"]=[6,8]
        with self.assertRaisesRegex(ValueError,"NONPUBLIC_RELEASE_OR_MISMATCH"):
            validate(c,k,badstatus)

if __name__=="__main__":
    unittest.main()
