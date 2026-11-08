#!/usr/bin/env bash
# CT03: one ORIGINAL Buffalo provider initial, own G1/physical consequence,
# one original Engine.generate(currentModel) review at most, optional B OMC.
# No evaluator truth, no D/M source or model, no retry, no hidden selection.
set -euo pipefail

if [[ "${CT03_LIVE_BATCH_AUTH:-}" != CT03_ONE_APPROVED_LOT ||
      "${BUFFALO_MODE:-}" != live ||
      "${BUFFALO_LIVE_AUTH:-}" != ONE_UPSTREAM_CALL ||
      "${BUFFALO_CT03_LIVE_AUTH:-}" != CT03_ONE_ROUND_EXPRESS_AUTH ||
      "${CT03_FROZEN_SHA:-}" != "${GITHUB_SHA:-}" ||
      "${GITHUB_EVENT_NAME:-}" != workflow_dispatch ||
      "${GITHUB_RUN_ATTEMPT:-}" != 1 ||
      "${GITHUB_REF:-}" != refs/heads/experiment/arena-ct00-ct02-20261107 ||
      ! "${GITHUB_SHA:-}" =~ ^[0-9a-f]{40}$ ||
      ! "${GITHUB_RUN_ID:-}" =~ ^[1-9][0-9]*$ ||
      "${CT03_OMC_BUDGET_MAX:-}" != 19 ||
      "${CT03_OMC_WORLD_ATTEMPTS:-}" != 1 ]]; then
  echo CT03_B_ROUNDS_MANUAL_FROZEN_LOT_REQUIRED >&2; exit 1
fi
test -n "${CLOUDFLARE_ACCOUNT_ID:-}"
test -n "${CLOUDFLARE_API_TOKEN:-}"
ROOT=artifacts/ct03-producer
PUBLIC=artifacts/ct03-public/construction.json
B="$ROOT/B"
INITIAL="$B/initial"
REVIEW="$B/revision"
ORIGINAL="$INITIAL/native-engine-result.json"
RECEIPT="$INITIAL/receipt.json"
REV_NATIVE="$REVIEW/native-engine-result.json"
REV_RECEIPT="$REVIEW/receipt.json"
G1="$ROOT/B-own-feedback"
PLAN="$ROOT/B-physical"
UPDATED="$ROOT/B-physical-feedback"
REVISED_PLAN="$ROOT/B-revision-physical"
RESULT="$ROOT/B-thirteenth-row.json"
LEDGER="$ROOT/b-provider-attempts.log"
test -s "$PUBLIC"
test -s "${CT03_DM_COUNT_ONLY_BUDGET:?CT03_B_DM_BUDGET_REQUIRED}"
python -m scripts.arena_cafe.ct03_lot_budget verify \
  --receipt "$CT03_DM_COUNT_ONLY_BUDGET" \
  --construction "$PUBLIC" \
  --run-id "$GITHUB_RUN_ID" --git-sha "$GITHUB_SHA"
test ! -e "$LEDGER"
test ! -e "$RESULT"
test ! -e "$INITIAL"
test ! -e "$REVIEW"
test ! -d "$ROOT/dm-ten"
test ! -d "$ROOT/dm-feedback"
mkdir -p "$B"
WORLD="$(python - "$PUBLIC" <<'PY'
from pathlib import Path
import json,sys
d=json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(d["world_public_id"])
PY
)"
python -m scripts.arena_cafe.ct03_b_visible \
  --construction "$PUBLIC" --world "$WORLD" --round initial \
  --out "$B/visible-initial.json"

# Write the attempted provider round BEFORE calling the original upstream.
printf 'B-initial attempted; GitHub run %s; code %s\n' \
  "$GITHUB_RUN_ID" "$GITHUB_SHA" > "$LEDGER"
initial_exit=0
if BUFFALO_ROUND_KIND=initial \
   BUFFALO_VISIBLE_INPUT="$PWD/$B/visible-initial.json" \
   BUFFALO_OUTPUT="$PWD/$INITIAL" \
   node scripts/arena_b_ct03_native_runner.mjs; then
  initial_exit=0
else
  initial_exit=$?
fi
test -s "$RECEIPT"
NATIVE="$(python - "$RECEIPT" "$initial_exit" <<'PY'
from pathlib import Path
import json,sys
r=json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert r["case_id"]=="CT-03" and r["round_kind"]=="initial"
assert r["mode"]=="live" and type(r["provider_calls"]) is int
assert r["provider_calls"] in (0,1)
if r["model_returned"] and r["status"]=="CT03_NATIVE_HORIZON_MISMATCH":
    assert int(sys.argv[2])!=0 and r["provider_calls"]==1
    assert r["horizon_matches_case"] is False
    print("invalid-horizon")
