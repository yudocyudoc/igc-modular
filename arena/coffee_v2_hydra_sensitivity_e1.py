"""E1: Q75-only sensitivity of milk priority to 90s -> 30s automatic extraction.

The historical 90s arms are READ from accepted run 44234407455 and are not
re-simulated. Exactly two new 30s B arms are run on the verified P11-selected
Q75 CONSTRUCTION inputs. Never publish private order IDs, traces, or raw views.
This is a conditional model comparison, not real-shop calibration.
"""
from __future__ import annotations

import argparse
import copy
import csv
import os
from pathlib import Path

from .common import ArenaError, digest, read_json, write_json
from . import coffee_v2_hydra_physical_b as b
from . import coffee_v2_hydra_causes_c as c
from . import coffee_v2_hydra_policies_d as d
from . import coffee_v2_p11 as p11
from . import coffee_v2_reference_inputs as inputs

SCHEMA="arena.coffee.p47.e1.q75-extraction-sensitivity/1"
HISTORICAL_SCHEMA="arena.coffee.p46.public-eight-scenario-aggregate/1"
HISTORICAL_D_RUN=44234407455
HISTORICAL_D_SHA="e2da7eeaadd7c9e361ca38090a3de25a161916f3"
SOURCE_RUN_ID=43684660729
Q75_LABEL="HIGHER_PAID_INPUT_Q75"
BASE="FCFS_READY_ASSUMED"
MILK="PRIORITIZE_MILK_READY"
OLD_AUTO_MIN=1.5
NEW_AUTO_MIN=0.5
EPS=1e-8


def require(value,code):
    if not value:
        raise ArenaError("COFFEE_P47_E1_"+code)


def rounded(value):
    return round(float(value),9)


def _historical_q75(archive,original_dossier,*,allow_fixture=False):
    """Pin an authenticated D public aggregate and its 90s physical world.

    An explicitly flagged fixture may use a synthetic D public aggregate in
    unit tests. The CLI NEVER enables that exception.
    """
    b.validate(original_dossier)
    require(original_dossier["durations_min"]["espresso_auto_min"]["value"]==
            OLD_AUTO_MIN,"HISTORICAL_PHYSICS_NOT_90_SECONDS")
    require(isinstance(archive,dict) and
            archive.get("schema")==HISTORICAL_SCHEMA and
            archive.get("scenario_count")==8 and
            archive.get("selected_loads")==list(d.ALLOWED_CONSTRUCTION) and
            len(archive.get("results",[]))==2 and
            [x.get("load_label") for x in archive["results"]]==
                list(d.ALLOWED_CONSTRUCTION),
            "NOT_ACCEPTED_D_EIGHT_ARM_ARTIFACT")
    receipt=archive.get("execution_and_consumption",{})
    require(isinstance(receipt,dict),"HISTORICAL_RECEIPT_MISSING")
    if allow_fixture:
        require(receipt.get("status")=="LOCAL_FIXTURE_NOT_GITHUB_RUN" and
                archive.get("source_view_run_id") is None,
                "FIXTURE_MUST_NOT_CLAIM_REAL_CUSTODY")
    else:
        require(receipt.get("status")=="GITHUB_MANUAL_EIGHT_ARM_DISPATCH" and
                receipt.get("github_run_id")==HISTORICAL_D_RUN and
                receipt.get("github_commit_sha")==HISTORICAL_D_SHA and
                receipt.get("source_view_run_id")==SOURCE_RUN_ID and
                receipt.get("R2_views_successfully_retrieved")==8 and
                archive.get("source_view_run_id")==SOURCE_RUN_ID,
                "HISTORICAL_D_RUN_IDENTITY_OR_CUSTODY_MISMATCH")
    q75=archive["results"][1]
    provenance=q75.get("source_provenance",{})
    require(q75.get("physical_dossier_sha256")==digest(original_dossier) and
            provenance.get("verified_adapter")==
                "P11_P39_CONSTRUCTION_SELECT_CASE_DAY" and
            provenance.get("selected_load_label")==Q75_LABEL and
            provenance.get("partition")=="CONSTRUCTION" and
            provenance.get("selection_receipt_sha256")==
                archive.get("source_selection_sha256") and
            len(q75.get("arms",[]))==4 and
            [arm.get("policy") for arm in q75["arms"]]==list(d.POLICIES),
            "HISTORICAL_D_Q75_PROVENANCE_OR_POLICY_MISMATCH")
    for arm in q75["arms"]:
        require(arm["paid_orders"]==q75["paid_orders"] and
                arm["synthetic_beverages"]==q75["synthetic_beverages"],
                "HISTORICAL_D_LOAD_NOT_CONSERVED")
    if not allow_fixture:
        require(q75["paid_orders"]==46 and
                q75["synthetic_beverages"]==53,
                "NOT_PREVIOUS_Q75_46_53_INPUT")
    return q75


