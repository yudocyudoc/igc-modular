"""Visual P01: synthetic ZIP fixtures, no access to any private source or R2."""
import csv
import hashlib
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
import zipfile

from arena.common import ArenaError
from arena import coffee_v2_video_inventory as inv

EVENT_HEADERS=[
    "registro_id","tipo_evento","estado","rol_actor",
    "observado_desde_video_s","observado_hasta_video_s",
    "apto_parametro_servicio_arena","continuidad_verificada",
    "velocidad_real_verificada","retirada_pase_observada",
    "recepcion_cliente_confirmada","duracion_servicio_min_s",
    "duracion_servicio_max_s","fuentes_registros_json",
]
DETECTION_HEADERS=["video_s","video_second","label_source","label",
                   "synthetic","detection_id"]

def csv_bytes(fields,rows):
    buf=io.StringIO(newline="")
    out=csv.DictWriter(buf,fieldnames=fields,lineterminator="\n")
    out.writeheader();out.writerows(rows)
    return buf.getvalue().encode("utf-8")

def fixture(master_mismatch=False,dup_id=False,eligible=False,
            tamper_manifest=False):
    events=[
      {"registro_id":"E-1","tipo_evento":"maquina_activa",
       "estado":"observado","rol_actor":"barista",
       "observado_desde_video_s":"0.0","observado_hasta_video_s":"0.0",
       "apto_parametro_servicio_arena":"True" if eligible else "False",
       "continuidad_verificada":"False",
       "velocidad_real_verificada":"False",
       "retirada_pase_observada":"False",
       "recepcion_cliente_confirmada":"False",
       "duracion_servicio_min_s":"",
       "duracion_servicio_max_s":"",
       "fuentes_registros_json":'[{"a": 1,"b":2}]'},
      {"registro_id":"E-1" if dup_id else "E-2",
       "tipo_evento":"persona_visible",
       "estado":"probable","rol_actor":"no_determinado",
       "observado_desde_video_s":"900.0","observado_hasta_video_s":"900.0",
       "apto_parametro_servicio_arena":"False",
       "continuidad_verificada":"False",
       "velocidad_real_verificada":"False",
       "retirada_pase_observada":"True",
       "recepcion_cliente_confirmada":"False",
       "duracion_servicio_min_s":"",
       "duracion_servicio_max_s":"",
       "fuentes_registros_json":"[]"},
    ]
    first=dict(events[0])
    first["apto_parametro_servicio_arena"]=first["apto_parametro_servicio_arena"].lower()
    first["fuentes_registros_json"]='[{"b":2,"a":1}]'
    if master_mismatch:first["tipo_evento"]="alterado"
    detection=[
      {"video_s":"0.0","video_second":"0","label_source":"manual",
       "label":"personal","synthetic":"False","detection_id":"PD-1"},
      {"video_s":"1.0","video_second":"1","label_source":"inferred",
       "label":"fila","synthetic":"False","detection_id":"PD-2"},
    ]
    files={
      inv.CONSOLIDATED:csv_bytes(EVENT_HEADERS,events),
      inv.MASTER:csv_bytes(EVENT_HEADERS,[first]),
      inv.DETECTIONS:csv_bytes(DETECTION_HEADERS,detection),
      "video2/sintetico_pico_v1/salida/eventos_truth.csv":
        b"SUPER_PRIVATE_TRUTH_CANARY,NO_UPLOAD\nSECRET,MUST_NEVER_READ\n",
      "video2/sintetico_pico_v1/generar_escenarios.py":
        b"SUPER_PRIVATE_GENERATOR_CANARY=987654321\n",
    }
    meta={"schema":"cafeteria.pilot-package/1","files":{
      name:{"sha256":hashlib.sha256(raw).hexdigest(),"bytes":len(raw)}
      for name,raw in files.items()}}
    if tamper_manifest:
        meta["files"][inv.CONSOLIDATED]["sha256"]="0"*64
    files[inv.MANIFEST]=json.dumps(meta).encode()
    z=io.BytesIO()
    with zipfile.ZipFile(z,"w",zipfile.ZIP_DEFLATED) as out:
        for name,raw in files.items():out.writestr(name,raw)
    return z.getvalue()

