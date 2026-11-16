# P39 — Timers históricos y Hydra de tres grupos (PR de implementación)

**Pregunta:** ¿qué cambia en el modelo al utilizar los 37 pares de timer y representar los tres grupos instalados, sin convertir muestras parciales en ciclos completos?

## Lo que se conserva

- El dossier histórico `EXAMPLE_REFERENCE_DOSSIER_ASSUMPTIONS_ONLY.json` y el experimento de **1 → 2 grupos** permanecen inalterados como ejemplos sintéticos, NO como representación de la Hydra.
- Los parámetros de D/M/B, los datos sintéticos POS y los contratos P05/P12 anteriores no se reescriben.
- La fuente del video2 y la fuente de POS sintético no se enlazan por pedido ni por hora. Una observación de máquina no identifica el pedido sintético ni prueba disponibilidad conjunta.
- Cero OMC, mundos nuevos o POST al proveedor; el ZIP histórico original solo puede abrirse en el custodio de GitHub.

## Proyección permitida

`arena/coffee_hydra_timers_p39.py` autentica el objeto R2 histórico por SHA-256, lee **solo** `video2/completo_v1/eventos_consolidados.csv` y su entrada en el manifiesto, selecciona los **37 pares `medicion_temporizador`** e incluye sus etiquetas G01/G02/G03, relojes de video, lecturas de contador, unidades, incertidumbre y referencias de evidencia. Debe conservar el reparto 17/13/7 y tres ejemplos anclados (TM-T12, TM-T31, TM-T33).

Clasifica una pareja como incremento local compatible, discrepancia o posible reinicio. **Ninguna** pareja se convierte automáticamente en tiempo total de extracción, purga confirmada, bebida terminada o ciclo certificado.

La proyección pequeña es un artefacto temporal de custodia; los productores solo consumen ese JSON, nunca el ZIP completo. El informe público exporta únicamente conteos y restricciones, no las 37 filas detalladas.

## Modelo y predicción que cambian

`experiments/coffee_v2/HYDRA_THREE_GROUPS_DECLARED_P39.json` declara **G01/G02/G03 instalados**, pero estados reales de habilitación no verificados. El escenario de tres grupos habilitados es **ASSUMED**. `coffee_v2_reference_inputs.read_hydra_machine_view` exige evidencia efectiva para las etiquetas antes de que `coffee_hydra_p39.prepare` construya un nuevo dossier versionado con `espresso_group.units=3`. Eso sí cambia el parámetro de entrada del simulador. **La duración automática permanece en 1.5 minutos**, identificada como supuesto histórico; los timers parciales no la calibran.

El instrumento actual sigue simplificando montar, retirar y limpiar en una sola preparación manual supuesta; no está demostrado el paralelismo real con el barista. El diagnóstico informa este límite expresamente.

## Hipótesis que siguen abiertas

- **H1:** los tres grupos instalados están simultáneamente habilitados durante las ráfagas — desconocido.
- **H2:** la restricción está en alimentar y atender la máquina con trabajo manual — desconocido hasta revisar intervalos de barista.
- **H3:** aun con tres grupos habilitados se producen bloqueos de extracción — predicción condicional del simulador, no observación empírica.
- **H4:** las lecturas parciales permiten estimar duración total de extracción — **no demostrada**.

En el PR38, el clasificador de M se corrige: **espresso no vinculante en ambas cargas; preparación activa solo en carga alta**, a partir de los stocks nativos previos. No repetir OMC.

## Prueba científica: presupuesto y autorización separados

La integración auténtica está preconfigurada como **cuatro escenarios de la referencia**: Q25 y Q75 × un grupo (historical B0) versus **tres habilitados supuestos**, con mismos pagos, recetas, duraciones y recursos restantes. Registra entregas al corte, P90, cola y ocupación simulada por grupo (sin doble reserva de slot). Reproduce B0 del artifact histórico como control de deriva.

**No se despacha por fusionar código:** la ciencia auténtica requiere `workflow_dispatch` manual en `main` con `run_authentic_integration=true`. Las pruebas de PR solo usan fixtures inventados y no abren R2. No se alteran disparadores históricos para ejecutar modelos nuevos. Toda ejecución debe registrarse con su consumo real de GitHub/R2.

## Qué significa un resultado válido

- La presencia de G01/G02/G03 exige representar tres grupos instalados.
- Que aparezcan en distintos instantes **no demuestra** que estén habilitados simultáneamente.
- Los incrementos de un timer no identifican duración automática total, pedidos ni tiempos de barista.
- La nueva simulación podrá mostrar consecuencias **condicionales de 1 versus 3 grupos asumidos**, no recomendar compra ni identificar un cuello de botella real.

**Siguiente observación útil:** revisar segmentos T12/T31/T33 y otros necesarios para acreditar inicio/fin, extracción vs purga, disponibilidad simultánea de grupos y trabajo manual para cargar/retirar. No reconstruir toda la extracción ni fingir que el primer video es esta cafetería.
