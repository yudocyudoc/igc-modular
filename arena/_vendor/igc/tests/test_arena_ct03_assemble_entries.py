"""CT03 full 13-entry assembly with synthetic D/M, B/provider, solver fixtures.

No private-world selection, original Buffalo call, OMC or actual lock archive.
"""
import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.arena_cafe.ct03_dm_feedback_round import build
from scripts.arena_cafe.ct03_dm_lock_projection import project as project_dm
from scripts.arena_cafe.ct03_b_physical_prepare import prepare as prepare_B
from scripts.arena_cafe.ct03_b_lock_projection import project as project_B
from scripts.arena_cafe.ct03_assemble_entries import assemble
from scripts.arena_cafe.ct03_prospective_lock import registry,validate_row
from test_arena_ct03_dm_feedback_round import make_all_twelve,T
from test_arena_ct03_b_lock_projection import (
    prepare_fixture,review_receipt,provenance
)
from test_arena_ct03_b_own_feedback import public


def fixture(root):
    producer=root/"producer"
    producer.mkdir()
    source,planned,reused=make_all_twelve(producer)
    dm=build(ten_root=planned,ct02_root=source,reuse=reused,
             construction=public(),recorded_at=T,out=producer/"dm")
    d=json.loads((planned/"D/manifest.json").read_text())
    m=json.loads((planned/"M/manifest.json").read_text())
    d12=project_dm(dm,d,m,{})
    b=root/"B"
    b.mkdir()
    native,receipt,plan,feedback,packet,physical=prepare_fixture(b)
    second=review_receipt(receipt,native,packet)
    rev_plan=prepare_B(native,second,public(),feedback,b/"revision",
                       revision_provenance=provenance(native,receipt,packet))
    b13=project_B(original_native=native,initial_receipt=receipt,
                  construction=public(),b_feedback=feedback,packet=packet,
                  initial_plan=plan,initial_physical=physical,
                  revision_native=native,revision_receipt=second,
                  revision_plan=rev_plan)
    return d12,b13,d,m


class StrictThirteenAssemblyTests(unittest.TestCase):
    def test_exact_all_thirteen_from_own_feedback_and_actual_round_shaped_B(self):
        with TemporaryDirectory(dir=".") as temp:
            root=Path(temp).relative_to(Path.cwd())
            d12,b13,d,m=fixture(root)
            entries=assemble(d12,b13,public(),d,m)
            self.assertEqual(entries["schema"],"igc-ct03-prospective-entries/1.0")
            self.assertEqual(len(entries["rows"]),13)
            self.assertEqual([r["arm"] for r in entries["rows"]],
                             ["B"]+["D"]*6+["M"]*6)
            self.assertEqual(entries["condition_id"],"C0")
            expected=registry(d,m)
            self.assertEqual(len(expected),13)
            for row in entries["rows"]:
                validate_row(row,expected,entries["world_public_id"])
            b=entries["rows"][0]
            self.assertEqual(b["candidate_id"],"B-original")
            self.assertEqual(b["decision"]["status"],"RATIFIED")
            self.assertEqual(b["initial"],b["final"])
            # No prospective archive, withheld truth or evaluator invoked.
            self.assertFalse((root/"producer/lock.json").exists())
            self.assertFalse((root/"B/lock.json").exists())

    def test_other_world_or_missing_B_prevents_thirteenth_entry(self):
        with TemporaryDirectory(dir=".") as temp:
            root=Path(temp).relative_to(Path.cwd())
            d12,b13,d,m=fixture(root)
            bad=copy.deepcopy(b13)
            bad["world_public_id"]="OTHER_WORLD"
            with self.assertRaisesRegex(ValueError,"PUBLIC_SCOPE_OR_STATUS"):
                assemble(d12,bad,public(),d,m)
            with self.assertRaisesRegex(ValueError,"PUBLIC_SCOPE_OR_STATUS"):
                assemble(d12,{},public(),d,m)

    def test_missing_D_row_or_replaced_native_B_is_rejected(self):
        with TemporaryDirectory(dir=".") as temp:
            root=Path(temp).relative_to(Path.cwd())
            d12,b13,d,m=fixture(root)
            missing=copy.deepcopy(d12)
            missing["rows"].pop()
            with self.assertRaisesRegex(ValueError,"PUBLIC_SCOPE_OR_STATUS"):
                assemble(missing,b13,public(),d,m)
            forged=copy.deepcopy(b13)
            forged["row"]["initial"]["native_sha256"]="sha256:"+"f"*64
            with self.assertRaisesRegex(ValueError,"CURRENT_MODEL_PARENT_MISMATCH"):
                assemble(d12,forged,public(),d,m)

if __name__=="__main__":
    unittest.main()
