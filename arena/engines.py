"""Replaceable preparation adapters. Buffalo live remains the original upstream route."""
from pathlib import Path
from typing import Protocol

from .common import ArenaError
from .legacy import load


class Engine(Protocol):
    def prepare(self, output: Path) -> dict: ...


class OriginalD:
    def prepare(self, output):
        return load("ct03_d_prepare").prepare(Path(output))


class OriginalM:
    def prepare(self, output):
        return load("ct03_m_prepare").prepare(Path(output))


class OriginalB:
    def prepare(self, output):
        from .runtime import verify
        from .common import write_json
        info=verify(include_history=False)
        output=Path(output)
        if output.exists():
            raise ArenaError("Refuse to overwrite Buffalo preparation.")
        output.mkdir(parents=True)
        manifest={"schema":"arena.buffalo-preparation/1","engine":"UB-IAD/sd-ai::Engine.generate",
                  "upstream_commit":info["buffalo_commit"],"candidate_count":1,
                  "status":"ORIGINAL_SOURCE_READY_NOT_GENERATED",
                  "transport":"ORIGINAL_OPENROUTER_SDK_TO_CLOUDFLARE_ADAPTER",
                  "provider_posts":0,"new_omc":0}
        write_json(output/"manifest.json",manifest)
        return manifest


class Engines:
    def __init__(self):
        self._engines = {"D": OriginalD(), "M": OriginalM(), "B": OriginalB()}

    def register(self, name, adapter):
        if name in self._engines:
            raise ArenaError("Refuse to silently replace an existing engine.")
        self._engines[name] = adapter

    def prepare(self, name, output):
        if name not in self._engines:
            raise ArenaError("Engine preparation unavailable: " + name)
        return self._engines[name].prepare(output)
