"""P02/P05 exact public time-profile operator: offline fixture and leak guards."""
import copy
from decimal import Decimal
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from arena.common import ArenaError, digest
from arena import coffee_v2_pos_profile as v2

def fixtures():
    times=["0","4.9999","5.0","15","59.9999"]
    pos=[]
    lines=[]
    for i,t in enumerate(times):
        pos.append({
            "pos_record_id":f"TEST_POS_PRIVATE_ID_{i}",
            "order_id":f"TEST_ORDER_PRIVATE_ID_{i}",
            "pos_record_type":"sale","sale_status":"paid_synthetic",
            "timestamp_min_from_peak_start":t,"synthetic":"True",
            "source_class":"synthetic_pos_view"
        })
        lines.append({
            "pos_line_id":f"TEST_LINE_PRIVATE_ID_{i}",
            "pos_record_id":pos[-1]["pos_record_id"],
            "order_id":pos[-1]["order_id"],
            "synthetic_sku":"CAFE-LECHE" if i%2 else "CAFE-EXT",
            "quantity":"1","timestamp_min_from_peak_start":t,
            "synthetic":"True","source_class":"synthetic_pos_line_item"
        })
    visual=[{
        "minute_from_peak_start":str(i),"sample_seconds":"60",
        "mean_public_customer_tracklets_per_second":str(i%5),
        "mean_manual_queue_marks_per_second":str(i%2),
        "source_class":"video_customer_presence_proxy_not_arrival_count",
        "synthetic":"False"
    } for i in range(60)]
    public={
       "schema":"arena.coffee-peak.public-b0/1",
       "evidence_kind":"SYNTHETIC_POS_AND_VIDEO_PROXY",
       "source_package_sha256":"p"*64,
       "condition":"B0","selection":{"scenario_id":"fixture-ONLY","replication":1,
                                     "day_of_week":1},
       "time":{"future_pos_and_truth":"NOT_RELEASED",
               "construction_end_exclusive":60.0,"window_end":103.237},
       "pos_records":pos,"pos_line_items":lines,"video_proxy":visual}
    case={"condition":"B0","frontier":"PAID_ORDER_TO_PICKUP",
          "source_package_sha256":public["source_package_sha256"],
          "public_sha256":digest(public),
          "input":{"public_paid_order_count_before_cut":5,
                   "rate_orders_per_hour":5.0}}
    return public,case

class PublicTimeProfilesTests(unittest.TestCase):
    def test_half_open_edges_conserve_five_payments_and_proxy_seconds(self):
        public,case=fixtures()
        data=v2.observe(public,case)
        self.assertEqual(data["payment_count"],5)
        self.assertEqual(data["line_item_count"],5)
        self.assertEqual([p["bin_width_min"] for p in data["temporal_profiles"]],[5,15])
        bins=data["temporal_profiles"][0]["bins"]
        self.assertEqual([x["synthetic_paid_orders"] for x in bins],
                         [2,1,0,1,0,0,0,0,0,0,0,1])
        self.assertEqual(bins[0]["paid_rate_equivalent_orders_per_hour"],24.0)
        self.assertEqual(bins[1]["paid_rate_equivalent_orders_per_hour"],12.0)
        self.assertEqual(bins[0]["proxy_seconds_summarized"],300)
        self.assertEqual(bins[0]["mean_public_visible_tracklets_per_sample_second"],2.0)
        self.assertEqual(data["temporal_profiles"][1]["sum_paid_orders"],5)
        self.assertEqual([x["synthetic_paid_orders"] for x in
                          data["temporal_profiles"][1]["bins"]],[3,1,0,1])
        self.assertEqual(data["post_construction_status"],
                         "UNKNOWN_HELDOUT_NOT_ZERO_NOT_EXTRAPOLATED")
        self.assertTrue(data["sku_quantities_not_resource_time_or_verified_recipes"])
        self.assertTrue(data["no_arrival_pickup_or_service_calibration"])
        self.assertFalse(data["reserved_truth_access"])

    def test_no_original_ids_or_raw_pos_events_survive_in_output(self):
        public,case=fixtures()
        data=v2.observe(public,case)
        with TemporaryDirectory() as tmp:
            out=Path(tmp)/"results"
            receipt=v2.render(data,out)
            self.assertEqual(receipt["status"],"PUBLIC_PROFILE_REPRODUCED_NOT_FITTED")
            contents="".join(p.read_text() for p in out.iterdir())
            for forbidden in ("TEST_POS_PRIVATE_ID_","TEST_ORDER_PRIVATE_ID_",
                              "TEST_LINE_PRIVATE_ID_", "customer_id",
                              "future_truth", "paid_order_to_pickup_wait_seconds"):
                self.assertNotIn(forbidden,contents)
            self.assertIn("UNKNOWN_HELDOUT",contents)
            self.assertIn("15.0,20.0,1,",contents)
            with self.assertRaisesRegex(ArenaError,"REFUSE_OVERWRITE"):
                v2.render(data,out)

    def test_rejects_future_payment_source_mismatch_and_missing_proxy(self):
        for name in ("future","wrong_count","wrong_hash","wrong_proxy_semantics",
                     "missing_minute","bad_pos_kind","line_nonmatch",
                     "line_duplicate","bad_item_quantity"):
            public,case=fixtures()
            if name=="future":
                public["pos_records"][0]["timestamp_min_from_peak_start"]="60"
            elif name=="wrong_count":
                case["input"]["public_paid_order_count_before_cut"]=6
            elif name=="wrong_hash":
                case["public_sha256"]="sha256:"+"0"*64
            elif name=="wrong_proxy_semantics":
                public["video_proxy"][0]["source_class"]="arrivals_observed"
            elif name=="missing_minute":
                public["video_proxy"].pop()
            elif name=="bad_pos_kind":
                public["pos_records"][0]["pos_record_type"]="arrival"
            elif name=="line_nonmatch":
                public["pos_line_items"][0]["timestamp_min_from_peak_start"]="2"
            elif name=="line_duplicate":
                public["pos_line_items"][1]["pos_line_id"]=public["pos_line_items"][0]["pos_line_id"]
            elif name=="bad_item_quantity":
                public["pos_line_items"][0]["quantity"]="-1"
            if name not in ("wrong_count","wrong_hash"):
                case["public_sha256"]=digest(public)
            with self.subTest(name=name),self.assertRaises(ArenaError):
                v2.observe(public,case)

    def test_profile_operator_widths_fixed_and_halfopen(self):
        public,case=fixtures()
        for widths in ((0,5),(7,15),(5,5),[5,15],(60,0)):
            with self.subTest(widths=widths),self.assertRaisesRegex(
                    ArenaError,"INVALID_TIME_BIN_OPERATORS"):
                v2.observe(public,case,widths=widths)
