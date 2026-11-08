"""Choose ONE CT-03 world privately after the single lot is authorized.

No public outputs, no seed input, no solver or provider call. The configuration
must reside outside the repository and producer workspaces. Tests patch the
random generator; real execution uses SystemRandom from OS entropy.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import secrets

from scripts.arena_v0_contract import canonical, digest
from scripts.arena_cafe.ct03_prospective_lock import PROTOCOL
from scripts.arena_cafe.ct03_world_custody import validate


def choose():
    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    rng = secrets.SystemRandom()
    return validate({
        "world_public_id": "CT03-" + secrets.token_hex(8),
        "stage_count": rng.choice((2, 3)),
        "capacity": round(rng.uniform(1.2, 2.8), 10),
        "response_time": round(rng.uniform(0.5, 1.5), 10),
        "custody_nonce": secrets.token_urlsafe(32),
        "protocol_sha256": digest(protocol),
    })


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    if a.out.exists():
        raise ValueError("CT03_PRIVATE_WORLD_CONFIG_REFUSE_OVERWRITE")
    # Never print or commit the selected private parameters.
    config = choose()
    a.out.parent.mkdir(parents=True, exist_ok=True)
    with a.out.open("xb") as out:
        out.write(canonical(config) + b"\n")
    a.out.chmod(0o600)
    print("CT03_PRIVATE_CONFIG_WRITTEN_NO_PARAMETERS_EMITTED")


if __name__ == "__main__":
    main()
