import ctypes
import json
from pathlib import Path
import unittest
from unittest.mock import Mock

from arena.common import ArenaError
from arena.connections import Connections
from arena.github import ApiError, GitHub
from arena.setup import link_github
from arena.windows_vault import WindowsVault, Credential
from test_arena import MemoryVault


class NativeVaultTests(unittest.TestCase):
    def test_native_windows_adapter_roundtrip_uses_namespaced_credential_and_frees_read(self):
        """ABI contract fixture; no credential is written to the actual OS vault."""
        api = Mock()
        saved = {}

        def write(pointer, flags):
            item = ctypes.cast(pointer, ctypes.POINTER(Credential)).contents
            saved.update(target=item.TargetName, type=item.Type, persist=item.Persist,
                         raw=ctypes.string_at(item.CredentialBlob, item.CredentialBlobSize))
            self.assertEqual(flags, 0)
            return 1

        def read(target, kind, flags, out):
            self.assertEqual((target, kind, flags), ("igc-arena/buffalo/api_token", 1, 0))
            saved["buffer"] = (ctypes.c_ubyte * len(saved["raw"])).from_buffer_copy(saved["raw"])
            saved["credential"] = Credential(Type=1, CredentialBlobSize=len(saved["raw"]), CredentialBlob=saved["buffer"])
            ctypes.cast(out, ctypes.POINTER(ctypes.POINTER(Credential)))[0] = ctypes.pointer(saved["credential"])
            return 1

        api.CredWriteW.side_effect, api.CredReadW.side_effect = write, read
        vault = WindowsVault(dll=api, last_error=lambda: 0)
        vault.set_password("igc-arena", "buffalo/api_token", "fixture-sensitive-ñ")
        self.assertEqual(vault.get_password("igc-arena", "buffalo/api_token"), "fixture-sensitive-ñ")
        self.assertEqual((saved["target"], saved["type"], saved["persist"]), ("igc-arena/buffalo/api_token", 1, 2))
        api.CredFree.assert_called_once()
        with self.assertRaises(ArenaError):
            vault.get_password("another-app", "its-token")

    def test_native_vault_missing_entry_is_not_an_authentication_error(self):
        api = Mock()
        api.CredReadW.return_value = 0
        vault = WindowsVault(dll=api, last_error=lambda: 1168)
        self.assertIsNone(vault.get_password("igc-arena", "missing"))

    def test_capture_imports_existing_names_in_one_operation_without_showing_values(self):
        vault = MemoryVault()
        connections = Connections({"buffalo": {"api_token": ["env:CLOUDFLARE_API_TOKEN", "vault:buffalo/api_token"]},
                                   "storage": {"secret": ["env:CT03_R2_SECRET_ACCESS_KEY", "vault:storage/secret"]}},
                                  environ={"CLOUDFLARE_API_TOKEN": "fixture-sensitive", "CT03_R2_SECRET_ACCESS_KEY": "fixture-r2-sensitive"}, vault=vault)
        report = connections.capture_environment()
        self.assertEqual(len(vault.values), 2)
        self.assertNotIn("fixture-sensitive", json.dumps(report))
        self.assertNotIn("fixture-r2-sensitive", json.dumps(report))


class SetupAPI:
    def __init__(self):
        self.environments = {"producer"}
        self.secrets = {None: {"CLOUDFLARE_API_TOKEN"}, "producer": set()}
        self.writes = []

    def secret_names(self, environment=None):
        return self.secrets.get(environment, set())

    def repo(self, method, path, payload=None):
        bits = path.strip("/").split("/")
        environment = bits[1]
        if method == "GET" and len(bits) == 2:
            if environment not in self.environments:
                raise ApiError(404)
            return {"name": environment}
        if path.endswith("/public-key"):
            return {"key": "PUBLIC_KEY_FIXTURE", "key_id": "KEY_ID_FIXTURE"}
        if method == "PUT":
            self.writes.append((path, payload))
            if len(bits) == 2:
                self.environments.add(environment)
            else:
                self.secrets.setdefault(environment, set()).add(bits[-1])
            return {}
        raise AssertionError((method, path, payload))


