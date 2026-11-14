# Cafetería B0 · Buffalo R1 — revisión auténtica con `currentModel`

## Fuente y límites de la revisión

La revisión usa **exclusivamente** el original Buffalo B-LIVE-01 y el
diagnóstico propio almacenado por Ledger/ATMS. No utiliza salidas, parámetros
ajustados, modelos, ni resultados evaluados de D/M; tampoco utiliza verdad
sintética reservada, R2 ni observaciones posteriores al corte.

- Buffalo original: run [43537333254](https://github.com/yudocyudoc/igc-modular/actions/runs/43537333254),
  artifact `14090920829`, hash ZIP
  `70f9e9f846a33cd470b00dbaf0bf189b0b6c7a029b68bd84485f7c6bbe748265`.
- Feedback B reproducible: run
  [43561168032](https://github.com/yudocyudoc/igc-modular/actions/runs/43561168032),
  artifact `14100770369`, SHA ZIP
  `51b56dc28e5c229a280adf3f38062744992a61dc21dff48973e18f48105d10d8`.
- Caso B0: `sha256:756d16d2824a9052f5494dd41c3eef1f0e8826537deffbfc7cd39b0ca2d2457f`.
- Padre nativo original: `sha256:5c7fc9c73a5f03849d5d2cb1a3cb8352ac9c6d0117621b5e49fc6991694a8d40` (bytes del JSON).
- Diagnóstico B: `sha256:86e80cea5a9ee919681ac041ed3b8a6658c657b46b89efd03e4bccdc02c45ec8`.
- `as_known_at` del padre B: `2026-11-14T05:22:00.385365+00:00` (orden lógico).

El adaptador valida run, SHA, nombre y hash del artifact en GitHub,
reproduce `projection_hash` usando la SQLite final y el ATMS original,
contrasta `currentModel` **byte por byte al interpretar el JSON** con el
nativo B-LIVE-01, comprueba diagnóstico, parent hash y contexto original.

## Una sola llamada pagada al método original

El ejecutor Node invoca:

```js
new Engine().generate(reviewPrompt, originalCurrentModel, {
  underlyingModel: OR_SLUG,
  supportsArrays: false,
  supportsModules: false,
  supportsSubTypes: false,
  mentorMode: false,
  problemStatement: originalPublicProblem,
  backgroundKnowledge: originalPublicBackground,
  maxTokens: 16000,
  timeoutMinutes: 7
})
```

Se intercepta la petición **real** del SDK y se comprueba
que contiene exactamente **un mensaje `assistant` idéntico a
`JSON.stringify(currentModel,null,2)`**.
Esto prueba que Buffalo recibió el padre como parte de su mecanismo
original de revisión; no se sustituye por una simulación de un prompt.

El diagnóstico propio se añade como contexto de reconsideración junto al
prompt público original. Se pide revisar puertos stock-flow, tipo de flujo de
entrada, relaciones causales y discrepancia de `dt`. No se impone una
estructura final ni una ecuación corregida; el motor puede seguir rechazado
en G1 y **no se le obliga a aprobarse**.

El máximo es **1 POST** a Cloudflare Workers AI, a través del adaptador
ya fijado, sin retries automáticos ni segundo SDK fetch. Se guarda recibo
ANTES de HTTP, petición SDK, petición efectiva, respuesta cruda,
nativo original revisado, diagnóstico G1 y `final.json` con gasto observado
o incierto. Timeout/HTTP fallido no autoriza automáticamente nuevo POST.

## Reglas para ejecutar

No se ejecuta en push ni PR. El workflow
`.github/workflows/coffee-buffalo-review.yml` solo permite
`workflow_dispatch` manual sobre `main` con `authorized=yes`,
acceso al environment ya configurado `arena-provider` y
`github.run_attempt=1`.

```bash
gh workflow run coffee-buffalo-review.yml \
  --repo yudocyudoc/igc-modular \
  --ref main -f authorized=yes
```

**No** usar `Re-run jobs` ante fallos ni crear un segundo dispatch. La
admisión inspecciona el historial y bloquea una segunda revisión. Solo tras
el merge, CI verde y validación de contratos debería autorizarse el POST.
La autorización concede una llamada al proveedor con coste potencial.

## Qué contaría como éxito

Una ejecución exitosa debe evidenciar:

1. El SDK incluyó el **padre exacto** en la petición de revisión.
2. Cloudflare devolvió 200 y respuesta cruda archivada.
3. `Engine.generate` original devolvió un nativo de horizonte B0.
4. G1 diagnóstico del nativo revisado, con su resultado **admisible o bloqueado**.

Esto **no** acredita simulación G2, ajuste a entregas observadas,
capacidad real de la cafetería, criterio económico, G3, lock científico ni
mejora cuantitativa de las predicciones. Una revisión fallida o bloqueada es
también un resultado científico legítimo. La ronda previa B-LIVE-01 permanece
inmutable.

## Próxima fase

Solo si el modelo revisado es admisible para la traducción Modelica de
cafetería se propone un presupuesto OMC separado y se comprueba G2, antes
de cerrar el lock G3. No se comparará con la verdad reservada antes de ese lock.
