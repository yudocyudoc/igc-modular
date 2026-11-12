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
and checks output/source lineage against the inner manifest. The example fixes
**one** B0 scenario (`demanda_bajo__dias6_7_bajo__paciencia_sensible`),
replication **1**, day **1**, the 103.237-minute nominal window, and the
construction cutoff **[0,60) min**. `resumen_escenarios.csv` identifies the
scenario/replication; `day_of_week` is selected from POS records.

The only exported construction data are `inputs/producer-public-b0.json`:
POS payments/refunds and their line items before minute 60 and pre-cutoff
video-presence proxy (not arrival counts). The future POS, all `*_truth` CSV/JSON,
scenario summary totals and generator parameters are **not exported**.
No scores, service-time claims, profit, counterfactuals or engine results are
produced. A sale is a payment, not a delivery; a refund is a financial event.

**Security limit:** the import process necessarily reads the original archive
for hash validation. P0–P1 does not create an isolated producer job, R2 custody,
or a lock; it does not claim technical blinding. Do not make the whole ZIP
available to future D/B/M producer jobs. Build separate jobs/mounts and custody
before any real experiment. There is no live backend for this protocol, and
all OMC/provider/workflow budgets must be zero. CT-03 code, quotas, and its
existing workflows remain unchanged.
