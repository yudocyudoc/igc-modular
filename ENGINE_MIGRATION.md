# Migración nativa de D/M/B y conexión de ejecución

Solicitud expresa del usuario: migrar y conectar los motores en GitHub, sin clonar los motores completos en su entorno local. Esta implementación es una excepción puntual al reparto habitual: después de esta entrega gpt-web continúa como coder y Codex/Astra como revisor.

## Qué se trasladó

- D: generador, Modelica, comprobación de CSV, enlace a observaciones, feedback propio y proyección de sus seis plazas.
- M: compositor y backend Short E1, registro/catálogo, moléculas materiales y de información, política M2, revisión original y validación física de las seis plazas.
- B: Engine.generate y QuantitativeEngineBrain originales de UB-IAD/sd-ai, cierre de imports de sus utilidades y package-lock.json original. Se conserva LICENSE MIT. El renderer/prompts/método no se reescribieron.
- Adaptadores Buffalo: ruta OpenRouter SDK → Cloudflare Workers AI, límites originales, G1, traducción provisional, OMC, feedback, segunda ronda con su propio currentModel y estados negativos.
- Evidencia de los dos OMC ya ejecutados en CT-02, suficiente para verificar/reutilizar D0/M0 sin repetirlos.

Las fuentes fijadas son IGC 881f92792e4a67de0eb33a04662089029c0e6918 y Buffalo 5199f7b45f3a7ae4a773cb0dd8542940aabe9edc. ENGINES_MANIFEST.json comprueba 103 archivos de ejecución/evidencia por sus blobs Git; el manifiesto original de 39 archivos se conserva.

Los motores, lockfiles y evidencia se transfirieron con las APIs de GitHub. La exportación histórica se hizo en una rama aislada migration/export-ct02-native-evidence de IGC, sin cambiar su main: run 42442804546, commit 74a37a9cc3f0d1d9eaad17328ba6f68508cff32e. Se seleccionaron las fuentes/CSV/logs/manifiestos necesarios; no se trasladaron ejecutables ni objetos compilados. El origen es procedencia, no una dependencia de ejecución.

## Ejecución independiente

El workflow arena-run.yml no descarga código ni artifacts de IGC ni de sd-ai. Las copias originales están en arena/_vendor. Solo se instalan dependencias npm según el lock original y bibliotecas estándar fijadas, además de la imagen OMC por digest.

Los workspaces se materializan únicamente dentro del runner de GitHub. Se reubica el guard de rama de cinco adaptadores operativos al main de este repositorio, dejando registro en runtime.json; no se cambian ecuaciones, prompts, heurísticas, solver ni parámetros.

Buffalo no recibe los resultados históricos D0/M0: su checkout excluye arena/_vendor/ct02, su workspace no los copia y solo descarga observaciones comunes y el recibo numérico de consumo D/M. Los productores no exportan credenciales R2.

## Un solo recorrido

1. Congelar el SHA real y admitir modo/presupuesto.
2. En paralelo, comprobar acceso Workers AI sin inferencia y acceso R2 sin seleccionar un mundo.
3. Reservar una única selección de mundo en R2 mediante PutObject con If-None-Match: *; ejecutar un OMC y publicar únicamente los cuatro cortes comunes.
4. Reutilizar D0/M0 verificados; ejecutar diez iniciales nuevos y las revisiones M seleccionadas por su método original.
5. Ejecutar Buffalo y, si procede, su revisión propia; máximo dos POST.
6. Juntar las trece plazas y archivar el lock como artifact inmutable.
7. Verificar identidad del artifact, SHA, observaciones y cierre de los jobs originales antes de construir el cliente que lee la reserva.
8. Evaluar t6/t8 sin solver/proveedor adicional y publicar score, consumo e informe.

Máximo: 19 OMC nuevos incluido el mundo, 2 POST Buffalo y un despacho de workflow. Un fallo del proveedor o solver no provoca reintentos. La reevaluación de software puede usar el mismo lock inmutable y los productores de su primer intento; no regenera modelos ni reabre sus predicciones.

La custodia es por datos, jobs y credenciales, con un mismo operador posible. No es una certificación de independencia frente al administrador.

## Conexiones iniciales: tres valores secretos, dos entornos reutilizables

El identificador público de cuenta y el bucket privado existente se encuentran en arena/resources/connections.json; se pueden sobrescribir mediante variables del repositorio. El bucket ya existente tiene r2.dev desactivado y ningún dominio público asociado, comprobados durante la migración. No se creó otro servicio de custodia.

- Entorno arena-provider: CLOUDFLARE_API_TOKEN, dedicado a Workers AI Edit, sin lectura/escritura R2.
- Entorno arena-custodian: CT03_R2_ACCESS_KEY_ID y CT03_R2_SECRET_ACCESS_KEY, de la conexión S3 limitada al bucket privado.

Se reutilizan para todas las etapas pertinentes; no se vuelven a configurar por experimento. La bóveda de Windows queda como opción local y no se exige al runner.

La conexión disponible para editar código no expone escritura de Actions secrets. Esta migración no fingió copiarlos desde IGC: GitHub no devuelve sus valores. El script de enlace opcional conserva secretos existentes y publica solo entradas faltantes cuando lo ejecuta un operador con acceso, o se pueden cargar una vez en Settings → Environments. No se deben enviar por chat.

## Validación y límites

- CI sobre motores migrados: fuentes intactas, regresiones originales, reutilización de los dos CT-02 y Buffalo original inicial/revisión con transporte mock y memoria real.
- CI de plataforma: integración completa, controles de cuota y despacho, aislamiento de credenciales y apertura posterior al lock.
- Linter de workflows: actionlint fijado.
- El push usa únicamente integración con fixtures; no autoriza gasto físico.
- No se ha ejecutado una nueva simulación, POST Buffalo ni selección real de mundo durante la migración. Las pruebas no demuestran eficacia científica ni validación externa.

Las credenciales iniciales y una autorización explícita mode=live/authorized=yes son necesarias para consumir el lote. Su código ya está conectado; no hace falta otro coordinador, intermediario de firmas o archivista externo.

Referencias: [S3 conditional PutObject](https://developers.cloudflare.com/r2/api/s3/extensions/), [R2 consistency](https://developers.cloudflare.com/r2/reference/consistency/), [GitHub artifact download](https://github.com/actions/download-artifact), [Buffalo upstream](https://github.com/UB-IAD/sd-ai/tree/5199f7b45f3a7ae4a773cb0dd8542940aabe9edc).

## Incorporación del trabajo del coder

Se conserva la corrección de despacho del PR #1: `return_run_details: true` solicita a GitHub el identificador confirmado de la ejecución. Se incorporan sus dos regresiones al recorrido nativo. El workflow del puente al repositorio IGC queda sustituido por `arena-run.yml`; no se requiere `IGC_ACTIONS_TOKEN`.
