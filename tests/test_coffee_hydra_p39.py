"""P39 first15 machine timer projection + three-group model, GitHub CI only.

All rows in this fixture are invented for parser testing. Do not report
these tests as validation against the historical ZIP or cafe.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from arena.common import ArenaError, read_json, write_json
from arena import coffee_hydra_timers_p39 as timers
from arena import coffee_hydra_p39 as hydra
from arena import coffee_v2_reference_inputs as inputs
from test_coffee_v2_reference import dossier, paid, item

ROOT=Path(__file__).resolve().parents[1]
EQUIPMENT=ROOT/"experiments/coffee_v2/HYDRA_THREE_GROUPS_DECLARED_P39.json"
HISTORICAL=ROOT/"experiments/coffee_v2/EXAMPLE_REFERENCE_DOSSIER_ASSUMPTIONS_ONLY.json"


def record(rid,group,start,end,c0,c1):
    return {
        "tipo_registro":"medicion_temporizador","registro_id":rid,
        "grupos_extraccion_json":json.dumps([{"grupo":group}]),
        "observado_desde_video_s":str(start),
        "observado_hasta_video_s":str(end),
        "lectura_inicial":str(c0),"lectura_final":str(c1),
        "unidad_medida":"s_mostrados_contador",
        "criterio_temporal":"PAR_DE_LECTURAS",
        "duracion_servicio_estado":"NO_COMPLETA",
        "faltantes_json":"[]",
        "evidencias_json":"[]",
        "fuentes_registros_json":"[]",
    }


def full_source():
    rows=[
        record("TM-T12","G01",640.014,668.010,2,30),
        record("TM-T31","G03",12.000,40.011,0,28),
        record("TM-T33","G03",118.012,122.006,28,32),
    ]
    groups=["G01"]*16+["G02"]*13+["G03"]*5
    for i,group in enumerate(groups):
        rows.append(record("TM-T"+str(100+i),group,300+i*1.0,
                           302+i*1.0,5,7))
    assert len(rows)==37
    return rows + [{"tipo_registro":"otro"} for _ in range(980-37)]


def machine_view(dir):
    result=timers.project_rows(
        full_source(),member_sha="sha256:"+"a"*64)
    write_json(Path(dir)/"machine-timers.json",result,exclusive=True)
    return result


class HydraTimerIntegrationTests(unittest.TestCase):
    def test_pin_37_pairs_and_17_13_7_with_examples_not_full_cycles(self):
        with TemporaryDirectory() as tmp:
            result=machine_view(tmp)
            self.assertEqual(len(result["rows"]),37)
            self.assertEqual(result["count_by_labeled_group"],timers.EXPECTED)
            for rid in timers.EXAMPLES:
                self.assertIn(rid,{x["registro_id"] for x in result["rows"]})
            parsed=inputs.read_hydra_machine_view(tmp)
            self.assertEqual(parsed["timer_pairs"],37)
            self.assertEqual(parsed["identifiable_complete_auto_extraction_cycles"],0)
            self.assertTrue(parsed["machine_group_evidence_used_for_configuration"])
            self.assertTrue(parsed["distinct_groups_observed_not_concurrent_capacity_proved"])
            self.assertEqual(parsed["timer_pair_local_compatible"],37)

    def test_reset_partial_counter_does_not_become_extraction_duration(self):
        rows=[
            record("TM-T12","G01",640.014,668.010,30,0),
            record("TM-T31","G03",12,40,0,28),
            record("TM-T33","G03",118,122,28,32),
        ]
        output=timers.project_rows(rows,member_sha="sha256:"+"f"*64)
        self.assertEqual(output["rows"][0]["pair_observation_status"],
                         "RESET_OR_WRAP_OR_DIFFERENT_ACTIVATION")
        self.assertIsNone(output["rows"][0]["complete_extraction_duration_s"])
        rows[0]["grupos_extraccion_json"]='["UNKNOWN"]'
        output=timers.project_rows(rows,member_sha="sha256:"+"f"*64)
        self.assertEqual(output["rows"][0]["grupo"],"UNKNOWN")
        rows[0]["unidad_medida"]="minutos"
        with self.assertRaisesRegex(ArenaError,
                                    "COUNTER_UNIT_MUST_BE_SECONDS_SHOWN"):
            timers.project_rows(rows,member_sha="sha256:"+"f"*64)

    def test_observed_invalid_or_corrupted_machine_view_fails_closed(self):
        with TemporaryDirectory() as tmp:
            result=machine_view(tmp)
            result["rows"][0]["complete_extraction_duration_s"]=28
            write_json(Path(tmp)/"machine-timers.json",result)
            with self.assertRaisesRegex(ArenaError,
                                        "P39_TIMER_ROW_OR_CYCLE_FALSELY_IDENTIFIED"):
                inputs.read_hydra_machine_view(tmp)
            result=machine_view_after_corruption_reset(tmp)
            result["rows"][0]["observado_hasta_video_s"]=9000
            write_json(Path(tmp)/"machine-timers.json",result)
            with self.assertRaisesRegex(ArenaError,
                                        "P39_TIMER_CLOCK_OR_STATUS_TAMPERED"):
                inputs.read_hydra_machine_view(tmp)

    def test_timer_view_really_changes_three_group_model_config(self):
        with TemporaryDirectory() as tmp:
            machine_view(tmp)
            base=read_json(HISTORICAL)
            before=copy.deepcopy(base)
            obs,cfg,three=hydra.prepare(tmp,EQUIPMENT,base)
            self.assertEqual(obs["group_presence_counts"],timers.EXPECTED)
            self.assertEqual(base,before)
            self.assertEqual(base["resources"]["espresso_group"]["units"],1)
            self.assertEqual(three["resources"]["espresso_group"]["units"],3)
            self.assertEqual(three["durations"],base["durations"])
            self.assertEqual(three["resources"]["barista"],
                             base["resources"]["barista"])
            altered=read_json(EQUIPMENT)
            altered["duration_policy"]["machine_timer_pairs_can_be_used_as_complete_cycles"]=True
            p=Path(tmp)/"invalid.json"
            write_json(p,altered,exclusive=True)
            with self.assertRaisesRegex(ArenaError,
                                        "PARTIAL_TIMER_CANNOT_CALIBRATE"):
                hydra.prepare(tmp,p,base)
            result=read_json(Path(tmp)/"machine-timers.json")
            result["rows"]=[x for x in result["rows"]
                            if x["grupo"]!="G03"]
            write_json(Path(tmp)/"machine-timers.json",result)
            with self.assertRaisesRegex(ArenaError,"P39_MACHINE_PROJECTION_CONTRACT"):
                hydra.prepare(tmp,EQUIPMENT,base)

    def test_no_two_extractions_share_simulated_group_slot(self):
        i=[("espresso_auto",0.0,1.5,("espresso_group",)),
           ("espresso_auto",0.25,1.75,("espresso_group",)),
           ("espresso_auto",0.5,2.0,("espresso_group",))]
        result=hydra.allocate_group_slots(i,3)
        self.assertEqual(set(result["slots"]),{"G01","G02","G03"})
        self.assertEqual(result["total_tasks"],3)
        with self.assertRaisesRegex(ArenaError,
                                    "OVERLAPPING_EXTRACTION_WITHOUT_GROUP_SLOT"):
            hydra.allocate_group_slots(i,2)
        later=i+[("espresso_auto",2.1,3.1,("espresso_group",))]
        self.assertEqual(hydra.allocate_group_slots(later,3)["total_tasks"],4)

    def test_two_declared_loads_one_vs_three_only_no_new_model(self):
        with TemporaryDirectory() as tmp:
            machine_view(tmp)
            days={}
            selected=[]
            for label,n in ((hydra.SELECTED[0],19),(hydra.SELECTED[1],46)):
                positions=[paid(str(i)+label,time=2*i) for i in range(n)]
                lines=[item(str(i)+label,time=2*i) for i in range(n)]
                days[label]={"positions":positions,"items":lines,
                             "partition":"CONSTRUCTION","horizon":105.0}
                selected.append({"load_label":label,"case_id":label,"day":1})
            with patch.object(hydra.p11,"_verified_load_choices",
                              return_value={"selected":selected}), \
                 patch.object(hydra.inputs,"select_case_day",
                              side_effect=lambda path,id,day:days[id]):
                result=hydra.diagnose(
                    tmp,tmp,EQUIPMENT,read_json(HISTORICAL))
            self.assertEqual(len(result["scenarios"]),2)
            self.assertEqual(result["timer_pairs_used_for_group_identity_count"],37)
            self.assertEqual(result["timer_pairs_used_to_calibrate_auto_time"],0)
            self.assertEqual(result["configured_installed_groups"],
                             list(timers.GROUPS))
            for r in result["scenarios"]:
                b,a=r["comparison"]
                self.assertEqual([b["assumed_enabled_group_count"],
                                  a["assumed_enabled_group_count"]],[1,3])
                self.assertEqual(b["paid_orders"],a["paid_orders"])
                self.assertEqual(b["beverage_units"],a["beverage_units"])
                self.assertEqual(b["assumed_automatic_extraction_min"],1.5)
                self.assertEqual(a["assumed_automatic_extraction_min"],1.5)
                self.assertEqual(a["simulated_group_slots"][
                    "capacity_groups_simulated"],3)
            hydra.export_report(result,Path(tmp)/"out")
            report=(Path(tmp)/"out/DECISION.md").read_text()
            self.assertIn("UNKNOWN",report)
            self.assertIn("90 s",report)


def machine_view_after_corruption_reset(path):
    output=timers.project_rows(
        full_source(),member_sha="sha256:"+"a"*64)
    write_json(Path(path)/"machine-timers.json",output)
    return output


if __name__=="__main__":
    unittest.main()
