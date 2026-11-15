# S5: ¿alcanza el personal de apoyo libre para mejorar las entregas?

**Pregunta operativa única:** ¿la reasignación de handoff del barista hacia personal existente sigue mejorando el servicio cuando esa persona debe realizar sus propias tareas?

El ensayo anterior suponía un apoyo enteramente libre. Eso podía exagerar la viabilidad de S5. Este PR lo corrige con una agenda de ocupación **no desplazable**: la entrega debe caber completa en un hueco libre; las otras tareas mantienen su prioridad. Es un supuesto declarado, no ocupación medida.

## Comparación acotada, no otra campaña de infraestructura

- Se reutilizan **exactamente** los dos días CONSTRUCTION Q25/Q75 ya seleccionados por pagos sintéticos, tomados de las vistas autorizadas del run GitHub #43684660729.
- Se conservan los mismos POS, recetas, personal y máquinas en B0 y S5.
- Tres niveles hipotéticos de **disponibilidad del apoyo durante el pico**: 100%, 50% (5 min ocupados / 5 libres) y 0% (apoyo en otras tareas hasta el corte).
- Total: **6 pares físicos, 12 simulaciones de referencia**. No se reejecutan D/M/B ni el generador.
- Cada par compara entregas antes del cierre, pendientes al corte, p90 de pago a entrega tras drenaje, y tiempo de entrega que absorbe el apoyo.
- Como ambas políticas tienen idénticos pedidos previamente pagados, un handoff antes del corte **no es automáticamente una nueva venta**.
- Se reusa la grilla económica P11 **únicamente como hipótesis**: 0/60/150 MXN de oportunidad por reasignación y 0/20/50 MXN de valor de adelantar handoff. Ninguna cifra es margen real.
- Se mantiene la compuerta ATMS: si S5 no conserva soporte condicional bajo el dossier, **no se simula**.

**Decisión buscada:** saber bajo qué niveles discretos de disponibilidad S5 adelanta entregas, cuándo las perjudica y qué **medición dirigida** se requiere antes de recomendar reasignaciones reales. No se interpolan porcentajes no probados ni se afirma saturación empírica.

## GitHub es el único laboratorio

El workflow \`.github/workflows/coffee-s5-availability.yml\` hace CI con fixtures en PR y, **al fusionarse en main**, ejecuta una vez el análisis de construcción sobre vistas autorizadas ya existentes en R2. Ese job sólo descarga archivos P05 permitidos (no ZIP, truth, EVALUATION ni clave), calcula los seis pares y publica \`DECISION.md\`, \`decision.json\`, dos CSV agregados y recibos en un artifact GitHub.

**Cero POST, OMC, mundos nuevos y G3**. No repetir el costoso workflow original.

El resultado será útil para plantear una visita breve a la cafetería: medir tiempos de ocupación del apoyo, tiempo de preparación manual y de entrega y coste de oportunidad. Si el apoyo no tiene ventanas libres, S5 puede ser peor sin importar cuán prometedora pareciera la simulación de antes.

**Límite:** la referencia especializada sigue siendo diferente de D/M/B. La siguiente prueba que aporte valor a los brazos será P08: representación versionada de la misma intervención en al menos un método, no atribuirla a un modelo original que no tiene esa tarea.
