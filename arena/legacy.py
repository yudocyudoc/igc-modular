"""Explicit adapter to byte-preserved original contracts, not a replacement engine."""
import hashlib
import importlib
import sys
from pathlib import Path

from .common import ArenaError, read_json

ROOT = Path(__file__).resolve().parent
VENDOR = ROOT / "_vendor/igc"


def verify():
    manifest = read_json(ROOT / "_vendor/UPSTREAM_MANIFEST.json")
    for entry in manifest["files"]:
        file = VENDOR / entry["path"]
        if not file.is_file() or hashlib.sha256(file.read_bytes()).hexdigest() != entry["sha256"]:
            raise ArenaError("Original source differs from extraction: " + entry["path"])
    return {"commit": manifest["commit"], "files": len(manifest["files"]), "unchanged": True}


def load(name):
    path = str(VENDOR)
    if path not in sys.path:
        sys.path.insert(0, path)
    return importlib.import_module("scripts.arena_cafe." + name)

