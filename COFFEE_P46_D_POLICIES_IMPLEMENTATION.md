# Entrega D — Comparación operativa acotada sobre B/C aceptados

**Base inmutable:** PR45, `5ee1ea43d525afda2d47d7fde7db5ffcd115bc20` (**C_ACCEPT**), sobre PR44 `c850926ef6a13c0efaa4311e80844b89a3f8708b` (**B_ACCEPT**). Este PR es **apilado**, sin alterar los HEAD anteriores ni las rutas históricas.

**Fuentes de reglas:** plan original del 17-nov, sección 7 (D1–D3) disponible en la entrega de proyecto; actualización D4 descrita por Astra al usuario, pero su archivo local `C:/Users/admin1/Documents/igc-arena/PLAN_GPT_WEB_ARENA_DECISION_OPERATIVA_Y_CALIBRACION_2026-11-17.md` **no es accesible desde GitHub ni desde este entorno**. Se implementa el contrato explícito que comunicó Astra; confirmar coincidencia literal con D4 antes de declarar que la versión actualizada del plan está cotejada.

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

La función `compare_existing_construction_q25_q75(view_dir,dossier,dispatch_authorized=True)` está preparada para un lote ulterior desde `main`. Reutiliza los selectores autorizados `coffee_v2_p11._verified_load_choices()` y `coffee_v2_reference_inputs.select_case_day()`, exige partición `CONSTRUCTION`, separa Q25 y Q75, usa **sus** horizontes fuente y compara cuatro políticas en cada uno: **exactamente ocho escenarios**. No abre reservados, truth ni nuevos datasets. No recupera automáticamente nada desde R2.

La llamada sin `dispatch_authorized=True` se rechaza **antes de leer** los archivos. La existencia histórica del run P39 demuestra que estas cargas se seleccionaron antes, pero **no acredita disponibilidad privada actual ni autorización de nuevo despacho**. Un ejecutor posterior en `main` deberá comprobar la disponibilidad con los permisos y gasto vigentes y publicar run/commit/artifact/consumo sin declarar cero por ausencia de factura. El workflow de este PR no ejecuta esas ocho simulaciones.

El diagnóstico C se reutiliza con etiqueta explícita de la política activa. Sólo admite microfixtures `SOFTWARE_TOY_` o las etiquetas exactas de construcción `CONSTRUCTION_SYNTHETIC_Q25/Q75`. No presenta una fuente sintética como pedidos reales.

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

**Revisión solicitada a Astra:** fidelidad de las cuatro reglas respecto a D4, equivalencia exacta B al seleccionar base, eventos de sustitución de prioridades, visibilidad de pedidos perdedores y deltas por persona, bloqueo de las ocho simulaciones privadas hasta autorización y ausencia de cambios físicos silenciosos. Emitir `D_ACCEPT` o `D_FIX` con SHA y caso mínimo; no fusionar PR43/44/45/46 por CI verde.
