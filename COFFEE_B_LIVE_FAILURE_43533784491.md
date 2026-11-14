# Corrección del primer despacho Buffalo Live — 0 POST

## Observación verificada (GitHub run 43533784491)

- Admisión pública, preflight Cloudflare y `npm ci` terminaron bien.
- `CLOUDFLARE_API_TOKEN` estaba presente y enmascarado; `CLOUDFLARE_ACCOUNT_ID` llegó **vacío** en el paso de generación.
- El preflight ya recuperaba el ID público de `arena/resources/connections.json`, mientras que `coffee_live.generate()` exigía únicamente la variable de entorno. Por eso falló en `COFFEE_B_LIVE_PROVIDER_CREDENTIALS_REQUIRED` **antes** de reservar el intento.
- Se descargó el artifact `coffee-b-live-43533784491` (ID `14088099211`), y se comprobó SHA-256 del ZIP: `c15251e8a129a93dced1997f9aa29a29e5c6554450e1d24042de34655f643789`; contenidos exclusivos: `admission.json`, `final.json`, `input.json`. Ningún `attempt.json`, `provider/`, `node.log` o `process.json`.
- Su `final.json` afirma `NO_PROVIDER_ATTEMPT`, `attempt_reserved=false`, `provider_posts_observed=0` y `provider_may_have_consumed=false`, confirmado por la secuencia de pasos de GitHub.

## Reparación

1. El generador hereda el mismo fallback de ID de cuenta que el preflight, desde la configuración **pública y fijada**. Si existe una variable contradictoria, falla antes de reservar consumo. El token sigue llegando del entorno `arena-provider`; nunca se escribe ni registra.
2. Historial sigue siendo fail-closed. **Una única excepción auditada** para el run `43533784491` requiere que coincidan SHA de ejecución, job, estados de pasos, metadata GitHub, artifact ID y digest ZIP, contenidos exclusivos y recibo exacto de cero intentos. La descarga del ZIP se realiza con acceso read-only mediante la conexión GitHub del job de admisión. Ninguna ejecución fallida genérica recibe permiso de repetición.
3. Pruebas negativas de cuenta vacía, cuenta distinta, archivo alterado, nuevo `attempt.json`, recibo con consumo y estado del paso alterado.

## Instrucción operativa

No usar GitHub **Re-run jobs** sobre el run original. Tras revisión y merge, hacer **un despacho nuevo** en `main`, con el mismo source_run_id `43532737911` y artifact_id `14088545399`. No habrá POST automático desde este PR. Si cualquier check nuevo falla, no despachar.

La reparación no modifica la custodia privada, el lock READINESS_ONLY, CT03, motores originales ni los datos sintéticos. No se ha realizado ninguna llamada al proveedor.