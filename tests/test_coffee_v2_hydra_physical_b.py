"""P44 B toy-world tests. These are software invariants, NOT cafe calibration.

A real video2 operation has no matching synthetic paid order in these tests.
The pre-existing P06/P39 baseline still runs in its own unmodified route.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from arena.common import ArenaError, read_json
from arena import coffee_v2_hydra_physical_b as b
from arena import coffee_hydra_episodes_a as a
from arena import coffee_v2_reference as old
from test_coffee_v2_reference import paid, item

ROOT=Path(__file__).resolve().parents[1]
DOSSIER=ROOT/"experiments/coffee_v2/HYDRA_TWO_OPERATORS_PHYSICAL_B_ASSUMPTIONS.json"
VIEW=ROOT/"experiments/coffee_v2/VIDEO2_EPISODE_REVIEW_A.json"
HIST=ROOT/"experiments/coffee_v2/EXAMPLE_REFERENCE_DOSSIER_ASSUMPTIONS_ONLY.json"


def setup():
    return read_json(DOSSIER)


def run(drinks=1,d=None,milk=False,horizon=10):
    d=d or setup()
    positions=[paid(str(i),time=0) for i in range(drinks)]
    lines=[item(str(i),"con_leche" if milk else "solo_extraccion")
           for i in range(drinks)]
    return b._engine(positions,lines,d,horizon)


def stages(trace,stage,event="start"):
    return [x for x in trace if x["event"]==event and x["stage"]==stage]


def group_changes(trace,state):
    return [x for x in trace if x["event"]=="group_state"
            and x["to"]==state]


class PhysicalB(unittest.TestCase):
    def test_two_identified_actors_two_distinct_stations_prep_in_parallel(self):
        result,trace,_=run(2)
        prep=stages(trace,"prepare")
        self.assertEqual(len(prep),2)
        self.assertEqual([x["time"] for x in prep],[0,0])
        self.assertEqual({x["actor"] for x in prep},{"B01","B02"})
        self.assertEqual({t for x in prep for t in x["tokens"]
                          if t.startswith("S:")},
                         {"S:puesto_izquierdo","S:puesto_derecho"})
        # Prepared off-group: load requires group, prep does not.
        self.assertFalse(any(any(z.startswith("G:") for z in x["tokens"])
                             for x in prep))
        self.assertEqual(result["operators_scenario_assumed"],["B01","B02"])
        self.assertEqual(result["modeled_handoffs_before_cut"],2)

    def test_two_actors_one_station_remains_serial_in_same_clock(self):
        d=setup()
        d["prep_stations"]=["puesto_izquierdo"]
        result,trace,_=run(2,d)
        self.assertEqual(len(stages(trace,"prepare")),2)
        self.assertEqual(sum(x["time"]==0 for x in stages(trace,"prepare")),1)
        self.assertEqual(b.capabilities(d)["resource_units"]["barista"],2)
        self.assertEqual(b.capabilities(d)["resource_units"]["prep_space"],1)

    def test_group_persists_after_counter_stop_waiting_for_operator_to_remove(self):
        d=setup()
        d["enabled_group_ids"]=["G01"]
        d["operators"]["B01"]["availability_windows_min"]=[[0,1],[3,30]]
        d["operators"]["B02"]["availability_windows_min"]=[[0,0.05]]
        _,trace,completed=run(1,d,horizon=9)
        auto_end=stages(trace,"extract_auto","finish")[0]["time"]
        remove_start=stages(trace,"remove","start")[0]["time"]
        release=group_changes(trace,"FREE")[0]["time"]
        self.assertAlmostEqual(auto_end,2.1)
        self.assertAlmostEqual(remove_start,3.0)
        self.assertAlmostEqual(release,3.15)
        self.assertLess(auto_end,remove_start)
        self.assertLess(remove_start,release)
        held=group_changes(trace,"AWAITING_REMOVAL")
        self.assertEqual(len(held),1)
        self.assertEqual(held[0]["group"],"G01")
        self.assertGreater(completed["0"],release)
        self.assertTrue(all(x["group"]=="G01"
                    for x in trace if x["event"]=="group_state"))

    def test_optional_clean_held_group_until_clean_finishes(self):
        d=setup()
        d["clean_after_every_beverage_assumed"]=True
        _,trace,_=run(1,d)
        self.assertEqual(len(stages(trace,"clean")),1)
        remove_end=stages(trace,"remove","finish")[0]["time"]
        clean_start=stages(trace,"clean")[0]["time"]
        clean_end=stages(trace,"clean","finish")[0]["time"]
        released=group_changes(trace,"FREE")[0]["time"]
        self.assertEqual(clean_start,remove_end)
        self.assertGreater(clean_end,remove_end)
        self.assertEqual(clean_end,released)
        self.assertEqual(group_changes(trace,"AWAITING_CLEAN")[0]["group"],
                         group_changes(trace,"CLEANING")[0]["group"])
        self.assertEqual(len(stages(trace,"clean","start")),1)

    def test_automatic_machine_work_overlaps_other_beverage_manual_work(self):
        _,trace,_=run(3)
        autos=stages(trace,"extract_auto")
        preps=stages(trace,"prepare")
        ends={(x["job"],x["stage"]):x["time"] for x in trace
              if x["event"]=="finish"}
        self.assertTrue(any(a0["time"] < ends[(p0["job"],"prepare")]
                            and a0["job"]!=p0["job"] and
                            p0["time"] < ends[(a0["job"],"extract_auto")]
                            for a0 in autos for p0 in preps))

    def test_exclusive_group_identity_no_double_reservation_during_cycle(self):
        d=setup()
        d["enabled_group_ids"]=["G01"]
        result,trace,_=run(3,d,horizon=15)
        assignments=group_changes(trace,"LOADING")
        frees=group_changes(trace,"FREE")
        self.assertEqual(len(assignments),3)
        self.assertEqual(len(frees),3)
        self.assertEqual(result["max_simultaneous_group_reservations"],1)
        for a0,f0 in zip(assignments,frees):
            self.assertEqual(a0["job"],f0["job"])
            self.assertLess(a0["time"],f0["time"])
            self.assertEqual(a0["group"],f0["group"])
        for previous,next_start in zip(frees,assignments[1:]):
            self.assertLessEqual(previous["time"],next_start["time"])

    def test_operator_skills_not_implicitly_interchangeable(self):
        d=setup()
        d["operators"]["B01"]["skills"]=[
            "prepare","load","remove","clean","handoff"]
        d["operators"]["B02"]["availability_windows_min"]=[[2,240]]
        result,trace,_=run(1,d,milk=True,horizon=12)
        milk_tasks=stages(trace,"milk")
        self.assertEqual(len(milk_tasks),1)
        self.assertEqual(milk_tasks[0]["actor"],"B02")
        self.assertGreaterEqual(milk_tasks[0]["time"],2)
        self.assertEqual(result["stage_counts"]["milk"],1)

    def test_no_hidden_full_shift_when_operator_windows_end(self):
        d=setup()
        for person in d["operators"].values():
            person["availability_windows_min"]=[[0,1]]
        with self.assertRaisesRegex(ArenaError,
              "NO_FUTURE_EVENT_TO_RESOLVE_PENDING_TASKS"):
            b._engine([paid("A",time=1.1)],[item("A",time=1.1)],d,5)

    def test_milk_precedence_is_explicit_not_inferred_from_video(self):
        result,trace,_=run(2,milk=True)
        self.assertEqual(result["stage_counts"]["milk"],2)
        for milk in stages(trace,"milk"):
            group_events=[x for x in trace
                          if x["event"]=="group_state" and
                          x["job"]==milk["job"] and x["to"]=="FREE"]
            self.assertEqual(len(group_events),1)
            self.assertLessEqual(group_events[0]["time"],milk["time"])

    def test_a3_can_check_corrected_representation_without_rewriting_A(self):
        bridge=b.episode_adapter(read_json(VIEW),setup())
        states={x["question"]:x["status"] for x in bridge["checks"]}
        self.assertEqual(states[
            "manual_preparation_concurrency_vs_resource_capacity"],
            "COMPATIBLE")
        self.assertEqual(states["portafilter_remains_after_timer_stop"],
                         "COMPATIBLE")
        self.assertEqual(states["automatic_time_vs_displayed_counter"],
                         "INDETERMINATE")
        self.assertTrue(bridge["no_new_simulation"])
        legacy=a.check(read_json(VIEW),read_json(HIST))
        oldstates={x["question"]:x["status"] for x in legacy["checks"]}
        self.assertEqual(oldstates[
            "manual_preparation_concurrency_vs_resource_capacity"],
            "CONTRADICTED")
        self.assertEqual(oldstates["portafilter_remains_after_timer_stop"],
                         "NOT_REPRESENTED")
        with TemporaryDirectory() as tmp:
            b.export_bridge(bridge,Path(tmp)/"report")
            text=(Path(tmp)/"report/B_REPRESENTATION.md").read_text()
            self.assertIn("COMPATIBLE",text)

    def _concurrency(self,d):
        bridge=b.episode_adapter(read_json(VIEW),d)
        return next(row for row in bridge["checks"] if row["question"]==
                    "manual_preparation_concurrency_vs_resource_capacity")

    def test_astra_negative_b02_without_prepare_skill_not_compatible(self):
        d=setup()
        d["operators"]["B02"]["skills"].remove("prepare")
        _,trace,_=run(2,d)
        self.assertEqual([x["time"] for x in stages(trace,"prepare")],
                         [0,0.5])
        row=self._concurrency(d)
        self.assertEqual(row["status"],"CONTRADICTED")
        self.assertEqual(row["model"]["instant_specific_status"],
                         "CONTRADICTED")
        for sample in row["model"]["sample_feasibility"]:
            self.assertEqual(sample["missing_prepare_skill"],["B02"])
            self.assertFalse(sample["scenario_concurrency_feasible"])

    def test_astra_negative_disjoint_operator_calendars_not_compatible(self):
        d=setup()
        d["operators"]["B01"]["availability_windows_min"]=[[0,20]]
        d["operators"]["B02"]["availability_windows_min"]=[[21,240]]
        _,trace,_=run(2,d)
        self.assertEqual([x["time"] for x in stages(trace,"prepare")],
                         [0,0.5])
        row=self._concurrency(d)
        self.assertEqual(row["status"],"CONTRADICTED")
        for sample in row["model"]["sample_feasibility"]:
            self.assertTrue(sample["structure_permits_simultaneous_prepare"])
            self.assertEqual(sample["joint_feasible_calendar_windows_min"],[])
            self.assertFalse(sample["scenario_concurrency_feasible"])

    def test_positive_feasibility_does_not_align_video_to_scenario_clock(self):
        d=setup()
        # Video samples are at 48 s and 104 s, but those are NOT scenario
        # minutes. A shifted yet jointly available shift remains feasible.
        d["operators"]["B02"]["availability_windows_min"]=[[5,240]]
        row=self._concurrency(d)
        self.assertEqual(row["status"],"COMPATIBLE")
        self.assertEqual(row["model"]["sample_instant_clock_alignment"],
                         "NOT_ESTABLISHED")
        self.assertEqual(row["model"]["instant_specific_status"],
                         "INDETERMINATE")
        self.assertTrue(all(x["scenario_concurrency_feasible"] for x in
                            row["model"]["sample_feasibility"]))

    def test_touching_windows_and_too_short_windows_do_not_overlap(self):
        d=setup()
        d["operators"]["B01"]["availability_windows_min"]=[[0,10]]
        d["operators"]["B02"]["availability_windows_min"]=[[10,240]]
        self.assertEqual(self._concurrency(d)["status"],"CONTRADICTED")
        d=setup()
        d["operators"]["B01"]["availability_windows_min"]=[[0,0.4]]
        self.assertEqual(self._concurrency(d)["status"],"CONTRADICTED")

    def test_missing_observed_station_not_hidden_by_worker_headcount(self):
        d=setup()
        d["prep_stations"]=["puesto_izquierdo"]
        row=self._concurrency(d)
        self.assertEqual(row["status"],"CONTRADICTED")
        self.assertTrue(any(x["unavailable_prep_stations"] for x in
                            row["model"]["sample_feasibility"]))

    def test_two_stations_only_if_two_people_both_needed(self):
        d=setup()
        d["prep_stations"]=["puesto_izquierdo","puesto_derecho"]
        d["operators"]["B02"]["availability_windows_min"]=[[5,240]]
        result,trace,_=run(2,d)
        first=[x for x in stages(trace,"prepare") if x["time"]==0]
        self.assertEqual(len(first),1)
        self.assertEqual(result["operators_scenario_assumed"],["B01","B02"])

    def test_invalid_duration_group_and_calendar_fails_closed(self):
        d=setup();d["durations_min"]["load_min"]["value"]=0
        with self.assertRaisesRegex(ArenaError,"INVALID_NUMERIC"):
            b.validate(d)
        d=setup();d["enabled_group_ids"]=["G01","G01"]
        with self.assertRaisesRegex(ArenaError,"GROUP_IDENTITY"):
            b.validate(d)
        d=setup();d["operators"]["B01"]["availability_windows_min"]=[
            [0,3],[2,30]]
        with self.assertRaisesRegex(ArenaError,"INVALID_OR_OVERLAPPING_WINDOWS"):
            b.validate(d)

    def test_public_result_aggregated_no_video_or_synthetic_ids(self):
        result,trace,_=run(1)
        serialized=json.dumps(result)
        self.assertNotIn("pay0",serialized)
        self.assertNotIn("order_id",serialized)
        self.assertNotIn("operadores.jpg",serialized)
        self.assertNotIn("TM-T31",serialized)
        self.assertTrue(result["no_empirical_capacity_or_wait_conclusion"])
        self.assertEqual(result["stage_counts"]["clean"],0)
        self.assertEqual(result["stage_counts"]["prepare"],1)
        self.assertEqual(result["stage_counts"]["handoff"],1)
        self.assertGreater(len(trace),8)
        self.assertTrue(any(x["event"]=="group_state" for x in trace))

    def test_old_reference_engine_results_unmodified_by_b_import(self):
        hist=read_json(HIST)
        a0=old.simulate([paid("A")],[item("A")],hist,6)
        self.assertEqual(a0["modeled_handoffs_during_halfopen_peak"],1)
        self.assertAlmostEqual(
            a0["modeled_paid_to_handoff_p90_full_drain_min"],
            .5+1.5+.2)
        self.assertEqual(hist["resources"]["barista"]["units"],1)
        self.assertEqual(hist["resources"]["espresso_group"]["units"],1)
        self.assertNotEqual(hist["schema"],b.SCHEMA)


if __name__=="__main__":
    unittest.main()
