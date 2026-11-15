# Arena Cafetería — ATMS gobierna la ejecución (PR #32 sobre #31)

**Objetivo:** cerrar la brecha detectada tras el PR #31: ATMS ya explicaba qué sostenía S5, pero un cambio de soporte no impedía que Arena ejecutara la comparación P11. Esta entrega transforma el estado ATMS en una decisión operacional verificable, sin pretender que ATMS prueba causalidad o ROI.

**Orden de PRs:** PR #30 ya fue fusionado por otro motivo (recuperación de Buffalo G2); el #31 ATMS decisional permanece abierto; el **PR #32 es draft apilado sobre #31**, por lo que no debe fusionarse sin revisar antes el #31.

## Contrato operativo

El módulo `arena/decision_atms_gate.py` recibe exclusivamente el dossier P07, protocolo P11 y predecisión ATMS derivada de ambos. No acepta una proyección arbitraria aunque sus hashes sean autoconsistentes: regenera el journal esperado a partir de los contratos fuente y verifica igualdad estructural.

La regla es explícita y no negociable:

| Soporte ATMS para `S5_CONDITIONAL_SIMULATABLE` | Acción real de Arena |
|---|---|
| Presente con entornos consistentes | `RUN_P11_CONDITIONAL_REFERENCE` (sólo bajo supuestos declarados) |
| Ausente por retractación de premisa, justificación o nogood | `DO_NOT_RUN_P11_MEASURE_OR_REVISIT_PREMISES` |
| Restaurado en la proyección | Vuelve a ser admisible bajo **las mismas restricciones condicionales** |
| `S5_REAL_FEASIBLE` o `S5_REAL_ECONOMIC_BENEFIT` | No se promueven a verdad, admisión empresarial o beneficio real |

**Punto preciso de consumo:** `arena/coffee_e2e.py::run_decision` llama a la compuerta después de crear la predecisión y **antes** de `decision.compare`. Si la compuerta devuelve abstención, escribe `atms-predecision.json` y `atms-execution-gate.json` con cero simulaciones autorizadas, y falla cerrado con `COFFEE_ATMS_ABSTAIN_MEASURE_FIRST_NO_P11_SIMULATION`. No invoca la comparación ni la exportación P11. Esto no convierte una abstención en un éxito artificial del workflow completo.

Con soporte suficiente, el resultado P11 incorpora `atms_execution_gate_sha256`, y ambos recibos ATMS viajan en el artifact del job de referencia. `final_report` exige los recibos vinculados; se niega a tratar un run antiguo sin snapshot como si tuviera una predecisión moderna. La revisión post-sello de `decision_atms.postevaluation` reconstruye los eventos de la compuerta para conservar sus retractaciones y restituciones en la memoria resultante.

## Qué se puede corregir y qué NO

La superficie `revision_events` acepta para pruebas y futura adaptación a Ledger **únicamente** `retract`, `restore` y `nogood`, ligados al conjunto original de supuestos y reglas de S5; se pueden retirar también `nogood` creados en esa misma rama. No puede añadir nuevos supuestos supuestamente medidos, crear justificaciones favorables a ingresos, cambiar el corpus, actualizar retroactivamente la validez ni abrir truth.

**La CLI pública NO ingiere ni autoriza archivos arbitrarios con revisiones.** Las revisiones inyectadas son hoy un punto de prueba/API controlado y se etiquetan como hipotéticas. Su conversión a cambios canónicos exige un adaptador de Ledger con permisos, fuente verificable y bitemporalidad; no puede hacerse mediante un archivo opcional sin auditoría.

La presencia de personal de apoyo en el dossier sigue marcada **ASSUMED**, no medida. Una comparación permitida bajo este gate es **condicional**, nunca una recomendación para invertir, contratar o reasignar personal en una cafetería real.

## Pruebas decisivas sólo en GitHub Actions

`tests/test_decision_atms_gate.py` cubre:

1. Con soporte válido: recibe decisión RUN, nunca ganancia económica real.
2. Retractar `A_SUPPORT`: soportes de S5 desaparecen y el propio `run_decision` **no llama a `decision.compare` ni a `decision.export`**. Queda recibo de abstención con `allowed_simulations: 0`.
3. Restaurar `A_SUPPORT`: soportes vuelven, la comparación puede correr; su recibo está enlazado por SHA.
4. Declarar un nogood específico y retirarlo: primero bloquea, luego restitución lógica.
5. Rechazar premisas inyectadas, reglas inventadas, hash fuente adulterado y cambios retroactivos.
6. Verificar que el replay post-sello conserva la secuencia efectiva y no inventa evidencia de factibilidad ni beneficio.
7. Conservar el esquema de reportes viejos, pero **no** aceptar un recibo ATMS huérfano de su snapshot.

Se ejecuta junto con las regresiones del PR #31, los contratos originales y las pruebas de integración de Arena. **No se ejecuta ningún análisis, cálculo ni simulación en el entorno del asistente**; los ejemplos son fixtures ficticios procesados por GitHub Actions. No se abre R2, ni se realiza OMC, POST o G3. No se modifica el workflow de producción `coffee-end-to-end.yml`, porque ese archivo tiene un disparador `push main` que podría consumir una campaña real sólo por fusionar un cambio de infraestructura.

## Limitación conocida y siguiente integración

La abstención es **fail-closed**: cuando un job del lote invoca el gate sin soporte, aborta la ruta de P11; el recibo queda escrito en el filesystem del runner, pero el workflow de producción no tiene todavía un artifact de abstenciones con `if: failure()`. No se altera ese workflow automáticamente para evitar un nuevo lote costoso. El paso posterior es un camino administrativo de **`MEASURE_FIRST` con artefacto propio y sin ejecución P11**, integrado con una memoria ATMS/ledger canónica persistente, con autorización de cambio de premisas basada en fuentes reales y sin contaminación de la reserva.

**Aceptación de este PR:** demuestra mediante pruebas de llamadas observables que la pérdida de soporte cambia la **ejecución** de Arena, no sólo la narración. No declara terminada la memoria canónica ni la asesoría empresarial.
