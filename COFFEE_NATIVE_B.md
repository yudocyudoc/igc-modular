# PR C — Buffalo coffee B0 original Engine.generate, offline only

This independent, versioned adapter builds **the same paid-order public
case** as coffee D and M. It does not open the source ZIP or R2, and does
not inherit CT-03's 8-hour horizon. The real Buffalo \`Engine.generate\`
is invoked in \`arena/buffalo/coffee_runner.mjs\` using the pinned original
SDK; the SDK's OpenRouter request is intercepted locally and answered from
an explicitly labeled **Cloudflare-shaped offline fixture**.

This PR has **no live mode**. Exporting provider or R2 credentials to the
offline runner is rejected. No network function is ever delegated to the
original fetch; at most one SDK request is intercepted. The exact SDK JSON
schema request, translated Cloudflare request (without secrets), local
provider fixture, original Engine output, and attempt receipt are preserved.
The receipt records zero real POSTs, zero OMC, and zero scientific lock.

Run public-only preparation:

\`\`\`sh
python -m arena.coffee_native_b --public-dir /path/to/producer-public \
 --assumptions examples/coffee_public_assumptions_v1.json \
 --out /tmp/coffee-b-input.json
\`\`\`

Offline integration requires the pinned native-engine workspace with npm
dependencies and runs under the existing native-engine CI:

\`\`\`sh
node tests/coffee_buffalo_node_contract.mjs "$RUNNER_TEMP/arena-native"
\`\`\`

**Limitations**: The current vendored Modelica translator requires exactly
8 hours and cannot legitimately compile a 103.237-minute coffee horizon.
A changed horizon is *not* rewritten to eight hours; the native model and
reason for stopping remain in the receipt. A **versioned, derived** coffee-scope Modelica translator is included
(`arena/coffee_adapters/b_translation.py`). Its original vendored source remains
untouched; only the version, pinned simulation-scope guard and solver-scope
receipt differ. The extension requires horizon `103.237/60` hours, Euler,
`dt=horizon/64` and accepts only equations/functions supported by the original.
A fixture can now be explicitly translated with `translate_offline_fixture()`,
which archives a Modelica file and byte-hash receipt while retaining the label
`TRANSLATED_FIXTURE_NOT_COMPILED_NOT_SCIENTIFIC`. This is **not** physical
inference or an attested native from a paid provider; equation parity and model
compilation still require separate validation.
A passing local mock does NOT prove the provider will produce a valid native,
that Buffalo can express a true pickup counter, or that it can handle
machine/barista staffing, prepayment abandonments or S1–S5.

No paid provider, DES, R2 or OMC experiment is authorized here. The workflow
remains \`READINESS_ONLY\`; no fixture may be promoted to a scientific lock.
