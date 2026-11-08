#!/usr/bin/env bash
# CT03 — only the ten ORIGINAL unreused D1..D5 M1..M5 physical initials.
# NEVER invoked from ordinary CI; CT03 authorization is still NOT granted.
# A failed candidate keeps its own G2_FAILED receipt; other arms continue.
set -euo pipefail

if [[ "${CT03_LIVE_BATCH_AUTH:-}" != "CT03_ONE_APPROVED_LOT" ||
      "${CT03_DM_TEN_AUTH:-}" != "EXACTLY_TEN_ORIGINAL_INITIALS" ||
      "${GITHUB_EVENT_NAME:-}" != "workflow_dispatch" ||
      "${GITHUB_RUN_ATTEMPT:-}" != "1" ||
      "${GITHUB_REF:-}" != "refs/heads/experiment/arena-ct00-ct02-20261107" ||
      "${CT03_FROZEN_SHA:-}" != "${GITHUB_SHA:-}" ||
      ! "${GITHUB_SHA:-}" =~ ^[0-9a-f]{40}$ ||
      "${CT03_OMC_BUDGET_MAX:-}" != "19" ||
      "${CT03_OMC_WORLD_ATTEMPTS:-}" != "1" ]]; then
  echo CT03_DM_MANUAL_AUTH_FROZEN_SHA_WORLD_BUDGET_GATE >&2
  exit 1
fi

OUT="artifacts/ct03-producer/dm-ten"
test -s "$OUT/plan.json"
test -d "$RUNNER_TEMP/e1-libs/msl"
test -d "$RUNNER_TEMP/e1-libs/systemdynamics"
test -d "$RUNNER_TEMP/e1-home"
test ! -e "$OUT/attempts.log"

# Immutable digest captured in the real CT-02 run; no floating image tags.
IMAGE="openmodelica/openmodelica@sha256:8993c8273224aeacbc018f351c00d60879c5aec386c77a58019318c44c938c9b"
touch "$OUT/attempts.log"
attempts=0
failed=0
for arm in D M; do
  for index in 1 2 3 4 5; do
    attempts=$((attempts + 1))
    if (( attempts > 10 )); then
      echo CT03_DM_EXACT_TEN_ATTEMPT_CEILING >&2; exit 1
    fi
    prefix=$(printf '%s%02d' "${arm,,}" "$index")
    log="$OUT/$arm/$prefix-omc.log"
    gate="$OUT/$arm/$prefix-gate.log"
    script="$OUT/commands/$arm$index.mos"
    test -s "$script"
    test ! -e "$log"
    test ! -e "$gate"
    printf '%s attempted; GitHub run %s; code %s\n' \
      "$arm$index" "$GITHUB_RUN_ID" "$GITHUB_SHA" >> "$OUT/attempts.log"

    # Capture OMC exit with pipefail, no retry.
    code=0
    if docker run --rm --network none \
       --user "$(id -u):$(id -g)" \
       -v "$PWD:/repo" -w /repo \
       -v "$RUNNER_TEMP/e1-home:/omhome" -e HOME=/omhome \
       -v "$RUNNER_TEMP/e1-libs:/thirdparty:ro" \
       -e OPENMODELICALIBRARY=/thirdparty/msl:/thirdparty/systemdynamics \
       "$IMAGE" omc "$script" 2>&1 | tee "$log"; then
      code=0
    else
      code=$?
    fi

    if (( code != 0 )); then
      failed=$((failed + 1))
      python -m scripts.arena_cafe.ct03_dm_initial_batch record-failure \
        --out "$OUT" --arm "$arm" --index "$index" \
        --run-id "$GITHUB_RUN_ID" --git-sha "$GITHUB_SHA" \
        --failure-class OMC_EXIT_NONZERO --omc-exit-code "$code"
      printf 'OMC_EXIT_NONZERO code=%s\n' "$code" > "$gate"
      continue
    fi

    if python -m scripts.arena_cafe.ct03_dm_initial_batch verify-one \
      --out "$OUT" --arm "$arm" --index "$index" \
      --run-id "$GITHUB_RUN_ID" --git-sha "$GITHUB_SHA" \
      > "$gate" 2>&1; then
      cat "$gate"
    else
      failed=$((failed + 1))
      cat "$gate" >&2
      python -m scripts.arena_cafe.ct03_dm_initial_batch record-failure \
        --out "$OUT" --arm "$arm" --index "$index" \
        --run-id "$GITHUB_RUN_ID" --git-sha "$GITHUB_SHA" \
        --failure-class G2_CHECK_FAILED --omc-exit-code 0
    fi
  done
done

test "$attempts" = 10
python - "$OUT" "$failed" <<'PY'
from pathlib import Path
import json,sys
out=Path(sys.argv[1])
failed=int(sys.argv[2])
lines=(out/"attempts.log").read_text().splitlines()
assert len(lines)==10
status={"schema":"igc-ct03-dm-ten-attempts-summary/1.0",
        "attempts":10,"failed_routes":failed,
        "native_results_expected":10,
        "retry_count":0,"new_provider_calls":0,
        "world_producer_private_access":False,
        "not_a_scientific_score":True}
(out/"attempts-summary.json").write_text(
    json.dumps(status,sort_keys=True,separators=(',',':'))+"\n")
print(json.dumps({"CT03_DM_TEN_DONE":status},sort_keys=True))
PY
