# Arena V2.1 — P11: primera comparación condicional B0/S5

**Rama:** PR #28, apilado sobre PR #27 → #26 → #25. **Objeto:** implementar el hito 4 del `17.1 de la hoja V2.1: efectos de un mecanismo B0 frente a una intervención representable, rangos/sensibilidad y costes condicionales, o medición priorizada. Esto NO evalúa D/M/B, no reutiliza V1 como reserva nueva, no inicia G3, no recomienda inversiones reales y no crea semanas nuevas.

## 1. Enfoque y frontera

- **Entrada:** perfiles POS y partidas sintéticas de construcción **autorizados** por el PR #26, cargados por `arena/coffee_v2_reference_inputs.py`. No son llegadas reales, ni ventas reales ni entregas observadas.
- **Referencia:** motor físico acotado P06/P07/P10 del PR #27, con extracción automática y trabajo manual separados, recursos exclusivos y pedido terminado tras completar todas sus bebidas.
- **Políticas:** B0 = barista realiza entrega; S5 = personal de apoyo **ya existente** asume el handoff. Ambas políticas mantienen EXACTAMENTE el mismo personal disponible, capacidades de equipo, duraciones, entrada temporal, mezcla, estado inicial y alcance. La única diferencia es la asignación de la tarea de entrega; lo verifica `counterfactual_pair_gate`. Si el apoyo no existe en el dossier, S5 NO es representable.
- **No simuladas:** contratar S1, comprar máquina S2, S3/S4, abandono, inventarios/insumos, clientes y llegadas reales, calidad, costes reales. Se mantiene el cero de backlog inicial como supuesto, no medición.

**Importante:** las 18 condiciones del generador antiguo varían demanda/días/paciencia, NO son experimentos contrafactuales S1–S5. El resultado P11 es una nueva comparación **condicional de referencia** sobre entradas POS ya existentes. No representa efectos causales observados.

## 2. Selección declarada ANTES del resultado

El manifiesto `experiments/coffee_v2/P11_INITIAL_CONDITIONAL_PROTOCOL_V1.json` declara la regla `CONSTRUCTION_POS_LOAD_Q25_Q75_INPUT_ONLY/1`. Sólo usa **CONSTRUCTION**; DEVELOPMENT no se usa para elegir y EVALUATION nunca se abre.

1. Verificar el bundle del productor y sus hashes.
2. Considerar todas las 36 semanas de CONSTRUCTION × 7 días = 252 días sintéticos. Un día con algún bin reservado/oculto de V1 **no** es un cero observado y se excluye íntegramente. También se excluyen días con cero pagos al seleccionar el primer ejemplo representable.
3. Ordenar todos los días restantes por: total de pagos sintéticos en la ventana, pico de pagos por cinco minutos, ID opaco y número de día. Seleccionar rango **Q25 (floor)** y **Q75 (ceil)** como dos cargas ilustrativas diferentes en orden; nunca seleccionar por resultados B0/S5, esperas, ingresos o verdad oculta.
4. Etiquetarlas **carga pagada sintética baja/alta en la selección**, NO "no saturada" o "saturada" como hecho. Saturación depende de recursos/duraciones desconocidos. Si los dos valores elegidos empatan, se informa la falta de contraste.

No se elige un escenario que favorezca S5, ni se escala el mismo caso para fabricar demanda: son vistas autorizadas de días ya generados.

## 3. Ensayo físico y sensibilidad: 13 variantes × 2 cargas × 2 políticas

El dossier de P07 declara duraciones con valor base, extremos y recurso por tarea. Los 13 escenarios **fijos** son:

- NOMINAL;
- extremos LOW/HIGH *uno a la vez* de las cuatro duraciones manual setup, espresso automático, acabado con leche y handoff (8);
- todas las duraciones en límite bajo y alto simultáneamente (2);
- barista +1 unidad y grupo espresso +1 unidad, **ambos brazos a la vez** (2), como hipótesis estructurales de capacidad, no S1/S2 ejecutadas ni inversión recomendada.

En total: **26 comparaciones pareadas y 52 ejecuciones de referencia**. Cada par reutiliza los mismos pedidos POS, ítems y pago/timestamps, sin truth, sin nuevas semillas ni ajustes a resultados. La sensibilidad OAT + extremos conjuntos **no** agota todas las interacciones posibles: los rangos son hipótesis sobre la estructura, no intervalos estadísticos de confianza.

Se reportan, por escenario:
- pedidos pagados y bebidas sintéticas, idénticos B0/S5;
- handoffs **modelados** estrictamente antes del final del pico y su diferencia;
- pedidos abiertos al corte y entregas durante el drenaje posterior (separados);
- p90 **modelado con drenaje completo** de pago a handoff, no p90 empírico ni p90 observado sólo durante el pico;
- minutos por unidad de recurso, tiempo de barista liberado y soporte existente ocupado, con balance de transferencia.

La salida no incluye tiempos/IDs de órdenes individuales ni una medida física del cuello de botella real.

## 4. Economía ilustrativa: valor del tiempo, NO ventas ni ROI

