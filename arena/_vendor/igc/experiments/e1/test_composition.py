"""E1 decisive falsifiers. Independent evaluator worlds are NOT supplied here."""
import copy
import json
import sys
import unittest
from collections import Counter
from pathlib import Path

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import composer
import backend


def run(name):
    cfg,classes,_=composer.load_registry(HERE/name)
    return cfg,classes,composer.enumerate_graphs(cfg,classes)


class E1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base_cfg,cls.base_classes,cls.base=run("registry.base.json")
        cls.ext_cfg,cls.ext_classes,cls.ext=run("registry.extended.json")

    def test_base_reproduces_small_reference_space_without_variant_list(self):
        self.assertEqual(len(self.base),6)
        self.assertEqual(len({k for k,_ in self.base}),6)
        for _,g in self.base:
            composer.check_graph(g,self.base_cfg,self.base_classes)
        stages=Counter(sum(x["role"]=="transit" for x in g["instances"]) for _,g in self.base)
        self.assertEqual(dict(stages),{0:2,1:2,2:2})

    def test_swapped_registry_adds_valid_msl_component_without_composer_edit(self):
        self.assertEqual(len(self.ext),15)
        base_hashes={key for key,_ in self.base}
        ext_hashes={key for key,_ in self.ext}
        self.assertTrue(base_hashes.issubset(ext_hashes))
        self.assertEqual(len(ext_hashes-base_hashes),9)
        self.assertTrue(any(any(x["role"]=="amplifier" for x in g["instances"])
                            for _,g in self.ext))
        self.assertEqual(
            {x["modelica"] for x in self.ext_cfg["new_classes"]},
            {"Modelica.Blocks.Math.Gain"}
        )

    def test_renaming_extension_role_still_produces_models_without_algorithm_change(self):
        cfg=copy.deepcopy(self.ext_cfg)
        cfg["roles"]["telemetry"]=cfg["roles"].pop("amplifier")
        cfg["new_classes"][0]["roles"]=["telemetry"]
        made=composer.enumerate_graphs(cfg,self.ext_classes if False else
            {**self.base_classes, "signal-gain":cfg["new_classes"][0]})
        self.assertEqual(len(made),15)
        self.assertTrue(any(any(x["role"]=="telemetry" for x in g["instances"])
                            for _,g in made))

    def test_resource_budget_from_registry_alone_changes_search_space(self):
        cfg=copy.deepcopy(self.base_cfg)
        cfg["roles"]["transit"]["max_instances"]=0
        self.assertEqual(len(composer.enumerate_graphs(cfg,self.base_classes)),2)
        cfg["roles"]["transit"]["max_instances"]=3
        self.assertEqual(len(composer.enumerate_graphs(cfg,self.base_classes)),8)

    def test_repeated_instance_ids_are_not_new_canonical_structures(self):
        g=copy.deepcopy(next(g for _,g in self.base
                             if sum(x["role"]=="transit" for x in g["instances"])==2))
        before=composer.canonical(g)
        rename={x["id"]:"test"+str(i) for i,x in enumerate(g["instances"])}
        for x in g["instances"]:x["id"]=rename[x["id"]]
        for e in g["links"]:
            for field in ("from","to"):
                name,port=e[field].split(".")
                e[field]=rename[name]+"."+port
        self.assertEqual(before,composer.canonical(g))
        composer.check_graph(g,self.base_cfg,self.base_classes)

    def test_wrong_signal_and_material_units_fail_independently(self):
        cfg=copy.deepcopy(self.ext_cfg)
        classes=copy.deepcopy(self.ext_classes)
        classes["signal-gain"]["ports"][0]["unit"]="units"
        with self.assertRaisesRegex(ValueError,"UNIT_MISMATCH"):
            composer.enumerate_graphs(cfg,classes)
        classes=copy.deepcopy(self.ext_classes)
        classes["signal-gain"]["ports"][0]["type"]="FLOW<Shipment>"
        # Lost information input, not a valid edge; the system cannot hallucinate adapter.
        self.assertEqual(len(composer.enumerate_graphs(cfg,classes)),6)

    def test_bad_parameter_binding_cannot_be_sneaked_into_graph(self):
        cfg=copy.deepcopy(self.ext_cfg)
        cfg["roles"]["amplifier"]["parameters"]["k"]=10
        # Registry inputs undergo a separate parameter-range check in loader;
        # AST compiler also verifies parameters before generating Modelica.
        _,g=next((k,g) for k,g in self.ext if any(
             x["role"]=="amplifier" for x in g["instances"]))
        bad=copy.deepcopy(g)
        next(x for x in bad["instances"] if x["role"]=="amplifier")["parameters"]["k"]=10
        with self.assertRaisesRegex(ValueError,"PARAMETER_NOT_ADMISSIBLE"):
            backend.render_model("Bad",bad,self.ext_cfg,self.ext_classes)

    def test_fails_on_disconnected_typed_physical_cycle(self):
        _,g=next((k,g) for k,g in self.base if sum(
            x["role"]=="transit" for x in g["instances"])==2)
        bad=copy.deepcopy(g)
        # Physically connect transit1 -> transit0 while keeping other ports typed.
        for edge in bad["links"]:
            if edge["from"]=="transit1.completed":
                edge["to"]="transit0.arrival"
        with self.assertRaisesRegex(ValueError,"MULTIPLE_INCOMING|DISCONNECTED_MATERIAL"):
            composer.check_graph(bad,self.base_cfg,self.base_classes)

    def test_no_topology_code_or_ode(self):
        code=(HERE/"composer.py").read_text(encoding="utf-8")
        compiler=(HERE/"backend.py").read_text(encoding="utf-8")
        for source in (code,compiler):
            self.assertNotIn("TransitAndReport",source)
            self.assertNotIn("TransitOnly",source)
            self.assertNotIn("for transit_stages in",source)
            self.assertNotIn("der(stock)",source)
        for i,(k,g) in enumerate(self.ext):
            model=backend.render_model("Test"+str(i),g,self.ext_cfg,self.ext_classes)
            self.assertIn("  model Test"+str(i),model)
            self.assertNotIn("der(",model)
            self.assertEqual(model.count("connect("),len(g["links"])+1)

    def test_undersized_search_budget_fails_closed(self):
        cfg=copy.deepcopy(self.ext_cfg)
        cfg["max_candidates"]=2
        with self.assertRaisesRegex(ValueError,"SEARCH_BUDGET_EXCEEDED"):
            composer.enumerate_graphs(cfg,self.ext_classes)

    def test_generation_is_not_inference(self):
        self.assertNotIn("truth",json.dumps(self.base_cfg).lower())
        self.assertNotIn("gold",json.dumps(self.ext_cfg).lower())
        self.assertTrue(all(not {"world_id","true_structure","oracle"}&set(g)
                            for _,g in self.ext))


if __name__=="__main__":
    unittest.main()
