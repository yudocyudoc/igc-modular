"""Protocol registry. Scientific conditions belong to their explicit adapter."""
import re

from .common import ArenaError


class CT03:
    def validate(self, config, path):
        allowed = {"id", "protocol", "backend", "source", "budget", "github"}
        if set(config) - allowed:
            raise ArenaError("Unknown experiment fields; connections and credentials belong outside experiment files.")
        if config["backend"] not in ("fixture", "github"):
            raise ArenaError("CT03 backend must be fixture or github.")
        budget = config["budget"]
        if set(budget) != {"omc", "provider_posts", "workflow"}:
            raise ArenaError("CT03 budgets are omc, provider_posts, workflow.")
        if config["backend"] == "fixture":
            if any(budget.values()):
                raise ArenaError("Fixture integration must have zero external consumption budget.")
            source = config.get("source", {})
            if set(source) - {"path", "time_column", "value_column", "time_unit"} or "path" not in source:
                raise ArenaError("Invalid source mapping.")
            source["path"] = str((path.parent / source["path"]).resolve())
        else:
            github = config.get("github", {})
            if set(github) != {"repository", "ref", "freeze_sha", "poll_seconds"}:
                raise ArenaError("Declare github repository, ref, freeze_sha, poll_seconds.")
            if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", github["repository"]):
                raise ArenaError("Invalid GitHub repository.")
            if github["ref"] != "main" or not (github["freeze_sha"] == "HEAD" or re.fullmatch(r"[0-9a-f]{40}", github["freeze_sha"])):
                raise ArenaError("Native CT03 requires main and HEAD or a full frozen SHA.")
            if budget != {"omc": 19, "provider_posts": 2, "workflow": 1}:
                raise ArenaError("Existing CT03 protocol has fixed maxima: 19 new OMC, 2 Buffalo POST, 1 workflow dispatch.")
            if type(github["poll_seconds"]) is not int or not 1 <= github["poll_seconds"] <= 60:
                raise ArenaError("poll_seconds must be between 1 and 60.")

    def verify(self):
        from .legacy import verify
        return verify()

    def backend(self, config, connections):
        if config["backend"] == "fixture":
            from .fixture import FixtureBackend
            return FixtureBackend()
        from .github import GitHub
        from .remote import GitHubBackend
        return GitHubBackend(GitHub(config["github"]["repository"], connections.resolve("github", "token")))

    def check(self, config, connections):
        original = self.verify()
        if config["backend"] == "fixture":
            from .data import ingest, ct03_public
            source = config["source"]
            data = ingest(source["path"], time_column=source.get("time_column", "time"),
                          value_column=source.get("value_column", "delivered"), time_unit=source.get("time_unit", "hours"))
            ct03_public(data, world="FIXTURE_CHECK", source_hash="sha256:"+"a"*64)
            detail = {"records": data["record_count"], "capabilities": data["capabilities"], "credentials_required": []}
        else:
            detail = self.backend(config, connections).api.inspect(config["github"], configure=False)
        return {"status": "CHECKED", "backend": config["backend"], "upstream": original,
                "budget": config["budget"], "detail": detail, "external_compute_started": False}


from .coffee_peak import CoffeePeakCapacityV1

_registry = {"ct03": CT03(), "coffee_peak_capacity_v1": CoffeePeakCapacityV1()}


def register(name, adapter):
    if not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9_-]{0,60}", name):
        raise ArenaError("Invalid protocol adapter name.")
    if name in _registry:
        raise ArenaError("Refuse to silently replace an existing scientific protocol.")
    for method in ("validate", "verify", "backend", "check"):
        if not callable(getattr(adapter, method, None)):
            raise ArenaError("Protocol adapter missing method: " + method)
    _registry[name] = adapter


def get(name):
    if not isinstance(name, str) or name not in _registry:
        raise ArenaError("Protocol adapter unavailable. Register it explicitly; do not guess compatibility.")
    return _registry[name]