def verified_30s_dossier(original):
    """Change only extraction duration (and its evidence annotation)."""
    b.validate(original)
    require(original["durations_min"]["espresso_auto_min"]["value"]==
            OLD_AUTO_MIN,"EXPECTED_OLD_90S_DOSSIER")
    updated=copy.deepcopy(original)
    updated["durations_min"]["espresso_auto_min"]["value"]=NEW_AUTO_MIN
    updated["durations_min"]["espresso_auto_min"]["evidence"]=(
        "E1_30S_SENSITIVITY_FROM_PARTIAL_T31_T33_T12_COUNTER_EPISODES_"
        "NOT_FULL_CYCLE_OR_REAL_SHOP_CALIBRATION")
    b.validate(updated)
    controlled=copy.deepcopy(updated)
    controlled["durations_min"]["espresso_auto_min"]["value"]=OLD_AUTO_MIN
    controlled["durations_min"]["espresso_auto_min"]["evidence"]=(
        original["durations_min"]["espresso_auto_min"]["evidence"])
    require(controlled==original,"E1_CHANGED_OTHER_PHYSICAL_PARAMETER")
    return updated


def _waits(diag):
    accounting=diag["causal_accounting"]
    return {
        "total_resource_wait_task_min":
            accounting["total_resource_wait_task_min"],
        "stage_resource_wait_task_min":{
            stage:record["resource_wait_task_min"]
            for stage,record in accounting["stage_breakdown"].items()},
        "strict_extraction_signal_task_min":
            diag["hypotheses"]["extraction_limits"]["signal_task_min"],
        "manual_block_with_group_free_task_min":
            diag["hypotheses"]["preparation_or_loading_limits"][
                "signal_task_min_MANUAL_BLOCKED_WITH_GROUP_FREE"],
    }


def _stage_changes(base_trace,milk_trace):
    base=d.starts_by_task(base_trace)
    variant=d.starts_by_task(milk_trace)
    require(set(base)==set(variant),"POLICY_CHANGED_FINISHED_TASK_SET")
    output={stage:{"earlier_task_starts":0,"later_task_starts":0,
                   "earlier_start_min":0.0,"later_start_min":0.0,
                   "changed_actor_assignments":0}
            for stage in b.STAGES}
    for key in base:
        left,right=base[key],variant[key]
        row=output[key[2]]
        delta=right["time"]-left["time"]
        if delta>EPS:
            row["later_task_starts"]+=1
            row["later_start_min"]+=delta
        if delta<-EPS:
            row["earlier_task_starts"]+=1
            row["earlier_start_min"]-=delta
        if left["actor"]!=right["actor"]:
            row["changed_actor_assignments"]+=1
    for row in output.values():
        for name in ("earlier_start_min","later_start_min"):
            row[name]=rounded(row[name])
    return output


def _actor_work(base_trace,milk_trace,dossier):
    base_work=d.actor_work(base_trace,dossier)
    milk_work=d.actor_work(milk_trace,dossier)
    result={}
    for actor in dossier["operators"]:
        require(actor in base_work and actor in milk_work,
                "OPERATOR_MISSING_FROM_RESULTS")
        a,z=base_work[actor],milk_work[actor]
        result[actor]={
            "fcfs_busy_manual_min":a["busy_manual_minutes"],
            "milk_busy_manual_min":z["busy_manual_minutes"],
            "delta_busy_manual_min_positive_is_more_work":
                rounded(z["busy_manual_minutes"]-a["busy_manual_minutes"]),
            "fcfs_stage_busy_manual_min":a["stage_busy_manual_min"],
            "milk_stage_busy_manual_min":z["stage_busy_manual_min"],
        }
    return result


