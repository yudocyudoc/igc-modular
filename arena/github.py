"""GitHub REST adapter. No solver, data transformation, or provider credentials."""
import io
import json
import re
import stat
import urllib.error
import urllib.parse
import urllib.request
from pathlib import PurePosixPath
import zipfile

from .common import ArenaError


class ApiError(ArenaError):
    def __init__(self, status):
        self.status = status
        super().__init__(f"GitHub API returned HTTP {status}; response body suppressed.")


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urllib.parse.urlparse(newurl).scheme != "https":
            raise ArenaError("Refuse a non-HTTPS artifact redirect.")
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if urllib.parse.urlparse(req.full_url).netloc != urllib.parse.urlparse(newurl).netloc:
            redirected.remove_header("Authorization")
        return redirected


class GitHub:
    def __init__(self, repository, secret, *, opener=None):
        self.repository = repository
        self._secret = secret
        self._opener = opener or urllib.request.build_opener(SafeRedirect())

    def request(self, method, path, payload=None, *, binary=False):
        if not path.startswith("/"):
            raise ArenaError("GitHub API path must be relative to its fixed host.")
        req = urllib.request.Request("https://api.github.com" + path,
            data=json.dumps(payload).encode() if payload is not None else None,
            headers={"Authorization": "Bearer " + self._secret.value,
                     "Accept": "application/vnd.github+json", "Content-Type": "application/json",
                     "X-GitHub-Api-Version": "2026-03-10", "User-Agent": "igc-arena/0.1"}, method=method)
        try:
            with self._opener.open(req, timeout=30) as response:
                raw = response.read(50_000_001)
            if len(raw) > 50_000_000:
                raise ArenaError("Artifact/API response exceeds the 50 MB local adapter limit.")
            return raw if binary else json.loads(raw) if raw else None
        except urllib.error.HTTPError as error:
            raise ApiError(error.code) from None
        except (urllib.error.URLError, OSError):
            raise ArenaError("GitHub network operation failed. A dispatch may have been accepted; never automatically repeat it.") from None

    def repo(self, method, suffix, payload=None, **kwargs):
        return self.request(method, "/repos/" + self.repository + suffix, payload, **kwargs)

    def variable(self, environment, name, value=None):
        base = "/environments/" + urllib.parse.quote(environment, safe="") + "/variables"
        try:
            current = self.repo("GET", base + "/" + name)
        except ApiError as error:
            if error.status != 404:
                raise
            current = None
        if value is None:
            return current["value"] if current else None
        # Writing the same approved value also verifies write access before OMC.
        self.repo("PATCH" if current else "POST", base + ("/" + name if current else ""),
                  {"name": name, "value": value})

    def secret_names(self, environment=None):
        base = "/environments/" + urllib.parse.quote(environment, safe="") + "/secrets" if environment else "/actions/secrets"
        names, page = set(), 1
        while True:
            data = self.repo("GET", base + f"?per_page=100&page={page}")
            rows = data["secrets"]
            names.update(row["name"] for row in rows)
            if len(names) >= data["total_count"] or len(rows) < 100:
                return names
            page += 1

    def run(self, run_id):
        return self.repo("GET", f"/actions/runs/{int(run_id)}")

    def dispatch(self, workflow, ref, inputs):
        reply = self.repo("POST", "/actions/workflows/" + workflow + "/dispatches",
                          {"ref": ref, "inputs": inputs})
        run_id = reply.get("workflow_run_id") if isinstance(reply, dict) else None
        if type(run_id) is not int or run_id <= 0:
            raise ArenaError("Dispatch has no confirmed run ID. Preserve this run and reconcile it; do not dispatch again.")
        return run_id

    def artifact(self, run_id, name):
        rows, page = [], 1
        while True:
            data = self.repo("GET", f"/actions/runs/{int(run_id)}/artifacts?per_page=100&page={page}")
            rows.extend(row for row in data["artifacts"] if row["name"] == name and not row["expired"])
            if len(data["artifacts"]) < 100:
                break
            page += 1
        if len(rows) != 1:
            raise ArenaError("Expected one unexpired public artifact: " + name)
        raw = self.repo("GET", f"/actions/artifacts/{rows[0]['id']}/zip", binary=True)
        try:
            archive = zipfile.ZipFile(io.BytesIO(raw))
            result, total = {}, 0
            for info in archive.infolist():
                path = PurePosixPath(info.filename)
                if path.is_absolute() or ".." in path.parts or "\\" in info.filename or stat.S_ISLNK(info.external_attr >> 16):
                    raise ArenaError("Unsafe artifact member.")
                if info.is_dir():
                    continue
                total += info.file_size
                if total > 50_000_000 or info.filename in result:
                    raise ArenaError("Oversized or duplicate artifact members.")
                result[info.filename] = archive.read(info)
            return result
        except (zipfile.BadZipFile, RuntimeError):
            raise ArenaError("Invalid public artifact ZIP.") from None

    def inspect(self, settings, *, configure=False):
        """Run readiness needs read access, not secret/admin access.

        Each data role checks its actual credentials inside GitHub before the
        world starts. No new secret copy or intermediate variable is required.
        """
        ref=settings["ref"]
        actual=self.repo("GET","/commits/"+urllib.parse.quote(ref,safe=""))["sha"]
        expected=settings["freeze_sha"]
        if expected!="HEAD" and actual!=expected:
            raise ArenaError("Frozen code differs from the selected branch.")
        workflow=self.repo("GET","/actions/workflows/arena-run.yml")
        if workflow["state"]!="active":
            raise ArenaError("Native Arena workflow is not registered/active.")
        return {"workflows_registered":True,"frozen_code_sha":actual,
                "credential_check":"ROLE_PREFLIGHT_JOBS_BEFORE_COMPUTE",
                "admin_writes_required_to_run":False,"private_objects_read":False}
