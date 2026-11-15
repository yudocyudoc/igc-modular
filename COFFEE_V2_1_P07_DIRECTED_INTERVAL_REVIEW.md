# Arena V2.1 — P07: revisión dirigida de intervalos físicos (PR #24)

**Objetivo:** preparar mediciones verificables para distinguir el mecanismo S2 (máquina ocupada) del S5 (trabajo manual/regla de asignación). **Estado del conocimiento:** `MEASURE_FIRST`. Este PR **no** incluye observaciones nuevas, tiempo de servicio estimado, calibración, intervención rentable ni validación empresarial.

## Punto de partida verificado

- PR #22: 980 eventos del video completo y 53,270 filas de detección; **0** intervalos de duración de servicio elegibles y **0** continuidades confirmadas. El paquete custodio **no contiene** video original ni fotogramas.
- PR #23: los 10 pagos **sintéticos** de B0 se distribuyen en perfiles de 5 y 15 minutos; cuatro pagos entre 15–20 min no demuestran saturación de barista ni máquina.
- La selección inicial debe ser descriptiva/exploratoria. Los minutos 60–103.237 de la reserva V1 **no** se liberan para calibración V2. El video completo que se hubiera visto antes tampoco constituye reserva ciega por sí mismo.

## Qué se mide y qué NO

| Registro | Unidad | Inclusión para construir rangos | Prohibición |
| --- | --- | --- | --- |
| `MANUAL_ACTIVE` | segundos de operador efectivamente ocupado en una tarea | extremos observados, recurso y tarea locales, doble revisión y confianza alta | no asumir que todo el ciclo de máquina ocupa al barista |
| `MACHINE_BUSY` | segundos de ocupación exclusiva de un recurso concreto | iguales garantías, máquina identificada | no asumir capacidad de todos los grupos desde un solo ciclo |
| Concurrencia | intersección temporal de manual y máquina en la misma ventana | pares de intervalos de ambas clases elegibles | sumar los pares como si fueran segundos únicos, productividad o capacidad |
| Inicio/fin censurado | límite visible de ventana, con indicador de censura | evidencia de visibilidad, no duración exacta | reemplazar un extremo oculto por uno inventado |
| Recurso disponible, cola, entrega, demanda, ticket | pendiente de observaciones independientes | no representado en el validador actual | inferirlo de personas visibles o del POS sintético |

`task_id` relaciona tareas sin asignar identidad de cliente ni vínculo POS. `resource_id` identifica localmente una máquina o un operador sin indicar identidad personal. `evidence_ref` se conserva solo en la hoja **privada** y apunta a la zona/tiempo revisados en video; no se copia a la salida. Los intervalos `DUAL_CONFIRMED` contienen **dos juegos de extremos temporales y censura**, uno por revisor. El software verifica concordancia frente a la tolerancia fijada en el manifiesto (`max_dual_endpoint_delta_s`, segundos, más `agreement_tolerance_reason`), IDs distintos, evidencia y coherencia, pero **no puede certificar independencia real entre revisores ni autenticidad del medio**. Los archivos privados deben conservar ambas hojas originales antes de su consolidación.

## Diseño mínimo para primera revisión

1. Recuperar la grabación **original** por un canal de propietario/custodio; no subirla a GitHub, adjuntos de Actions, R2 ni productores. Anotar SHA-256 y duración real del medio.
2. Seleccionar y registrar **antes de codificar intervalos** pequeñas ventanas no superpuestas, exclusivamente dentro de los primeros 60 min del video: al menos una de actividad visible, una relativamente tranquila y una incierta cuando exista evidencia. El validador rechaza ventanas después del segundo 3600 para no incorporar la reserva histórica V1 al alcance de esta revisión. Las categorías son provisionales, no condiciones empíricas de saturación. Registrar razón de selección, incluso si no se encuentra el contraste buscado. Los conteos de eventos del PR #22 y el perfil sintético del PR #23 sólo sirven como pistas para navegar; no son selección causal.
3. Revisar comienzos/fines de tareas manuales y de ocupación de máquinas, con recursos exclusivos, tareas opacas y visibilidad/oclusiones. Cada intervalo se revisa de forma independiente y se adjudica con dos revisores distintos si se pretende usar como candidato de calibración.
4. Mantener intervalos dudosos como `DRAFT`/`DISPUTED` y extremos no visibles como `CENSORED`. No eliminarlos del denominador. El validador no reportará una duración exacta para ellos.
5. Auditar la representatividad de ventanas, estados iniciales/finales, disponibilidad de recursos, trazabilidad de revisión y compatibilidad antes de usar los rangos en P06/P07. Si no hay video, pedir nueva observación emparejada en el local y mantener `MEASURE_FIRST`.

