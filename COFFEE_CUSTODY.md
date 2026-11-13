# Coffee peak P2 — R2 custody boundary (pre-scientific)

This increment depends on PR #7 (P0–P1). It does **not** change CT-03,
`arena/_vendor`, original D/B/M, their budgets, or the existing workflows.

## What is now technically separated

- The ZIP is staged privately as `coffee-peak/v1/source/<sha256>.zip` in the
  existing R2 bucket. It is never placed into Git or uploaded as a GitHub
  Actions artifact.
- A new custodian job, the only role with R2 credentials, checks the pinned
  archive/manifest, fixes B0, emits ONE public view and privately persists the
  source↔opaque-ID linkage. The stable selection reservation is atomic,
  independent of GitHub run ID; a second run cannot silently choose it again.
- Private linkage and a ready receipt reside under
  `coffee-peak/v1/runs/<run-id>-<commit-prefix>/private/`.
- The public view and receipt are also durably mirrored in R2 under the run's
  `public/` prefix, so GitHub artifact expiry does not destroy reproducibility.
  Only `producer-public-b0.json` and `release.json` are uploaded to Actions.
- An independent producer-boundary job has no custodian/provider credentials,
  cannot receive the ZIP, checks public hashes/whitelists and produces a
  zero-consumption receipt. It does **not** execute D, B, or M.
- The existing R2 S3 transport from `arena/custody.py` is reused. Its
  `ct03/` reservation logic is **not** reused, called, or changed.

## Bootstrap, once, from a trusted environment

The source lives in Google Drive. The GitHub runner has no Google Drive access;
therefore it cannot fetch the private ZIP on its own. Use an authorized machine
with the existing R2 S3 credentials in environment variables and put the original
ZIP in the path declared by `examples/coffee_peak.toml`, then run:

```shell
python -m arena.coffee_custody stage-source --config examples/coffee_peak.toml
```

The upload checks the full ZIP and every required manifest member **before**
an atomic R2 `put-object --if-none-match '*'`. Do not publish the ZIP by HTTP
or upload it to GitHub Actions. If the staged key exists, the process stops;
no silent overwrites or automatic retries occur. Do not copy credentials to
shell arguments, GitHub artifacts or source control.

Then, after PR #7 and this incremental PR are reviewed and merged to `main`, use
[Coffee peak — R2 custody boundary](.github/workflows/coffee-peak-custody.yml)
with `mode=preflight` to check contracts without R2 or `mode=admit`,
`authorized=yes` for a single, deliberately authorized R2 admission. Admission
needs the source already staged at its immutable key. The job reuses the
existing `arena-custodian` GitHub environment and credentials.

No other `arena-run.yml` (CT-03) workflow is involved. No paid provider/solver
calls, new CT-03 world or scientific inference occur.

## Still intentionally closed

This is P2 **custody and access-boundary infrastructure**, not a complete
scientific run. Since there are no native D/B/M cafeteria model outputs,
there is no genuine prediction lock, no evaluator job and **no reading of the
reserved truth after lock**. `require_real_lock_before_reveal()` is a negative
fail-closed interface: it cannot replace an archived GitHub lock verification.
Before any scientific run, implement producer adapters, immutable model/
prediction artifact archive verification via GitHub's API, and an evaluator
which first validates that archive and only then acquires R2 credentials.

## Offline validation

```shell
python -m unittest discover -s tests -v
python -m arena run examples/smoke.toml --out runs/ci-smoke
```

`tests/test_coffee_custody.py` covers private/public partition, persistent
opaque linkage, atomic reservation, no retries, denial of credentials, tamper
rejection, no release after partial R2 failure and fail-closed lock gate.
Fixture tests use a fake in-memory R2 object store. They prove software
contracts, not live bucket permissions or a completed scientific experiment.
