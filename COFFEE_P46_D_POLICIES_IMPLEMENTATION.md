# Entrega D — Comparación operativa acotada sobre B/C aceptados

**Base inmutable:** PR45, `5ee1ea43d525afda2d47d7fde7db5ffcd115bc20` (**C_ACCEPT**), sobre PR44 `c850926ef6a13c0efaa4311e80844b89a3f8708b` (**B_ACCEPT**). Este PR es **apilado**, sin alterar los HEAD anteriores ni las rutas históricas.

**Fuentes de reglas:** plan original del 17-nov, sección 7 (D1–D3) disponible en la entrega de proyecto; actualización D4 descrita por Astra al usuario, pero su archivo local `C:/Users/admin1/Documents/igc-arena/PLAN_GPT_WEB_ARENA_DECISION_OPERATIVA_Y_CALIBRACION_2026-11-17.md` **no es accesible desde GitHub ni desde este entorno**. Se implementa el contrato explícito que comunicó Astra; confirmar coincidencia literal con D4 antes de declarar que la versión actualizada del plan está cotejada.

## Retro de Astra sobre PR46 — D_FIX en 2f124756, correcciones D1–D3

**Dictamen:** Astra aceptó la mecánica de las cuatro políticas y reprodujo la identidad exacta FCFS con B. La entrega D completa permanecía en **D_FIX** por trazabilidad del lote de construcción, vinculación de la política ejecutada y lectura del resultado.

**D1 · Recorrido manual unido:** la exportación ahora acepta `CASE_SET_SCHEMA` y crea `D_Q25_Q75_AGGREGATE.json`, `D_Q25_Q75_PAIRED.csv`, `D_Q25_Q75_OPERATOR_STAGE.csv` y `D_Q25_Q75_DECISION.md`. El CI usa `test_coffee_v2_reference.make_view` para ejecutar selección P11, ocho brazos y exportación sin secretos. Existe un nuevo workflow **manual** `.github/workflows/coffee-hydra-p46-d-manual.yml`, disponible al integrarse en `main`. Requiere selección positiva de autorización, rama main, primer intento, ejecución `workflow_dispatch`, y referencia de workflow correcta. Dos pasos separados: primero reutiliza `coffee_s5_availability.fetch_existing_construction_views()` para leer **exclusivamente las vistas del run 43684660729** con las credenciales R2 existentes, luego ejecuta comparación/exportación en otro paso **sin credenciales R2**. El artifact público es sólo agregado; las vistas privadas no se suben y se borran al terminar. Se publica un recibo de intento incluso en fallo: una lectura fallida puede tener coste y por eso el gasto R2 es **UNKNOWN** sin factura. No se inició la ejecución manual ni se pidió autorización de gasto en este PR.

**D2 · Procedencia y política ejecutada:** una llamada directa a `compare` con etiquetas Q25/Q75 se rechaza aunque el texto concuerde: sólo la ruta que verificó los archivos y seleccionó caso/día mediante P11/`select_case_day` recibe la capacidad interna de construcción. El informe conserva el digest de la selección, el digest de caso/día, partición, horizonte, fingerprint de entradas y (cuando corresponde) run histórico de vistas. Cada variante no-FCFS produce un marcador PRIVADO `dispatch_policy_identity` al empezar la simulación, **también si hay 0 sobrescrituras**; C deduce su política de la traza y rechaza la política contraria. La base B no cambia ni un byte en el resultado/traza de su modo histórico. El informe del microfixture declara `SOFTWARE_TOY_ONLY_NOT_REAL_CAFE`; la futura lectura R2 registrará intentos de GET y coste no verificado, sin una afirmación fija «R2=0».

**D3 · Decisión y trabajo desplazado:** el reporte clasifica dirección y signo del P90 por carga: empeora, mejora con o sin pedidos retrasados, empate con cambios o prioridad no activada. La mejora P90 con perdedores se reporta explícitamente como costo/compensación, no como elección recomendada. Se incluyen por operador y etapa **número de tareas, minutos ocupados y diferencias frente a FCFS**; también número y minutos de inicio adelantado/demorado por etapa. El artifact Q25/Q75 presenta una tabla pareada de ocho filas y lectura de concordancia/diferencia entre Q25/Q75; sólo la prueba de software exporta por pedido, el artifact de construcción nunca incluye filas de pedidos ni tareas.

