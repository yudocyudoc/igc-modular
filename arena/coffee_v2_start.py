"""Coffee Arena V2.1 P00/P01: pinned history + decision-oriented public inventory.

Read-only. No R2, private source/truth, OMC, provider, new world or
scientific lock. The authorized public view is an observation model, NOT
a direct measurement of arrivals, preparation or pickups.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import os
from pathlib import Path
import re
import sys
from tempfile import TemporaryDirectory

from .common import ArenaError, digest, read_json, write_json
from .connections import Secret
from .coffee_adapters.shared import sha_bytes
from . import coffee_dm_campaign as dm, coffee_feedback as fb
from .coffee_domain import build_case
from .buffalo.validation import diagnose
from .github import GitHub

SCHEMA = "arena.coffee-v2.p00-p01-evidence/1"
REPO = "yudocyudoc/igc-modular"
# Historical evidence is deliberately pinned. Unknown "latest" is forbidden.
HISTORY = [
    (43532737911, 14088545399, "4dd62c8b323096abfa3aca8675a311738cdce34e",
     ".github/workflows/coffee-peak-custody.yml","workflow_dispatch",
     "coffee-public-43532737911","872cf83210a54c88563a13130c3cec819bf1a978db93d6b08610634f282c42d2",
     "PUBLIC_CUSTODY_B0"),
    (43537333254,14090920829,"399eddbc0d674e8b2370f908a75ba73e694153c3",
     ".github/workflows/coffee-buffalo-live.yml","workflow_dispatch",
     "coffee-b-live-43537333254","70f9e9f846a33cd470b00dbaf0bf189b0b6c7a029b68bd84485f7c6bbe748265",
     "BUFFALO_ORIGINAL_G1"),
    (43547506584,14095080561,"ad939be28597139eb7868dfc37f3f39fa5475205",
     ".github/workflows/coffee-dm-native.yml","push",
     "coffee-dm-native-43547506584","d7d91f825c4d63fe334592f282fea5acf33844ac8487f94feb8e69d86b55414c",
     "DM_12_NATIVE_CANDIDATES"),
    (43548909533,14095701577,"54566cc6197a2508e0b5695bddc3b2836492ee4a",
     ".github/workflows/coffee-dm-modelica.yml","workflow_dispatch",
     "coffee-dm-g2-43548909533","3e6611e9981566101d8f1941f0f588e5812921a3ee162d53258dfc5b33b12ebd",
     "DM_12_OMC_CHECKMODEL_ONLY_LAUNCH_FAILURE"),
    (43550618982,14094919865,"69638301626dd482556f58eaead298a5c620d9bf",
     ".github/workflows/coffee-dm-modelica.yml","workflow_dispatch",
     "coffee-dm-g2-43550618982","1f10695e4dcd27ad4f29552c3c954b4ce26efb131594b0b18076f52a26701925",
     "DM_12_PHYSICAL_G2_NOT_G3"),
    (43558078534,14099445220,"20340bf8b9d6f4549e66fc864a8c29b44c51d7c9",
     ".github/workflows/coffee-b0-feedback.yml","push",
     "coffee-b0-own-feedback-43558078534","1944596c63ffb3b75bee64f3e8e87d3c966a9c8faece8e84aafa20dea6219f8c",
     "FEEDBACK_HISTORICAL_TIMESTAMP_DEFECT_PRESERVED"),
    (43561168032,14100770369,"227e7f20137d99d5da122ffb8a0ee93b069548c7",
     ".github/workflows/coffee-b0-feedback.yml","push",
     "coffee-b0-own-feedback-43561168032","51b56dc28e5c229a280adf3f38062744992a61dc21dff48973e18f48105d10d8",
     "FEEDBACK_13_OF_13_REPLAYED"),
    (43565759793,14102098459,"402cfe945839ca29718c385def6aab9e846ef117",
     ".github/workflows/coffee-buffalo-review.yml","workflow_dispatch",
     "coffee-b-review-43565759793","686db7b34ca177e055a0c4d6fbbef771368baaa412491dad2ed07c1a20a59b65",
     "BUFFALO_R1_G1_TRANSLATED_NOT_G2"),
]
NO_PRIVATE = (*dm.NO_R2, "OPEN_ROUTER_API_KEY")


def need(ok, why):
    if not ok:
        raise ArenaError("COFFEE_V2_P00_P01_" + why)


def identity(env=None):
    env = os.environ if env is None else env
    need(env.get("GITHUB_REPOSITORY") == REPO and
         env.get("GITHUB_REF") == "refs/heads/main" and
         env.get("GITHUB_EVENT_NAME") in ("push", "workflow_dispatch") and
         env.get("GITHUB_RUN_ATTEMPT") == "1" and
         re.fullmatch(r"[1-9][0-9]{0,19}",env.get("GITHUB_RUN_ID","")),
         "MAIN_FIRST_RUN_ONLY")
    need(not any(env.get(k) for k in NO_PRIVATE),
         "PRIVATE_OR_PROVIDER_SECRET_PRESENT")
    return int(env["GITHUB_RUN_ID"])


def verify_history(api):
    """Read metadata only for eight historical, immutable GitHub artifacts."""
    result=[]
    for (run_id,artifact_id,sha,workflow,event,name,zip_sha,stage) in HISTORY:
        run=api.run(run_id)
        meta=api.repo("GET",f"/actions/artifacts/{artifact_id}")
        need(run.get("id")==run_id and run.get("head_sha")==sha and
             run.get("head_branch")=="main" and run.get("path")==workflow and
             run.get("event")==event and run.get("run_attempt")==1 and
             run.get("status")=="completed" and run.get("conclusion")=="success",
             "RUN_IDENTITY_FAILED")
        need(meta.get("id")==artifact_id and meta.get("name")==name and
             meta.get("digest")=="sha256:"+zip_sha and
             meta.get("expired") is False and
             meta.get("workflow_run",{}).get("id")==run_id,
             "HISTORICAL_ARTIFACT_NOT_AVAILABLE_OR_HASH_CHANGED")
        result.append({
            "stage":stage,"run_id":run_id,"commit":sha,
            "workflow":workflow,"event":event,"artifact_id":artifact_id,
            "artifact_name":name,"artifact_zip_sha256":"sha256:"+zip_sha,
            "verification":"GITHUB_RUN_AND_ARTIFACT_METADATA_VERIFIED",
        })
    return result


def obtain(api, artifact):
    return api.repo("GET",f"/actions/artifacts/{artifact}/zip",binary=True)


def _number(value, *, name, low=0, high=1e12):
    try:
        x=float(value)
    except (TypeError,ValueError):
        raise ArenaError("COFFEE_V2_P00_P01_BAD_NUMERIC_"+name) from None
    need(math.isfinite(x) and low <= x <= high,"BAD_NUMERIC_"+name)
    return x


def summarize_public(public,case):
    """Declared source coverage vs actual engineering-model consumption."""
    need(public.get("schema")=="arena.coffee-peak.public-b0/1"
         and public.get("condition")=="B0"
         and public.get("selection")==dm.SELECTION
         and case.get("case_sha256",dm.CASE_SHA256)==dm.CASE_SHA256
         and case.get("public_sha256")==dm.PUBLIC_SHA256
         and case.get("input",{}).get("rate_orders_per_hour")==10.0
         and public.get("time",{}).get("construction_end_exclusive")==60.0
         and public["time"].get("window_end")==103.237
         and public["time"].get("future_pos_and_truth")=="NOT_RELEASED",
         "PUBLIC_B0_CONTRACT_MISMATCH")
    pos=public.get("pos_records")
    items=public.get("pos_line_items")
    proxy=public.get("video_proxy")
    need(type(pos) is list and type(items) is list and type(proxy) is list
         and len(pos)==10 and len(items)==13 and len(proxy)==60,
         "PUBLIC_B0_ROWS_NOT_10_13_60")
    paid=[r for r in pos if r.get("pos_record_type")=="sale"]
    need(len(paid)==10 and all(r.get("sale_status")=="paid_synthetic"
             and r.get("synthetic")=="True" and
             r.get("source_class")=="synthetic_pos_view"
             and _number(r.get("timestamp_min_from_peak_start"),
                         name="POS_TIME",high=60)<60
             for r in paid), "PUBLIC_B0_PAYMENTS_NOT_CONSTRUCTION_ONLY")
    order_map={p["order_id"]:p for p in paid}
    need(len(order_map)==10,"PAID_ORDER_IDS_NOT_UNIQUE")
    ids=set()
    for line in items:
        key=line.get("pos_line_id")
        ref=order_map.get(line.get("order_id"))
        need(key not in ids and ref is not None
             and ref["pos_record_id"]==line.get("pos_record_id")
             and line.get("synthetic")=="True"
             and line.get("source_class")=="synthetic_pos_line_item"
             and _number(line.get("quantity"),name="LINE_QTY",low=1)<1000,
             "LINE_ITEM_IS_NOT_AUTHENTIC_PUBLIC_JOIN")
        ids.add(key)
    bins=set()
    for row in proxy:
        t=_number(row.get("minute_from_peak_start"),name="VIDEO_MINUTE",high=59)
        need(t==int(t) and t not in bins and
             row.get("source_class")=="video_customer_presence_proxy_not_arrival_count"
             and row.get("synthetic")=="False" and
             _number(row.get("sample_seconds"),name="VIDEO_SAMPLE_SECONDS",high=60)>0,
             "VIDEO_PROXIES_ARE_NOT_60_PUBLIC_BINS")
        bins.add(int(t))
    need(bins==set(range(60)),"VIDEO_PROXY_BIN_GAP")
    timestamp=sorted(_number(row["timestamp_min_from_peak_start"],
                             name="POS_TIME") for row in paid)
    sku=sorted({x["synthetic_sku"] for x in items})
    need(set(sku)=={"CAFE-EXT","CAFE-LECHE"},
         "UNDECLARED_SYNTHETIC_SKU")
    return {
        "source_type":"ADMITTED_SYNTHETIC_POS_AND_VIDEO_PROXY",
        "evidence_kind":"NOT_REAL_BUSINESS_TRANSACTIONS",
        "public_source_sha256":dm.PUBLIC_SHA256,
        "case_sha256":dm.CASE_SHA256,
        "selection":dm.SELECTION,
        "time":{"unit":"minutes_from_peak_start","construction":[0,60],
                "construction_upper_exclusive":True,
                "nominal_window_end_minutes":103.237,
                "future_43_237_minutes":"NOT_ADMITTED_FOR_PRODUCERS"},
        "counts":{"paid_orders":10,"line_items":13,"minute_proxy_bins":60,
                  "public_refunds":0,
                  "synthetic_beverage_quantity":sum(int(p["beverage_count"]) for p in paid)},
        "timestamps":{"first_paid_min":timestamp[0],
                      "last_paid_min":timestamp[-1],
                      "profile_retained_by_public_source":True,
                      "profile_consumed_by_V1_models":False},
        "skus":sku,
        "observed_paid_rate_orders_per_hour":10.0,
        "modeled_rate_constant_after_minute_60_is_assumption":True,
        "none_of_these_are_measured_pickups":True,
    }


def source_coverage(s):
    """Never promote an inaccessible document claim to verified file evidence."""
    c=s["counts"]
    return [
        {"source":"PUBLIC_B0_POS","kind":"SYNTHETIC_POS_VIEW",
         "verification":"ZIP_BYTES_SHA256_VERIFIED",
         "temporal_coverage":"10 event timestamps in [0,60) min",
         "semantic_coverage":"10 payments, not arrivals/pickups",
         "admitted_rows":c["paid_orders"],"consumed_in_v1":c["paid_orders"],
         "consumption_granularity":"COUNT_TO_CONSTANT_RATE",
         "permission":"PRODUCER_PUBLIC","missing":"pickup timestamp, arrivals, wait"},
        {"source":"PUBLIC_B0_LINE_ITEMS","kind":"SYNTHETIC_POS_LINE_ITEMS",
         "verification":"ZIP_BYTES_SHA256_VERIFIED",
         "temporal_coverage":"joined to 10 payments in [0,60)",
         "semantic_coverage":"13 synthetic line items and SKU codes",
         "admitted_rows":c["line_items"],"consumed_in_v1":0,
         "consumption_granularity":"ADMISSION_VALIDATED_NOT_WORKLOAD_CALIBRATED",
         "permission":"PRODUCER_PUBLIC","missing":"measured manual and machine task times"},
        {"source":"PUBLIC_B0_VIDEO_PROXY","kind":"OBSERVATIONAL_PROXY_IN_SYNTHETIC_VIEW",
         "verification":"ZIP_BYTES_SHA256_VERIFIED",
         "temporal_coverage":"60 complete [minute,minute+1) bins",
         "semantic_coverage":"tracklets and manual queue marks as proxies",
         "admitted_rows":c["minute_proxy_bins"],"consumed_in_v1":0,
         "consumption_granularity":"ADMITTED_NOT_USED_TO_FIT_SERVICE_CAPACITY",
         "permission":"PRODUCER_PUBLIC","missing":"visible pickups and task concurrency"},
        {"source":"VIDEO2_ORIGINAL_FULL","kind":"VIDEO_EXTRACTION_DOCUMENTED_EXTERNALLY",
         "verification":"ROADMAP_CLAIM_ONLY_NOT_SOURCE_BYTES_VERIFIED",
         "temporal_coverage":"roadmap reports 01:43:14.224, 6195 visual samples",
         "semantic_coverage":"variable-specific coverage NOT YET INSPECTED",
         "admitted_rows":None,"consumed_in_v1":0,
         "consumption_granularity":"NOT_IMPORTED_IN_THIS_READ_ONLY_RUN",
         "permission":"SOURCE_OWNER_REVIEW_REQUIRED",
         "missing":"verify video2/README, blocks, superseded files, manual review"},
        {"source":"PRIVATE_SYNTHETIC_PACKAGE","kind":"SYNTHETIC_CUSTODIAN_ONLY",
         "verification":"SOURCE_HASH_ATTESTED_BY_HISTORICAL_CUSTODY_ONLY",
         "temporal_coverage":"roadmap reports 54 synthetic weeks, NOT audited here",
         "semantic_coverage":"truth and scenario generator withheld",
         "admitted_rows":None,"consumed_in_v1":None,
         "consumption_granularity":"NOT_OPENED_PUBLIC_RUN",
         "permission":"CUSTODIAN_EVALUATOR_ONLY",
         "missing":"custodian-only inventory of rows, scenarios, replicas and supersessions"},
        {"source":"RESERVED_B0_FUTURE","kind":"HELDOUT_SYNTHETIC_OUTCOMES",
         "verification":"NOT_OPENED",
         "temporal_coverage":"[60,103.237] min withheld",
         "semantic_coverage":"future pickups/truth NOT supplied",
         "admitted_rows":None,"consumed_in_v1":0,
         "consumption_granularity":"RESERVED_FOR_EVALUATION",
         "permission":"EVALUATOR_ONLY_AFTER_SCIENTIFIC_LOCK",
         "missing":"none; intentionally reserved"},
    ]


def decision_matrix(s):
    n=s["counts"]
    return [
        {"data":"POS payments","rows_available":n["paid_orders"],
         "rows_used_v1":n["paid_orders"],"classification":"USED_DIRECTLY",
         "operator":"COUNT_PAID_ORDERS_DIVIDED_BY_ONE_HOUR",
         "informs":"paid_order_rate_10_orders_per_hour",
         "candidate_mechanism":"exogenous payment inflow",
         "decision_relevance":"B0 baseline","limitation":"not arrivals or completed drinks"},
        {"data":"POS payment timestamps","rows_available":n["paid_orders"],
         "rows_used_v1":0,"classification":"UNSUPPORTED_BY_MODEL",
         "operator":"NONE_V1_CONSTANT_RATE",
         "informs":"time_varying_paid_order_inflow_candidate_P05",
         "candidate_mechanism":"burst-driven backlog",
         "decision_relevance":"separate saturation from low-demand average",
         "limitation":"no post-cutoff payments"},
        {"data":"POS line-item SKU and quantity","rows_available":n["line_items"],
         "rows_used_v1":0,"classification":"UNSUPPORTED_BY_MODEL",
         "operator":"VALIDATED_AT_ADMISSION_NOT_USED_FOR_WORKLOAD",
         "informs":"recipe_or_task_load_NOT_ESTIMATED",
         "candidate_mechanism":"extraction/milk/manual concurrency",
         "decision_relevance":"S2/S4/S5 require actual resource times",
         "limitation":"13 lines are not 13 equal resource cycles"},
        {"data":"minute visual presence/queue proxies",
         "rows_available":n["minute_proxy_bins"],"rows_used_v1":0,
         "classification":"INSUFFICIENT_QUALITY",
         "operator":"PUBLIC_PROXY_PRESERVED_NOT_CALIBRATED",
         "informs":"presence_shape_only",
         "candidate_mechanism":"possible crowding, not service rate",
         "decision_relevance":"directed task/queue review P01",
         "limitation":"tracklets != arrivals or uniquely linked customers"},
        {"data":"service capacity","rows_available":1,"rows_used_v1":1,
         "classification":"USED_AS_CONSTRAINT",
         "operator":"PUBLIC_ASSUMPTION_12_ORDERS_PER_HOUR",
         "informs":"service_capacity","candidate_mechanism":"aggregate service limit",
         "decision_relevance":"S2/S1 effects NOT representable as resource increments",
         "limitation":"not measured; 10/h assumed input does not saturate 12/h"},
        {"data":"response time","rows_available":1,"rows_used_v1":1,
         "classification":"USED_AS_CONSTRAINT",
         "operator":"PUBLIC_ASSUMPTION_0_1_HOUR",
         "informs":"response_time","candidate_mechanism":"lag",
         "decision_relevance":"response bottleneck not identified",
         "limitation":"6 minutes is assumed, not measured"},
        {"data":"postpayment loss","rows_available":1,"rows_used_v1":1,
         "classification":"USED_AS_CONSTRAINT",
         "operator":"PUBLIC_ASSUMPTION_0_05_PER_HOUR",
         "informs":"postpayment_loss_rate","candidate_mechanism":"paid-order exit",
         "decision_relevance":"abandonment/reimbursements require distinct evidence",
         "limitation":"not a measured customer impatience rate"},
        {"data":"future deliveries/pickups",
         "rows_available":None,"rows_used_v1":0,
         "classification":"RESERVED_FOR_EVALUATION",
         "operator":"NONE_NEVER_OPENED",
         "informs":"G3_PICKUPS_RESERVED",
         "candidate_mechanism":"not calibration input",
         "decision_relevance":"prediction gate AFTER lock",
         "limitation":"no observed pickups available for R0 model fitting"},
    ]


def unknowns():
    return [
        {"parameter":"physical_machine_busy_time","identification":"NOT_IDENTIFIABLE_FOR_THIS_CASE",
         "needed":"visible resource busy start/end per task; left/right censor",
         "decision":"S2 machine capacity vs S5 reassignment"},
        {"parameter":"barista_manual_active_time","identification":"NOT_IDENTIFIABLE_FOR_THIS_CASE",
         "needed":"same task manual active intervals and overlaps",
         "decision":"S5 reassignment vs S2 machine capacity"},
        {"parameter":"task_recipe_and_item_load","identification":"ASSUMED",
         "needed":"sample linked SKU/task resource usage; 13 synthetic lines not timings",
         "decision":"S2/S4/S5"},
        {"parameter":"paid_order_to_pickup_elapsed","identification":"NOT_IDENTIFIABLE_FOR_THIS_CASE",
         "needed":"matched payment and pickup timestamps (same order)",
         "decision":"real service and wait; no fabricated p90"},
        {"parameter":"service_capacity_orders_per_hour","identification":"ASSUMED",
         "value":12.0,"unit":"orders/hour",
         "needed":"task durations, concurrency and resource count",
         "decision":"do not infer additional staff/machine impact from scalar capacity"},
        {"parameter":"initial_backlog","identification":"ASSUMED",
         "value":0,"unit":"orders",
         "needed":"snapshot/interval of paid unfinished work before t=0",
         "decision":"backlog at peak start"},
        {"parameter":"incremental_price_and_costs","identification":"NOT_IDENTIFIABLE_FOR_THIS_CASE",
         "needed":"actual labor, electricity, machine, ingredients, refunds",
         "decision":"economic contribution threshold, not actual ROI"},
    ]


def measurement():
    return {
        "status":"MEASURE_FIRST_NO_SX_SELECTED",
        "question":"Is peak limitation predominantly operator manual time or a shared machine resource?",
        "rival_mechanisms":[
            {"id":"MANUAL_TIME_BOTTLENECK","candidate_policy":"S5",
             "explanation":"Operator unavailable during mutually exclusive manual tasks",
             "result_to_test":"manual work queue persists while machine may be free"},
            {"id":"MACHINE_RESOURCE_BOTTLENECK","candidate_policy":"S2",
             "explanation":"Machine remains occupied while compatible manual work can overlap",
             "result_to_test":"machine busy time dominates while operator is sometimes free"},
        ],
        "target_measurement":"Paired timestamp intervals per identified task and resource",
        "events":["manual_task_start","manual_task_end",
                  "machine_busy_start","machine_busy_end",
                  "paid_order_ready_or_pickup_if_linkable"],
        "units":"minutes_from_video_start; task-local opaque ID; resource type",
        "window":"directed reviewed intervals of observed morning peak",
        "sample":"prioritize episodes with overlapping tasks and visible backlog; no target N inferred yet",
        "censoring":"mark off-camera, ambiguous association, clip boundaries and parallel tasks",
        "decision_rule":"Do not select S2 or S5 until feasible competing explanations can be compared using quality-controlled evidence; otherwise continue MEASURE_FIRST",
        "other_required_inputs":"resource count and cost ranges prior to recommending an investment",
        "evidence_is_not":"a complete staffing census, proof of machine saturation, or ROI",
    }


def _safe_r1(r0raw,r1raw):
    """Independent original-vs-revision native and provider-receipt audit."""
    r0=fb._safe_archive(r0raw,expected_digest="sha256:"+HISTORY[1][6])
    r1=fb._safe_archive(r1raw,expected_digest="sha256:"+HISTORY[-1][6])
    before,initial_receipt,original_sha,_,_=fb._verify_b(r0)
    required={"input.json","admission.json","attempt.json","final.json",
       "process.json","review-analysis.json","provider/receipt.json",
       "provider/sdk-request.json","provider/native-engine-result.json",
       "provider/translated.mo","provider/translation-report.json",
       "provider/cloudflare-effective-request.json",
       "provider/provider-raw.json","provider/cf-call-started.json"}
    need(required<=set(r1),"R1_RECEIPT_OR_NATIVE_MISSING")
    info={name:json.loads(r1[name]) for name in (
       "input.json","admission.json","attempt.json","final.json",
       "review-analysis.json","provider/receipt.json","provider/sdk-request.json",
       "provider/native-engine-result.json","provider/translation-report.json")}
    inp=info["input.json"]
    rec=info["provider/receipt.json"]
    fin=info["final.json"]
    analysis=info["review-analysis.json"]
    native=info["provider/native-engine-result.json"]
    script=info["provider/sdk-request.json"]
    trans=info["provider/translation-report.json"]
    need(rec.get("run_id")==HISTORY[-1][0]
         and rec.get("run_sha")==HISTORY[-1][2]
         and rec.get("case_sha256")==dm.CASE_SHA256
         and rec.get("source_parent_live_run")==HISTORY[1][0]
         and rec.get("source_feedback_run")==HISTORY[-2][0]
         and rec.get("parent_native_file_sha256")==original_sha
         and rec.get("feedback_diagnostic_sha256")==
             "sha256:86e80cea5a9ee919681ac041ed3b8a6658c657b46b89efd03e4bccdc02c45ec8"
         and rec.get("original_engine")=="Engine.generate"
         and rec.get("original_current_model_in_sdk_request") is True
         and rec.get("sdk_interceptions")==rec.get("provider_posts")==1
         and rec.get("http_status")==200 and rec.get("model_returned") is True
         and rec.get("raw_provider_saved") is True and rec.get("retry") is False
         and rec.get("new_omc")==0 and rec.get("r2_access") is False
         and rec.get("truth_access") is False
         and rec.get("scientific_lock_created") is False
         and fin.get("status")=="REVIEW_NATIVE_RETURNED_NOT_G2"
         and fin.get("provider_posts_observed")==1
         and fin.get("retries")==0
         and inp.get("currentModel")==before["model"]
         and inp.get("source_model_sha256")==original_sha
         and inp.get("feedback_run_id")==HISTORY[-2][0]
         and info["admission.json"].get("as_of_replayed") is True,
         "R1_PARENT_PROVIDER_OR_BUDGET_NOT_AUTHENTIC")
    messages=script.get("messages",[])
    assistants=[m for m in messages if m.get("role")=="assistant"]
    need(len(assistants)==1 and
         json.loads(assistants[0].get("content","null"))==before["model"]
         and messages[-1].get("role")=="user"
         and messages[-1].get("content","").endswith(inp["prompt"]),
         "R1_SDK_DID_NOT_CONSUME_EXACT_CURRENTMODEL")
    need(sha_bytes(r1["provider/native-engine-result.json"])==
             rec.get("native_file_sha256")==
             analysis.get("revised_native_file_sha256")
         and analysis.get("parent_native_file_sha256")==original_sha
         and analysis.get("native_semantic_admissible") is True
         and analysis.get("translation_status")==
             "TRANSLATABLE_G1_ONLY_NOT_SIMULATED"
         and trans.get("variables")==len(native["model"]["variables"])
         and trans.get("status")==
             "TRANSLATED_WITH_EXPLICIT_LOOKUP_ASSUMPTIONS"
         and trans.get("model")==analysis.get("translated_model"),
         "R1_TRANSLATED_OR_NATIVE_BYTES_NOT_VERIFIED")
    recheck=diagnose(native)
    need(recheck["admissible"] is True and
         recheck["diagnostics"]==analysis.get("native_semantic_diagnostics"),
         "R1_SEMANTIC_RECHECK_NOT_REPRODUCIBLE")
    prior=before["model"]
    newer=native["model"]
    def shape(m):
        types={}
        for v in m["variables"]:
            types[v["type"]]=types.get(v["type"],0)+1
        return {"variables":len(m["variables"]),"relationships":len(m["relationships"]),
                "stocks":types.get("stock",0),"flows":types.get("flow",0),
                "dt_hours":m["specs"]["dt"]}
    old,new=shape(prior),shape(newer)
    name_type=lambda m:{v["name"]:v["type"] for v in m["variables"]}
    need(old["variables"]==10 and old["relationships"]==0
         and new["variables"]==11 and new["relationships"]==12
         and old["stocks"]==new["stocks"]==2
         and old["flows"]==2 and new["flows"]==3
         and name_type(prior)["Paid Order Rate"]=="variable"
         and name_type(newer)["Paid Order Rate"]=="flow"
         and new["dt_hours"]==(103.237/60)/64,
         "R1_NOT_THE_PREVIOUSLY_AUDITED_NATIVE_CHANGE")
    return {
      "status":"R1_INDEPENDENT_NATIVE_AND_SDK_BYTES_AUDITED",
      "source_run":HISTORY[-1][0],"parent_run":HISTORY[1][0],
      "parent_file_sha256":original_sha,
      "revised_file_sha256":rec["native_file_sha256"],
      "original":old,"revision":new,
      "paid_order_rate_type_before":"variable",
      "paid_order_rate_type_after":"flow",
      "original_current_model_in_real_sdk_request":True,
      "feedback_as_of_replayed_before_review":True,
      "provider_posts_observed":1,
      "tokens_observed":rec.get("provider_usage",{}).get("total_tokens"),
      "G1_native_admissible":True,"Modelica_translation":"G1_TRANSLATABLE",
      "G2_modelica_simulation":"NOT_PERFORMED",
      "G3_heldout_evaluation":"NOT_PERFORMED",
      "external_truth_access":False,
    }


def compile_package(public_raw,r0_raw,r1_raw,history,assumptions,out):
    out=Path(out)
    need(not out.exists(),"OUTPUT_EXISTS")
    files=dm.validate_public_zip(public_raw)
    public=json.loads(files["producer-public-b0.json"])
    release=json.loads(files["release.json"])
    with TemporaryDirectory() as temporary:
        tmp=Path(temporary)
        for name,raw in files.items():
            (tmp/name).write_bytes(raw)
        case=build_case(tmp,assumptions,environment={})
    need(digest(case)==dm.CASE_SHA256,"REBUILT_CASE_HASH_MISMATCH")
    audit=_safe_r1(r0_raw,r1_raw)
    summary=summarize_public(public,case)
    coverage=source_coverage(summary)
    matrix=decision_matrix(summary)
    out.mkdir(parents=True,mode=0o700)
    p00={
      "schema":SCHEMA,"phase":"P00_HISTORY_FROZEN",
      "V1_history":history,
      "source_original_archive_hash":"sha256:"+dm.SOURCE_PACKAGE_SHA256,
      "original_source_private":"NOT_OPENED",
      "case_sha256":dm.CASE_SHA256,
      "public_sha256":dm.PUBLIC_SHA256,
      "r1_independent_audit":audit,
      "historical_solver_invocations":24,
      "historical_cloudflare_provider_posts_observed":2,
      "G2_DM":"12_SUCCESSFUL_SIMULATIONS_NOT_G3",
      "G2_BUFFALO_R1":"NOT_PERFORMED",
      "reserved_truth_access":False,
      "scientific_lock_created":False,
      "new_omc":0,"new_provider_posts":0,"r2_access":False,
      "historical_failed_first_G2_run_preserved":True,
      "historical_preP2_feedback_timestamp_defect_preserved":True,
    }
    sources={"schema":SCHEMA,"phase":"P01_SOURCE_COVERAGE",
             "public_summary":summary,"coverage":coverage,
             "coverage_dimensions":{
               "temporal":"public 60/103.237 min only; video2 full source not inspected",
               "semantic":"paid POS and visible proxies, not physical pickups/tasks",
               "admitted_dataset":"one B0 scenario, one replication, one day",
               "actual_model_consumption":"one constant paid-order rate and five assumed parameters"
             },
             "no_claim_of_complete_video_inventory":True}
    measures={"schema":SCHEMA,"phase":"P01_DECISION_MECHANISM",
              "matrix":matrix,"unknowns":unknowns(),
              "first_intervention_or_measurement":measurement(),
              "evaluation_v1_reserve_not_opened":True}
    write_json(out/"p00-v1-status.json",p00,exclusive=True)
    write_json(out/"p01-sources.json",sources,exclusive=True)
    write_json(out/"p01-mechanisms.json",measures,exclusive=True)
    with (out/"p01-consumption.csv").open("x",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(matrix[0]))
        w.writeheader()
        for row in matrix:
            need(set(row)==set(matrix[0]),"INCONSISTENT_CONSUMPTION_FIELDS")
            w.writerow(row)
    text=(
      "# Arena cafetería V2.1 — P00/P01 primera entrega verificable\n\n"
      "## Estado V1\n\n"
      f"- **{len(history)} artifacts históricos**: identidad y digest GitHub autenticados.\n"
      "- D/M: 12 G2 auténticos, 24 invocaciones OMC históricas; G3 NO realizado.\n"
      "- Buffalo R0 y R1: 2 POST reales históricos; auditoría independiente R1"
      " de hashes nativos, solicitud SDK, revisión y traducción G1.\n"
      "- Buffalo G2: no realizado. Sin lock científico ni verdad reservada.\n\n"
      "## Cobertura pública comprobada\n\n"
      f"- {summary['counts']['paid_orders']} pagos sintéticos, "
      f"{summary['counts']['line_items']} partidas sintéticas, "
      f"{summary['counts']['minute_proxy_bins']} minutos de proxies visibles.\n"
      "- V1: 10 pagos agregados en 10 pedidos/h; se **desaprovechan** tiempos,"
      " mezclas por partida y proxies para calibración.\n"
      "- V1 B0 se seleccionó en un escenario de demanda baja; no acredita pico"
      " máximo ni saturación. No equiparar ventas, personas, vasos y entregas.\n"
      "- Video2 completo y 54 semanas sintéticas: sólo referencias"
      " documentales; sus bytes NO fueron inspeccionados aquí.\n\n"
      "## Decisión inicial (todavía no una intervención)\n\n"
      "**MEASURE_FIRST**: comparar ocupación de máquina frente a actividad manual"
      " del barista y sus solapamientos, preservando censura e incertidumbre."
      " No seleccionar contratación (S1), compra de equipo (S2),"
      " ni reasignación (S5) con el actual dato agregado 10/h < 12/h"
      " supuestos. El informe detallado está en p01-mechanisms.json.\n\n"
      "## Seguridad y alcance\n\n"
      "- Archivos publicados aquí sólo contienen conteos, nombres de campos,"
      " fuentes y diagnósticos; ningún ID POS, modelo rival, prompt, verdad"
      " privada o vínculo de custodio.\n"
      "- Ningún POST nuevo, OMC, R2, scoring G3 o nuevo mundo.\n"
      "- Para completar P01, un custodio autorizado debe inspeccionar"
      " **solo cobertura y metadatos** del video2 y paquete privado,"
      " sin liberar resultados futuros a productores.\n")
    (out/"REVIEW.md").write_text(text,encoding="utf-8")
    filenames=sorted(p.name for p in out.iterdir())
    receipt={"schema":SCHEMA,"status":"P00_FROZEN_P01_PUBLIC_INVENTORIED_MORE_SOURCES_PENDING",
             "case_sha256":dm.CASE_SHA256,"public_source_sha256":dm.PUBLIC_SHA256,
             "historical_artifacts_verified":len(history),
             "G1_buffalo_original_R1_bytes_verified":True,
             "public_pos_payments":10,"public_line_items":13,
             "public_visual_proxy_minutes":60,
             "source_video2_bytes_inspected":False,
             "private_week_scenarios_rows_inspected":False,
             "scientific_lock_created":False,"new_provider_posts":0,
             "new_omc":0,"r2_access":False,"truth_access":False,
             "output_sha256":{p:sha_bytes((out/p).read_bytes()) for p in filenames}}
    write_json(out/"receipt.json",receipt,exclusive=True)
    need(set(out.iterdir())=={out/f for f in filenames+["receipt.json"]},
         "UNEXPECTED_OUTPUT_FILES")
    return receipt


def execute(out, *,env=None,api=None,assumptions=dm.ASSUMPTIONS):
    env=os.environ if env is None else env
    identity(env)
    if api is None:
        need(bool(env.get("GH_TOKEN")),"READONLY_GITHUB_TOKEN_REQUIRED")
        api=GitHub(REPO,Secret(env["GH_TOKEN"],"GITHUB_TOKEN"))
    history=verify_history(api)
    return compile_package(
       obtain(api,HISTORY[0][1]),
       obtain(api,HISTORY[1][1]),
       obtain(api,HISTORY[-1][1]),
       history,assumptions,out)


def main(argv=None):
    p=argparse.ArgumentParser(description="V2.1 P00/P01 exact public history, no private truth")
    p.add_argument("--out",type=Path,required=True)
    args=p.parse_args(argv)
    try:
        receipt=execute(args.out)
        print(json.dumps({key:receipt[key] for key in (
          "status","historical_artifacts_verified",
          "G1_buffalo_original_R1_bytes_verified",
          "new_omc","new_provider_posts","r2_access","truth_access")},
          sort_keys=True))
        return 0
    except (ArenaError,ValueError,TypeError,KeyError, OSError,
            ImportError,json.JSONDecodeError) as exc:
        print(json.dumps({"status":"P00_P01_STOPPED_NO_EXTERNAL_CONSUMPTION",
            "reason":str(exc) if isinstance(exc,ArenaError)
                     else "INPUT_OR_IMPLEMENTATION_INVALID"}),file=sys.stderr)
        return 2

if __name__=="__main__":
    raise SystemExit(main())
