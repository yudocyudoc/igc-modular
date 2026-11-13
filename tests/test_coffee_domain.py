"""Public-domain contracts, negative leak tests, and trace projections; offline only."""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from arena.common import ArenaError, digest, write_json
from arena.coffee_peak import _load_package, _build_public
from arena.coffee_domain import (
    build_case, validate_assumptions, project_native_counter, PROVENANCE, CUTS_MIN,
)
from arena.coffee_score import PREDICTION_CUTS
from test_coffee_peak import make_zip

ROOT = Path(__file__).resolve().parents[1]
ASSUMPTIONS = ROOT / 'examples/coffee_public_assumptions_v1.json'


class CoffeeDomainTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        source = self.root / 'source.zip'
        sha = make_zip(source)
        settings = {
            'source': {'path': str(source), 'sha256': sha},
            'selection': {'scenario_id': 'case-a', 'replication': 1, 'day_of_week': 1},
            'construction_end_min': 60.0, 'window_end_min': 103.237,
        }
        zf, _ = _load_package(source, sha)
        with zf:
            public = _build_public(zf, settings, sha)
        self.public = self.root / 'public'
        self.public.mkdir()
        write_json(self.public / 'producer-public-b0.json', public)
        release = {
            'schema': 'arena.coffee-peak.public-release/1', 'protocol': 'coffee_peak_capacity_v1',
            'run_id': '123', 'frozen_sha': 'a' * 40,
            'source_package_sha256': sha, 'public_sha256': digest(public),
            'condition': 'B0', 'construction_end_exclusive': 60.0,
            'private_custody_completed': True, 'truth_released': False,
            'producer_models_generated': 0, 'evidence_kind': 'PRE_SCIENTIFIC_CUSTODY_ADMISSION',
        }
        write_json(self.public / 'release.json', release)
        self.assumptions = json.loads(ASSUMPTIONS.read_text(encoding='utf-8'))

    def test_shared_case_uses_paid_orders_not_pickup_or_beverages(self):
        case = build_case(self.public, ASSUMPTIONS, environment={})
        self.assertEqual(case['input']['public_paid_order_count_before_cut'], 1)
        self.assertEqual(case['input']['rate_orders_per_hour'], 1.0)
        self.assertFalse(case['input']['payment_is_pickup'])
        self.assertEqual(case['observables']['primary'], 'orders_picked_up_cumulative')
        self.assertEqual(case['time']['horizon_hours'], 103.237 / 60)
        self.assertEqual(tuple(case['observables']['prediction_cuts_min']), PREDICTION_CUTS)
        self.assertNotIn('P10', json.dumps(case))
        self.assertNotIn('P80', json.dumps(case))
        self.assertNotIn('SECRET-FUTURE-TRUTH', json.dumps(case))
        self.assertNotIn('seed', json.dumps(case))
        self.assertNotIn('truth_events', json.dumps(case))
        self.assertFalse(case['restrictions']['physical_model_executed'])

    def test_rejects_synthetic_generator_assumptions_falsely_marked_public(self):
        h = copy.deepcopy(self.assumptions)
        h['parameters']['service_capacity']['origin'] = 'synthetic_scenario_truth'
        with self.assertRaisesRegex(ArenaError, 'ASSUMPTION_PROVENANCE_OR_UNIT_INVALID'):
            validate_assumptions(h)

    def test_rejects_units_swap_minute_vs_hour_and_unbounded_rate(self):
        h = copy.deepcopy(self.assumptions)
        h['parameters']['response_time']['unit'] = 'minutes'
        with self.assertRaisesRegex(ArenaError, 'ASSUMPTION_PROVENANCE_OR_UNIT_INVALID'):
            validate_assumptions(h)
        h = copy.deepcopy(self.assumptions)
        h['parameters']['service_capacity']['value'] = float('nan')
        with self.assertRaisesRegex(ArenaError, 'ASSUMPTION_NONFINITE'):
            validate_assumptions(h)

    def test_zero_initial_is_hypothesis_not_reconstructed_prior_work(self):
        h = copy.deepcopy(self.assumptions)
        h['parameters']['initial_paid_orders']['value'] = 2
        h['parameters']['initial_paid_orders']['admissible_range'] = [0, 2]
        with self.assertRaisesRegex(ArenaError, 'INITIAL_BACKLOG_MUST_BE_ZERO'):
            validate_assumptions(h)

    def test_bad_public_modified_after_release_is_rejected(self):
        p = self.public / 'producer-public-b0.json'
        v = json.loads(p.read_text())
        v['pos_records'][0]['timestamp_min_from_peak_start'] = '1.000'
        write_json(p, v)
        with self.assertRaisesRegex(ArenaError, 'PUBLIC_RELEASE_COMMITMENT_INVALID'):
            build_case(self.public, ASSUMPTIONS, environment={})

    def test_future_payment_is_rejected_even_with_recomputed_release_hash(self):
        p = self.public / 'producer-public-b0.json'
        v = json.loads(p.read_text())
        v['pos_records'][0]['timestamp_min_from_peak_start'] = '62.0'
        write_json(p, v)
        r = self.public / 'release.json'
        release = json.loads(r.read_text()); release['public_sha256'] = digest(v)
        write_json(r, release)
        with self.assertRaisesRegex(ArenaError, 'POS_OUTSIDE_CONSTRUCTION'):
            build_case(self.public, ASSUMPTIONS, environment={})

    def test_custody_creds_are_refused(self):
        with self.assertRaisesRegex(ArenaError, 'PRODUCER_HAS_PRIVATE_CREDENTIAL'):
            build_case(self.public, ASSUMPTIONS,
                       environment={'CT03_R2_ACCESS_KEY_ID': 'masked'})

    def test_fixture_rate_conversion_detects_sixty_fold_bug(self):
        # Fixture's one payment in one hour is 1 order/hour, never 1/60.
        case = build_case(self.public, ASSUMPTIONS, environment={})
        self.assertEqual(case['input']['rate_orders_per_hour'], 1.0)
        self.assertNotEqual(case['input']['rate_orders_per_hour'], 1/60)
        self.assertEqual(case['hypotheses']['parameters']['response_time']['value'] * 60, 6)
        self.assertEqual(case['representability']['M']['unchanged_catalog_response_time_min_hours'], 0.1)

    def test_project_native_cumulative_duplicate_times_last_row_wins(self):
        rows = [{'time': 0.0, 'deliveredTotal': 0},
                {'time': 80/60, 'deliveredTotal': 3},
                {'time': 80/60, 'deliveredTotal': 4},
                {'time': 100/60, 'deliveredTotal': 7},
                {'time': 103.237/60, 'deliveredTotal': 8}]
        projected = project_native_counter(rows, arm='M', native_counter='deliveredTotal',time_unit='hours')
        self.assertEqual(projected['duplicate_timestamp_rows'], 1)
        self.assertEqual(projected['predictions']['80.0']['orders_picked_up_cumulative'], 4)
        self.assertEqual(projected['predictions']['103.237']['orders_picked_up_cumulative'], 8)
        self.assertEqual(projected['status'], 'ENGINEERING_PROJECTION_ONLY_NOT_NATIVE_VALIDATED')

    def test_no_payment_as_pickup_or_information_flow_as_pickup(self):
        with self.assertRaisesRegex(ArenaError, 'NATIVE_COUNTER_NOT_ATTESTED'):
            project_native_counter([{'time': 0,'reportedDeliveryRate': 2}],arm='M',
                                   native_counter='reportedDeliveryRate',time_unit='hours')
        with self.assertRaisesRegex(ArenaError, 'NATIVE_COUNTER_NOT_ATTESTED'):
            project_native_counter([{'time': 0,'delivered': 2}],arm='B',
                                   native_counter='delivered',time_unit='hours')

    def test_projection_rejects_decreasing_values_and_incomplete_horizon(self):
        with self.assertRaisesRegex(ArenaError, 'TRACE_NOT_FINITE_MONOTONE'):
            project_native_counter([{'time': 0,'delivered': 5},
                                    {'time': 103.237,'delivered': 4}],arm='D',
                                   native_counter='delivered',time_unit='minutes')
        with self.assertRaisesRegex(ArenaError, 'NATIVE_TRACE_COVERAGE_INCOMPLETE'):
            project_native_counter([{'time': 0,'delivered': 0},
                                    {'time': 100,'delivered': 5}],arm='D',
                                   native_counter='delivered',time_unit='minutes')

    def test_real_package_only_if_available_uses_pos_construction_not_truth(self):
        real = Path('/mnt/data/piloto_cafeteria_documentacion_y_datos_completosACTUALIZADO.zip')
        if not real.exists():
            self.skipTest('17 MB synthetic ZIP not shipped in repository')
        sha = hashlib.sha256(real.read_bytes()).hexdigest()
        cfg = {'selection': {'scenario_id': 'demanda_bajo__dias6_7_bajo__paciencia_sensible',
                             'replication': 1, 'day_of_week': 1},
               'construction_end_min': 60, 'window_end_min': 103.237}
        zf, _ = _load_package(real, sha)
        with zf:
            public = _build_public(zf, cfg, sha)
        write_json(self.public/'producer-public-b0.json', public)
        release = json.loads((self.public/'release.json').read_text())
        release.update({'source_package_sha256': sha, 'public_sha256': digest(public)})
        write_json(self.public/'release.json', release)
        case = build_case(self.public, ASSUMPTIONS, environment={})
        self.assertEqual(case['input']['public_paid_order_count_before_cut'], 10)
        self.assertEqual(case['input']['rate_orders_per_hour'], 10.0)
        self.assertEqual(case['selection']['day_of_week'], 1)
        self.assertNotIn('orders_ready', case['input'])

    def test_cli_new_process(self):
        dest = self.root / 'case.json'
        # The fixture release declares run 123. CI exposes its own GitHub run ID;
        # run this subprocess as an isolated producer test, not as that live run.
        env = os.environ.copy()
        for key in ('GITHUB_RUN_ID', 'GITHUB_SHA', 'GH_TOKEN', 'GITHUB_TOKEN'):
            env.pop(key, None)
        process = subprocess.run(
            [sys.executable, '-m', 'arena.coffee_domain',
             '--public-dir', str(self.public),
             '--assumptions', str(ASSUMPTIONS), '--out', str(dest)],
            cwd=ROOT, capture_output=True, text=True, env=env,
        )
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(json.loads(dest.read_text())['schema'], 'arena.coffee-peak.public-case/1')
        again = subprocess.run(
            [sys.executable, '-m', 'arena.coffee_domain',
             '--public-dir', str(self.public),
             '--assumptions', str(ASSUMPTIONS), '--out', str(dest)],
            cwd=ROOT, capture_output=True, text=True, env=env,
        )
        self.assertEqual(again.returncode, 2)
        self.assertIn('REFUSE_CASE_OVERWRITE', again.stderr)


if __name__ == '__main__':
    unittest.main()
