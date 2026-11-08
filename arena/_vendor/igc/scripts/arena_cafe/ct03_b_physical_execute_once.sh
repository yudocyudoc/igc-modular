#!/usr/bin/env bash
# CT-03 Buffalo physical attempt, one authorized ORIGINAL native per invocation.
# Do not call this from PR CI or outside the separately approved CT03 lot.
# A solver/CSV failure is a consumed attempt, never a reason to retry.
set -euo pipefail

if [[ "${CT03_LIVE_BATCH_AUTH:-}" != CT03_ONE_APPROVED_LOT ||
      "${CT03_B_PHYSICAL_AUTH:-}" != EXACT_ORIGINAL_B_NATIVE_ONCE ||
      "${GITHUB_EVENT_NAME:-}" != workflow_dispatch ||
      "${GITHUB_RUN_ATTEMPT:-}" != 1 ||
      "${GITHUB_REF:-}" != refs/heads/experiment/arena-ct00-ct02-20261107 ||
      "${CT03_FROZEN_SHA:-}" != "${GITHUB_SHA:-}" ||
      ! "${GITHUB_SHA:-}" =~ ^[0-9a-f]{40}$ ||
      "${CT03_OMC_BUDGET_MAX:-}" != 19 ||
      "${CT03_OMC_WORLD_ATTEMPTS:-}" != 1 ||
      ! "${GITHUB_RUN_ID:-}" =~ ^[1-9][0-9]*$ ]]; then
    echo CT03_B_PHYSICAL_MANUAL_AUTH_SHA_AND_GLOBAL_BUDGET_REQUIRED >&2
    exit 1
fi
if (( $# != 5 )); then
  echo CT03_B_PHYSICAL_EXPECT_ROOT_NATIVE_RECEIPT_PLAN_OUT >&2; exit 1
fi
ROOT="$1"
NATIVE="$2"
RECEIPT="$3"
PLAN="$4"
OUT="$5"
# Production artifacts are confined to the public producer workspace.
case "$ROOT" in
  artifacts/ct03-producer/B-physical|artifacts/ct03-producer/B-revision-physical) ;;
  *) echo CT03_B_PHYSICAL_ROOT_OUTSIDE_FROZEN_PRODUCER >&2; exit 1 ;;
esac
test -s "$PLAN"
test -s "$NATIVE"
test -s "$RECEIPT"
test -d "$ROOT"
test -d "$RUNNER_TEMP/e1-libs/msl"
test -d "$RUNNER_TEMP/e1-libs/systemdynamics"
test -d "$RUNNER_TEMP/e1-home"
test ! -e "$OUT"
test ! -e "$ROOT/omc-exit.json"
test ! -e "$ROOT/b-original-omc.log"
MODE="$(python - "$PLAN" <<'PY'
from pathlib import Path
import json,sys
p=json.loads(Path(sys.argv[1]).read_text())
assert p["status"]=="B_NATIVE_PHYSICAL_PLANNED_NO_OMC"
assert p["round_kind"] in ("initial","revision")
print(p["round_kind"])
PY
)"

python -m scripts.arena_cafe.ct03_b_physical_outcome \
  --preflight-only --native "$NATIVE" --receipt "$RECEIPT" \
  --plan "$PLAN" --root "$ROOT" --out "$OUT" \
  --git-sha "$GITHUB_SHA" --run-id "$GITHUB_RUN_ID"

# The budget is derived from retained consumed attempts, not an adjustable
# numerical counter. Exactly ten original D/M attempts plus one custodian
# world count and all M/B prior physical attempts share the 19-run ceiling.
: "${CT03_DM_COUNT_ONLY_BUDGET:?CT03_B_DM_COUNT_ONLY_RECEIPT_REQUIRED}"
test -s "$CT03_DM_COUNT_ONLY_BUDGET"
CT03_PUBLIC_CONSTRUCTION="${CT03_PUBLIC_CONSTRUCTION:-artifacts/ct03-public/construction.json}"
test -s "$CT03_PUBLIC_CONSTRUCTION"
# The B job never mounts or reads D/M native sources, CSV, or feedback.
python -m scripts.arena_cafe.ct03_lot_budget verify \
  --receipt "$CT03_DM_COUNT_ONLY_BUDGET" \
  --construction "$CT03_PUBLIC_CONSTRUCTION" \
  --run-id "$GITHUB_RUN_ID" --git-sha "$GITHUB_SHA"
