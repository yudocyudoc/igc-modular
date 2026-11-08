"""Static safety contract for the manual hosted physical entry point.

The CI tests these guards without acquiring credentials or running OMC/Buffalo.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/physical-ct03.yml"


class PhysicalWorkflowContractTests(unittest.TestCase):
    def test_only_manual_launch_and_explicit_paid_authorization(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("  workflow_dispatch:", text)
        self.assertNotIn("\n  push:", text)
        self.assertNotIn("\n  pull_request:", text)
        self.assertIn("default: check", text)
        self.assertIn("default: 'no'", text)
        self.assertIn('if [[ "$MODE" == "execute" && "$AUTH" != "yes" ]]', text)
        self.assertIn("concurrency:", text)
        self.assertIn("cancel-in-progress: false", text)

    def test_gateway_uses_dedicated_remote_token_and_preserves_run_state(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("secrets.IGC_ACTIONS_TOKEN", text)
        self.assertIn("python -m arena check examples/ct03.toml", text)
        self.assertIn("python -m arena run examples/ct03.toml --out runs/ct03 --authorize", text)
        self.assertIn("runs/ct03/run.sqlite", text)
        self.assertIn("python -m arena resume runs/ct03", text)
        self.assertIn("if: ${{ always() }}", text)
        self.assertNotIn("secrets.CLOUDFLARE_API_TOKEN", text)
        self.assertNotIn("secrets.CT03_R2_SECRET_ACCESS_KEY", text)


if __name__ == "__main__":
    unittest.main()