elif r["model_returned"]:
    assert int(sys.argv[2])==0
    assert r["provider_calls"]==1 and r["status"]=="ORIGINAL_ENGINE_LIVE_OUTPUT_RETURNED"
    print("yes")
else:
    assert r["status"] in ("CT03_PROVIDER_ATTEMPT_NO_NATIVE",
                           "CT03_PREPROVIDER_NO_NATIVE",
                           "ORIGINAL_ENGINE_NO_NATIVE_MODEL","RUNNER_FAILURE")
    print("no")
PY
)"

if [[ "$NATIVE" = no ]]; then
  # NO_NATIVE occupies the denominator, without a synthetic model or retry.
  python -m scripts.arena_cafe.ct03_b_lock_projection \
    --construction "$PUBLIC" --initial-receipt "$RECEIPT" \
    --out "$RESULT"
  echo CT03_B_ORIGINAL_NO_NATIVE_NO_SECOND_PROVIDER
  exit 0
fi
if [[ "$NATIVE" = invalid-horizon ]]; then
  # An ORIGINAL native exists but violates the frozen 8h horizon.
  # Preserve its real SHA/receipt as G0_REJECTED; never feed it to G1/OMC.
  python -m scripts.arena_cafe.ct03_b_lock_projection \
    --construction "$PUBLIC" --initial-receipt "$RECEIPT" \
    --original-native "$ORIGINAL" --out "$RESULT"
  test -s "$RESULT"
  test "$(wc -l < "$LEDGER")" = 1
  echo CT03_B_ORIGINAL_G0_HORIZON_REJECTED_NO_SECOND_PROVIDER
  exit 0
fi

python -m scripts.arena_cafe.ct03_b_own_feedback \
  --native "$ORIGINAL" --receipt "$RECEIPT" \
  --construction "$PUBLIC" \
  --recorded-at "$(date -u +%Y-%m-%dT%H:%M:%S+00:00)" \
  --out "$G1"
python -m scripts.arena_cafe.ct03_b_physical_prepare \
  --native "$ORIGINAL" --receipt "$RECEIPT" \
  --construction "$PUBLIC" --b-feedback "$G1/status.json" \
  --out "$PLAN"

INITIAL_PHYSICAL=()
REVIEW_FEEDBACK="$G1/status.json"
REVIEW_PACKET="$G1/own-revision-packet.json"
PLAN_STATUS="$(python - "$PLAN/plan.json" <<'PY'
import json,sys
from pathlib import Path
print(json.loads(Path(sys.argv[1]).read_text())["status"])
PY
)"
if [[ "$PLAN_STATUS" = B_NATIVE_PHYSICAL_PLANNED_NO_OMC ]]; then
  bash scripts/arena_cafe/ct03_b_physical_execute_once.sh \
    "$PLAN" "$ORIGINAL" "$RECEIPT" "$PLAN/plan.json" \
    "$PLAN/physical-result.json"
  INITIAL_PHYSICAL=(--initial-physical "$PLAN/physical-result.json")
  # Read own four-cut B consequence BEFORE the actual currentModel review.
  python -m scripts.arena_cafe.ct03_b_physical_feedback \
    --native "$ORIGINAL" --receipt "$RECEIPT" \
    --construction "$PUBLIC" --g1-dir "$G1" \
    --initial-plan "$PLAN/plan.json" \
    --physical "$PLAN/physical-result.json" --physical-root "$PLAN" \
    --recorded-at "$(date -u +%Y-%m-%dT%H:%M:%S+00:00)" \
    --out "$UPDATED"
  REVIEW_FEEDBACK="$UPDATED/status.json"
  REVIEW_PACKET="$UPDATED/own-revision-packet.json"
else
  test "$PLAN_STATUS" = B_NATIVE_G1_TRANSLATION_BLOCKED_NO_OMC -o \
       "$PLAN_STATUS" = B_OBSERVABLE_UNRESOLVED_NO_OMC
fi

python -m scripts.arena_cafe.ct03_b_visible \
  --construction "$PUBLIC" --world "$WORLD" --round revision \
  --out "$B/visible-revision.json"

# The second original provider attempt consumes its slot even if no model
# returns. No retry and no post-failure switch to another provider.
test "$(wc -l < "$LEDGER")" = 1
printf 'B-revision attempted; GitHub run %s; code %s\n' \
  "$GITHUB_RUN_ID" "$GITHUB_SHA" >> "$LEDGER"