def compare_verified_q75(view_dir,archive,original_dossier,*,
                         dispatch_authorized=False,source_receipt=None,
                         allow_fixture_for_tests=False):
    """Exactly two new B runs, after verified Q75 provenance and authorization.

    No R2 calls are performed here. The caller supplies a read-only view dir.
    Only unit tests may set allow_fixture_for_tests=True.
    """
    require(dispatch_authorized is True,"REQUIRES_EXPLICIT_TWO_ARM_AUTHORIZATION")
    q75=_historical_q75(archive,original_dossier,
                        allow_fixture=allow_fixture_for_tests)
    if not allow_fixture_for_tests:
        require(isinstance(source_receipt,dict) and
                source_receipt.get("status")==
                    "EXISTING_CONSTRUCTION_VIEWS_VERIFIED_NO_NEW_CORPUS" and
                source_receipt.get("read_only_source_run_id")==SOURCE_RUN_ID and
                source_receipt.get("R2_views_successfully_retrieved")==8,
                "CURRENT_PRIVATE_SOURCE_RECEIPT_INVALID")
    else:
        require(source_receipt is None,
                "FIXTURE_MUST_NOT_CLAIM_PRIVATE_SOURCE_RECEIPT")
    selection=p11._verified_load_choices(view_dir)
    require([x["load_label"] for x in selection["selected"]]==
            list(d.ALLOWED_CONSTRUCTION) and
            digest(selection)==archive["source_selection_sha256"],
            "Q75_SELECTION_DIFFERS_FROM_ACCEPTED_D_RUN")
    chosen=selection["selected"][1]
    require(chosen["load_label"]==Q75_LABEL,
            "NOT_THE_Q75_CONSTRUCTION_SELECTION")
    case=inputs.select_case_day(view_dir,chosen["case_id"],chosen["day"])
    require(case["partition"]=="CONSTRUCTION" and
            case["horizon"]==q75["source_horizon_min"] and
            digest({"case_id":chosen["case_id"],"day":chosen["day"]})==
                q75["source_provenance"]["selected_case_day_digest"] and
            digest({"positions":case["positions"],"items":case["items"]})==
                q75["source_provenance"]["case_paid_input_digest"],
            "Q75_CASE_DAY_OR_INPUT_NOT_HISTORICAL")
    baseline_digest=digest({
        "positions":case["positions"],"lines":case["items"],
        "horizon_min":case["horizon"],"physical_dossier":original_dossier})
    require(baseline_digest==q75["scenario_input_sha256"],
            "NOT_SAME_Q75_INPUT_OR_ORIGINAL_PHYSICS")
    changed=verified_30s_dossier(original_dossier)
    runs={}
    for policy in (BASE,MILK):
        result,trace,completed=b._engine(
            case["positions"],case["items"],changed,case["horizon"],
            dispatch_policy=policy)
        diagnosis=c.diagnose_trace(
            result,trace,changed,fixture_label="CONSTRUCTION_SYNTHETIC_Q75",
            dispatch_policy=policy,
            _construction_capability=c._VERIFIED_CONSTRUCTION_ADAPTER)
        require(diagnosis["dispatch_policy"]==policy and
                result["paid_orders"]==q75["paid_orders"] and
                result["synthetic_beverages"]==q75["synthetic_beverages"] and
                len(completed)==q75["paid_orders"],
                "E1_MASS_BALANCE_OR_POLICY_NOT_MATCHED")
        runs[policy]=(result,trace,completed,diagnosis)
    base_result,base_trace,base_done,base_diag=runs[BASE]
    milk_result,milk_trace,milk_done,milk_diag=runs[MILK]
    require(set(base_done)==set(milk_done),"FINISHED_ORDER_SET_DIFFERS")
    delays=[milk_done[k]-base_done[k] for k in base_done]
    earlier=sum(x<-EPS for x in delays)
    later=sum(x>EPS for x in delays)
    unchanged=len(delays)-earlier-later
    old={arm["policy"]:arm for arm in q75["arms"]}
    delta_old=(old[MILK]["p90_paid_to_handoff_full_drain_min"]-
               old[BASE]["p90_paid_to_handoff_full_drain_min"])
    delta_new=(milk_result["modeled_paid_to_handoff_p90_full_drain_min"]-
               base_result["modeled_paid_to_handoff_p90_full_drain_min"])
    overrides=[e for e in milk_trace if e["event"]=="dispatch_override"]
    require(all(e["policy"]==MILK and e["selected_stage"]=="milk"
                for e in overrides),"NOT_EXCLUSIVELY_MILK_PRIORITY")
    old_reference=[
        {"auto_extraction_seconds":90,"policy":policy,
         "p50_paid_to_handoff_min":old[policy][
             "p50_paid_to_handoff_full_drain_min"],
         "p90_paid_to_handoff_min":old[policy][
             "p90_paid_to_handoff_full_drain_min"],
         "handoffs_before_source_cut":
             old[policy]["handoffs_before_source_cut"],
         "source":"ARCHIVED_ACCEPTED_D_RUN_44234407455_NOT_RERUN"}
        for policy in (BASE,MILK)]
    new_scenarios=[
        {"auto_extraction_seconds":30,"policy":policy,
         "p50_paid_to_handoff_min":runs[policy][0][
             "modeled_paid_to_handoff_p50_full_drain_min"],
         "p90_paid_to_handoff_min":runs[policy][0][
             "modeled_paid_to_handoff_p90_full_drain_min"],
         "handoffs_before_source_cut":runs[policy][0][
             "modeled_handoffs_before_cut"],
         "orders_pending_at_source_cut":runs[policy][0][
             "modeled_handoffs_after_cut"],
         "waits_C":_waits(runs[policy][3]),
         "source":"NEW_30_SECOND_E1_CONDITIONAL_MODEL"}
        for policy in (BASE,MILK)]
    require(all(r["handoffs_before_source_cut"]+
                r["orders_pending_at_source_cut"]==q75["paid_orders"]
                for r in new_scenarios),
            "ORDERS_NOT_CONSERVED_AT_SOURCE_CUT")
    return {
        "schema":SCHEMA,
        "scope":"Q75_VERIFIED_CONSTRUCTION_NOT_REAL_CAFE",
        "historical_D_run_id":HISTORICAL_D_RUN if not
            allow_fixture_for_tests else None,
        "historical_D_commit_sha":HISTORICAL_D_SHA if not
            allow_fixture_for_tests else None,
        "R2_source_run_id":SOURCE_RUN_ID if not
            allow_fixture_for_tests else None,
        "source_selection_sha256":digest(selection),
        "q75_selected_case_day_digest":q75["source_provenance"][
            "selected_case_day_digest"],
        "q75_input_digest_90s":baseline_digest,
        "q75_input_digest_30s":digest({
            "positions":case["positions"],"lines":case["items"],
            "horizon_min":case["horizon"],"physical_dossier":changed}),
        "physical_dossier_90s_sha256":digest(original_dossier),
        "physical_dossier_30s_sha256":digest(changed),
        "changed_physical_parameter":"durations_min.espresso_auto_min.value",
        "physical_parameter_before_min":OLD_AUTO_MIN,
        "physical_parameter_after_min":NEW_AUTO_MIN,
        "counter_evidence_not_full_cycle_calibration":True,
        "paid_orders":q75["paid_orders"],
        "synthetic_beverages":q75["synthetic_beverages"],
        "source_horizon_min":case["horizon"],
        "historical_90s_arms":old_reference,
        "new_30s_arms":new_scenarios,
        "new_scenarios_executed":2,
        "old_scenarios_rerun":0,
        "delta_p90_milk_minus_FCFS_at_90s_seconds":rounded(60*delta_old),
        "delta_p90_milk_minus_FCFS_at_30s_seconds":rounded(60*delta_new),
        "difference_of_policy_effect_30s_minus_90s_seconds":
            rounded(60*(delta_new-delta_old)),
        "milk_vs_FCFS_at_30s":{
            "priority_dispatch_overrides":len(overrides),
            "orders_earlier":earlier,
            "orders_later":later,
            "orders_unchanged":unchanged,
            "maximum_order_delay_seconds":rounded(
                60*max([x for x in delays if x>EPS],default=0.0)),
            "maximum_order_advance_seconds":rounded(
                -60*min([x for x in delays if x<-EPS],default=0.0)),
            "stage_start_shifts":_stage_changes(base_trace,milk_trace),
            "operator_manual_work":_actor_work(
                base_trace,milk_trace,changed),
        },
        "classification":(
            "MODEL_MILK_P90_ADVANTAGE_PERSISTS_30S" if delta_new<-EPS else
            "MODEL_MILK_P90_TIES_30S" if abs(delta_new)<=EPS else
            "MODEL_MILK_P90_REVERSES_30S"),
        "limits":{
            "FCFS_is_assumed_not_observed_dispatch":True,
            "not_a_real_shop_calibration_or_service_effect":True,
            "timer_29_32_31s_are_partial_contextual_readings":True,
            "no_private_per_order_or_task_rows_exported":True,
            "no_stochastic_replicates_or_uncertainty_estimate":True,
            "no_new_world_corpus_solver_or_provider":True,
        },
    }