class SetupTests(unittest.TestCase):
    def connections(self, *, values=None):
        return Connections({"storage": {"secret": ["env:CT03_R2_SECRET_ACCESS_KEY", "vault:storage/secret"]}},
            environ=values or {}, vault=MemoryVault(), environments=["custodian", "producer"],
            bindings={"producer": {"CLOUDFLARE_API_TOKEN": "buffalo.api_token"},
                      "custodian": {"CT03_R2_SECRET_ACCESS_KEY": "storage.secret"}})

    def test_plan_reuses_historical_secret_without_requiring_a_local_copy(self):
        api = SetupAPI()
        plan = link_github(api, self.connections())
        self.assertEqual(plan["environments_to_create"], ["custodian"])
        self.assertEqual([x["name"] for x in plan["missing_secret_bindings"]], ["CT03_R2_SECRET_ACCESS_KEY"])
        self.assertEqual(api.writes, [])

    def test_missing_local_input_stops_before_any_administrative_write(self):
        api = SetupAPI()
        with self.assertRaises(ArenaError):
            link_github(api, self.connections(), apply=True)
        self.assertEqual(api.writes, [])

    def test_apply_sends_only_ciphertext_and_second_apply_is_noop(self):
        api = SetupAPI()
        sealer = Mock()
        sealer.encrypt.return_value = "SEALED_CIPHERTEXT_FIXTURE"
        connections = self.connections(values={"CT03_R2_SECRET_ACCESS_KEY": "fixture-sensitive"})
        plan = link_github(api, connections, apply=True, sealer=sealer)
        self.assertTrue(plan["applied"])
        self.assertEqual(len(api.writes), 2)
        self.assertNotIn("fixture-sensitive", json.dumps(api.writes)+json.dumps(plan))
        self.assertTrue(api.writes[-1][0].endswith("/CT03_R2_SECRET_ACCESS_KEY"))
        sealer.encrypt.assert_called_once()
        count = len(api.writes)
        link_github(api, connections, apply=True, sealer=sealer)
        self.assertEqual(count, len(api.writes))

    def test_existing_github_secrets_need_no_local_values_or_encryption_dependency(self):
        api = SetupAPI()
        api.environments.add("custodian")
        api.secrets[None].add("CT03_R2_SECRET_ACCESS_KEY")
        connections = self.connections()
        result = link_github(api, connections, apply=True)
        self.assertEqual(result["missing_secret_bindings"], [])
        self.assertEqual(connections.vault.reads, [])
        self.assertEqual(api.writes, [])


class GitHubInspectionTests(unittest.TestCase):
    def test_existing_repository_names_are_reused_and_ack_is_not_written_before_world(self):
        from arena import config
        root = Path(__file__).resolve().parents[1]
        settings = config.load(root/"examples/ct03.toml")["github"]
        api = GitHub("yudocyudoc/IGC", Mock())
        api.secret_names = Mock(side_effect=lambda environment=None: set() if environment else {
            "CT03_R2_ACCOUNT_ID", "CT03_R2_ACCESS_KEY_ID", "CT03_R2_SECRET_ACCESS_KEY",
            "CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN"})
        writes = []

        def repo(method, suffix, payload=None):
            if method != "GET":
                writes.append((method, suffix, payload))
                return {}
            if suffix.startswith("/commits/"):
                return {"sha": settings["freeze_sha"]}
            if "/runs?" in suffix:
                return {"total_count": 0}
            if suffix.startswith("/actions/workflows/"):
                return {"state": "active"}
            if "/variables/" in suffix:
                raise ApiError(404)
            raise AssertionError(suffix)

        api.repo = repo
        result = api.inspect(settings, configure=True)
        self.assertTrue(result["existing_secret_names_present"])
        self.assertEqual(len(writes), 3)
        self.assertTrue(all("/variables" in row[1] for row in writes))
        self.assertFalse(any("CT03_EXTERNAL_CUSTODIAN_ACK" in json.dumps(row) for row in writes))
        self.assertFalse(any("/secrets" in row[1] for row in writes))


if __name__ == "__main__":
    unittest.main()
