"""P39 consumer: observed machine labels + assumed enabled groups.

Historical one-group dossier is preserved byte-for-byte. The pinned
first-15min video2 timer pairs are distinct from synthetic CONSTRUCTION POS
days: no matching of timestamps, drinks or orders is attempted.

The bounded comparison is two existing construction loads, under 1 and
3 enabled groups, with EVERY OTHER parameter held fixed. This is a
hypothetical infrastructure representation correction, not a purchase.
"""
from __future__ import annotations

import argparse
import copy
import json
from collections import defaultdict
from pathlib import Path

from .common import ArenaError, digest, read_json, write_json
from . import coffee_v2_reference as physical
from . import coffee_v2_reference_inputs as inputs
from . import coffee_v2_p11 as p11
from . import coffee_next_action as next_action
from . import coffee_hydra_timers_p39 as timers
from . import coffee_espresso_p38 as p38

SCHEMA="arena.coffee.p39.hydra-model-consumption/1"
CONFIG_SCHEMA="arena.coffee.p39.hydra-declared-configuration/1"
INPUT_HORIZON_MIN=105.0
SELECTED=("LOWER_PAID_INPUT_Q25","HIGHER_PAID_INPUT_Q75")


def need(ok,code):
    if not ok:
        raise ArenaError("COFFEE_P39_HYDRA_"+code)


def prepare(machine_dir, config_path, historical_dossier):
    """Machine observation must affect the model configuration, not just log."""
    machine=inputs.read_hydra_machine_view(machine_dir)
    cfg=read_json(config_path)
    need(cfg.get("schema")==CONFIG_SCHEMA,"WRONG_DECLARED_CONFIGURATION")
    machine_cfg=cfg.get("equipment",{})
    installed=machine_cfg.get("installed_group_ids")
    enabled=machine_cfg.get("assumed_enabled_group_ids_in_scenario")
    state=machine_cfg.get("availability_by_group")
    need(installed==list(timers.GROUPS) and
         enabled==list(timers.GROUPS) and
         type(state) is dict and set(state)==set(timers.GROUPS) and
         all(state[x]=="NOT_INDEPENDENTLY_VERIFIED" for x in state) and
         machine_cfg.get("installed_status")==
         "USER_IDENTIFIED_WITH_VIDEO_GROUP_LABELS" and
         machine_cfg.get("enabled_status")==
         "SCENARIO_ASSUMPTION_NOT_OBSERVED_SIMULTANEOUS_AVAILABILITY",
         "THREE_GROUPS_VERSUS_AVAILABILITY_NOT_SEPARATED")
    need(set(machine["group_presence_counts"])==set(installed)
         and all(machine["group_presence_counts"][id]>0 for id in enabled),
         "MACHINE_VIEW_DOES_NOT_SUPPORT_GROUP_IDENTITIES")
    need(cfg.get("duration_policy",{}).get(
        "machine_timer_pairs_can_be_used_as_complete_cycles") is False and
         machine["identifiable_complete_auto_extraction_cycles"]==0 and
         cfg["duration_policy"]["existing_illustrative_espresso_auto_min"]==1.5
         and cfg.get("preserve_historical_one_group_dossier") is True and
         cfg.get("not_an_equipment_purchase_or_intervention") is True,
         "PARTIAL_TIMER_CANNOT_CALIBRATE_AUTOMATIC_TIME")
    physical.config_gate(historical_dossier)
    need(historical_dossier["policy"]=="B0" and
         historical_dossier["resources"]["espresso_group"]["units"]==1 and
         historical_dossier["durations"]["espresso_auto_min"]["value"]==1.5,
         "ORIGINAL_1_GROUP_90_SECOND_DOSSIER_REQUIRED")
    new=copy.deepcopy(historical_dossier)
    new["resources"]["espresso_group"]={
        "units":len(enabled),
        "status":"ASSUMED",
        "evidence":"HYDRA_THREE_GROUPS_ASSUMED_ENABLED_NOT_OBSERVED",
    }
    physical.config_gate(new)
    before=copy.deepcopy(new)
    before["resources"]["espresso_group"]=historical_dossier[
        "resources"]["espresso_group"]
    need(before==historical_dossier,
         "CHANGED_OTHER_ASSUMPTIONS_OR_AUTOMATIC_TIMES")
    return machine,cfg,new


