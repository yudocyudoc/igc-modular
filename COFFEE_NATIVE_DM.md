# Coffee B0 native preparation — original D and M (engineering only)

This PR implements **PR B** of `PLAN_ADAPTADORES_NATIVOS_CAFETERIA_V1.md`.
It depends on #10 (#7 → #8 → #9 → #10); it does not modify `_vendor`, CT-03,
Buffalo or any original grammar, library or producer semantics.

## Public input and invocation

For an authorized **public-only** folder containing `producer-public-b0.json`
and `release.json`, run without custody or provider secrets:

```bash
python -m arena.coffee_native_dm \
  --public-dir /path/to/producer-public \
  --assumptions examples/coffee_public_assumptions_v1.json \
  --out runs/coffee-native-dm-preparation
```

The command **only** reads the previously released construction view. It does
not consume ZIP, future POS, R2, truth, provider or solver. It reconstructs the
public case with the P0–P3 read boundary, verifies original vendored identities,
then invokes the original D/M generators. Running the command does **not**
create a scientific lock or change `NO_NATIVE` in the existing P3 workflow.
The workflow has deliberately not been changed to include this step until
Astra validates the new artifacts and provenance.

- **D**: original `scripts.arena_d_v01.topology`, `lint_structure`, and
  `modelica`; six structures in the original order, one to three stocks with
  and without loss. The original `generate()` contract demands at least two
  observed *deliveries*; construction has none, so the adapter calls the
  primitives directly rather than supplying fake readings. `capacity=12
  orders/hour`, `responseTime=0.1 hour`, and `lossTime=20 hours` are public,
  unfitted nominal values; loss time comes from the declared positive hazard
  `0.05/hour`. The no-loss alternatives remain zero-loss. Initial states are
  zero **by hypothesis**, not because the real café was empty.
- **M**: original Short E1 `composer.load_registry`, `enumerate_graphs`,
  `check_graph` and `backend.render_model`; original
  `scripts.arena_m_visible_pulse.stimulus_only_replace` changes **only** the
  external E1 stimulus. Uses the externally versioned registry
  `arena/coffee_adapters/registry.coffee.v1.json`, pointing at the unchanged E0
  molecular catalog. Its preparation and dispatch bounded queues use 12
  orders/hour and **0.1 hour (six minutes)**; transit/reporting retains
  original 100 orders/hour, 1.6 hour priors. The six complete ASTs and three
  topology-only material projections remain separate; topology grouping is
  **not evidence** of identical numerical trajectories.

Both use the exact same accepted *paid-order* rectangular source:
`input_rate = paid POS orders before 60 min / 1 hour`, extended by an
unverified future assumption through `103.237/60` hours. Public payments
are **not** pickups; `delivered` (D) and `deliveredTotal` (M) are only the
native counters **proposed** for cumulative order pickup.
`reportedDeliveryRate` (M) is informational, not physical delivery.

The output contains D Modelica files, M native.mo, each candidate's full
graph/AST, declared parameter sources, registry snapshot, byte SHA-256,
material grouping and generated-but-not-run validation script. No CSV from
an OMC run exists. Manifest `model_validation` is
`GENERATED_NOT_COMPILED_OR_SIMULATED`, with 0 new OMC and 0 provider calls.

## Method limits and stop rules

D does not model shared barista/espresso resources, station occupancy,
recipes, prepayment abandonment, queues with separate roles or a causal
link to hiring a worker/machine. Its post-payment loss is a structural
option, not a refund or observed abandonment. M uses original bounded
queues; it does **not** include abandonment or shared resources.
**Neither** adapter establishes individual waiting-time p90, profitability,
S1–S5 policy efficacy or empirical calibration of pickups.

An assumption outside the pinned coffee M registry fails (no silent
extension of response-time bounds). A source drift or changed stimulus
interface fails closed. Modelica equations are emitted only by the pinned
original sources. Both arm outputs are **preparations**, not native *simulations*
or sealed scientific predictions. Provider B is the next PR and remains
untouched. Neither a fixture nor a passing CI test counts as measured café
performance.

## Regression commands

```bash
python -m unittest discover -s tests -v
python -m arena run examples/smoke.toml --out runs/ci-smoke
```

`tests/test_coffee_native_dm.py` uses the original vendored sources in a full
checkout. In a reduced local copy it deliberately skips those source-dependent
tests instead of pretending a mock is a native model. The initial public-only
fixture tests can run without solver/provider/R2. Do not invoke the staging or
`admit` live workflow to test these adapters: a reservation is one-shot.