COUNT="$(python - "$CT03_DM_COUNT_ONLY_BUDGET" "$MODE" "$CT03_PUBLIC_CONSTRUCTION" <<'PY'
from pathlib import Path
import os,re,sys,json
from scripts.arena_cafe.ct03_lot_budget import verify_receipt
r=json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
mode=sys.argv[2];run=os.environ["GITHUB_RUN_ID"];sha=os.environ["GITHUB_SHA"]
construction=json.loads(Path(sys.argv[3]).read_text(encoding="utf-8"))
before=verify_receipt(r,run_id=run,git_sha=sha,construction=construction)
p=Path("artifacts/ct03-producer/b-physical-attempts.log")
prior=[] if not p.exists() else p.read_text(encoding="utf-8").splitlines()
assert len(prior)<=1
assert all(re.fullmatch(
    rf"B-(initial|revision) attempted; GitHub run {run}; code {sha}",line)
    for line in prior)
assert mode not in [x.split(" attempted;")[0].removeprefix("B-") for x in prior]
assert not (mode=="initial" and prior)
assert before+len(prior)<19, "CT03_B_PHYSICAL_GLOBAL_19_OMC_EXHAUSTED"
assert len(prior)<2, "CT03_B_MORE_THAN_TWO_PHYSICAL_ATTEMPTS"
print(before+len(prior))
PY
)"
echo "CT03_B_PREVIOUS_ATTEMPTS_COUNT=$COUNT MAX=19"

ATTEMPTS="artifacts/ct03-producer/b-physical-attempts.log"
printf 'B-%s attempted; GitHub run %s; code %s\n' \
  "$MODE" "$GITHUB_RUN_ID" "$GITHUB_SHA" >> "$ATTEMPTS"

IMAGE="openmodelica/openmodelica@sha256:8993c8273224aeacbc018f351c00d60879c5aec386c77a58019318c44c938c9b"
code=0
if docker run --rm --network none \
    --user "$(id -u):$(id -g)" \
    -v "$PWD:/repo" -w /repo \
    -v "$RUNNER_TEMP/e1-home:/omhome" -e HOME=/omhome \
    -v "$RUNNER_TEMP/e1-libs:/thirdparty:ro" \
    -e OPENMODELICALIBRARY=/thirdparty/msl:/thirdparty/systemdynamics \
    "$IMAGE" omc "$ROOT/initial.mos" 2>&1 | tee "$ROOT/b-original-omc.log"; then
  code=0
else
  code=$?
fi

python - "$ROOT/omc-exit.json" "$MODE" "$code" <<'PY'
import json,os,sys
from pathlib import Path
data={"arm":"B","round_kind":sys.argv[2],
      "run_id":os.environ["GITHUB_RUN_ID"],
      "git_sha":os.environ["GITHUB_SHA"],
      "exit_code":int(sys.argv[3]),"attempted":True}
Path(sys.argv[1]).write_text(
    json.dumps(data,sort_keys=True,separators=(',',':'))+"\n")
PY

python -m scripts.arena_cafe.ct03_b_physical_outcome \
  --native "$NATIVE" --receipt "$RECEIPT" --plan "$PLAN" \
  --root "$ROOT" --git-sha "$GITHUB_SHA" --run-id "$GITHUB_RUN_ID" \
  --out "$OUT"
# A typed G2_FAILED report is a successfully recorded failed attempt;
# a true integrity error stops and preserves artifacts for adjudication.