Las hipótesis fijas del protocolo en MXN por pico son:
- Coste incremental de **oportunidad de reasignar apoyo existente**: 0, 60 y 150 MXN/pico.
- Valor **hipotético** de realizar un handoff antes de terminar el pico, frente a hacerlo durante el drenaje: 0, 20 y 50 MXN/handoff adicional.

Son números ilustrativos, NO nómina, precio, margen real, ahorro validado, preferencia del negocio ni un SLA negociado.

Para cada una de las 26 comparaciones se calculan nueve celdas económicas:

`valor_neto_ilustrativo = (handoffs_pico_S5 - handoffs_pico_B0) × valor_por_handoff_a_tiempo - coste_oportunidad_S5`

**No se cuentan como ventas incrementales** los handoffs adelantados: el modelo recibe exactamente los mismos pedidos ya pagados y drena ambas colas. El umbral `costo/delta_handoffs_pico` sólo está definido si S5 logra una diferencia positiva de handoffs. Cuando el delta es 0 o negativo, no se imprime un umbral de conveniencia inexistente. Los signos positivos/negativos describen las **hipótesis**, no una recomendación del negocio.

La función de decisión real sigue pendiente: el usuario debe definir valor del tiempo, calidad de servicio/umbral y coste de oportunidad antes de recomendar. Se muestra el compromiso entre entregas dentro de pico, p90 modelado, trabajo del barista y coste supuesto.

## 5. Registro de identificabilidad y medición que podría cambiar la decisión

**Primera medición priorizada:** disponibilidad real del personal de apoyo, por intervalo y tarea durante el pico (minutos libres y solape con handoff). **Si ese apoyo no está realmente libre**, el mecanismo S5 descrito no es representable y cualquier beneficio simulado deja de ser aplicable.

**Segunda:** la duración cuya variación LOW/HIGH más cambia el delta de handoffs en la grilla, calculada **sólo sobre hipótesis del modelo**. Es un ranking exploratorio de sensibilidad, no causalidad medida. Medir inicio/fin y solapamientos manual-máquina en una muestra dirigida si se justifica.

**Economía:** coste de oportunidad de esa reasignación y valor real de entrega a tiempo/limitaciones de calidad. Sin esos datos, la decisión debe seguir etiquetada `NOT_IDENTIFIABLE_WITHOUT_REAL_SERVICE_COSTS`.

No se vuelve a extraer el MP4 como requisito de infraestructura; una nueva medición específica es una opción que depende de la incertidumbre decisional identificada.

## 6. Archivos y prueba

`arena/coffee_v2_p11.py`: validación estricta del protocolo, selección por carga POS anterior a simulación, escenarios declarados, pares contrafactuales, economía ilustrativa, ficha de medición y CSV/JSON de salida. Todos los archivos de productor se comprueban por SHA antes de usar la selección; la capa de lectura P06/P10 verifica P12 y rechaza cualquier día con bins reservados.

`tests/test_coffee_v2_p11.py`: ZIP **ficticio** íntegro, selección determinista, 26 pares, 234 celdas económicas, integridad de salidas, bloqueo de cambios en protocolo/partition/costes, rechazo de apoyo inexistente, recibos, privacidad y rechazo de adulteraciones.

`.github/workflows/coffee-v2-p11.yml`: CI offline con regresiones de motores originales, sin fuente privada ni LLM.

## 7. Ejecución integrada en GitHub con R2 existente

El workflow **Coffee Arena - one complete R2 run** obtiene el contenedor histórico ya custodiado, fijado por SHA `4ff97ae4d8fe52a5c1d1701aa713fda09b6730ef63d9cbab23e6af30dfad2a5f`. El adaptador de corpus valida los mismos miembros bajo el prefijo `video2/`, conservando la identidad del archivo original. No depende de subir otra versión del ZIP ni de crear un repositorio privado.

El custodio prepara y conserva en R2 las 45 semanas autorizadas. Otro job recibe sólo las vistas; el proceso de referencia no recibe credenciales R2 ni el ZIP. La ejecución del siguiente comando ocurre dentro de ese job de GitHub:

~~~sh
python -m arena.coffee_v2_p11 \
  --views /ruta-publicable/vistas-productor \
  --dossier experiments/coffee_v2/EXAMPLE_REFERENCE_DOSSIER_ASSUMPTIONS_ONLY.json \
  --protocol experiments/coffee_v2/P11_INITIAL_CONDITIONAL_PROTOCOL_V1.json \
  --out /ruta-nueva/p11-condicional
~~~

Se producen `paired-sensitivity.csv`, `economics-conditional.csv`, `p11-conditional-summary.json`, `REVIEW.md` y `receipt.json`. Los archivos son reproducibles con el mismo bundle/manifiesto, dossier y protocolo. No abrir ninguno en un directorio de truth o en la partición EVALUATION.

**Alcance:** P11 sigue siendo condicional. El mismo workflow incorpora por separado el contraste retrospectivo de los D/M/B originales con el caso V1, usando un lock archivado antes de abrir la verdad; no confunde ese contraste con validación causal de S5. Ver `COFFEE_END_TO_END.md` para la entrada, artifacts, presupuesto y límites.
