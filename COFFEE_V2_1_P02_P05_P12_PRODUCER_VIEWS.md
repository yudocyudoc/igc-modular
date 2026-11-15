# Arena V2.1 — PR #26: vistas autorizadas P02/P05 y partición P12 temprana

**Base:** PR #25 (catálogo sintético en custodia). Este PR **no modifica motores D/M/B, no repite video, no recalibra el mundo generador y no inicia experimentos pagados**.

## Pregunta y frontera de fuente

Se aprovecha el paquete sintético v1 actualizado, fijado en el módulo P01/P02 por SHA-256, con 18 regímenes, 3 réplicas cada uno y siete días por semana. El video original y su evidencia visual son fuentes de contexto; el POS sintético no son observaciones reales de caja, llegadas o entregas.

La vista productora NO recibe:
- nombres \`scenario_id\` que revelan demanda, perfil de paciencia o factores de los días;
- \`seed\`, resúmenes del mundo, parámetros generadores, vinculaciones privadas o archivos \`*truth*\`;
- ningún registro POS ni partida de los **tres regímenes de EVALUATION (9 semanas)**;
- los minutos históricos reservados de V1 **[60, 103.237...) de su caso B0 original**.

El esquema V1 y la evaluación original siguen congelados. Una reserva V2 basada en el mismo generador **no equivale a una muestra externa**, y la mera partición no constituye un lock científico.

## Entrega técnica

\`arena/coffee_v2_producer_views.py\` prepara vistas **offline dentro de custodia**, sobre el mismo ZIP y la misma clave/SQLite fijados por el PR #25.

Las salidas de productor son:
- \`producer-case-index.csv\`: identificador HMAC opaco, partición (CONSTRUCTION o DEVELOPMENT), réplica y cantidad de pagos/partidas liberados.
- \`producer-pos-observations.csv\`: pagos/reembolsos con segundo ID opaco de evento y pedido, tiempo original en minutos, arquetipo de pedido y montos **rotulados como hipótesis sintéticas**. No incluye la columna JSON incrustada con IDs originales, el nombre del escenario ni campos de demanda oculta.
- \`producer-line-items.csv\`: partidas vinculadas al evento de venta permitido; SKU, arquetipo de trabajo, cantidad, precio y coste unitario hipotéticos. **No** se supone que son consumos/ciclos físicos reales.
- \`producer-paid-bins-5min.csv\`: conteos temporales por caso, día y bin semiabierto de 5 minutos; el último bin termina en el horizonte de pico declarado. Se informan pagos y reembolsos separados; las tasas son equivalentes dentro del intervalo, **no llegadas, capacidad ni entregas**.
- \`producer-video-proxy-minute.csv\`: 104 marcas por minuto con tiempo muestreado y, cuando existan, proxies de presencia/cola. El multiplicador de intensidad sintética que usa el generador no se publica como observación visual.
- \`p12-split-plan.json\`: fuente, versión de la asignación, cantidades 12/3/3 regímenes, definición de unidad de partición, operador, compromisos de integridad y advertencia **NOT_G3**.
- \`producer-view-summary.json\` y \`producer-manifest.json\`: conteos de liberación, rechazos/exclusiones, hashes de salida, límites, sin truth ni IDs privados.

## Compuerta de admisión y reproducibilidad

El módulo requiere el catálogo SQLite **privado** ya construido por P01/P02, y su clave custodiada. Vuelve a comprobar el paquete real fijado por SHA (incluidos hashes de salidas; para truth sólo hash de bytes), verifica huella de clave, hash fuente y mapa exacto escenario-réplica→partición/ID de la SQLite. **Si la clave se regenera, el catálogo cambia o se altera la fuente, detiene la liberación.** No selecciona silenciosamente un archivo más reciente.

La separación no se establece por filas aleatorias ni por eventos dentro de un mismo día; cada escenario completo y sus tres réplicas permanecen en una sola partición. Hay 45 semanas autorizadas (36 construcción, 9 desarrollo) y nueve reservadas. Sólo se liberan registros de POS/partidas correspondientes a las 45, siempre excluyendo el drenaje posterior al horizonte de pico; los bins ocultos por V1 se marcan desconocidos, no como conteos cero. La censura/exclusión se registra. Para el caso original seleccionado en V1, se excluyen los eventos a partir de 60 minutos de su primera réplica/día: preserva el histórico sin fingir novedad predictiva.

No hay ejecución de \`D/M/B\`, OMC, R2, provider, DES, G3 o nueva semilla en esta entrega.

## Ejecución local del custodio

Se requiere el resultado privado *ya persistido* del PR #25:

~~~sh
python -m arena.coffee_v2_producer_views \
  --source /ruta-privada/paquete_sintetico_pico_v1.zip \
  --private-dir /ruta-privada/corpus-custodia \
  --out /ruta-controlada/producer-v2
~~~

El proceso no publica por sí mismo ninguna salida a Actions: el propietario/custodio debe decidir qué directorio se puede transferir a los productores. **Nunca subir** el ZIP, catálogo privado, clave HMAC, lista de casos originales o verdad del simulador. La vista de productor contiene IDs opacos, no necesariamente anonimato estadístico frente a correlaciones de comportamiento.

## Pruebas y aceptación

El CI usa únicamente un ZIP **ficticio**, no el corpus privado real. Cubre reproducibilidad y carácter secreto de los identificadores; bloqueo de cambio de clave/partición; conservación POS→partidas y bins con intervalos semiabiertos; exclusión EVALUATION; censura histórica V1; no filtración de nombres/IDs/semillas/truth; integridad de hashes publicables y rechazo de sobrescritura. Se conservan los contratos de los motores originales.

**P12 sólo está declarado**, no se ha abierto G3 ni verificado rendimiento. No se elige todavía S1–S5. La siguiente etapa de la hoja V2.1 es **P06/P07/P10 mínimo**: una referencia física acotada con trabajos, recursos, simultaneidad y rangos de parámetros, informando las métricas que estos datos pueden o no soportar; después **P11 B0/Sx** con sensibilidad y contribución condicional.
