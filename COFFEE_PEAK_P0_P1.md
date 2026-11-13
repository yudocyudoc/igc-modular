## Coffee peak pilot: P0–P1 (offline only)

The `coffee_peak_capacity_v1` protocol is a **distinct admission fixture**, not a
variation of the closed CT-03 experiment. D, B and M keep their original
methods and are **not executed** in this increment. The baseline operating
condition is **B0** (not the Buffalo arm B).

Put the source ZIP in `inputs/` (untracked), retaining its original name:
`piloto_cafeteria_documentacion_y_datos_completosACTUALIZADO.zip`.
Its pinned SHA-256 is declared in `examples/coffee_peak.toml`.

```shell
python -m arena check examples/coffee_peak.toml
python -m arena run examples/coffee_peak.toml --out runs/coffee-peak-p0
python -m arena report runs/coffee-peak-p0
```

The importer checks every listed ZIP member against `MANIFIESTO_PAQUETE.json`,
requires all four original source/configuration files and their hashes, and
requires exactly the 19 declared v1 synthetic outputs in the inner manifest.
Successful hashes alone do not prove this completeness. The example fixes
**one** B0 scenario (`demanda_bajo__dias6_7_bajo__paciencia_sensible`),
replication **1**, day **1**, the 103.237-minute nominal window, and the
construction cutoff **[0,60) min**. `resumen_escenarios.csv` identifies the
scenario/replication; `day_of_week` is selected from POS records.

The only exported construction data are `inputs/producer-public-b0.json`:
POS payments/refunds and their line items before minute 60 and pre-cutoff
video-presence proxy (not arrival counts). The future POS, all `*_truth` CSV/JSON,
scenario summary totals and generator parameters are **not exported**.
The POS, order and line-item identifiers released in the producer view are
new, random opaque tokens, unrelated to source party/arrival ordinals. The
importer preserves their parent/child joins for this one view, but **does not
persist the private source-ID mapping**. A future evaluator must create and
seal a separate mapping before running producers; this P0 fixture must never
be described as longitudinally linkable to private truth. All construction
cutoffs must be on whole-minute boundaries because each visual proxy row
summarizes a complete `[minute, minute+1)` bin (sample count is not elapsed
duration). Line items are checked for unique IDs, same order and time as a
parent sale, valid synthetic provenance and nonnegative pre-cutoff times.

No scores, service-time claims, profit, counterfactuals or engine results are
produced. A sale is a payment, not a delivery; a refund is a financial event.

**Security limit:** the import process necessarily reads the original archive
for hash validation. P0–P1 does not create an isolated producer job, R2 custody,
or a lock; it does not claim technical blinding. Do not make the whole ZIP
available to future D/B/M producer jobs. Build separate jobs/mounts and custody
before any real experiment. There is no live backend for this protocol, and
all OMC/provider/workflow budgets must be zero. CT-03 code, quotas, and its
existing workflows remain unchanged.