class VideoInventoryTests(TestCase):
    def audit_bytes(self,raw,*,historical=False):
        with TemporaryDirectory() as temporary:
            file=Path(temporary)/"source.zip"
            file.write_bytes(raw)
            return inv.audit(file,expected_sha=hashlib.sha256(raw).hexdigest(),
                             historical=historical)

    def test_semantically_same_master_not_double_counted_and_no_truth_access(self):
        raw=fixture()
        accessed=[]
        original=zipfile.ZipFile.read
        def spy(z,name,*args,**kwargs):
            accessed.append(name if isinstance(name,str) else name.filename)
            return original(z,name,*args,**kwargs)
        with patch.object(zipfile.ZipFile,"read",spy):
            result=self.audit_bytes(raw)
        self.assertEqual(set(accessed),set(inv.ALLOWED)|{inv.MANIFEST})
        self.assertTrue(result["first15_event_coverage"][
          "master_semantically_identical_to_consolidated"])
        self.assertEqual(result["first15_event_coverage"][
          "additional_consolidated_events_after_first_15min"],1)
        self.assertEqual(result["full_event_coverage"]["rows"],2)
        self.assertEqual(result["detection_coverage"]["distinct_video_seconds"],2)
        self.assertEqual(result["full_event_coverage"][
          "parameter_service_eligible_rows"],0)
        self.assertEqual(result["private_synthetic_truth_members_opened"],0)
        self.assertEqual(result["private_generator_members_opened"],0)
        out=json.dumps(result)
        self.assertNotIn("PRIVATE_TRUTH_CANARY",out)
        self.assertNotIn("PRIVATE_GENERATOR_CANARY",out)
        self.assertNotIn("E-1",out)
        self.assertNotIn("PD-1",out)
        self.assertTrue(result["semantic_limits"]["video_original_missing"])
        self.assertTrue(result["semantic_limits"]["frame_evidence_missing"])

    def test_sha_manifest_parent_duplicates_semantics_and_eligibility_fail_closed(self):
        r=fixture()
        with TemporaryDirectory() as tmp:
            file=Path(tmp)/"source.zip";file.write_bytes(r)
            with self.assertRaisesRegex(ArenaError,"SOURCE_ARCHIVE_SHA256"):
                inv.audit(file,expected_sha="0"*64,historical=False)
        for name,kwargs,reason in (
            ("manifest",{"tamper_manifest":True},"VISUAL_MEMBER_MANIFEST_HASH"),
            ("master",{"master_mismatch":True},"MASTER_EVENTS_DIFFER"),
            ("duplicate",{"dup_id":True},"DUPLICATE_OR_EMPTY"),
            ("false_eligibility",{"eligible":True},"CANNOT_DECLARE_SERVICE"),
        ):
            with self.subTest(name=name),self.assertRaisesRegex(ArenaError,reason):
                self.audit_bytes(fixture(**kwargs))
        with self.assertRaisesRegex(ArenaError,"PINNED_VISUAL_ROW_COUNTS_CHANGED"):
            self.audit_bytes(r,historical=True)

    def test_export_only_aggregates_and_explicit_measure_first(self):
        result=self.audit_bytes(fixture())
        with TemporaryDirectory() as tmp:
            dst=Path(tmp)/"out"
            receipt=inv.export(result,dst)
            self.assertEqual(len(receipt["outputs"]),2)
            self.assertEqual(sorted(x.name for x in dst.iterdir()),
                             ["REVIEW.md","p01-visual-coverage.json","receipt.json"])
            contents="\n".join(p.read_text() for p in dst.iterdir())
            self.assertIn("MEASURE_FIRST",contents)
            self.assertIn("no_verified_contiguous_service_intervals",contents)
            self.assertNotIn("SUPER_PRIVATE_TRUTH_CANARY",contents)
            self.assertEqual(receipt["private_rows_opened"],0)
            with self.assertRaisesRegex(ArenaError,"OUTPUT_EXISTS"):
                inv.export(result,dst)