def allocate_group_slots(intervals, n):
    """Assign simulated espresso work to identical exclusive group slots.

    This does NOT identify which physical G01/G02/G03 was used in video.
    The clock intervals are returned by the reference scheduler.
    """
    need(type(n) is int and 1<=n<=3,
         "GROUP_SLOT_COUNT")
    slots={name:{"busy_min":0.0,"tasks":0} for name in timers.GROUPS[:n]}
    end_by_slot={k:0.0 for k in slots}
    relevant=sorted(((start,end) for stage,start,end,required in intervals
                     if stage=="espresso_auto"),key=lambda x:(x[0],x[1]))
    for start,end in relevant:
        need(0<=start<end and end<10000,"INVALID_ESPRESSO_INTERVAL")
        chosen=next((k for k in slots if end_by_slot[k]<=start+1e-8),None)
        need(chosen is not None,"OVERLAPPING_EXTRACTION_WITHOUT_GROUP_SLOT")
        end_by_slot[chosen]=end
        slots[chosen]["busy_min"]+=end-start
        slots[chosen]["tasks"]+=1
    return {
        "slots":{k:{"simulated_busy_min":round(v["busy_min"],6),
                    "simulated_espresso_tasks":v["tasks"]}
                 for k,v in slots.items()},
        "capacity_groups_simulated":n,
        "total_tasks":len(relevant),
        "no_group_slot_double_booked":True,
        "group_ids_are_abstract_simulated_slots_not_video_tracking":True,
    }


