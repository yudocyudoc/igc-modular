# Arena V2.1 — P01: auditoría de cobertura visual original

**Fuente verificada en el entorno del propietario:** piloto_cafeteria_documentacion_y_datos_completosACTUALIZADO.zip, SHA-256 completo:
4ff97ae4d8fe52a5c1d1701aa713fda09b6730ef63d9cbab23e6af30dfad2a5f.

Coincide con la fuente histórica fijada. Los archivos privados permanecen fuera de GitHub y de los productores D/M/B. Se inspeccionaron únicamente los tres CSV visuales y el manifiesto de hashes; no se abrieron las filas de verdad sintética, POS sintético reservado, parámetros de generación ni modelos del mundo.

## Evidencia verificable

| Subconjunto de observación visual | Filas | Cobertura |
| --- | ---: | --- |
| video2/completo_v1/eventos_consolidados.csv | **980** | 0–6,194.007 segundos |
| video2/maestro_15m_v2/eventos_maestro.csv | **288** | 0–899.002 segundos |
| video2/sintetico_pico_v1/revision_fila/personas_clasificadas_1s.csv | **53,270** | detecciones en 6,195 segundos |

Los tres hashes de miembro se contrastaron con MANIFIESTO_PAQUETE.json:
- Consolidado: 8f836f929d732e77f878d11134c882895c7cc4562735a2e933f9231bb066fddd
- Maestro: 1e81b5464d871cb621e18dd8880a99ccb33be714e458785e25cb345099336d72
- Detecciones: 0f5df09c54b9d198c73666535420648fbd604078fa3ab35c232dc66a7ce0921c

**288/288** IDs del maestro están en el consolidado. El contenido semántico coincide tras comparar los campos JSON decodificados y normalizar booleanos; son eventos de origen **solapado**, no 288 adicionales. El consolidado tiene 692 eventos adicionales después de los primeros quince minutos.

| Bloque del video | Eventos consolidados | Detecciones (NO personas únicas) |
| --- | ---: | ---: |
| 0–15 min | 288 | 7,808 |
| 15–30 min | 149 | 7,239 |
| 30–45 min | 106 | 9,294 |
| 45–60 min | 110 | 8,539 |
| 60–75 min | 97 | 7,409 |
| 75–90 min | 113 | 7,212 |
| 90–103.24 min | 117 | 5,769 |

Del consolidado, 928 eventos tienen estado observado, 43 probable y 9 acotado. De las detecciones, 904 tienen origen manual, 12,554 inferido, 6,013 dudoso y 33,799 sin etiqueta de procedencia; son filas de detección, no observaciones independientes de 53,270 personas.

Se identificaron **5 banderas de retirada del pase** y **3 de recepción confirmada**. Son banderas de anotación, no ocho pedidos únicos ni retiros vinculados al POS sintético.

Los **980/980 eventos** están marcados como NO aptos para estimar parámetros de servicio directamente; 980/980 tienen continuidad temporal NO verificada. Ningún evento declara intervalos completos de duración de servicio. Las marcas sobre extracción, portafiltro, vapor o preparación pueden orientar una nueva revisión, **no** justificar una capacidad medida.

La malla de detecciones tiene los 6,195 segundos enteros (0–6194) sin huecos. Esto verifica muestreo temporal, no clasificación perfecta. La fuente ZIP no incluye ni video original ni los fotogramas a los que apuntan sus anotaciones, por lo que no se pueden revalidar las dudas visuales desde este paquete.

## Contrato de ejecución y seguridad

arena/coffee_v2_video_inventory.py verifica el SHA-256 íntegro del ZIP local y hashes del manifiesto de los tres CSV visuales. Lee solo esos tres miembros y MANIFIESTO_PAQUETE.json; genera conteos y coberturas agregadas sin filas, actores, cajas, tracks, textos descriptivos, rutas de fotogramas individuales ni verdad reservada.

Ejecutar **únicamente en un entorno de propietario/custodio** y publicar únicamente sus agregados:

    python -m arena.coffee_v2_video_inventory \
      --source /ruta-privada/piloto_cafeteria_documentacion_y_datos_completosACTUALIZADO.zip \
      --out /ruta-privada/auditoria-visual-p01

La suite de pruebas incluye ZIP ficticio con miembros reservados señuelo para verificar que jamás se leen. No requiere provider/OMC/R2 ni abre G3. Nunca subir el ZIP a GitHub ni montarlo en un workflow de productores.

## Resultado para elegir mecanismo

El hallazgo **reduce incertidumbre sobre la existencia de anotaciones**: se dispone de información distribuida por la ventana completa y no solo por los primeros quince minutos. Pero **NO identifica el cuello de botella ni tiempos físicos validados**.

Se mantiene el estado **MEASURE_FIRST**, con dos mecanismos rivales:
- S2: límite por ocupación exclusiva de máquina.
- S5: límite por tiempo manual activo/compatibilidad de tareas de un operador.

La siguiente medición requiere intervalos emparejados inicio/fin de tarea manual e inicio/fin de máquina ocupada, IDs locales de tarea, disponibilidad de recursos, concurrencia, oclusión y censura. Si no puede revisarse la grabación original, el mecanismo sigue parcialmente no identificable y no se recomienda invertir ni reasignar personal por este inventario.

**Estado:** P01 visual/cobertura documentada y verificable; P01 semántico y catálogo del paquete privado continúan pendientes, así como P02/P05 y el eventual B-G2. No se reescribe V1 ni se utiliza la reserva para seleccionar escenarios V2.
