"""One idempotent setup operation; existing remote secrets are never downloaded or replaced."""
import base64
import re
import urllib.parse

from .common import ArenaError
from .github import ApiError


class SodiumSealer:
    def __init__(self):
        try:
            from nacl import encoding, public
        except ImportError:
            raise ArenaError("Uploading a genuinely missing GitHub secret needs the optional github-setup extra. Existing secrets need no upload.") from None
        self.encoding, self.public = encoding, public

    def encrypt(self, public_key, secret):
        key = self.public.PublicKey(public_key.encode(), self.encoding.Base64Encoder())
        return base64.b64encode(self.public.SealedBox(key).encrypt(secret.value.encode())).decode()


def link_github(api, connections, *, apply=False, sealer=None):
    repository_names = api.secret_names()
    known, missing_environments, missing = {}, [], []
    environments = sorted(set(connections.environments) | set(connections.bindings))
    for environment in environments:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", environment):
            raise ArenaError("Invalid configured environment name.")
        try:
            api.repo("GET", "/environments/"+environment)
            known[environment] = api.secret_names(environment)
        except ApiError as error:
            if error.status != 404:
                raise
            missing_environments.append(environment)
            known[environment] = set()
        for name, binding in connections.bindings.get(environment, {}).items():
            if not re.fullmatch(r"[A-Z_][A-Z_0-9]*", name) or not re.fullmatch(r"[a-z_]+[.][a-z_]+", binding):
                raise ArenaError("Invalid secret binding; use a connection.field reference.")
            if name not in repository_names | known[environment]:
                connection, key = binding.split(".")
                missing.append((environment, name, connection, key))
    plan = {"existing_secrets_reused": True, "existing_secrets_replaced": False,
            "environments_to_create": missing_environments,
            "missing_secret_bindings": [{"environment": env, "name": name, "connection": conn+"."+key}
                                        for env,name,conn,key in missing],
            "applied": False, "external_compute_started": False}
    if not apply:
        return plan
    # Resolve all missing inputs before making administrative changes. Existing
    # GitHub secrets do not need local copies and are not read into this process.
    pending = [(env,name,connections.resolve(conn,key)) for env,name,conn,key in missing]
    if pending:
        sealer = sealer or SodiumSealer()
    for environment in missing_environments:
        api.repo("PUT", "/environments/"+environment, {})
    for environment, name, secret in pending:
        base = "/environments/"+environment+"/secrets"
        public_key = api.repo("GET", base+"/public-key")
        encrypted = sealer.encrypt(public_key["key"], secret)
        api.repo("PUT", base+"/"+name, {"key_id": public_key["key_id"], "encrypted_value": encrypted})
    plan["applied"] = True
    return plan

