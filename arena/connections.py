"""Credential references: existing environment, optional OS vault, existing gh session.

Experiments name connections. Only adapters resolve values, in memory. No .env
writer, plaintext fallback, automatic credential creation, or secret export API.
"""
from dataclasses import dataclass, field
import importlib
import os
import subprocess
import tomllib
from pathlib import Path

from .common import ArenaError


@dataclass(frozen=True)
class Secret:
    value: str = field(repr=False)
    source: str

    def __str__(self):
        return "<secret>"


class SystemVault:
    """Use an explicitly selected native secure keyring, not third-party plaintext backends."""
    service = "igc-arena"

    def _backend(self):
        import sys
        if sys.platform == "win32":
            from .windows_vault import WindowsVault
            return WindowsVault()
        elif sys.platform == "darwin":
            module = "keyring.backends.macOS"
        else:
            module = "keyring.backends.SecretService"
        try:
            backend = importlib.import_module(module).Keyring()
            if backend.priority <= 0:
                raise RuntimeError()
            return backend
        except Exception:
            raise ArenaError("OS vault unavailable. Environment credentials still work; install the vault extra only if needed.") from None

    def get(self, name):
        try:
            return self._backend().get_password(self.service, name)
        except ArenaError:
            raise
        except Exception:
            raise ArenaError("OS vault could not be read or is locked.") from None

    def set(self, name, value):
        if not value:
            raise ArenaError("Refuse to store an empty credential.")
        try:
            self._backend().set_password(self.service, name, value)
        except ArenaError:
            raise
        except Exception:
            raise ArenaError("OS vault could not store the credential.") from None


class Connections:
    def __init__(self, config, *, environ=None, vault=None, gh_runner=None, bindings=None, environments=None):
        self.config = config
        self.bindings = bindings or {}
        self.environments = environments or []
        self.environ = os.environ if environ is None else environ
        self.vault = vault or SystemVault()
        self.gh_runner = gh_runner or subprocess.run

    @classmethod
    def load(cls, path, **kwargs):
        with Path(path).open("rb") as stream:
            config = tomllib.load(stream)
        return cls(config.get("connections", {}), bindings=config.get("github_bindings", {}),
                   environments=config.get("github_environments", []), **kwargs)

    def refs(self, connection, key):
        refs = self.config.get(connection, {}).get(key)
        if not isinstance(refs, list) or not refs or not all(isinstance(x, str) for x in refs):
            raise ArenaError(f"Missing connection reference: {connection}.{key}")
        for ref in refs:
            if not (ref.startswith("env:") or ref.startswith("vault:") or ref == "gh:github.com"):
                raise ArenaError("Connection files accept references only, never literal credentials.")
        return refs

    def resolve(self, connection, key):
        for ref in self.refs(connection, key):
            value = None
            if ref.startswith("env:"):
                value = self.environ.get(ref[4:])
            elif ref.startswith("vault:"):
                try:
                    value = self.vault.get(ref[6:])
                except ArenaError:
                    continue
            elif ref == "gh:github.com":
                try:
                    result = self.gh_runner(["gh", "auth", "token", "--hostname", "github.com"],
                                            capture_output=True, text=True, timeout=10)
                    if result.returncode == 0:
                        value = result.stdout.strip()
                except (OSError, subprocess.TimeoutExpired):
                    pass
            if value:
                return Secret(value, ref)
        raise ArenaError(f"Connection unavailable: {connection}.{key}. Reuse an existing environment, vault entry or authenticated gh session.")

    def check(self):
        result = {}
        for name, fields in self.config.items():
            result[name] = {}
            for key in fields:
                try:
                    resolved = self.resolve(name, key)
                    result[name][key] = {"available": True, "source": resolved.source,
                                         "authentication_validated": False}
                except ArenaError as error:
                    result[name][key] = {"available": False, "reason": str(error)}
        return result

    def store(self, connection, key, value):
        refs = [ref for ref in self.refs(connection, key) if ref.startswith("vault:")]
        if not refs:
            raise ArenaError("This connection has no OS vault reference.")
        self.vault.set(refs[0][6:], value)

    def capture_environment(self):
        """Capture already supplied variables once; never prompt or inspect other credentials."""
        pending = {}
        for name, fields in self.config.items():
            for key in fields:
                refs = self.refs(name, key)
                targets = [ref[6:] for ref in refs if ref.startswith("vault:")]
                values = [self.environ[ref[4:]] for ref in refs if ref.startswith("env:") and self.environ.get(ref[4:])]
                if not targets or not values:
                    continue
                target, value = targets[0], values[0]
                if target in pending and pending[target] != value:
                    raise ArenaError("Conflicting existing variables map to one vault entry; nothing was stored.")
                pending[target] = value
        for target, value in pending.items():
            self.vault.set(target, value)
        return {"stored_entries": sorted(pending), "values_displayed": False}

