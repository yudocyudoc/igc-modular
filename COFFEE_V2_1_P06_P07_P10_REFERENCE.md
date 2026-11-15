# Arena V2.1 — P06/P07/P10 mínimo: referencia física y compuertas

**Base:** PR #27 apilado sobre #26 (que depende de #25). Implementa el hito 3 de la hoja V2.1 (``8, 9, 11 y 17.1). **Todavía no es P11, una recomendación, G3 ni una validación real.**

## Frontera correcta

La referencia especializada es independiente de los motores originales D/M/B y del mundo sintético que creó el paquete. Entrada: POS **sintético pagado** con tiempos, ítems y cantidad de bebidas, **exclusivamente** desde la vista autorizada del PR #26. No recibe truth, semillas, etiquetas de factores de escenario ni IDs de origen.

Frontera: **pago sintético → preparación de bebidas → handoff modelado**. Se excluyen explícitamente llegadas reales, caja, abandono, inventarios, reembolsos tratados como salidas físicas, costes reales y tiempos de servicio medidos. Un pedido de dos bebidas sólo termina una vez completadas ambas. No se convierten anotaciones visuales, personas detectadas ni POS en entregas observadas.

## P06: mecanismo físico mínimo

Se elige **una referencia determinista de eventos discretos pequeña** porque hay pedidos/partidas individuales y se necesita asignar recursos exclusivos; la hoja V2.1 (`9.2) admite este enfoque cuando las colas y concurrencias individuales importan. No se desarrollan simultáneamente dos simuladores SD/DES completos ni se sustituye al productor D por esta referencia.

| Arquetipo | Etapas de esta referencia | Recursos exclusivos |
| --- | --- | --- |
| `solo_extraccion` | preparación manual → extracción automática | barista y área de preparación; luego grupo de espresso |
| `con_leche` | preparación manual → extracción automática → acabado con leche | barista/área; luego grupo; luego barista/vapor/área |
| pedido listo | handoff **por pedido** | barista o apoyo existente, más espacio de entrega |

La máquina continúa ocupada automáticamente aunque el barista esté trabajando en otra bebida. Las tareas adquieren simultáneamente los recursos compatibles y los liberan al finalizar. **Simplificación explícita:** el acabado con leche ocurre después de la extracción de esa bebida; la preparación simultánea de leche y extracción de la misma bebida, lotes, preparaciones ajenas al POS y otras labores no están representadas. FIFO con búsqueda de otras tareas compatibles para no bloquear todo el proceso por un recurso ocupado.

Políticas estructurales admitidas:
- **B0:** barista realiza el handoff.
- **S5_TRANSFER_HANDOFF_TO_EXISTING_SUPPORT:** el handoff se reasigna a **personal de apoyo ya existente** en el dossier; no se crea otro trabajador ni se aumenta la capacidad automáticamente. Sin apoyo declarado, el caso se rechaza. Que la persona esté efectivamente libre es una **hipótesis a contrastar en P11**, no una observación del video.

No se implementan S1–S4 ni se elige todavía ninguna intervención como recomendación.

## P07: hipótesis e identificabilidad

`arena/coffee_v2_reference.py` requiere un dossier versionado con seis recursos (barista, grupo de espresso, vapor, espacio, pase, apoyo existente), cuatro duraciones, unidades, límites, procedencia y estado `ASSUMED`/`BOUNDED`. El modelo no acepta ahora `MEASURED` porque todavía no existe una verificación de mediciones físicas dentro de este contrato. Se declara el estado inicial **cero pendiente supuesto**, no observado. Reporta como `NOT_IDENTIFIABLE_FOR_THIS_CASE` las duraciones/capacidades reales, llegadas, espera real de pago a entrega y resultados económicos.

`experiments/coffee_v2/EXAMPLE_REFERENCE_DOSSIER_ASSUMPTIONS_ONLY.json` es un **ejemplo ilustrativo de ingeniería**: ninguna cifra debe presentarse como un tiempo o dotación real. Las unidades de trabajo sí están fijadas (minutos por bebida para setup/extracción/acabado y minutos por pedido para entrega).

## P10: compuertas y resultados

El adaptador `arena/coffee_v2_reference_inputs.py` consume **sólo ocho archivos permitidos** de la vista P26, validando su conjunto y todos sus SHA, linaje del paquete original, partición P12, existencia y pertenencia del caso, y los 21 bins de 5 minutos. Rechaza casos con bins reservados de V1 en vez de interpretar las celdas ocultas como ceros. Nunca lee el ZIP original, SQLite privada o archivos truth.

El motor verifica **adquisición exclusiva de recursos**, disponibilidad de vapor cuando se requieren bebidas con leche, vínculo de partidas con pagos, multiplicidad de bebidas, no negatividad, conservación de recursos y:
- pedidos pagados = handoffs modelados dentro del pico + pendientes al corte;
- handoffs modelados hasta drenar = pedidos pagados;
- operaciones de preparación y extracción = unidades de bebida;
- reembolsos POS **no** equivalen a entregas negativas.

Las métricas habilitadas son **simuladas y condicionales**: pedidos/bebidas sintéticos, handoffs antes del corte semiabierto, backlog al corte, drenaje posterior, operaciones por recurso y percentiles **modelados con drenaje completo**. El p90 resultante **no** es espera real de clientes, ni una espera p90 observada en la ventana (tiene censura en el borde).

La salida sólo contiene agregados, identificador opaco del caso, manifiesto/hash y registro de parámetros. No publica órdenes ni trazas de cada bebida. No identifica empíricamente un cuello de botella ni una contribución real.

## Reproducción sin gasto

Requiere vistas de productor ya generadas y publicadas bajo el permiso correcto; no copiar truth ni el catálogo privado:

~~~bash
python -m arena.coffee_v2_reference \
  --views /ruta/vistas-P26-autorizadas \
  --case-id ID_OPACO_DE_UN_CASO_CONSTRUCTION \
  --day 1 \
  --dossier experiments/coffee_v2/EXAMPLE_REFERENCE_DOSSIER_ASSUMPTIONS_ONLY.json \
  --out /ruta-nueva/referencia
~~~

Los tests usan únicamente fixtures ficticios: recursos y trabajo simultáneos, pedido de dos bebidas, política S5 sin nuevos empleados, reembolso, censura de corte, unidad física, rechazo de un supuesto marcado como `MEASURED`, y adulteración de una vista POS. La integración científica posterior requerirá jobs de ejecución, presupuesto, sellado y custodia, no basta con CI verde.

**Consumo:** cero POST, cero OMC, cero R2, cero G3, cero nuevos mundos. Motores originales, CT-03 y V1 intactos.

## Siguiente paso P11

Elegir una intervención condicionada mediante el mecanismo y la evidencia disponible, fijar **antes de ejecutar** regímenes no saturado y potencialmente saturado, rangos de duraciones, apoyo y costes, criterios de factibilidad y la métrica de decisión. Comparar B0/Sx con las mismas entradas autorizadas y registrar cuándo cambia la elección. No abrir EVALUATION ni afirmar ROI real por una diferencia simulada.

**Alcance de este PR:** software de referencia física verificable, no análisis empresarial final ni comparación D/M/B.
