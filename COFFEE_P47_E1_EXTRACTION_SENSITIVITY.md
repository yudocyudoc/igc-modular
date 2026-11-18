# P47 E1 — Sensibilidad de la prioridad de leche al tiempo de extracción (Q75)

**Estado:** implementación propuesta en PR, sin despacho privado. **Revisor independiente:** Astra. **Aceptación pendiente:** \`E1_ACCEPT\` / \`E1_FIX\`, por SHA. **No fusionar ni ejecutar el workflow privado por CI verde.**

## Pregunta predefinida

> ¿La ventaja condicional de priorizar leche sobre FCFS en Q75 se conserva si se reemplaza **únicamente** la extracción automática supuesta de 90 segundos por **30 segundos**?

Ni 90s ni 30s son medidas completas calibradas del ciclo del local. Los episodios de temporizador T31/T33/T12 ofrecen lecturas contextuales aproximadas 29/32/31 s; el paro del contador NO implica que el grupo esté libre. No son estimación estadística de la duración. Esta es una prueba de **sensibilidad estructural** sobre una carga sintética CONSTRUCTION, no una prueba de productividad real.

## Protocolo acotado: cuatro celdas, sólo dos escenarios nuevos

| Extracción automática | Política | Procedencia |
|---|---|---|
| 90s | FCFS_READY_ASSUMED | **Reutilizar resultado aceptado** del D run 44234407455 |
| 90s | PRIORITIZE_MILK_READY | **Reutilizar resultado aceptado** del D run 44234407455 |
| 30s | FCFS_READY_ASSUMED | **Ejecutar motor B una vez** con mismo Q75 |
| 30s | PRIORITIZE_MILK_READY | **Ejecutar motor B una vez** con mismo Q75 |

**ÚNICA variable física modificable:** \`durations_min.espresso_auto_min.value = 1.5 → 0.5\` (minutos), y la anotación de procedencia de ese campo (no otro parámetro físico). La retirada \`remove\` de **0,15 min** continúa después de la extracción automática; el grupo queda retenido hasta terminar \`remove\` y la limpieza condicional si corresponde. Se conservan los mismos 3 grupos habilitados, B01/B02, puestos, aptitudes, calendarios, vapor, pase, 46 pedidos, 53 bebidas, recetas, horizonte de 103,2370666667 min, demás tiempos, precedencias y política FCFS como comparador supuesto. No se incorpora personal extra ni la asignación de apoyo S5.

**Estimando principal:** \`ΔP90(30s) = P90(leche,30s) - P90(FCFS,30s)\` en **segundos por pedido**, y \`ΔΔ = ΔP90(30s) - ΔP90(90s)\`. El efecto nominal histórico \`ΔP90(90s) ≈ -3,837 s\` se **lee de la salida original**, sin recálculo de los brazos de 90s. Un delta negativo en el modelo favorece leche para el P90 agregado.

**Tradeoffs obligatorios a 30s:** pedidos adelantados, demorados y sin cambio; máximo retraso y adelanto en segundos (agregados sin IDs); overrides de despacho; entregas al corte; P50; diagnóstico C de min-tarea por etapa, señal de los tres grupos ocupados y bloqueo manual con grupo libre; minutos manuales por B01/B02 y desplazamientos de inicios por etapa. Los conteos no se duplican por operador. No se asume que bajar espera total implique bajar P90.

## Cadena de procedencia obligatoria

1. **Antes de cualquier acceso privado**, el workflow obtiene de GitHub **el artifact público D del run 44234407455** (archivo \`D_Q25_Q75_AGGREGATE.json\`) y verifica \`schema\`, 8 escenarios, \`github_run_id=44234407455\`, \`github_commit_sha=e2da7eea...\`, \`source_view_run_id=43684660729\`, ocho vistas recuperadas y secuencia de políticas.
2. El archivo D Q75 exige \`source_selection_sha256\`, \`selected_case_day_digest\`, \`case_paid_input_digest\`, \`scenario_input_sha256\` y \`physical_dossier_sha256\`. Deben coincidir con la **selección P11 real** y con el dossier original de 90s. Los cambios de Q25, caso/día, entradas, horizonte o recetas invalidan la comparación.
3. Sólo con autorización explícita y tras la verificación del histórico se recuperan las **ocho vistas existentes** del run fuente \`43684660729\`, mediante la misma conexión R2 del entorno \`arena-custodian\`; se selecciona sólo Q75 para ejecutar nuevos escenarios. Un GET puede generar costo incluso si falla: el recibo marca costo **UNKNOWN_NO_PROVIDER_RECEIPT**.
4. **Exactamente dos ejecuciones nuevas** de \`b._engine\` con duración automática de 0,5 min, bajo FCFS y leche; se diagnostican con C. No se llama a D.compare (que ejecutaría cuatro políticas), ni a los viejos 90s, ni a motores OMC, LLM o proveedores.
5. Se exportan **únicamente agregados**; ninguna fila por pedido, trabajo individual, traza o ID privado se publica. Se entregan \`E1_Q75_SENSITIVITY_AGGREGATE.json\`, \`E1_Q75_FOUR_CELLS.csv\`, \`E1_Q75_30S_STAGE_WAITS.csv\`, \`E1_Q75_DECISION.md\`, además de recibos separados y limpieza al terminar.

## Límite de autorización y seguridad

- CI \`.github/workflows/coffee-hydra-p47-e1.yml\`: exclusivamente vistas **ficticias** de \`test_coffee_v2_reference.make_view\`, suites B/C/D, **0 R2/OMC/POST, 0 nueva campaña empírica**. El caso de prueba **no reproduce** los valores reales de Q75.
- Manual \`.github/workflows/coffee-hydra-p47-e1-manual.yml\`: solamente \`workflow_dispatch\` sobre \`main\`, input booleano \`authorize_two_scenarios=true\`, \`GITHUB_RUN_ATTEMPT=1\`, \`environment: arena-custodian\`. El paso de cálculo no recibe secretos; el paso de lectura sí usa los secretos existentes. Nuevo run y SHA en los recibos.
- **No usar este PR como autorización tácita para despachar E1:** solicitar \`E1_ACCEPT\` de Astra y, luego, autorización explícita del usuario para el lote privado acotado. No repetir lecturas si falla la fuente sin examinar el recibo; no reportar R2=0 sin facturación.

## Interpretación predefinida y límites

| Señal calculada | Lectura permitida |
|---|---|
| \`ΔP90(30s) < 0\` | La ventaja condicional del modelo **persiste** en esta sensibilidad; no prueba su generalidad |
| \`ΔP90(30s) = 0\` dentro de EPS | No se observa ventaja agregada P90 en el escenario modificado; revisar overrides |
| \`ΔP90(30s) > 0\` | La dirección se invierte; la hipótesis no es robusta al supuesto de extracción |
| Algún pedido demora pese a menor P90 | Publicar su cantidad y retraso máximo, sin atribuir rentabilidad |

Ningún resultado con dos configuraciones deterministas y una sola carga verifica la disponibilidad real de los tres grupos, el tiempo total de extracción, las aptitudes del personal, o una mejora en la cafetería. Se requieren medidas observacionales adicionales antes de recomendar un cambio.

## Revisión solicitada a Astra

Revisar por SHA: (1) **exactamente dos** invocaciones de B con 0,5 min y no cuatro ni ocho; (2) identidad histórica de D 44234407455 y selección P11 Q75; (3) 90s no re-ejecutados, único parámetro físico cambiado; (4) grupo retenido después de extraer, sin mutación B/C/D; (5) alcance privado de \`arena-custodian\`, compuertas antes de R2 y recibo de coste desconocido; (6) no divulgar filas privadas, correcto \`ΔΔ\` y conteos de pedidos tardíos. Emitir \`E1_ACCEPT\` o \`E1_FIX\` con contraejemplo mínimo; no fusionar ni despachar mientras esté pendiente.
