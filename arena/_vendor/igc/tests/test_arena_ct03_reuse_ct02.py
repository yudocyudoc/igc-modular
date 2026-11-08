"""Offline synthetic fixtures only: no OMC, no new world, no provider.

GitHub Actions separately downloads the authentic CT02 artifact and invokes
the same adapter; synthetic local fixtures never claim physical provenance.
"""
import copy
import csv
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.arena_v0_contract import canonical,digest
from scripts.arena_cafe.ct03_d_prepare import prepare as d_prepare, PROFILE
from scripts.arena_cafe.ct03_m_prepare import prepare as m_prepare
from scripts.arena_cafe.ct03_reuse_ct02 import (
    verify_native_dir, RUN_ID, RUN_SHA, IMAGE, IMAGE_DIGEST, MSL_REF, SD_REF
)
from scripts.arena_cafe.ct03_m_construction_diagnostic import sha_bytes


def synthetic_fixture(root):
    fresh=root/"fresh"
    source=root/"fixture-not-github"
    fresh.mkdir()
    source.mkdir()
    d=d_prepare(fresh/"D")
    m=m_prepare(fresh/"M")
    (source/"D").mkdir()
    (source/"M").mkdir()
    for name in ("D/manifest.json","M/manifest.json","M/native.mo"):
        (source/name).write_bytes((fresh/name).read_bytes())
    d0,m0=d["candidates"][0],m["candidates"][0]
    (source/"D"/(d0["name"]+".mo")).write_bytes(
        (fresh/"D"/(d0["name"]+".mo")).read_bytes())
    body={
        "schema":"igc-ct02-exact-two-technical-simulations/1.0",
        "purpose":"TECHNICAL_CONFORMITY_ONLY_NOT_CT03_G2",
        "authorized":False, "actual_omc_runs":0,"planned_omc_runs":2,
        "provider_calls":0,"des_runs":0,"image":IMAGE,"method":"euler",
        "start_h":0,"stop_h":8,"intervals":64,"dt_h":0.125,
        "selection":"FIXED_FIRST_ORIGINAL_D_AND_M_NO_FIT_NO_RANKING",
        "world_selected":False,"reserved_truth_opened":False
    }
    entries=[]
    outputs=[]
    for arm,candidate,model,native in [
        ("D",d0,d0["name"],d0["native_modelica_sha256"]),
        ("M",m0,"ArenaCT03M."+m0["class_name"],m["native_modelica_sha256"])
    ]:
        prefix=arm.lower()+"00"
        col="delivered" if arm=="D" else "deliveredTotal"
        cmd=[
            "getVersion();",
            ('loadFile("/repo/artifacts/ct02-exact-two/D/'+model+'.mo");'
             if arm=="D" else
             'loadFile("/repo/src/modelica/IGCMolecules.mo");\n'
             'loadFile("/repo/src/modelica/IGCInformationMolecules.mo");\n'
             'loadFile("/repo/artifacts/ct02-exact-two/M/native.mo");'),
            "checkModel("+model+");",
            "print(getErrorString());",
            "simulate("+model+",startTime=0,stopTime=8,numberOfIntervals=64,"
            'method="euler",outputFormat="csv",fileNamePrefix="'
            'artifacts/ct02-exact-two/'+prefix+'");',
            "print(getErrorString());",
        ]
        script="\n".join(cmd)+"\n"
        (source/(arm+"-single.mos")).write_text(script)
        with (source/(prefix+"_res.csv")).open("w",encoding="utf-8",newline="") as f:
            writer=csv.writer(f)
            writer.writerow(["time","delivered","lost","s1"] if arm=="D"
                            else ["time","deliveredTotal"])
            for i in range(65):
                t=i/8
                mass=1.7*min(t,2)
                delivered=.1*t
                writer.writerow([t,delivered,0,mass-delivered] if arm=="D"
                                else [t,delivered])
        (source/(arm+"-omc.log")).write_text(
            "OpenModelica 1.26.5 SYNTHETIC TEST ONLY\n"+
            prefix+"_res.csv\nLOG_SUCCESS MOCK ONLY\n")
        ident=candidate["id"] if arm=="D" else candidate["canonical_sha256"]
        row={"arm":arm,"candidate_id":ident,
             "native_sha256":native,
             "script_sha256":sha_bytes(script.encode()),
             "command_file":arm+"-single.mos",
             "csv_file":prefix+"_res.csv",
             "solver_log_file":arm+"-omc.log",
             "output_column":col}
        if arm=="M":
            row["parent_ast_sha256"]=candidate["full_ast_sha256"]
        entries.append(row)
        outputs.append({"arm":arm,"candidate_id":ident,
                        "native_sha256":native,
                        "script_sha256":row["script_sha256"],
                        "csv_sha256":sha_bytes((source/(prefix+"_res.csv")).read_bytes()),
                        "solver_log_sha256":sha_bytes((source/(arm+"-omc.log")).read_bytes()),
                        "output_column":col,"csv_rows":65,
                        "technical_status":"CSV_CHECKS_PASS_NOT_SCIENTIFIC_G2"})
    body["items"]=entries
    (source/"batch.json").write_bytes(canonical(body)+b"\n")
    conform={"schema":"igc-ct02-technical-conformity-results/1.0",
             "status":"TWO_TECHNICAL_CSVS_CHECKED_NOT_CT03_SCIENTIFIC_ACCEPTANCE",
             "git_sha":RUN_SHA,"run_id":RUN_ID,
             "attempted_omc":2,"successful_omc_csvs":2,"provider_posts":0,
             "source_plan_sha256":digest(body),"outputs":outputs}
    (source/"conformity.json").write_bytes(canonical(conform)+b"\n")
    (source/"attempts.log").write_text(
        "\n".join(x+" attempted; GitHub run "+RUN_ID+"; code "+RUN_SHA
                  for x in ("D","M"))+"\n")
    (source/"runtime-identity.txt").write_text("\n".join([
        "github_sha="+RUN_SHA,"github_run_id="+RUN_ID,
        "msl_ref="+MSL_REF,"systemdynamics_ref="+SD_REF,
        "image_digest="+IMAGE_DIGEST])+"\n")
    return source,fresh,d,m


