# Q75 leche · PR51 · Primera generación auténtica de Buffalo (una sola llamada opcional)

**Pregunta:** con baristas/máquina existentes, ¿hay fundamento para probar prioridad de leche frente a FCFS supuesto? Misma Q75 del PR46, sin nueva prioridad, sin prometer P90 de D/M/B ni beneficio real. No modifica PR49 ni PR50: ambos quedan congelados para auditoría Astra por SHA.

## Lo que hace el código nuevo

`arena/coffee_q75_buffalo_initial.py` usa `q75.prepare` para verificar **ocho ZIP públicos originales** (hash SHA-256 fijado en PR48). Rechaza un expediente que omita W01, invente otra lanza o pierda la política de prioridad. Utiliza la entrada `B` de PR49 y la compuerta de PR50 para producir una **nueva petición inicial** del `Engine.generate` original, sin reutilizar `currentModel` de B0/R1. La petición contiene los recursos exactos: dos baristas, dos puestos, tres grupos, W01 única, PASS01 único, habilidades, calendarios y duraciones supuestas, precedencias, simultaneidad y bloqueo de recursos; política FCFS de primera tarea ejecutable y leche primera leche ejecutable con fallback real.

**No se envían** el delta Hydra de −3,837 segundos, P90 de referencia, resultados de otros brazos, secuencias privadas de pedidos, salidas de un holdout ni diagnósticos falsos. El motor original solo recibe información de construcción. Si el modelo continuo no representa política/recursos o tiempo individual, el resultado científico correcto puede ser `COVERAGE_LIMITED`, no "la intervención tiene efecto cero". Tampoco se convierte la salida del LLM en un veredicto de negocio.

`arena/coffee_q75_buffalo_initial_runner.mjs` invoca **el motor cuantitativo original** vendorizado mediante la ruta SDK conocida, interceptada una sola vez, hacia el adaptador Cloudflare EV01 ya existente con **máximo 16 000 tokens de completado, reasoning_effort low, streaming deshabilitado y timeout fijo**. Se verifica la salida del SDK y se registra la petición efectiva sin secretos, el inicio de llamada antes del POST, la respuesta cruda, uso si el proveedor lo informa y recibo de éxito/error. **No hay reintento automático**. El hecho de reservar o fallar una llamada no demuestra costo cero.

**Correcciones previas al primer POST (Astra, 19/11):** la petición contiene la mezcla pública de **33 de 53 bebidas con leche** y limpieza después de cada bebida **desactivada**, y verifica que la regla hipotética de limpieza usaría un barista y un grupo. Se cierra la brecha entre reserva e invocación vinculando el hash **SHA-256 de los bytes exactos de `request.json`** en `attempt.json`. Python recalcula además el digest canónico al invocar; Node comprueba los bytes antes del SDK. Una alteración post-reserva bloquea el transporte. CI incorpora un test sin proveedor que invoca el `Engine.generate` original hasta la petición SDK y la transforma con el adaptador Cloudflare original, abortando antes de la red.

**Perfil metodológico:** `supportsArrays=false`, `supportsModules=false`, `supportsSubTypes=false`, `mentorMode=false`, cap 16 000. Es el **perfil escalar histórico de Buffalo**, sin subtipos nativos de cola. Los recibos registran esta configuración; no equivale a comprobar todo lo que Buffalo puede representar con colas habilitadas.

**Autorización efectiva en GitHub:** `environment: arena-provider` solo delimita acceso a variables/secretos. Al corte auditado Astra comprobó `protection_rules: []`; por lo tanto **NO existe una segunda aprobación humana automática por entorno**. La única aprobación operativa del workflow es el despacho explícito desde `main`, en primera tentativa, con `authorized=yes`. Si se desea segunda revisión humana, deberá configurarse y constatarse antes de describirla como existente. Ningún POST autorizado por esta documentación.

## Activación y gasto

El workflow `.github/workflows/coffee-q75-buffalo-initial-manual.yml` corre pruebas offline en PR. El job proveedor **solo** existe para `workflow_dispatch` en `main`, primer intento, entrada explícita `authorized=yes` y entorno `arena-provider`; ninguna ejecución desde este PR puede disparar consumo. Antes del POST verifica que no exista otro despacho anterior con intento potencial no conciliado, instala el SDK original, autentica la entrada y reserva la llamada. No usa R2 privado ni OpenModelica. Publica el artefacto aun si el proveedor falla, respetando seguridad y contabilidad.

