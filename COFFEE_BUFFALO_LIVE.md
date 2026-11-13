# Buffalo cafetería: habilitación live de un único POST

Este incremento agrega una entrada operativa para invocar la IA real de Cloudflare
Workers AI mediante el **Engine.generate original de Buffalo**, conservando
el adaptador histórico EV-01, sin editar `_vendor` ni el experimento CT-03.

La habilitación de código **no autoriza un gasto automático** ni dispara el
workflow. El único camino de pago es un `workflow_dispatch` manual sobre
`main`, intento 1, `authorized=yes`, después de integrar los PR dependientes.

## Conexión y límites

- Reutiliza el environment `arena-provider`, sus secretos y
  `CLOUDFLARE_ACCOUNT_ID` existentes.
- Utiliza `@cf/zai-org/glm-5.3-flash` a través de la petición JSON-schema
  original del SDK OpenRouter, interceptada por
  `scripts/arena_b_ev01_cf_adapter.mjs` y enviada por REST a Workers AI.
- Presupuesto por despacho: **máximo 1 POST**, **16 000 tokens máximos de
  salida**, **0 OMC**, **0 DES**, **0 R2** y **0 reintentos automáticos**.
- El token se emplea solamente en el preflight GET y en el paso que puede
  consumir. Los secretos del custodio no entran al job.

## Precondiciones antes de usarlo

1. Integrar en orden la cadena de PR #7 a #13; el workflow de pago está
   bloqueado en ramas que no sean `main`.
2. Ejecutar una admisión autorizada del custodio de cafetería, con el ZIP ya
   almacenado de manera privada en R2. Esa admisión debe producir y publicar
   exactamente el artefacto público `coffee-public-<run_id>`. Nunca publicar
   el ZIP ni la tabla privada de vinculación.
3. Seleccionar Actions → **Coffee Buffalo - one authorized live Workers AI POST**
   e introducir `public_run_id` (run del custodio) y `public_artifact_id`
   (ID exacto del artefacto público), más `authorized=yes`.
4. El preflight comprueba la identidad de run, workflow y artifact, la versión,
   escenario, réplica, día, hashes y corte público, ausencia de acceso reservado
   y la historia de intentos previos. También comprueba permiso Workers AI y
   denegación de listado de buckets R2, antes de gastar.
5. El intento se escribe **antes** de llamar a `Engine.generate`; si se
   pierde la respuesta, hay error HTTP o timeout, se trata como consumo
   potencial y **no se reintenta automáticamente**.

El artifact `coffee-b-live-<run_id>` incluye solicitud real, transformación
Cloudflare, respuesta original, nativo y sus hashes por bytes, recibos,
estado y consumo observado o incierto. Si faltan recibos tras un intento,
el consumo queda como **desconocido**, no cero.

## Qué NO acredita

Obtener el nativo Buffalo vía HTTP real **no prueba** que haya identificado
una dinámica de cafetería válida; faltan auditoría semántica, conservación
material, compilación Modelica, simulación, feedback propio Ledger/ATMS,
predicciones selladas D/B/M y evaluación de verdad reservada.

El job no abre R2 ni crea lock científico. Conserva las restricciones de
`READINESS_ONLY` del workflow de cafetería existente.

Verificación: `python -m unittest discover -s tests -v`,
`python -m arena run examples/smoke.toml --out runs/ci-smoke` y
`node --check arena/buffalo/coffee_live_runner.mjs`. Las pruebas son
offline: no invocan el proveedor real.
