from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from arena import config, orchestrator, protocols
from arena.common import ArenaError, write_json
from arena.connections import Connections


class ProtocolRegistryTests(unittest.TestCase):
    def test_new_protocol_backend_can_run_without_editing_coordinator_or_ct03(self):
        class Backend:
            def execute(self, store, *, authorize=False):
                store.transition("custom-stage", "COMPLETED")
                store.status("COMPLETED")
                result = {"evidence_kind": "TEST_ONLY", "run": store.report()}
                write_json(store.root/"result.json", result)
                return result

        class Protocol:
            def validate(self, settings, path):
                if settings["budget"] != {"test_resource": 0}:
                    raise ArenaError("Wrong test protocol budget")

            def verify(self):
                return {"test_protocol": True}

            def backend(self, settings, connections):
                return Backend()

            def check(self, settings, connections):
                return {"status": "CHECKED", "test_protocol": True}

        protocols.register("unit-test-protocol", Protocol())
        try:
            with TemporaryDirectory() as temp:
                source = Path(temp)/"experiment.toml"
                source.write_text('id="test"\nprotocol="unit-test-protocol"\nbackend="test-backend"\n[budget]\ntest_resource=0\n', encoding="utf-8")
                self.assertTrue(orchestrator.check(source, Connections({}))["test_protocol"])
                result = orchestrator.run(source, Path(temp)/"run", Connections({}), authorize=True)
                self.assertEqual(result["run"]["status"], "COMPLETED")
                self.assertEqual(result["run"]["stages"][0]["name"], "custom-stage")
        finally:
            del protocols._registry["unit-test-protocol"]

    def test_existing_scientific_protocol_cannot_be_silently_replaced(self):
        with self.assertRaisesRegex(ArenaError, "silently replace"):
            protocols.register("ct03", protocols.CT03())


if __name__ == "__main__":
    unittest.main()