**Presupuesto técnico incremental propuesto (NO AUTORIZADO):** exactamente **0–1 POST** inicial a Cloudflare Workers AI con salida acotada a 16 000 tokens; **0** llamadas de revisión, **0** OMC y **0** GET privado R2 en este lote. El costo monetario no puede fijarse con los artefactos disponibles: depende de la tarifa vigente, tokens de entrada/salida y facturación real. El presupuesto **no** incluye la segunda llamada de `currentModel` ni simulaciones para medir P90, que exigirían decisión y autorización separadas después del diagnóstico G1.

## Gate científico después del POST

Se archiva el modelo nativo original y se ejecuta diagnóstico semántico G1 sin reparación local. El traductor Modelica se usa solo como prueba de translatabilidad sin ejecutar simulaciones. No se publica valor de P90 si el modelo no representa la elección, recursos y pedido individual. El diagnóstico para Buffalo se debe registrar y recuperar a través de su propio carril Ledger/ATMS **antes de cualquier revisión**; el POST inicial no sustituye ese paso.

## Criterio de aceptación del PR

1. El código crea un `request.json` nuevo y auténtico para Q75, con `parent_model=null`, status `NOT_SENT`, digest reproducible, recursos W01 y dos reglas de elección; ningún resultado Hydra/R2 se filtra.
2. Pruebas negativas: W01→W01+W02, intento PR/push/rerun, fuente corrupta, padre falso, petición ya reservada; dry-run sin credenciales ni costos.
3. El CI de PR no incluye un solo POST, OMC ni GET R2; el job pagado no existe para eventos `pull_request`.
4. Revisión de Astra de PR49 y PR50 ocurre **por separado**; el PR51 no se fusiona ni despacha hasta el dictamen conjunto y aprobación explícita del techo de 1 POST.

**Regla de parada:** una generación G1 auténtica que declare cobertura insuficiente es un resultado útil, pero no concluye automáticamente el valor decisional incremental de los tres métodos. Una revisión requiere `currentModel` compatible con el padre auténtico, feedback propio y un segundo presupuesto.

## Incidente real Q75 y corrección del modelo (20/11/2026)

**Registro posterior a PR51:** En [Actions #44672512041](https://github.com/yudocyudoc/igc-modular/actions/runs/44672512041) hubo **exactamente un POST** a `@cf/zai-org/glm-5.3-flash`, con HTTP `410`, Cloudflare `5028` (`Model has been deprecated`). El recibo [artefacto 14601007266](https://github.com/yudocyudoc/igc-modular/actions/runs/44672512041/artifacts/14601007266) muestra `provider_posts=1`, `model_returned=false`, `provider_usage=null`, sin OMC ni R2 privados. **No se obtuvo modelo ni P90. El consumo monetario queda sin determinar.** Ese intento está gastado a efectos de la autorización previa.

Cloudflare anunció el 5/11/2026 que el modelo sería desactivado el 20/11/2026 y recomienda `@cf/zai-org/glm-5.3`: https://developers.cloudflare.com/changelog/post/2026-11-05-planned-model-deprecations/ . Se actualiza **únicamente el destino Cloudflare de Q75** a ese modelo, manteniendo intacto el alias virtual original de OpenRouter y el adaptador histórico EV01. El prompt y las restricciones Q75 siguen siendo los mismos; la identidad de solicitud cambia porque `request.json.model` cambia. En preflight, se exige que el catálogo devuelva el nombre exacto del nuevo modelo, en vez de comprobar la disponibilidad genérica de Workers AI. Una salida del catálogo con solo el modelo retirado debe fallar **antes** de reservar.

**No habilita otra llamada**: la compuerta de antecedentes continúa rechazando cualquier nuevo despacho después de #44672512041, que sí pudo consumir un POST. Para autorizar un segundo intento se requiere aprobar explícitamente otro presupuesto y conciliar su coste posible. Ningún cambio de código se interpreta como permiso para reintentar.