No se define aquí un umbral artificial de N intervalos para declarar identificabilidad. El tamaño muestral, discrepancia admisible entre revisores y política de ampliación se fijarán antes de usar intervalos para la primera comparación cuantitativa.

## Contrato y uso offline

El módulo `arena/coffee_v2_interval_review.py` usa solamente biblioteca estándar y `arena.common`. No abre los CSV de P01, ni B0, ni la fuente ZIP, ni el generador, ni la reserva. No decodifica ni reextrae video; **comprueba su hash** para ligar las anotaciones al medio exacto.

Primero crear una plantilla privada de **observaciones vacías**, con seis ventanas temporales predeclaradas y marcadas `PENDING`:

~~~sh
python -m arena.coffee_v2_interval_review --init --out /ruta-privada/p07-hoja
~~~

Después completar el manifiesto (`media_sha256`, `media_duration_s`, `windows`) y `intervals.csv` a partir del original; ejecutar:

~~~sh
python -m arena.coffee_v2_interval_review \
  --manifest /ruta-privada/p07-hoja/manifest.json \
  --intervals /ruta-privada/p07-hoja/intervals.csv \
  --media-file /ruta-privada/cafeteria-original.mp4 \
  --out /ruta-privada/p07-result
~~~

El contrato actual del borrador se versiona como `arena.coffee-v2.p07-directed-interval-review/3`; no se asume compatibilidad automática con las plantillas preliminares anteriores. La discrepancia entre revisores se registra y verifica, pero los intervalos siguen siendo **candidatos para posterior revisión de identificabilidad**, no medidas validadas de capacidad.

El plan sistemático `SYSTEMATIC_FIRST_HOUR_6X180/1` fija seis ventanas de tres minutos: 1–4, 11–14, 21–24, 31–34, 41–44 y 51–54 min. No se eligen según pagos sintéticos, eventos reconstruidos ni supuesta carga real. No son muestra aleatoria ni representan los 60 minutos enteros. Su posición no puede modificarse silenciosamente: si se necesitan ventanas adicionales, declarar otro protocolo `DIRECTED_EXPLORATORY/1` y justificar la selección.

Cada ventana exige `id`, `start_s`, `end_s`, `stratum` (`ACTIVITY`, `QUIET`, `UNCERTAIN`), `selection_reason`, `coverage_state`, `reviewer_ids` y `coverage_evidence_ref`. `coverage_state` puede ser `PENDING`, `PARTIAL`, `REVIEWED` o `NOT_VIEWABLE`. Para contar una ventana `REVIEWED`, dos revisores distintos declaran cobertura completa y evidencia local. Ventana vacía de filas **no equivale a inactividad observada**. Sólo los intervalos de ventanas completamente revisadas pueden llegar a contarse como candidatos aptos; las ventanas parciales y censuradas permanecen registradas.

Cada ventana también conserva su `selection_reason`. Los segundos pertenecen al reloj del **video original**, no a horas de POS. Cada fila usa exactamente las columnas de la plantilla: un intervalo manual o de máquina, sus límites, origen, revisores, nivel de confianza y referencia local de evidencia. Intervalos confirmados exactos del mismo recurso que se solapan son rechazados: dos tareas incompatibles no pueden ocuparlo a la vez.

