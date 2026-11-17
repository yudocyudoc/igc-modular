# P43 · Entrega A — Comprobador de episodios observados (sin cambiar motores)

## Pregunta y frontera

El encargo de Astra propone identificar qué reglas y recursos de la representación histórica son compatibles con observaciones de video2 antes de comparar políticas de preparación/carga, leche o entrega. **Este PR implementa sólo la Entrega A**: A1 proyección versionada, A2 pequeño banco de episodios conocidos, A3 veredictos explicables. No implementa B, C o D, ni ejecuta nuevas simulaciones.

La evidencia auténtica se recibió desde el ZIP privado `ENTREGA_GPT_WEB_ARENA_DECISION_Y_EVIDENCIA_2026-11-17.zip` vía Google Drive. Digest del ZIP: `9aee39f3413c0ea7b5f4449b193beb4be375d11cbf65a9f2dfc2fe5b4a0b0275`. Dentro, `evidencia/episodios_revisados.csv` (SHA `217c2bd2d3fd7664b935cfd4fe3e84793cc5d65f04a26d07a3a0d63ad062cc97`) contiene cuatro revisiones; `evidencia/operaciones_existentes.csv` (SHA `a6209a9d45a1c5f4b2453ef741bcdd6ae116bf3852111f30aa1bc5eea14da423`) contiene 36 eventos históricos. Las láminas de fotogramas **NO** se publican ni se cargan en artifacts.

La pequeña proyección legible `experiments/coffee_v2/VIDEO2_EPISODE_REVIEW_A.json` conserva cuatro revisiones y 12 operaciones pertinentes, sin notas libres, nombres, rostros, imágenes, órdenes ni vínculos con POS sintético. La proyección declara los hashes y el conteo del origen y marca lo no observado como `null`. La función `authenticate_original_zip` puede contrastar byte por byte el ZIP original contra esa proyección **cuando el archivo está disponible localmente**. GitHub CI, que sólo tiene la proyección reducida, no declara haber leído el ZIP privado de Astra ni inspeccionado el video; produce un informe de consistencia/representación a partir de las observaciones previamente revisadas.

### Separación de magnitudes

- `counter_elapsed_seconds`: valor estimado de lectura final del contador en T31/T33/T12; **29/32/31 s**; no define media ni distribución.
- `complete_service_seconds` y `group_released_video_s`: **desconocidos**. Contador detenido no equivale a grupo disponible.
- Ventanas `observed_window_video_seconds`: intervalos donde se observaron acciones; no se interpretan como ocupación continua ni como duración completa de una tarea.
- `order_id`: sin determinar para todas las operaciones; tampoco se conocen backlog inicial ni calendario completo de los operadores.
- T28/G02: **purga probable**, excluida de estimaciones de extracción de bebidas. No se registra una bebida adicional.

### Banco de preguntas

| Pregunta | Veredicto | Qué prueba y qué no |
|---|---|---|
| Dos operadores en muestras simultáneas frente a un único barista/puesto global | `CONTRADICTED` | E030/E062 con muestra 48.000 y E032/E064 con muestra 104.006; invalida la exclusividad global de la representación B0 en esos instantes; no demuestra dos baristas siempre disponibles |
| Si los 90 s se interpretan como tiempo transcurrido del contador en *todas* las extracciones | `CONTRADICTED` | T31 da el contexto del contador; T33, otro episodio, tiene lectura estimada final 32 s; **sólo** contradice la interpretación igualada a contador, **no** 90 s de ocupación/reutilización física |
| Máquina en extracción y B02 haciendo otra tarea | `COMPATIBLE` | E115/E149, recursos distintos; factibilidad de solapamiento, no predicción acertada de horarios |
| Clasificación probable de purga T28 y exclusión de bebida | `COMPATIBLE` | No cuenta T28 como extracción de bebida; no certifica visualmente purga con certeza |
| Portafiltro montado después del fin del contador | `NOT_REPRESENTED` | T31 final visto 41.014 y estabilizado hasta 48.000; falta estado posterior y liberación del grupo, sin afirmar ocupación continua |
| Backlog inicial, identidad de pedidos, disponibilidad continua | `INDETERMINATE` | Los datos no resuelven esas variables; no se heredan las condiciones del caso POS sintético |

Los veredictos se refieren a las **reglas y observables concretos declarados en cada pregunta**. Un `COMPATIBLE` significa que no existe conflicto con las restricciones que se examinaron, nunca que el modelo haya predicho esa secuencia. La coincidencia de ventanas manuales por sí sola no certifica actividad continua; el apoyo adicional procede de los fotogramas de muestra revisados por Astra y su anotación. El contraste temporal no transforma valores estimados en mediciones exactas.

### Resultado para el siguiente incremento

La representación histórica **no puede** expresar de manera fiel las muestras con dos personas preparando a la vez bajo su recurso manual globalmente serial, y **no representa** el estado portafiltro montado después del contador. Ambos son problemas de representación, no pruebas de cuello de botella real. Los datos no justifican contratar personal ni aumentar grupos de extracción.

La entrega B puede corregir esas capacidades **manteniendo una ruta histórica intacta**; después C instrumentará esperas y sólo entonces D probará políticas condicionadas a los mismos recursos.

### Ejecución y límites

- Tests de fixtures y guards adversariales en GitHub CI; regresiones P39/P42 sin tocar motores.
- Salida: un informe Markdown y un JSON con ID de comprobación, veredicto, condicionantes, regla contrastada, registros y supuestos.
- Opcional desde entorno donde existe el ZIP original: `python -m arena.coffee_hydra_episodes_a --source-zip ruta/al/paquete.zip --view experiments/coffee_v2/VIDEO2_EPISODE_REVIEW_A.json --historical-dossier experiments/coffee_v2/EXAMPLE_REFERENCE_DOSSIER_ASSUMPTIONS_ONLY.json --out ruta/nueva`. No ejecutar con `--source-zip` como si ese fichero estuviera disponible en GitHub CI.
- Cero R2, OMC, proveedor, nuevas referencias, mundos y enlaces con truth; sólo datos de construcción ya revisados.
- No modificar ni recalibrar P39 o P42. No fusionar hasta revisión independiente de Astra.
