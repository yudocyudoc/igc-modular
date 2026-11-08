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


class Engines:
    def __init__(self):
        self._engines = {"D": OriginalD(), "M": OriginalM()}

    def register(self, name, adapter):
        if name in self._engines:
            raise ArenaError("Refuse to silently replace an existing engine.")
        self._engines[name] = adapter

    def prepare(self, name, output):
        if name not in self._engines:
            raise ArenaError("Engine preparation unavailable: " + name)
        return self._engines[name].prepare(output)