def diagnose(view_dir,machine_dir,cfg_path,historical_dossier,
             *, archived_reference=None, native_m_root=None):
    """Two loads, B0-1 group and 3 assumed enabled groups: four ref runs."""
    machine,cfg,new=prepare(machine_dir,cfg_path,historical_dossier)
    selection=p11._verified_load_choices(view_dir)
    need(type(selection) is dict and
         type(selection.get("selected")) is list and
         len(selection["selected"])==2 and
         {x["load_label"] for x in selection["selected"]}==set(SELECTED),
         "EXACT_CONSTRUCTION_LOW_AND_HIGH_REQUIRED")
    published=archived_reference
    if published is not None:
        need(published.get("schema")==next_action.SCHEMA
             and published.get("dossier_sha256")==digest(historical_dossier),
             "ARCHIVED_REFERENCE_NOT_ORIGINAL_DOSSIER")
    outputs=[]
    for chosen in selection["selected"]:
        load=chosen["load_label"]
        case=inputs.select_case_day(
            view_dir,chosen["case_id"],chosen["day"])
        need(case["partition"]=="CONSTRUCTION" and
             abs(case["horizon"]-INPUT_HORIZON_MIN)<1e-6,
             "NO_RESERVED_CASE_OR_DIFFERENT_HORIZON")
        snapshots=[]
        for tag,dossier in (("HISTORICAL_ONE_ENABLED",historical_dossier),
                            ("HYDRA_THREE_ENABLED_ASSUMED",new)):
            result,intervals,_=physical._engine(
                case["positions"],case["items"],dossier,case["horizon"],
                diagnose_stage_waits=True)
            status=allocate_group_slots(
                intervals,dossier["resources"]["espresso_group"]["units"])
            need(status["total_tasks"]==result["synthetic_beverage_units"] and
                 max(row["simulated_espresso_tasks"] for row in
                     status["slots"].values())<=
                 result["synthetic_beverage_units"] and
                 len(status["slots"])==
                 dossier["resources"]["espresso_group"]["units"],
                 "GROUP_SIMULATION_AUDIT_INCONSISTENT")
            snapshots.append({
                "case":tag,
                "assumed_enabled_group_count":dossier["resources"][
                    "espresso_group"]["units"],
                "assumed_automatic_extraction_min":dossier["durations"][
                    "espresso_auto_min"]["value"],
                "paid_orders":result["synthetic_paid_orders"],
                "beverage_units":result["synthetic_beverage_units"],
                "handoffs_before_cut":result[
                    "modeled_handoffs_during_halfopen_peak"],
                "p90_paid_to_handoff_full_drain_min":result[
                    "modeled_paid_to_handoff_p90_full_drain_min"],
                "diagnostics":result["mechanism_diagnostics"],
                "simulated_group_slots":status,
            })
        before,after=snapshots
        need(before["paid_orders"]==after["paid_orders"]
             and before["beverage_units"]==after["beverage_units"]
             and before["assumed_automatic_extraction_min"]==
             after["assumed_automatic_extraction_min"]==1.5,
             "UNDECLARED_INPUT_OR_TIMING_CHANGE")
        if published is not None:
            candidate=[row for row in published["baseline"]
                       if row["load_label"]==load]
            need(len(candidate)==1 and
                 before["paid_orders"]==candidate[0]["paid_orders"] and
                 before["handoffs_before_cut"]==
                 candidate[0]["B0_peak_handoffs"] and
                 abs(before["p90_paid_to_handoff_full_drain_min"]-
                     candidate[0]["B0_p90_full_drain_min"])<1e-6,
                 "HISTORICAL_B0_NOT_REPRODUCED")
        m_stage=(p38.native_m_stage_diagnostic(
            native_m_root,load,before["paid_orders"])
            if native_m_root is not None else None)
        outputs.append({
            "load_label":load,
            "M_native_stage_cap_diagnostic":({
                "prep_max_uncapped_orders_per_hour":
                    m_stage["M_max_uncapped_preparation_release_per_hour"],
                "preparation_cap_binding":
                    m_stage["M_preparation_capacity_binding_in_sample"],
                "espresso_max_uncapped_orders_per_hour":
                    m_stage["M_max_uncapped_espresso_release_per_hour"],
                "espresso_cap_binding":
                    m_stage["M_espresso_capacity_bound_active_in_sample"],
                "epistemic_scope":"EXISTING_M_AGGREGATE_NOT_HYDRA_GROUP_CAPACITY",
            } if m_stage is not None else
                {"status":"NOT_READ_IN_FIXTURE_ONLY_TEST"}),
            "comparison":snapshots,
            "delta_handoffs_at_cut":
                after["handoffs_before_cut"]-before["handoffs_before_cut"],
            "delta_p90_min":round(
                after["p90_paid_to_handoff_full_drain_min"]-
                before["p90_paid_to_handoff_full_drain_min"],8),
            "same_paid_orders_and_beverage_mix":True,
            "change_only_one_to_three_assumed_enabled_groups":True,
        })
    need(len(outputs)==2,"NOT_TWO_LOADS")
    return {
        "schema":SCHEMA,
        "question":"WITH_THREE_INSTALLED_GROUPS_WHAT_IS_KNOWN_VS_ASSUMED",
        "status":"THREE_GROUP_HYDRA_SCENARIO_CONDITIONAL_NOT_CALIBRATED",
        "machine_evidence_consumer":machine,
        "configured_installed_groups":cfg["equipment"]["installed_group_ids"],
        "scenario_assumed_enabled_groups":cfg["equipment"][
            "assumed_enabled_group_ids_in_scenario"],
        "simultaneous_availability_observed":False,
        "timer_pairs_used_for_group_identity_count":machine["timer_pairs"],
        "automatic_extraction_time_minutes_used":1.5,
        "automatic_time_origin":"EXAMPLE_REFERENCE_DOSSIER_ASSUMPTION_ONLY",
        "timer_pairs_used_to_calibrate_auto_time":0,
        "manual_load_remove_clean_explicitly_modeled":False,
        "previous_one_to_two_group_result_applies_to_hydra":False,
        "scenarios":outputs,
        "hypotheses":{
            "H_PHYSICAL_EXTRACTION_CAPACITY_IN_PRACTICE":"UNTESTED_VIDEO_OCCUPANCY_AND_AVAILABILITY",
            "H_OPERATOR_CANNOT_FEED_THREE_GROUPS":"UNTESTED_OPERATOR_INTERVALS_NOT_AVAILABLE",
            "H_THREE_ENABLED_GROUPS_ALTERS_SYNTHETIC_REFERENCE":
                "TESTED_CONDITIONAL_ON_UNVERIFIED_1_5_MIN_PER_BEVERAGE",
        },
        "next_observation":"REVIEW_TIMER_RESETS_AND_VIDEO_SEGMENTS_TO_CONFIRM_COMPLETE_EXTRACTION_CYCLES_AND_CONCURRENT_G01_G02_G03_UTILIZATION",
        "no_real_business_capacity_or_roi_inferred":True,
        "external_consumption":{"new_OMC":0,"new_worlds":0,"provider_POST":0},
    }