def _validate_public(report):
    require(report.get("schema")==SCHEMA and
            report.get("scope")=="Q75_VERIFIED_CONSTRUCTION_NOT_REAL_CAFE" and
            report.get("new_scenarios_executed")==2 and
            report.get("old_scenarios_rerun")==0 and
            report.get("changed_physical_parameter")==
                "durations_min.espresso_auto_min.value" and
            len(report.get("historical_90s_arms",[]))==2 and
            len(report.get("new_30s_arms",[]))==2,
            "NOT_TWO_ARM_E1_PUBLIC_RESULT")
    for name in ("historical_90s_arms","new_30s_arms"):
        require([x["policy"] for x in report[name]]==[BASE,MILK],
                "NOT_BASE_AND_MILK_ONLY")


def export(report,output_dir,*,run_receipt=None):
    _validate_public(report)
    target=Path(output_dir)
    require(not target.exists(),"OUTPUT_ALREADY_EXISTS")
    target.mkdir(mode=0o700,parents=True)
    data=copy.deepcopy(report)
    if run_receipt is None:
        data["execution_and_consumption"]={
            "status":"LOCAL_SOFTWARE_FIXTURE_NO_R2_OR_HISTORICAL_CUSTODY",
            "R2_read_attempts":0,
            "R2_billing_cost":"NOT_APPLICABLE_LOCAL_FIXTURE",
            "new_solver_and_provider_attempts":0,
        }
    else:
        require(run_receipt.get("status")=="E1_MANUAL_TWO_ARM_DISPATCH" and
                run_receipt.get("github_run_id") and
                run_receipt.get("github_commit_sha") and
                run_receipt.get("R2_read_attempts")==8,
                "INVALID_E1_EXECUTION_RECEIPT")
        data["execution_and_consumption"]=dict(run_receipt)
    write_json(target/"E1_Q75_SENSITIVITY_AGGREGATE.json",data,exclusive=True)
    rows=[]
    for row in report["historical_90s_arms"]+report["new_30s_arms"]:
        rows.append({
            "auto_extraction_seconds":row["auto_extraction_seconds"],
            "policy":row["policy"],
            "paid_orders":report["paid_orders"],
            "synthetic_beverages":report["synthetic_beverages"],
            "p50_min":row["p50_paid_to_handoff_min"],
            "p90_min":row["p90_paid_to_handoff_min"],
            "handoffs_before_source_cut":row["handoffs_before_source_cut"],
            "source":row["source"],
        })
    with (target/"E1_Q75_FOUR_CELLS.csv").open(
            "x",encoding="utf-8",newline="") as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    stage=[]
    for policy in (BASE,MILK):
        item=next(x for x in report["new_30s_arms"] if x["policy"]==policy)
        for name,minutes in item["waits_C"]["stage_resource_wait_task_min"].items():
            stage.append({"policy":policy,"stage":name,
                          "resource_wait_task_min":minutes})
    with (target/"E1_Q75_30S_STAGE_WAITS.csv").open(
            "x",encoding="utf-8",newline="") as stream:
        writer=csv.DictWriter(stream,fieldnames=list(stage[0]))
        writer.writeheader()
        writer.writerows(stage)
    md=[
        "# E1 · Q75: sensibilidad 90s → 30s de extracción automática",
        "",
        "**Comparación de construcción sintética, NO calibración ni "
        "recomendación para la cafetería real.**",
        "",
        "Mismo Q75 verificado: "+str(report["paid_orders"])+" pedidos, "+
        str(report["synthetic_beverages"])+" bebidas. FCFS supuesta vs "
        "prioridad de leche; dos escenarios nuevos a 30s y dos resultados "
        "históricos a 90s **reutilizados sin ejecutar**.",
        "",
        "| Extracción | Política | P50 (min) | P90 (min) | Fuente |",
        "|---:|---|---:|---:|---|",
    ]
    for x in rows:
        md.append("| "+str(x["auto_extraction_seconds"])+"s | "+
                  x["policy"]+" | "+str(x["p50_min"])+" | "+
                  str(x["p90_min"])+" | "+x["source"]+" |")
    md.extend([
        "",
        "**ΔP90 leche − FCFS a 90s:** "+
        str(report["delta_p90_milk_minus_FCFS_at_90s_seconds"])+" s.",
        "**ΔP90 leche − FCFS a 30s:** "+
        str(report["delta_p90_milk_minus_FCFS_at_30s_seconds"])+" s.",
        "**Cambio del efecto de política:** "+
        str(report["difference_of_policy_effect_30s_minus_90s_seconds"])+" s.",
        "**Clasificación:** "+report["classification"],
        "**Perdedores a 30s:** "+
        str(report["milk_vs_FCFS_at_30s"]["orders_later"])+
        " pedidos, retraso máximo "+
        str(report["milk_vs_FCFS_at_30s"]["maximum_order_delay_seconds"])+" s.",
        "**Ganadores a 30s:** "+
        str(report["milk_vs_FCFS_at_30s"]["orders_earlier"])+
        " pedidos, adelanto máximo "+
        str(report["milk_vs_FCFS_at_30s"]["maximum_order_advance_seconds"])+" s.",
        "",
        "Los CSV y JSON agregados incluyen esperas por etapa y reparto de "
        "trabajo B01/B02. No se publica un solo ID ni tiempo de pedido.",
        "Los contadores ~29/32/31s son lecturas contextuales y no miden "
        "la duración completa ni prueban capacidad disponible real.",
        "**Costo R2:** "+
        str(data["execution_and_consumption"].get("R2_billing_cost")),
        "**Run nuevo:** "+
        str(data["execution_and_consumption"].get("github_run_id")),
        "**Run D histórico:** "+str(report["historical_D_run_id"]),
        "**Run fuente R2:** "+str(report["R2_source_run_id"]),
    ])
    (target/"E1_Q75_DECISION.md").write_text(
        "\n".join(md)+"\n",encoding="utf-8")
    return data


