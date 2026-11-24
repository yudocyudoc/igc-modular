"""Arena's loopback client for the private Buffalo service binding."""
import hashlib
import http.client
import json
from uuid import UUID

from ..common import ArenaError

MODEL = "57fed6310be45c10c263aecb796eeb72f993b318c5bc770013ff35e014cb4f39"


def private_merlin(operation, phase, task_id, model=None, port=8791):
    identifier = UUID(task_id)
    if str(identifier) != task_id or identifier.version != 4 or phase not in ("R", "I"):
        raise ArenaError("Invalid Merlin task identity")
    key = {"project_id": "arena-igc", "task_id": task_id, "phase": phase}
    if operation == "submit":
        if model is None or model.stat().st_size > 60002:
            raise ArenaError("Expected the versioned initial SD-JSON")
        content = model.read_bytes().removesuffix(b"\n").removesuffix(b"\r")
        if hashlib.sha256(content).hexdigest() != MODEL:
            raise ArenaError("Initial SD-JSON version mismatch")
        key.update(model_sha256=MODEL, sd_json=content.decode("utf-8"))
    elif operation != "read":
        raise ArenaError("Unknown Merlin operation")
    # Direct loopback only. No ambient HTTP proxy, redirects or automatic replay.
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=15)
    try:
        conn.request("POST", "/" + operation, body=json.dumps(key).encode(),
                     headers={"Content-Type": "application/json", "X-Arena-Client": "private-merlin-v1"})
        response = conn.getresponse()
        data = response.read(131073)
        if response.status != 200 or len(data) > 131072:
            raise ArenaError(f"Merlin {operation} returned HTTP {response.status}. Read the same task ID to reconcile.")
        result = json.loads(data)
        if not isinstance(result, dict) or any(result.get(k) != key[k] for k in ("phase","task_id","project_id")):
            raise ArenaError("Merlin task receipt identity mismatch")
        return result
    finally:
        conn.close()
