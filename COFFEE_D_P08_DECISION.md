# PR #37 — D con tres capacidades + disposición D/M/referencia

**Pregunta:** ¿D, con una capacidad para preparación y otra para espresso, también distingue el cuello de botella del servicio y cambia qué medición conviene hacer?

## Experimento y contrato

- **No se modifica el D original**: `_vendor/igc/scripts/arena_d_v01.py` mantiene su gramática stock-flow.
- Se selecciona la cadena original **de tres stocks sin pérdidas**. En una copia versionada de `modelica()` se sustituye exclusivamente la capacidad común de los flujos `f1`, `f2` y `f3` por `stageCap1`, `stageCap2`, `stageCap3`. Las cinco ecuaciones diferenciales y el pulso original se conservan línea por línea. Son **stocks genéricos**, no equipos o recetas identificados empíricamente.
- Se usan los dos recuentos de pagos sintéticos de M (Q25/Q75) y la **misma aproximación rectangular de 105 minutos**, no la secuencia realista de eventos que usa la referencia especializada.
- Capacidades supuestas **12 / 15 / 100 pedidos/h** para preparación / espresso / despacho, respuesta **0.1 h**. Variantes B0, **capacidad preparación ×2** y **capacidad espresso ×2**.
- Exactamente **6 simulaciones nativas D en OpenModelica**, sin reintentos; registros de códigos, logs, CSV, balance y drenaje.
- Ninguna diferencia continua de D/M se equipara a una entrega discreta de la referencia. El contraste usa **dirección**, no magnitud común.

## Loop de decisión

Tras los seis OMC el mismo workflow compara D/M/referencia en una grilla fija de dos cargas × dos acciones. Publica `THREEWAY_ATMS.json` y `DECISION.md` con cuatro filas, acuerdos, desacuerdos y el siguiente diagnóstico.

La regla está definida antes de conocer D: ante desacuerdo de dirección, priorizar **ocupación y tiempos de preparación, espresso y barista**; si concuerdan, medir correspondencia física y costes antes de adoptar. ATMS registra predecisión, datos simulados, disposición y la **ausencia de soporte para equivalencia causal, ROI o compra de equipo**.

## GitHub

`.github/workflows/coffee-d-p08.yml` prueba fixtures en PR y ejecuta OpenModelica exclusivamente en **main/push/intento 1**. Recupera artifacts existentes de la referencia (#43697007653) y M (#43702148041), sin volver a simularlos. Cero R2, proveedores, nuevos mundos, truth o G3.

Se busca una **prioridad de medición física**, no otra ronda de custodia. B permanece sin representar esas intervenciones.