**Aceptación requerida tras la corrección:** Astra debe verificar ambos caminos de D: microfixture de tres pagos y microfixture de vistas CONSTRUCTION de `make_view`, cotejando exportación del conjunto, recibos de run/commit/consumo, rechazo de etiquetas/cross-policy incorrectas, y resultados direccionales del P90. El conjunto privado queda sin ejecutar. Dictamen solicitado `D_ACCEPT / D_FIX` sobre el HEAD actualizado.

## Segunda retro de Astra — D_FIX en 93ecb906, dos correcciones localizadas

**D4-custodia:** El workflow manual `.github/workflows/coffee-hydra-p46-d-manual.yml` declara ahora **`environment: arena-custodian`** directamente en el job de ocho escenarios, igual que el precedente P39. Es el entorno donde el repositorio documenta las credenciales S3 de R2; las variables secretas siguen apareciendo únicamente en el paso de lectura, no en el paso separado de comparación. Existe una prueba estática de YAML que compara ese requisito con el precedente sin contactar R2. No implica que se hayan leído o comprobado los valores de los secretos ni la disponibilidad actual de las vistas.

**D4-unidades y cargas:** Los cambios de comienzo de tareas son totales **globales por etapa, una vez por tarea**, incluyendo extracción automática sin operador. El nuevo archivo **`D_Q25_Q75_STAGE_SHIFTS.csv`** tiene una sola fila por carga×política×etapa y contiene los conteos y minutos globales adelantados/demorados. **`D_Q25_Q75_OPERATOR_STAGE.csv`** sigue mostrando exclusivamente trabajo realmente asignado a cada operador: conteos de tareas manuales, minutos ocupados y delta de minutos por etapa frente a FCFS; no se duplican allí los cambios globales de inicio. La agregación pública conserva ahora `paid_orders` y `synthetic_beverages` por carga y política, también en la tabla pareada y Markdown. El caso específico de Astra —**un pedido, tres bebidas, una preparación demorada**— está fijado como regresión. Las pruebas del conjunto de ocho brazos validan que cada fila de la tabla global coincide con el JSON y que no existen columnas de inicios globales en el CSV por operador.

**Dictamen pendiente:** solicitar a Astra `D_ACCEPT / D_FIX` sobre el nuevo HEAD; el CI de PR solo ejecuta pruebas de software con vistas ficticias. **No se ejecutó** el workflow manual, ningún GET R2, ni las ocho comparaciones privadas.

## Reglas de despacho: exactamente cuatro brazos

El motor conserva **dos operadores B01/B02**, el número de grupos habilitados del dossier (tres en el nominal), puestos, vapor, pase, aptitudes, calendario asumido, duraciones, recetas, horizonte de la fuente y precedencias. Cada tarea ocupa su operador, recurso y grupo con la misma atomicidad y liberación de B.

1. **FCFS_READY_ASSUMED (base)**: primer trabajo ejecutable de la lista de elegibles. Es la política **supuesta** de B, no una observación del despacho del negocio. Elegir esta opción ejecuta literalmente el mismo código de selección de B; el resultado, la traza y las entregas deben coincidir exactamente.
2. **PRIORITIZE_LOAD_READY_WITH_FREE_GROUP:** si hay alguna carga elegible y completamente ejecutable ahora (actor disponible y apto, grupo FREE), seleccionar la primera carga de la cola antes que otras tareas ejecutables. Puede aplazar preparación, leche, retirada o entrega que habría empezado con FCFS. No preempta ninguna tarea ya iniciada.
3. **PRIORITIZE_MILK_READY:** dar prioridad sólo a una tarea de leche elegible y ejecutable (actor B01/B02, aptitud y disponibilidad, varilla libre). Puede postergar tareas manuales de otras etapas; no modifica precedencias de la misma bebida ni inventa trabajo paralelo en ella.
4. **PRIORITIZE_HANDOFF_READY:** dar prioridad sólo a una entrega elegible y ejecutable por B01/B02 y pase libre. Puede desplazar preparación/carga/leche y otros trabajos manuales. **No** asigna automáticamente `existing_support` como S5 histórico; aquel mecanismo no es el mismo.