second_exit=0
if BUFFALO_ROUND_KIND=revision \
   BUFFALO_VISIBLE_INPUT="$PWD/$B/visible-revision.json" \
   BUFFALO_OUTPUT="$PWD/$REVIEW" \
   BUFFALO_PARENT_NATIVE="$PWD/$ORIGINAL" \
   BUFFALO_PARENT_RECEIPT="$PWD/$RECEIPT" \
   BUFFALO_OWN_FEEDBACK="$PWD/$REVIEW_PACKET" \
   node scripts/arena_b_ct03_native_runner.mjs; then
  second_exit=0
else
  second_exit=$?
fi
test -s "$REV_RECEIPT"
REVIEW_NATIVE="$(python - "$REV_RECEIPT" "$second_exit" <<'PY'
from pathlib import Path
import json,sys
r=json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert r["case_id"]=="CT-03" and r["round_kind"]=="revision"
assert r["mode"]=="live" and type(r["provider_calls"]) is int
assert r["provider_calls"] in (0,1)
if r["model_returned"] and r["status"]=="CT03_NATIVE_HORIZON_MISMATCH":
    assert int(sys.argv[2])!=0 and r["provider_calls"]==1
    assert r["horizon_matches_case"] is False
    print("invalid-horizon")
elif r["model_returned"]:
    assert int(sys.argv[2])==0 and r["provider_calls"]==1
    assert r["status"]=="ORIGINAL_ENGINE_LIVE_OUTPUT_RETURNED"
    print("yes")
else:
    assert r["status"] in ("CT03_PROVIDER_ATTEMPT_NO_NATIVE",
                            "CT03_PREPROVIDER_NO_NATIVE")
    print("no")
PY
)"

ARGS=(--construction "$PUBLIC"
      --original-native "$ORIGINAL" --initial-receipt "$RECEIPT"
      --b-feedback "$G1/status.json"
      --packet "$G1/own-revision-packet.json"
      --initial-plan "$PLAN/plan.json"
      "${INITIAL_PHYSICAL[@]}"
      --out "$RESULT")
if [[ "$UPDATED" = "$ROOT/B-physical-feedback" && -e "$UPDATED/status.json" ]]; then
  ARGS+=(--review-feedback "$REVIEW_FEEDBACK"
         --review-packet "$REVIEW_PACKET")
fi
if [[ "$REVIEW_NATIVE" = no ]]; then
  # F172-10: the failed second runner has its OWN receipt. A consumed
  # POST is not the same as a never-launched review.
  ARGS+=(--revision-receipt "$REV_RECEIPT")
elif [[ "$REVIEW_NATIVE" = invalid-horizon ]]; then
  # F172-11: keep the native and receipt, but no translation/OMC.
  ARGS+=(--revision-native "$REV_NATIVE" --revision-receipt "$REV_RECEIPT")
else
  ARGS+=(--revision-native "$REV_NATIVE" --revision-receipt "$REV_RECEIPT")
  python -m scripts.arena_cafe.ct03_b_physical_prepare \
    --native "$REV_NATIVE" --receipt "$REV_RECEIPT" \
    --construction "$PUBLIC" --b-feedback "$REVIEW_FEEDBACK" \
    --revision-parent-native "$ORIGINAL" \
    --revision-parent-receipt "$RECEIPT" \
    --revision-packet "$REVIEW_PACKET" \
    --out "$REVISED_PLAN"
  ARGS+=(--revision-plan "$REVISED_PLAN/plan.json")
  SAME="$(python - "$RECEIPT" "$REV_RECEIPT" <<'PY'
from pathlib import Path
import json,sys
a,b=[json.loads(Path(p).read_text(encoding="utf-8")) for p in sys.argv[1:]]
print("yes" if a["result_sha256"]==b["result_sha256"] else "no")
PY
)"
  REV_STATUS="$(python - "$REVISED_PLAN/plan.json" <<'PY'
import json,sys
from pathlib import Path
print(json.loads(Path(sys.argv[1]).read_text())["status"])
PY
)"
  if [[ "$SAME" = no && "$REV_STATUS" = B_NATIVE_PHYSICAL_PLANNED_NO_OMC ]]; then
    bash scripts/arena_cafe/ct03_b_physical_execute_once.sh \
      "$REVISED_PLAN" "$REV_NATIVE" "$REV_RECEIPT" \
      "$REVISED_PLAN/plan.json" "$REVISED_PLAN/physical-result.json"
    ARGS+=(--revision-physical "$REVISED_PLAN/physical-result.json")
  fi
fi
python -m scripts.arena_cafe.ct03_b_lock_projection "${ARGS[@]}"
test -s "$RESULT"
test "$(wc -l < "$LEDGER")" = 2
echo CT03_B_THIRTEENTH_SLOT_RECORDED_NO_HELDOUT_ACCESS
