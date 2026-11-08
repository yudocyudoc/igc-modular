#!/usr/bin/env bash
# Future single authorized CT03 lot ONLY. No CI auto-trigger; no retries.
# 0..6 original M2 own_policy revisions, with frozen individual native sources.
set -euo pipefail

if [[ "${CT03_LIVE_BATCH_AUTH:-}" != CT03_ONE_APPROVED_LOT ||
      "${CT03_M_REVISIONS_AUTH:-}" != ORIGINAL_M2_SELECTED_ONLY ||
      "${GITHUB_EVENT_NAME:-}" != workflow_dispatch ||
      "${GITHUB_RUN_ATTEMPT:-}" != 1 ||
      "${GITHUB_REF:-}" != refs/heads/experiment/arena-ct00-ct02-20261107 ||
      "${CT03_FROZEN_SHA:-}" != "${GITHUB_SHA:-}" ||
      ! "${GITHUB_SHA:-}" =~ ^[0-9a-f]{40}$ ||
      "${CT03_OMC_BUDGET_MAX:-}" != 19 ||
      ! "${CT03_OMC_BEFORE_M_REVISIONS:-}" =~ ^(11|12)$ ]]; then
  echo CT03_M_REVISION_LOT_SHA_AND_BUDGET_AUTH_REQUIRED >&2
  exit 1
fi

DM="artifacts/ct03-producer/dm-feedback"
ROOT="$DM/producer-12"
REPORT="$ROOT/dm-feedback-report.json"
M_MANIFEST="artifacts/ct03-producer/dm-ten/M/manifest.json"
test -s "$REPORT"
test -s "$M_MANIFEST"
test -d "$RUNNER_TEMP/e1-libs/msl"
test -d "$RUNNER_TEMP/e1-libs/systemdynamics"
test -d "$RUNNER_TEMP/e1-home"
test ! -e "$ROOT/m-revision-attempts.log"
test ! -e "$ROOT/m-revision-outcomes.json"

# Preflight all candidate identities BEFORE the first OMC. Do not execute
# unselected parents, missing native renderings, or altered simulate.mos.
python - "$REPORT" "$DM" "$M_MANIFEST" "$ROOT/selected-M-indices.txt" <<'PY'
import json,sys
from pathlib import Path
from scripts.arena_cafe.ct03_m_revision_physical import _integrity
report=json.loads(Path(sys.argv[1]).read_text())
dm=Path(sys.argv[2])
m=json.loads(Path(sys.argv[3]).read_text())
p=Path(sys.argv[4])
assert report["schema"]=="igc-ct03-dm-own-construction-feedback-and-original-policy/1.0"
rows=[r for r in report["rows"]
      if r["arm"]=="M" and r["decision"]["status"]=="REVISED"]
assert len(rows)<=6 and len({r["index"] for r in rows})==len(rows)
for row in rows:
    assert row["index"] in range(6)
    _integrity(row,dm/"producer-12/revisions"/("M"+str(row["index"])),
               row["revision_native_manifest"],m["candidates"][row["index"]])
p.write_text("".join(str(row["index"])+"\n" for row in rows))
print("CT03_M_SELECTED_FOR_ORIGINAL_PHYSICS",len(rows))
PY

mapfile -t indices < "$ROOT/selected-M-indices.txt"
count=${#indices[@]}
previous="$CT03_OMC_BEFORE_M_REVISIONS"
# Reserve up to two B physical attempts (initial+revision) or the remainder
# if B initial has already been consumed. Global maximum stays 19.
if (( previous + count + (13 - previous) > 19 )); then
  echo CT03_M_REVISION_GLOBAL_BUDGET_EXCEEDED >&2
  exit 1
fi

if (( count > 0 )); then
  : > "$ROOT/m-revision-attempts.log"
fi
IMAGE="openmodelica/openmodelica@sha256:8993c8273224aeacbc018f351c00d60879c5aec386c77a58019318c44c938c9b"
for index in "${indices[@]}"; do
  dir="$ROOT/revisions/M$index"
  test -s "$dir/revision.mo"
  test -s "$dir/simulate.mos"
  test ! -e "$dir/mrev-omc.log"
  test ! -e "$dir/omc-exit.json"
  printf 'M%s attempted; GitHub run %s; code %s\n' \
      "$index" "$GITHUB_RUN_ID" "$GITHUB_SHA" >> "$ROOT/m-revision-attempts.log"
  code=0
  if docker run --rm --network none \
      --user "$(id -u):$(id -g)" \
      -v "$PWD:/repo" -w "/repo/$dir" \
      -v "$RUNNER_TEMP/e1-home:/omhome" -e HOME=/omhome \
      -v "$RUNNER_TEMP/e1-libs:/thirdparty:ro" \
      -e OPENMODELICALIBRARY=/thirdparty/msl:/thirdparty/systemdynamics \
      "$IMAGE" omc simulate.mos 2>&1 | tee "$dir/mrev-omc.log"; then
    code=0
  else
    code=$?
  fi
  python - "$dir/omc-exit.json" "$index" "$code" <<'PY'
import json,os,sys
from pathlib import Path
data={"arm":"M","index":int(sys.argv[2]),
      "run_id":os.environ["GITHUB_RUN_ID"],
      "git_sha":os.environ["GITHUB_SHA"],
      "exit_code":int(sys.argv[3]),"attempted":True}
Path(sys.argv[1]).write_text(json.dumps(
    data,sort_keys=True,separators=(',',':'))+"\n")
PY
done

python -m scripts.arena_cafe.ct03_m_revision_physical \
  --dm-feedback "$REPORT" --dm-root "$DM" \
  --m-manifest "$M_MANIFEST" \
  --run-id "$GITHUB_RUN_ID" --git-sha "$GITHUB_SHA" \
  --out "$ROOT/m-revision-outcomes.json"