En cada variante, si el candidato priorizado **no es ejecutable ahora**, se aplica la primera asignación ejecutable FCFS. Empates dentro de la clase favorecida respetan el orden ya existente de la cola. Se usa la misma función `choose()` del motor B: no hay reserva futura, nuevas estaciones, nuevos trabajadores ni reglas físicas duplicadas.

## Demostración del cambio, no sólo nueva cifra P90

- Registrar eventos PRIVADOS `dispatch_override` cuando la selección difiere de la primera tarea ejecutable de la cola en ese instante. Se incluye tarea desplazada, tarea elegida, operador, grupo y reloj asumido. La comparación pública seudonimiza los IDs.
- Calcular por pedido (etiquetas `P0001`, etc.) hora de entrega y delta respecto al mismo pedido bajo la base; mostrar tanto **adelantados como demorados**.
- Comparar por tarea hora de inicio, actor y grupo; mostrar tareas desplazadas y distribución del trabajo por B01/B02 en minutos y conteos.
- Incluir entregas antes del corte de **la fuente**, pendientes al corte, P50/P90 de pago a entrega hasta vaciar el sistema, deltas, contadores de intervenciones y esperas por etapa desde C.
- `NO_RULE_INTERVENTION` significa que la regla no cambió ninguna asignación: no se puede atribuir una mejora ficticia a ella. Un `P90` menor con algún pedido demorado exige explicar el intercambio.
- No imponer umbral económico, ganador universal ni magnitud de mejora real. Las cifras son del modelo condicional frente a una política base supuesta.

## Entradas y alcance: fixture ahora, Q25/Q75 después

El PR produce un **reporte público de cuatro políticas sobre el microcaso existente de tres pagos ficticios**. Además, las pruebas unitarias usan microfixtures ficticios adicionales de conflicto (una bebida con leche o sin leche y tres pagos tardíos) para verificar que leche y entrega **sí alteran** el despacho cuando hay preparación ejecutable a la espera. Son contraejemplos de software, no escenarios de un nuevo corpus ni una campaña científica. No se modifica la fuente P39 ni se consume el lote Q25/Q75.

La función `compare_existing_construction_q25_q75(view_dir,dossier,dispatch_authorized=True)` ahora realiza la **selección verificada** y ofrece el conjunto de ocho brazos a `export`. Reutiliza los selectores `coffee_v2_p11._verified_load_choices()` y `coffee_v2_reference_inputs.select_case_day()`, exige partición `CONSTRUCTION` y conserva los horizontes particulares de Q25 y Q75. El workflow manual tiene la recuperación privada ya conectada con `coffee_s5_availability.fetch_existing_construction_views()`, pero no se despacha automáticamente desde PR y no lee reservados, truth ni datasets nuevos.

La llamada sin `dispatch_authorized=True` se rechaza **antes de leer**. El workflow manual utiliza un checkbox explícito y sólo es ejecutable en `main` desde `workflow_dispatch`. La disponibilidad real de las vistas privadas sigue sin comprobarse: el run P39 sólo documenta una lectura histórica. El workflow publica run/commit/source y recibo de intentos GET en éxito o fallo, conservando como desconocido el costo facturado. No hay autorización implícita para disparar la ejecución desde este PR.

El diagnóstico C ya no acepta una etiqueta de política suministrada sin verificar: la compara con el identificador de política **ejecutada** presente en la traza. Para construcción exige además la capacidad interna del adaptador que seleccionó las vistas verificadas; los microfixtures conservan su ruta propia `SOFTWARE_TOY_`. Ninguna ruta presenta pedidos ficticios como observados.

### Resultado efectivo del microfixture público de tres pagos

