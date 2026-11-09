"""BF-00/BF-01/BF-02 offline bundle from immutable CT03/Buffalo-only archives.

A single public artifact. Does not call the LLM, solver, private R2 or custodian.
Any paid phase is blocked while the exact pulse has no shared implementation.
"""
import argparse
from hashlib import sha256
import json
from pathlib import Path

from .capabilities import capability_report,normalize_units_only,native_hash,PROFILE_ID
from .feedback import freeze_profile,own_feedback
from .validation import diagnose
from ..cloud import public_input
from ..common import ArenaError,write_json

SOURCE = {
 "ct03_raw":("ct03/B/initial/provider-raw.json","1c1d7d89f036feb090178a9f9bb8a822c0870fa7f4c234384db0f53ea5e6f348"),
 "ct03_receipt":("ct03/B/initial/receipt.json","ef4d65b540607adbb434f9c460f455a8de368ff55d275e088fb7c22883a06f1c"),
 "parent_raw":("parent/initial/provider-raw.json","be446c9af2d8bf9f227ceca56ec1a39d2a32036416a689cd31815b7442145505"),
 "parent_receipt":("parent/initial/receipt.json","0e82a2c9e0dfebb0ab35258fb4ee2f4030992c8e97ec09849dbc4bd80c0b7ff9"),
 "parent_native":("parent/initial/native-engine-result.json","7eaab603ef9e931774b989e58c3be2ce2eb20879157fd44fbb707502f4a66f54"),
 "parent_visible":("parent/visible-initial.json","0ee15a803f9bf564d414cc381fbbf6a81006ce6db36b4b632badf4896d6fa0f0"),
}
BATCH_ID="buffalo-adjust-v1"
MAX_POSTS=2
MAX_OMC=1


def offline_bundle(root, evidence):
    """Refuse unverified historical bytes; separate diagnostic from original CT03."""
    root=Path(root).resolve()
    evidence=Path(evidence).resolve()
    public=public_input(root)
    snapshots={}
    for key,(relative,digest) in SOURCE.items():
        file=evidence/relative
        if not file.is_file() or file.is_symlink():
            raise ArenaError("Missing genuine historical evidence: "+key)
        data=file.read_bytes()
        if sha256(data).hexdigest()!=digest:
            raise ArenaError("Historical source bytes changed: "+key)
        snapshots[key]=json.loads(data)
    old=snapshots["ct03_receipt"]
    parent=snapshots["parent_receipt"]
    if (old.get("provider_calls")!=1 or old.get("model_returned") is not False
        or parent.get("provider_calls")!=1 or parent.get("model_returned") is not True):
        raise ArenaError("Incorrect source attempt identities.")
    if old.get("source_snapshot_hash")!=parent.get("source_snapshot_hash"):
        raise ArenaError("Historical calls do not share the same public source.")
    if parent.get("source_snapshot_hash")!=public.get("source_snapshot_hash"):
        raise ArenaError("Downloaded public construction differs from the parent.")
    native=snapshots["parent_native"]
    parent_report=diagnose(native,raw_response=snapshots["parent_raw"])
    length_report=diagnose(snapshots.get("ct03_native",{}),
                           raw_response=snapshots["ct03_raw"])
    # The earlier run had NO model; classify the genuine provider envelope,
    # not a fabricated native.
    failure=[x for x in length_report["diagnostics"]
             if x["code"]=="OUTPUT_BUDGET_EXHAUSTED_NO_FINAL_CONTENT"]
    if len(failure)!=1:
        raise ArenaError("Original length/no-content evidence not reproduced.")
    normalization,view=normalize_units_only(native)
    caps=capability_report()
    profile=freeze_profile()
    feedback=own_feedback(native,parent,public,profile)
    output=root/"artifacts"/BATCH_ID
    if output.exists():
        raise ArenaError("Refuse overwrite of Buffalo adjust output.")
    output.mkdir(parents=True)
    files={
      "bf00-native-diagnostics.json":parent_report,
      "bf00-provider-length.json":{"schema":"buffalo-adjust-v1/length/1",
                                   "diagnostics":failure,
                                   "source_run_id":42455527897},
      "bf01-unit-view.json":normalization,
      "bf01-capability-report.json":caps,
      "bf02-profile.json":profile,
      "bf02-own-feedback.json":feedback,
    }
    for filename,content in files.items():
        write_json(output/filename,content,exclusive=True)
    result={
       "schema":"buffalo-adjust-v1/offline-report/1",
       "batch_id":BATCH_ID,
       "source_ct03_run":42455527897,
       "parent_diagnostic_run":42536740649,
       "parent_original_sha256":native_hash(native),
       "model_native_untouched":True,
       "bf00":{"status":"REPRODUCED","semantic_admissible":parent_report["admissible"],
               "error_codes":[d["code"] for d in parent_report["diagnostics"]
                               if d["severity"]=="ERROR"],
               "original_no_content":"OUTPUT_BUDGET_EXHAUSTED_NO_FINAL_CONTENT"},
       "bf01":{"status":caps["physical_compatibility"],
               "unit_changes":normalization["transformations"],
               "exact_rectangular_pulse_implemented_in_original_backend":False},
       "bf02":{"status":"PROFILE_FROZEN_NOT_AUTHORIZED_FOR_PAID_PHASES",
               "profile_sha256":profile["utf8_sha256"],
               "own_feedback_created":True},
       "future_fixed_budget":{"bf03_posts":1,"bf04_posts":1,"bf05_omc":1,
                             "provider_posts_max":MAX_POSTS,"new_omc_max":MAX_OMC,
                             "des_max":0,"dm_max":0,"new_worlds_max":0},
       "gate":"BLOCKED_PENDING_EXACT_SHARED_PULSE_AND_UPSTREAM_SYSTEM_CONFLICT_RESOLUTION",
       "ct03_lock_or_score_touched":False,
       "actual_consumption":{"provider_posts":0,"new_omc":0,"new_worlds":0},
       "no_automatic_retries":True,
    }
    write_json(output/"result.json",result,exclusive=True)
    return result


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument("phase",choices=["check","authorize-live"])
    parser.add_argument("--workspace",required=True,type=Path)
    parser.add_argument("--evidence",required=True,type=Path)
    args=parser.parse_args(argv)
    if args.phase=="authorize-live":
        raise ArenaError("INPUT_CAPABILITY_GAP: BF-03, BF-04 and BF-05 must not run yet.")
    result=offline_bundle(args.workspace,args.evidence)
    print(json.dumps(result,indent=2))


if __name__=="__main__":
    main()
