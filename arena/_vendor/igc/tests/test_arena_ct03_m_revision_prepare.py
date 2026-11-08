"""CT-02 original E1 renderer of exactly one legitimate M2 revision, no OMC."""
from copy import deepcopy
from datetime import datetime, timezone, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.arena_v0_contract import digest
from scripts.arena_cafe.ct03_m_prepare import prepare
from scripts.arena_cafe.ct03_m_revision_prepare import prepare_revision, validate_revision
from scripts.arena_cafe.ct_feedback_bridge import (
    make_context, record_feedback, own_m_decision
)

T=datetime(2026,11,7,12,0,tzinfo=timezone.utc)
SRC="sha256:"+"a"*64


def context():
    return make_context(experiment="CT03",world="W1",round_id="R0",
                        arm="M",condition="C0",source_hash=SRC)


def set_up(root):
    manifest=prepare(root/"initial")
    parent=manifest["candidates"][0]
    scope=context()
    graph=parent["original_ast"]
    diag={"arm":"M","condition":"C0","source_hash":SRC,
          "parent_hash":digest(graph),"evidence":"G3",
          "trace_sha256":"sha256:"+"b"*64,
          "no_future_truth":True,"own_evidence_only":True,
          "observations":[{"time":2,"residual":.3},
                          {"time":4,"residual":.4}]}
    db=root/"ledger.sqlite"
    record_feedback(db,scope,parent_hash=digest(graph),
                    diagnostic=diag,recorded_at=T.isoformat())
    decision=own_m_decision(db,scope,parent_graph=graph,
                 as_known_at=(T+timedelta(seconds=1)).isoformat())
    assert decision["status"]=="REVISED",decision
    return manifest,parent,decision


class CT03MRevisionTest(unittest.TestCase):
    def test_exact_own_policy_render_without_solver(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            manifest,parent,decision=set_up(root)
            out=root/"revised"
            report=prepare_revision(out,manifest,parent,decision)
            self.assertEqual(report["status"],"M2_REVISION_RENDERED_NOT_SOLVED_NOT_SCORED")
            self.assertEqual(report["executed_new_omc"],0)
            self.assertEqual(report["planned_new_omc"],1)
            self.assertEqual(report["parameter_edits"],decision["parameter_edits"])
            self.assertEqual(report["parent_canonical_topology"],parent["canonical_sha256"])
            self.assertEqual((out/"simulate.mos").read_text().count("simulate("),1)
            self.assertEqual((out/"simulate.mos").read_text().count('method="euler"'),1)
            with self.assertRaisesRegex(ValueError,"REFUSE_OVERWRITE"):
                prepare_revision(out,manifest,parent,decision)

    def test_wrong_parent_and_second_parameter_step_rejected(self):
        with TemporaryDirectory() as tmp:
            manifest,parent,decision=set_up(Path(tmp))
            with self.assertRaisesRegex(ValueError,"NOT_OWN_SIX_PARENT"):
                validate_revision(manifest,{**parent,"index":77},decision)
            altered=deepcopy(decision)
            altered["new_model"]["instances"] = deepcopy(altered["new_model"]["instances"])
            target=next(x for x in altered["new_model"]["instances"]
                        if x["role"]=="preparation")
            target["parameters"]["responseTime"] *= 2
            altered["new_graph_hash"]=digest(altered["new_model"])
            with self.assertRaisesRegex(ValueError,"UNAUTHORIZED_RESPONSE_TIME_EDIT"):
                validate_revision(manifest,parent,altered)


if __name__=="__main__":
    unittest.main()