| Política | Veces que la prioridad cambió una asignación | P90 pago→entrega | ΔP90 vs FCFS | Pedidos adelantados / demorados |
|---|---:|---:|---:|---:|
| Base FCFS supuesta | 0 | 3,49 min | 0,00 | 0 / 0 |
| Prioridad carga | 2 | 3,57 min | +0,08 min | 0 / 1 |
| Prioridad leche | 0 | 3,49 min | 0,00 | 0 / 0 |
| Prioridad entrega | 0 | 3,49 min | 0,00 | 0 / 0 |

La prioridad de carga adelantó tres inicios de tareas, demoró seis y el tercer pedido se entregó **0,10 min más tarde**; no adelantó ninguna entrega. Las políticas de leche y entrega **no intervinieron en ese microcaso**: eso no demuestra que no funcionen. Dos regresiones con competencia explícita comprueban que ambas sí cambian la asignación cuando hay trabajo anterior y tarea priorizada ejecutable. Este resultado no identifica la política operativa real ni un efecto en la cafetería.

## Evidencia de aceptación y límites

- Identidad exacta de `_engine(positions,lines,dossier,horizon)` y `_engine(...,dispatch_policy="FCFS_READY_ASSUMED")`: resultado, traza y finales. Es una prueba de compatibilidad más fuerte que compartir un P90.
- En t=0,50, el microfixture contiene una preparación pendiente y cargas ejecutables. La prioridad de carga debe intervenir y mostrar qué tarea empieza antes y qué tarea queda después.
- Variantes de leche y entrega se limitan a recursos/aptitudes de B01/B02, **nunca al trabajador adicional del S5 histórico**.
- Para cada brazo, mismo número de pagos, bebidas, recursos y tareas terminadas; no doble reserva de grupo. Intervalos de espera C particionan exactamente elegibilidad→inicio.
- La salida incluye JSON, MD y CSV por pedido seudonimizado; no contiene IDs reales/sintéticos de pago. El MD muestra dónde cambió la asignación y el JSON incluye intervenciones por evento y trabajo desplazado.
- Un caso de un solo pedido, sin competencia de tareas ejecutables, debe producir cero intervenciones y ningún cambio en servicio.
- Q25/Q75 requieren autorización explícita y sólo admiten vistas `CONSTRUCTION` previamente verificadas. Sin grilla, nuevas réplicas, OMC, proveedor ni video.

### Reproducción en GitHub Actions

```bash
python -m unittest discover -s tests -p test_coffee_v2_hydra_policies_d.py -v
python -m unittest discover -s tests -p test_coffee_v2_hydra_causes_c.py -v
python -m unittest discover -s tests -p test_coffee_v2_hydra_physical_b.py -v
python -m arena.coffee_v2_hydra_policies_d \
  --toy-input experiments/coffee_v2/C_FIXED_TOY_PAID_INPUT.json \
  --dossier experiments/coffee_v2/HYDRA_TWO_OPERATORS_PHYSICAL_B_ASSUMPTIONS.json \
  --out /tmp/p46-d-toy
```

Workflow: `.github/workflows/coffee-hydra-p46-d.yml` (CI offline). Artefactos: `D_PAIRED_POLICY_COMPARISON.json`, `D_PAIRED_POLICY_COMPARISON.md`, `D_ORDER_OUTCOMES_PSEUDONYMOUS.csv`.
**Workflow de lote ulterior:** `.github/workflows/coffee-hydra-p46-d-manual.yml`. Tras la integración en `main`, debe iniciarse explícitamente desde GitHub Actions con `authorize_eight_scenarios=true`; sólo descarga vistas del run `43684660729` y no lanza OMC/proveedor. Su estado actual es **NO EJECUTADO**, sin confirmación de disponibilidad privada ni costo R2. Las pruebas de CI PR se mantienen sin esas credenciales.


**Revisión solicitada a Astra:** fidelidad de las cuatro reglas respecto a D4, equivalencia exacta B al seleccionar base, eventos de sustitución de prioridades, visibilidad de pedidos perdedores y deltas por persona, bloqueo de las ocho simulaciones privadas hasta autorización y ausencia de cambios físicos silenciosos. Emitir `D_ACCEPT` o `D_FIX` con SHA y caso mínimo; no fusionar PR43/44/45/46 por CI verde.
