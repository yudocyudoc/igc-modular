# Arena V2.1 — PR #25 · P01/P02 inventario del corpus sintético completo

**Alcance:** seguir ``6.1–6.3, 17.1, 17.3 y 17.4 de la hoja de ruta V2.1. Reutilizar los datos; no volver a extraer video ni iniciar nuevos mundos simulados.

## Evidencia y versión

El ZIP propietario `paquete_sintetico_pico_v1.zip` se recuperó de la fuente de Google Drive registrada en la auditoría histórica (ID `1GsiI3gmAxqSvMpXBpLudUv8wkgPmtgyC`), fuera del repositorio. Se inspeccionó la versión disponible el 14–15 de noviembre de 2026. **No es la misma versión** que el ZIP de 14 entradas y ~14.2 MB descrito en el informe del 11 de noviembre: ahora hay **23 entradas y 15,351,718 bytes**, con digest completo:

`dd18a787a1ac3dcd065fe54bff9a2f567d945c60d16e7a646444dacaa6ffbef9`.

El manifiesto `cafeteria.synthetic-output-manifest/2` declara 19 salidas CSV/JSON. Sus 19 SHA-256 y tamaños se cotejaron contra bytes de los miembros en el entorno de análisis. Parámetros y escenarios corresponden a un generador `cafeteria.synthetic-scenario/1` que **no se calibró con tiempos físicos de servicio**.

| Conjunto | Actual comprobado o declarado | Límite |
| --- | ---: | --- |
| Diseño | 18 combinaciones de entrada × 3 réplicas = 54 semanas de 7 días | Condiciones de demanda/paciencia/días 6–7, no S1–S5 |
| POS sintético | 14,244 filas: 13,957 ventas, 287 reembolsos | Pagos, no llegadas ni entregas |
| Partidas POS sintéticas | 16,097 filas | Arquetipos inventados, no recetas ni consumo físico medido |
| Resúmenes semanales | 54 filas | Incluyen etiquetas de factores y semillas privadas |
| Perfil visual temporal | 104 minutos | Forma relativa de intensidad, no demanda absoluta |
| Hipótesis de vinculación de recepción | 4 filas declaradas | Alternativas mutuamente excluyentes, no cuatro ventas |
| Imputaciones del vínculo visual→POS | 300 filas y 400 líneas declaradas | Sorteos hipotéticos, no transacciones reales independientes |
| Verdad de pedidos, eventos y acciones | Archivos CSV/JSON | Se verifica SHA de bytes; NO se interpretan filas para productores |

Hay pagos sintéticos posteriores a la ventana 103.237 min. Los resultados para el pico se deben separar del drenaje posterior de la cola. Las variables económicas de este generador son supuestos ilustrativos, no márgenes reales ni ganancias; `net_profit_mxn` sigue sin valor.

## Implementación

Nuevo módulo `arena/coffee_v2_synthetic_corpus.py`:

- Verifica digest completo del ZIP, lista exacta de 23 miembros, esquema y hash de configuración y SHA de los 19 outputs, incluida la verdad **sólo a nivel de bytes**.
- Analiza en custodia únicamente los cuatro CSV necesarios ahora: resumen de escenarios, POS, partidas y perfil visual. Valida 18×3 claves, semillas, tipos, ventanas, integridad de pagos/partidas y origen sintético.
- Construye `catalog.sqlite` privado con procedencia y pertenencia de cada caso. Genera pseudónimos HMAC mediante clave local reservada.
- Define particiones por **escenario entero**, nunca por filas del mismo régimen: 12 escenarios en construcción (36 semanas), 3 desarrollo (9) y 3 evaluación sintética (9), conservando las 3 réplicas y 7 días de cada escenario en una única partición.
- Separa directorio privado (SQLite, clave) de salida **agregada** (`corpus-coverage.json`, `consumption-to-decision.csv`, `REVIEW.md` y `receipt.json`); ningún nombre de escenario, semilla, clave, verdad o fila POS sale al directorio publicable.

La partición por HMAC no demuestra independencia empírica ni crea ceguera humana retroactiva. Si se quiere un G3 futuro, modelos, políticas y métricas deben sellarse antes de abrir una reserva científica apropiada. La reserva histórica V1 **no se recicla como evaluación V2 independiente**. Además, la muestra de 54 semanas solo varía entradas del mismo mecanismo físico del generador: no implementa tratamientos contrafactuales S1–S5.

## Ejecución offline únicamente en custodia

~~~bash
python -m arena.coffee_v2_synthetic_corpus \
  --source /ruta-privada/paquete_sintetico_pico_v1.zip \
  --private-out /ruta-privada/corpus-custodia \
  --public-out /ruta-separada/revision-agregada
~~~

Para reproducir la misma asignación en otra carpeta privada usar la clave guardada localmente:

~~~bash
python -m arena.coffee_v2_synthetic_corpus \
  --source /ruta-privada/paquete_sintetico_pico_v1.zip \
  --key-file /ruta-privada/corpus-custodia/custody-key.bin \
  --private-out /otra-ruta-privada/corpus-custodia-v2 \
  --public-out /otra-ruta-separada/revision-agregada-v2
~~~

**Nunca subir a GitHub** el ZIP, los CSV originales, el SQLite, la clave, los nombres originales de escenarios ni la verdad. CI usa un paquete diminuto de datos ficticios. Cero R2, OMC, POST y mundos sintéticos nuevos.

## Matriz evidencia → consumo → mecanismo → decisión

| Fuente | Consumo de este PR | Uso siguiente |
| --- | --- | --- |
| Visual consolidado y detecciones | PR #22, separado del ZIP sintético | Contexto de proceso y proxy, no capacidad/servicio medidos |
| POS sintético 54 semanas | Ingesta completa y comprobación de joins | P02/P05: vistas autorizadas anonimizadas y perfiles temporales |
| Partidas | Joins con pagos comprobados | Arquetipos y cargas físicas **supuestas** según dossier |
| Resumen + semillas | Índice privado y particiones | P12: controlar desarrollo y evaluación, no dar latentes al productor |
| Truth sintético | Hash; filas sin interpretar | Evaluador después del lock, no calibración del productor |
| Costes/precios | Hipótesis ilustrativas | P11: sensibilidad/umbral, no ROI real |
| Políticas físicas S1–S5 | No implementadas por este generador | P06/P07/P10: representar una Sx de manera explícita |

**Próximo incremento:** construir las vistas P02/P05 de productor por casos *CONSTRUCTION/DEVELOPMENT* con IDs opacos y operadores temporales; mantener los casos reservados exclusivamente bajo custodia. Después P06/P07/P10 y primera decisión P11, conforme al `17.1. No se requieren nuevas anotaciones de video para avanzar sobre el laboratorio existente.

**Aceptación de PR #25:** ingesta/partición trazable del corpus sintético actualizado y matriz de consumo real, NO intervención ni conclusión empresarial.