def export_report(result,out):
    out=Path(out)
    need(not out.exists(),"NO_OUTPUT_OVERWRITE")
    out.mkdir(parents=True,exist_ok=False)
    write_json(out/"hydra-diagnosis.json",result,exclusive=True)
    machine=result["machine_evidence_consumer"]
    lines=[
        "# P39 — Synesso MVP Hydra: evidence consumed, limitations retained",
        "",
        "**Installed groups: G01, G02, G03** (owner declared; all 3 labeled",
        "in existing first-15min machine timer observations).",
        "Observed timer pairs: **"+str(machine["timer_pairs"])+
        "** (G01 "+str(machine["group_presence_counts"]["G01"])+
        ", G02 "+str(machine["group_presence_counts"]["G02"])+
        ", G03 "+str(machine["group_presence_counts"]["G03"])+").",
        "Locally compatible counter/video increments: "+
            str(machine["timer_pair_local_compatible"])+
            "; reset/ambiguous: "+
            str(machine["timer_pair_reset_or_unknown_activation"])+
            "; mismatched: "+str(machine["timer_pair_clock_mismatched"])+".",
        "Confirmed complete extraction cycles: **0**.",
        "Availability of all three groups at once: **UNKNOWN**.",
        "",
        "## Precisely one configuration factor changed (hypothetical)",
        "",
        "| Load | 1 group handoffs / P90 | 3 enabled groups handoffs / P90 | Δ handoffs | Δ P90 |",
        "|---|---|---|---:|---:|",
    ]
    for row in result["scenarios"]:
        b,a=row["comparison"]
        lines.append(
            f"| {row['load_label']} | "
            f"{b['handoffs_before_cut']} / "
            f"{b['p90_paid_to_handoff_full_drain_min']:.3f} min | "
            f"{a['handoffs_before_cut']} / "
            f"{a['p90_paid_to_handoff_full_drain_min']:.3f} min | "
            f"{row['delta_handoffs_at_cut']:+d} | "
            f"{row['delta_p90_min']:+.3f} min |")
    if all(row["M_native_stage_cap_diagnostic"].get(
            "prep_max_uncapped_orders_per_hour") is not None
           for row in result["scenarios"]):
        lines += [
            "",
            "## P38 correction from the original native M CSV",
            "",
            "| Load | Preparation uncapped / assumed cap (h⁻¹) | Prep cap binding? | Espresso uncapped / assumed cap (h⁻¹) | Espresso cap binding? |",
            "|---|---:|---|---:|---|",
        ]
        for row in result["scenarios"]:
            m=row["M_native_stage_cap_diagnostic"]
            lines.append(
                f"| {row['load_label']} | "
                f"{m['prep_max_uncapped_orders_per_hour']:.3f} / 12 | "
                f"{'yes' if m['preparation_cap_binding'] else 'no'} | "
                f"{m['espresso_max_uncapped_orders_per_hour']:.3f} / 15 | "
                f"{'yes' if m['espresso_cap_binding'] else 'no'} |")
        lines += [
            "The low-load preparation capacity is NOT binding; it only",
            "becomes binding in the high-load native M case. Neither",
            "case makes the generic espresso capacity binding.",
        ]
    lines += [
        "",
        "**Source / model boundary:** machine data are historical VIDEO2",
        "counter readings, NOT synthetic POS/recipes or independently",
        "verified extraction-cycle durations. The four reference cases",
        "are synthetic CONSTRUCTION only. The video timers determine",
        "which installed group identities must be represented, but not",
        "how many were jointly available at any particular moment.",
        "",
        "For both scenarios, espresso auto time remains **90 s**, the",
        "uncalibrated historical assumption, NOT the observed timer 28–32 s.",
        "The simulator still collapses manual loading/removal/cleaning",
        "into one assumed setup stage and does not measure real utilization.",
        "No upgrade/new machine is modeled. Installed equipment remains",
        "three groups across both configurations; 1 enabled is a historical",
        "model representation, 3 enabled is a conditional scenario.",
        "",
        "**Unresolved:** determine actual simultaneous enablement,",
        "extraction versus purge, censored endpoints, and operator",
        "load/remove/steam task overlap before deciding a real bottleneck.",
        "Not a purchase recommendation or empirical machine calibration.",
    ]
    (out/"DECISION.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    # Writing UTF-8 report files remains lossless; Windows cp1252 CI
    # consoles cannot encode the Delta/arrow characters used in tables.
    import sys
    report="\n".join(lines)
    encoding=sys.stdout.encoding or "utf-8"
    print(report.encode(encoding,errors="backslashreplace").decode(encoding))


def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("--views",required=True)
    p.add_argument("--machine",required=True)
    p.add_argument("--equipment",required=True)
    p.add_argument("--historical-dossier",required=True)
    p.add_argument("--reference",required=False)
    p.add_argument("--native-M",required=True)
    p.add_argument("--out",required=True)
    args=p.parse_args(argv)
    reference=read_json(args.reference) if args.reference else None
    export_report(diagnose(
        args.views,args.machine,args.equipment,
        read_json(args.historical_dossier),archived_reference=reference,
        native_m_root=args.native_M),
        args.out)


if __name__=="__main__":
    main()
