# Private Merlin task from Arena

This adapter uses Buffalo's private `ArenaMerlin` service binding and a local Wrangler client. The Arena CLI submits an already authorized task or reads it later with the same project, phase and UUID. The initial case uses the versioned dialysisClinic SD-JSON exported by `infra/buffalo-origin/generate-probe-model.mjs` in buffalo-01.

After the Buffalo endpoints and the relevant stage grant have been provisioned by the operator, start the local binding proxy with an authenticated Wrangler installation.

```sh
wrangler dev --config infra/private-merlin/wrangler.jsonc --ip 127.0.0.1 --port 8791
```

Use the UUID from the current Buffalo grant. Replace the model filename with the exact exported file.

```sh
python -m arena private-merlin submit --phase R --task-id "$TASK_ID" --model probe-initial-model.json
python -m arena private-merlin read --phase R --task-id "$TASK_ID"
```

Each CLI invocation opens a new connection. The proxy can also be restarted before reading. After the private R receipt, I accepts a distinct UUID from its own inference grant. A successful I receipt includes native completion, the answer and provider token usage. Output is model-generated HTML and should be displayed as text or sanitized by a renderer. If submission is interrupted, read the existing task ID. The service remains the authority for state and consumption.
