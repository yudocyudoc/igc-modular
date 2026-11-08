"""Twelve D/M lock rows: synthetic fixture, no true world, B or solver."""
import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.arena_cafe.ct03_dm_feedback_round import build
from scripts.arena_cafe.ct03_dm_lock_projection import project
from scripts.arena_cafe.ct03_prospective_lock import registry,validate_row
from test_arena_ct03_dm_feedback_round import (
    make_all_twelve,input_construction,T
)

class DMLockProjectionTests(unittest.TestCase):
    def test_existing_initials_and_own_ratification_project_twelve_not_B(self):
        with TemporaryDirectory(dir=".") as tmp:
            root=Path(tmp).relative_to(Path.cwd())
            source,planned,reused=make_all_twelve(root)
            dm=build(ten_root=planned,ct02_root=source,reuse=reused,
                     construction=input_construction(),recorded_at=T,
                     out=root/"dm")
            self.assertEqual(dm["M_revised_count"],0)
            d=json.loads((planned/"D/manifest.json").read_text())
            m=json.loads((planned/"M/manifest.json").read_text())
            pr=project(dm,d,m,{})
            self.assertEqual(pr["candidate_count"],12)
            self.assertEqual(pr["status"],
                             "TWELVE_D_M_LOCK_ROWS_VALID_B_NOT_INCLUDED_NOT_SEALED")
            self.assertEqual(pr["B_status"],
                             "REQUIRES_SEPARATE_REAL_ORIGINAL_B_EVIDENCE")
            self.assertEqual(pr["new_omc_by_projection"],0)
            self.assertFalse(pr["reserved_world_truth_read"])
            self.assertEqual(pr["M_physical_revised_count"],0)
            expected=registry(d,m)
            for row in pr["rows"]:
                validate_row(row,expected,dm["world_public_id"])
                self.assertEqual(row["final"],row["initial"])
                self.assertEqual(row["decision"]["status"],"RATIFIED")

    def test_own_policy_revision_must_have_separate_native_outcome(self):
        with TemporaryDirectory(dir=".") as tmp:
            root=Path(tmp).relative_to(Path.cwd())
            source,planned,reused=make_all_twelve(root)
            dm=build(ten_root=planned,ct02_root=source,reuse=reused,
                     construction=input_construction(late_observed=True),
                     recorded_at=T,out=root/"dm")
            self.assertGreater(dm["M_revised_count"],0)
            d=json.loads((planned/"D/manifest.json").read_text())
            m=json.loads((planned/"M/manifest.json").read_text())
            with self.assertRaisesRegex(ValueError,"REVISED_M_MISSING_PHYSICAL_OUTCOME"):
                project(dm,d,m,{})
            # G2 failure is explicit, never borrow initial trace as the revised result.
            outcomes={}
            for row in dm["rows"]:
                if row["arm"]=="M" and row["decision"]["status"]=="REVISED":
                    native=row["revision_native_manifest"]["native_modelica_sha256"]
                    outcomes[row["candidate_id"]]={
                        "status":"G2_FAILED","native_sha256":native,
                        "trace_sha256":None,
                        "receipt_sha256":"sha256:"+"d"*64,
                        "forecast":None,
                    }
            pr=project(dm,d,m,outcomes)
            self.assertEqual(pr["M_physical_revised_count"],len(outcomes))
            self.assertEqual(pr["candidate_count"],12)
            self.assertTrue(any(x["final"]["status"]=="G2_FAILED"
                                for x in pr["rows"] if x["arm"]=="M"))
            extra={**outcomes,"AN_EXTRA_REVISION":{
                "status":"G2_FAILED","native_sha256":"sha256:"+"f"*64,
                "trace_sha256":None,"receipt_sha256":"sha256:"+"e"*64,
                "forecast":None}}
            with self.assertRaisesRegex(ValueError,"EXTRA_REVISIONS"):
                project(dm,d,m,extra)

if __name__=="__main__":
    unittest.main()
