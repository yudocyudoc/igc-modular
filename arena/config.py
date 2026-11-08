"""Generic experiment envelope. Protocol-specific requirements live in adapters."""
from pathlib import Path
import re
import tomllib

from .common import ArenaError
from .protocols import get


def load(path):
    path = Path(path).resolve()
    with path.open("rb") as stream:
        config = tomllib.load(stream)
    if not isinstance(config.get("id"), str) or not re.fullmatch(r"[\w-]{1,80}", config["id"]):
        raise ArenaError("Invalid experiment ID.")
    if not isinstance(config.get("backend"), str):
        raise ArenaError("Select an execution backend.")
    budget = config.get("budget", {})
    if not isinstance(budget, dict) or not budget or any(type(x) is not int or x < 0 for x in budget.values()):
        raise ArenaError("Declare nonnegative integer resource budgets.")
    get(config.get("protocol")).validate(config, path)
    return config