class ReuseCT02Tests(unittest.TestCase):
    def test_two_initial_consequences_only_with_no_hidden_world(self):
        with TemporaryDirectory() as tmp:
            source,fresh,d,m=synthetic_fixture(Path(tmp))
            result=verify_native_dir(source,d,m,fresh_root=fresh)
            self.assertEqual(result["source_github_run_id"],RUN_ID)
            self.assertEqual([x["arm"] for x in result["items"]],["D","M"])
            self.assertEqual([x["forecast"][0]["time"] for x in result["items"]],[6,6])
            self.assertEqual([x["forecast"][1]["time"] for x in result["items"]],[8,8])
            self.assertFalse(result["own_feedback_or_decision_reused"])
            self.assertFalse(result["construction_observations_read"])
            self.assertFalse(result["world_selected"])
            self.assertEqual(result["new_omc"],0)
            self.assertEqual(result["new_provider_posts"],0)

    def test_mutated_trace_model_runtime_or_wrong_sha_blocks_reuse(self):
        for tamper,error in (
            ("csv","LOG_OR_TRACE"),
            ("native","ORIGINAL_M_SOURCE_CHANGED"),
            ("runtime","NUMERICAL_RUNTIME_DRIFT"),
            ("wrong_sha","ORIGINAL_RUN_OR_BUDGET_NOT_PROVEN"),
            ("attempts","ATTEMPTS_NOT_EXACTLY_TWO"),
        ):
            with self.subTest(tamper=tamper), TemporaryDirectory() as tmp:
                source,fresh,d,m=synthetic_fixture(Path(tmp))
                if tamper=="csv":
                    with (source/"d00_res.csv").open("a") as f:f.write("8,999,0,0\n")
                elif tamper=="native":
                    with (source/"M/native.mo").open("a") as f:f.write("\n// MUTATED\n")
                elif tamper=="runtime":
                    p=source/"runtime-identity.txt"
                    p.write_text(p.read_text().replace(MSL_REF,"0"*40))
                elif tamper=="wrong_sha":
                    p=source/"conformity.json";v=json.loads(p.read_text())
                    v["git_sha"]="a"*40;p.write_text(json.dumps(v))
                else:
                    p=source/"attempts.log";p.write_text(p.read_text()+"M retried\n")
                with self.assertRaisesRegex(ValueError,error):
                    verify_native_dir(source,d,m,fresh_root=fresh)

    def test_not_a_proof_that_local_fixture_came_from_github(self):
        with TemporaryDirectory() as tmp:
            source,fresh,d,m=synthetic_fixture(Path(tmp))
            result=verify_native_dir(source,d,m,fresh_root=fresh)
            self.assertEqual(result["custody_limit"],
                "LOCAL_CONTENT_CHECKS_REQUIRE_GITHUB_ACTIONS_ARTIFACT_ORIGIN_CHECK")
            self.assertEqual(result["scientific_limit"],
                "NOT_ALL_THIRTEEN_CT03_OR_EXTERNAL_VALIDATION")


if __name__=="__main__":
    unittest.main()