def _verified_manual():
    from . import coffee_e2e as e2e
    require(os.environ.get("GITHUB_EVENT_NAME")=="workflow_dispatch" and
            os.environ.get("GITHUB_REF")=="refs/heads/main" and
            os.environ.get("GITHUB_RUN_ATTEMPT")=="1" and
            os.environ.get("GITHUB_WORKFLOW_REF","").endswith(
                "/.github/workflows/coffee-hydra-p47-e1-manual.yml"
                "@refs/heads/main"),
            "MANUAL_MAIN_FIRST_ATTEMPT_ONLY")
    return e2e.execution_identity()


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument("--mode",choices=("verify-archive","fetch","compare"),
                        required=True)
    parser.add_argument("--authorize-two-scenarios",action="store_true")
    parser.add_argument("--source-run-id",type=int)
    parser.add_argument("--historical",required=True)
    parser.add_argument("--dossier",required=True)
    parser.add_argument("--historical-receipt")
    parser.add_argument("--source-receipt")
    parser.add_argument("--views")
    parser.add_argument("--out",required=True)
    args=parser.parse_args(argv)
    require(args.authorize_two_scenarios and
            args.source_run_id==SOURCE_RUN_ID,
            "MANUAL_REQUIRES_EXPLICIT_TWO_SCENARIOS")
    run_id,sha=_verified_manual()
    dossier=read_json(args.dossier)
    historical=read_json(args.historical)
    _historical_q75(historical,dossier)   # fail before R2 access
    out=Path(args.out)
    require(not out.exists(),"OUTPUT_ALREADY_EXISTS")
    if args.mode=="verify-archive":
        require(not args.source_receipt and not args.views and
                args.historical_receipt,
                "ARCHIVE_ONLY_ARGUMENTS")
        write_json(out,{
            "status":"HISTORICAL_D_ARCHIVE_VERIFIED_BEFORE_ANY_R2_READ",
            "github_run_id":run_id,"github_commit_sha":sha,
            "historical_D_run_id":HISTORICAL_D_RUN,
            "historical_D_sha":HISTORICAL_D_SHA,
            "historical_aggregate_sha256":digest(historical),
        },exclusive=True)
        print("E1_HISTORICAL_D_ARCHIVE_VERIFIED",HISTORICAL_D_RUN)
        return
    require(args.historical_receipt and
            Path(args.historical_receipt).is_file(),
            "HISTORICAL_ARCHIVE_GATE_RECEIPT_MISSING")
    gate=read_json(args.historical_receipt)
    require(gate.get("status")==
                "HISTORICAL_D_ARCHIVE_VERIFIED_BEFORE_ANY_R2_READ" and
            gate.get("github_run_id")==run_id and
            gate.get("github_commit_sha")==sha and
            gate.get("historical_D_run_id")==HISTORICAL_D_RUN and
            gate.get("historical_aggregate_sha256")==digest(historical),
            "HISTORICAL_ARCHIVE_GATE_NOT_THIS_RUN")
    require(args.source_receipt,"SOURCE_RECEIPT_REQUIRED")
    receipt_path=Path(args.source_receipt)
    if args.mode=="fetch":
        require(not args.views and not receipt_path.exists(),
                "FETCH_RECEIPT_OR_VIEWS_ALREADY_EXISTS")
        from . import coffee_s5_availability as s5
        from . import coffee_e2e as e2e
        write_json(receipt_path,{
            "status":"R2_READ_ATTEMPT_STARTED_OUTCOME_UNKNOWN",
            "github_run_id":run_id,"github_commit_sha":sha,
            "read_only_source_run_id":SOURCE_RUN_ID,
            "R2_read_attempts":"UNKNOWN_IF_PARTIAL_FAILURE",
            "R2_billing_cost":"UNKNOWN_NO_PROVIDER_RECEIPT",
            "new_solver_and_provider_attempts":0,"no_new_corpus":True,
        },exclusive=True)
        fetched=s5.fetch_existing_construction_views(out)
        require(fetched["read_only_source_run_id"]==SOURCE_RUN_ID,
                "R2_SOURCE_ID_CHANGED")
        final=dict(fetched)
        final.update({
            "github_run_id":run_id,"github_commit_sha":sha,
            "R2_read_attempts":len(e2e.VIEW_FILES),
            "R2_views_successfully_retrieved":len(e2e.VIEW_FILES),
            "R2_billing_cost":"UNKNOWN_NO_PROVIDER_RECEIPT",
            "new_solver_and_provider_attempts":0,"no_new_corpus":True,
        })
        write_json(receipt_path,final)
        print("E1_VERIFIED_HISTORICAL_VIEWS",SOURCE_RUN_ID,
              "GET_ATTEMPTS",len(e2e.VIEW_FILES),"BILLING_UNKNOWN")
        return
    require(args.mode=="compare" and args.views and
            Path(args.views).is_dir() and receipt_path.is_file(),
            "COMPARE_NEEDS_VERIFIED_VIEWS")
    source_receipt=read_json(receipt_path)
    require(source_receipt.get("github_run_id")==run_id and
            source_receipt.get("github_commit_sha")==sha,
            "PRIVATE_SOURCE_RECEIPT_CROSS_RUN")
    report=compare_verified_q75(
        args.views,historical,dossier,dispatch_authorized=True,
        source_receipt=source_receipt)
    execution={
        "status":"E1_MANUAL_TWO_ARM_DISPATCH",
        "github_run_id":run_id,"github_commit_sha":sha,
        "historical_D_run_id":HISTORICAL_D_RUN,
        "source_view_run_id":SOURCE_RUN_ID,
        "R2_read_attempts":source_receipt["R2_read_attempts"],
        "R2_views_successfully_retrieved":
            source_receipt["R2_views_successfully_retrieved"],
        "R2_billing_cost":"UNKNOWN_NO_PROVIDER_RECEIPT",
        "new_scenarios_executed":2,"historical_scenarios_rerun":0,
        "new_solver_and_provider_attempts":0,"new_synthetic_worlds":0,
        "new_corpus":False,
    }
    export(report,out,run_receipt=execution)
    print("E1_TWO_NEW_30S_ARMS",report["new_scenarios_executed"],
          "Q75_PAID",report["paid_orders"],
          "SOURCE_RUN_ID",SOURCE_RUN_ID,
          "BILLING_UNKNOWN",True)


if __name__=="__main__":
    main()