La salida contiene únicamente `p07-interval-summary.json` y `REVIEW.md`, sin filas ni IDs, tiempos individuales, video, fotogramas ni referencias locales. Existen pruebas negativas para la ausencia/adulteración del medio, solapamientos físicamente incompatibles, censura, alteración del contrato y filtración de IDs. Un `MEDIA_HASH_MISMATCH` o falta de video bloquea el cálculo. El hash sólo verifica que los bytes del archivo corresponden a los declarados; no verifica que el medio sea la grabación original ni que las marcas sean correctas. `DUAL_CONFIRMED` con extremos distintos fuera de tolerancia provoca un error explícito y exige resolver la disputa; nunca se corrige el dato automáticamente.


## Revisión histórica P031: evidencia previa, NO medición certificada

Existe un informe del 4 de noviembre de 2026, `INFORME_REVISION4_P031.md`, que trabajó sobre fotogramas del segmento 2748–2902 s (45:48–48:22). El informe registra la huella del video original como `sha256:cd37c9d3f231f4d307c4f3353ce1dc096fad4185bbdf6ffab06266b9d41290c5`, en aquel momento cotejada contra Drive; **este PR no ha recuperado ni cotejado de nuevo el MP4**. La revisión consistió en 78 fotogramas separados por dos segundos y 45 de refinamiento a un segundo, no en dos anotadores independientes del video continuo. Se documentó manipulación del barista y coexistencia local de hasta tres recipientes con contenido, sin prueba de tres bebidas terminadas, trabajo manual continuo ni motor de máquina activo.

P031 sirve como **pista exploratoria** para definir los tipos de anotación y posibles límites de visibilidad. No introduce duraciones a la calibración ni modifica las seis ventanas sistemáticas. Si se decide examinar P031 de nuevo, se registra como muestreo dirigido retrospectivo, con su sesgo de selección conocido y nuevas mediciones independientes; no se presenta como muestra de carga representativa.

## Relojes y recursos

Los tiempos que se registran son **segundos del video**. La verificación de checksum no acredita velocidad de reproducción real, continuidad del archivo o que 1 segundo de video sea 1 segundo de servicio. Antes de traducirlos en parámetros físicos debe verificarse esa correspondencia. El ID de recurso debe designar la **unidad exclusiva apropiada**: un grupo de extracción puede operar en paralelo a otro grupo o al vaporizador; un ID para toda la máquina podría crear incompatibilidades artificiales. La disponibilidad real y las pausas de equipo son mediciones separadas, todavía faltantes.

## Criterio para permitir el siguiente paso

**Hito de instrumentación (este PR):** contrato, plantilla, validador de dos anotaciones temporales, pruebas offline y CI sin acceso a datos privados. No acredita una sola medición verdadera.

**Compuerta de vinculación:** un intervalo completo aislado de máquina o personal mantiene `MEASURE_FIRST`, aunque tenga doble anotación concordante. Sólo una tarea con ambos intervalos vinculados permite el estado `PAIRED_INTERVAL_CANDIDATES_NEED_IDENTIFIABILITY_REVIEW`. Este estado tampoco identifica saturación ni autoriza elegir S2/S5: aún hacen falta disponibilidad, demanda/carga y representatividad.

**Hito de evidencia (requiere video o nueva observación):** suficientes intervalos vinculados y revisados, heterogeneidad de carga reconocida, tareas y recursos definidos, incertidumbre por visibilidad e identificabilidad documentadas. Podrá entonces evaluarse si hay evidencia útil para rangos de tiempo manual/ocupación, y qué medición adicional discrimina S2/S5.

**Hito de decisión posterior:** sólo con mecanismos representados y costes/rangos pertinentes, comparar B0/Sx bajo escenarios y reglas fijadas; no concluir S2/S5 por contar solapamientos. Ni este PR ni el verificador generan un lock científico, G2/G3 ni abren una reserva.

**Consumo de este PR:** 0 POST, 0 OMC, 0 R2, 0 nuevos mundos sintéticos, 0 acceso a verdad, 0 cambios a `_vendor`, CT-03 o V1.
