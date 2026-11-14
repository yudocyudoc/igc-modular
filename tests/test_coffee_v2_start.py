"""P00/P01 evidence-first: offline contracts without any R2, POST or OMC."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from arena.common import ArenaError, digest
from arena import coffee_dm_campaign as dm, coffee_v2_start as v2


def example_public():
    rows=[]
    lines=[]
    for i in range(10):
        pos_id=f"synthetic-pos-{i}"
        order_id=f"synthetic-order-{i}"
        row={
            "pos_record_id":pos_id,"order_id":order_id,
            "pos_record_type":"sale","sale_status":"paid_synthetic",
            "timestamp_min_from_peak_start":str(i+0.5),
            "beverage_count":"2" if i<3 else "1",
            "synthetic":"True","source_class":"synthetic_pos_view"}
        rows.append(row)
        for j in range(2 if i<3 else 1):
            lines.append({
                "pos_record_id":pos_id,"order_id":order_id,
                "pos_line_id":f"synthetic-line-{i}-{j}",
                "timestamp_min_from_peak_start":row["timestamp_min_from_peak_start"],
                "synthetic_sku":"CAFE-EXT" if i==0 else "CAFE-LECHE",
                "quantity":"1","synthetic":"True",
                "source_class":"synthetic_pos_line_item"})
    proxies=[{"minute_from_peak_start":str(i),
        "sample_seconds":"60",
        "source_class":"video_customer_presence_proxy_not_arrival_count",
        "synthetic":"False"} for i in range(60)]
    return {
      "schema":"arena.coffee-peak.public-b0/1",
      "condition":"B0","selection":dm.SELECTION,
      "time":{"construction_end_exclusive":60.0,"window_end":103.237,
              "future_pos_and_truth":"NOT_RELEASED"},
      "pos_records":rows,"pos_line_items":lines,"video_proxy":proxies,
    }


class CoffeeV21P00P01Tests(unittest.TestCase):
    def env(self):
        return {"GITHUB_REPOSITORY":v2.REPO,
                "GITHUB_REF":"refs/heads/main",
                "GITHUB_EVENT_NAME":"push",
                "GITHUB_RUN_ATTEMPT":"1","GITHUB_RUN_ID":"299"}

    def case(self):
        return {"case_sha256":dm.CASE_SHA256,
                "public_sha256":dm.PUBLIC_SHA256,
                "input":{"rate_orders_per_hour":10.0}}

    def test_no_external_credentials_in_main_first_read_only_runner(self):
        self.assertEqual(v2.identity(self.env()),299)
        for k,bad in (
            ("GITHUB_REF","refs/heads/feature"),
            ("GITHUB_EVENT_NAME","pull_request"),
            ("GITHUB_RUN_ATTEMPT","2"),
            ("GITHUB_REPOSITORY","other/repo"),
            ("CT03_R2_ACCESS_KEY_ID","present"),
            ("AWS_SECRET_ACCESS_KEY","present"),
            ("CLOUDFLARE_API_TOKEN","present"),
        ):
            e=self.env();e[k]=bad
            with self.subTest(k=k),self.assertRaises(ArenaError):
                v2.identity(e)

    def test_eight_immutable_runs_and_artifact_metadata(self):
        self.assertEqual(len(v2.HISTORY),8)
        class FakeAPI:
            def __init__(self):
                self.changed=False
            def run(self,r):
                t=next(x for x in v2.HISTORY if x[0]==r)
                return {"id":r,"head_sha":t[2],
                        "head_branch":"main","path":t[3],
                        "event":t[4],"run_attempt":1,
                        "status":"completed","conclusion":"success"}
            def repo(self,method,path,**kwargs):
                self.check=(method,path)
                art_id=int(path.rsplit("/",1)[1])
                t=next(x for x in v2.HISTORY if x[1]==art_id)
                return {"id":art_id,"name":t[5],
                        "digest":("sha256:"+t[6]
                                  if not self.changed else "sha256:"+"0"*64),
                        "expired":False,"workflow_run":{"id":t[0]}}
        api=FakeAPI()
        x=v2.verify_history(api)
        self.assertEqual(len(x),8)
        self.assertEqual(x[-1]["stage"],"BUFFALO_R1_G1_TRANSLATED_NOT_G2")
        api.changed=True
        with self.assertRaisesRegex(ArenaError,"HISTORICAL_ARTIFACT"):
            v2.verify_history(api)

    def test_actual_consumption_coverage_counts_and_semantic_guardrails(self):
        summary=v2.summarize_public(example_public(),self.case())
        self.assertEqual(summary["counts"],{
          "paid_orders":10,"line_items":13,"minute_proxy_bins":60,
          "public_refunds":0,"synthetic_beverage_quantity":13})
        self.assertFalse(summary["timestamps"]["profile_consumed_by_V1_models"])
        self.assertTrue(summary["none_of_these_are_measured_pickups"])
        cover=v2.source_coverage(summary)
        self.assertEqual(len(cover),6)
        self.assertEqual(cover[3]["verification"],
                         "ROADMAP_CLAIM_ONLY_NOT_SOURCE_BYTES_VERIFIED")
        self.assertIsNone(cover[3]["admitted_rows"])
        self.assertEqual(cover[4]["permission"],"CUSTODIAN_EVALUATOR_ONLY")
        matrix=v2.decision_matrix(summary)
        self.assertEqual(matrix[0]["rows_used_v1"],10)
        self.assertEqual(matrix[1]["rows_used_v1"],0)
        self.assertEqual(matrix[2]["rows_used_v1"],0)
        self.assertEqual(matrix[3]["rows_used_v1"],0)
        self.assertEqual(matrix[-1]["classification"],"RESERVED_FOR_EVALUATION")
        self.assertEqual(v2.measurement()["status"],"MEASURE_FIRST_NO_SX_SELECTED")
        self.assertEqual({m["candidate_policy"] for m in
                         v2.measurement()["rival_mechanisms"]},{"S2","S5"})
        self.assertNotIn("synthetic-pos-0",json.dumps([summary,cover,matrix]))

    def test_tampered_public_proxy_bins_orders_and_line_join_fail_closed(self):
        for kind in ("duplicate_minute","proxy_promoted_to_synthetic",
                     "bad_join","timestamp_outside","missing_line"):
            public=example_public()
            if kind=="duplicate_minute":
                public["video_proxy"][1]["minute_from_peak_start"]="0"
            elif kind=="proxy_promoted_to_synthetic":
                public["video_proxy"][0]["synthetic"]="True"
            elif kind=="bad_join":
                public["pos_line_items"][0]["order_id"]="not-a-paid-order"
            elif kind=="timestamp_outside":
                public["pos_records"][0]["timestamp_min_from_peak_start"]="61"
            else:
                public["pos_line_items"].pop()
            with self.subTest(kind=kind),self.assertRaises(ArenaError):
                v2.summarize_public(public,self.case())

    def test_compiled_report_has_no_raw_pos_ids_or_private_truth(self):
        public=example_public()
        fixture_bundles={
            "producer-public-b0.json":json.dumps(public).encode(),
            "release.json":b"{}",
        }
        def fake_build(temp,assumptions,environment=None):
            self.assertEqual(len(list(temp.iterdir())),2)
            return self.case()
        def r1(a,b):
            return {"status":"R1_INDEPENDENT_NATIVE_AND_SDK_BYTES_AUDITED",
                    "G1_native_admissible":True,"G2_modelica_simulation":"NOT_PERFORMED"}
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"work"
            with patch.object(v2.dm,"validate_public_zip",return_value=fixture_bundles), \
                 patch.object(v2,"build_case",side_effect=fake_build), \
                 patch.object(v2,"_safe_r1",side_effect=r1):
                receipt=v2.compile_package(b"fake public",b"r0",b"r1",
                                [],Path("unused"),p)
            self.assertEqual(receipt["new_provider_posts"],0)
            self.assertFalse(receipt["truth_access"])
            self.assertEqual(receipt["public_pos_payments"],10)
            self.assertEqual(len(receipt["output_sha256"]),5)
            self.assertTrue((p/"p00-v1-status.json").exists())
            files={f.name:f.read_text(encoding="utf-8") for f in p.iterdir()}
            whole="\n".join(files.values())
            self.assertNotIn("synthetic-pos-",whole)
            self.assertNotIn("synthetic-order-",whole)
            self.assertNotIn("synthetic-line-",whole)
            self.assertIn("MEASURE_FIRST_NO_SX_SELECTED",whole)
            self.assertIn("NOT_OPENED",whole)
            with self.assertRaisesRegex(ArenaError,"OUTPUT_EXISTS"):
                with patch.object(v2.dm,"validate_public_zip",
                                  return_value=fixture_bundles):
                    v2.compile_package(b"",b"",b"",[],None,p)

    def test_r1_archive_must_reject_foreign_bytes_before_interpreting_it(self):
        with self.assertRaisesRegex(ArenaError,"GITHUB_ZIP_SHA256_MISMATCH"):
            v2._safe_r1(b"foreign parent archive",b"foreign revision archive")
