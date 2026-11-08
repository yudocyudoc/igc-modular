"""Application API shared by CLI and future UI; the experiment never resolves secrets."""
from pathlib import Path

from . import config
from .common import ArenaError, read_json, write_json
from .protocols import get
from .store import RunStore
from .reporting import write_report


def backend(settings, connections):
    return get(settings["protocol"]).backend(settings, connections)


def check(experiment, connections):
    settings = config.load(experiment)
    return get(settings["protocol"]).check(settings, connections)


def run(experiment, out, connections, *, authorize=False, adapter=None):
    settings = config.load(experiment)
    if settings["backend"] != "fixture" and not authorize:
        raise ArenaError("Authorize the whole live lot once with --authorize. No external job has been started.")
    if Path(out).exists():
        raise ArenaError("Run directory already exists. Use resume/status; do not overwrite or create another live lot.")
    get(settings["protocol"]).verify()
    execution = adapter or backend(settings, connections)
    store = RunStore(out, config=settings)
    try:
        result = execution.execute(store, authorize=authorize)
        write_report(result, store.root)
        return result
    except BaseException:
        if not store.report()["stages"]:
            store.status("PREFLIGHT_FAILED")
        write_json(store.root/"status.json", store.report())
        raise
    finally:
        store.close()


def resume(root, connections, *, adapter=None):
    store = RunStore(root)
    try:
        if store.report()["status"] in ("COMPLETED", "INTEGRATION_COMPLETED") and (store.root/"result.json").exists():
            result = read_json(store.root/"result.json")
            write_report(result, store.root)
            return result
        execution = adapter or backend(store.config, connections)
        result = execution.execute(store, authorize=False)
        write_report(result, store.root)
        return result
    finally:
        store.close()


def status(root):
    store = RunStore(root)
    try:
        return store.report()
    finally:
        store.close()

