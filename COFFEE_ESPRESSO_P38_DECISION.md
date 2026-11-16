# PR #38 — ¿Por qué espresso ayuda en referencia y no en modelos agregados?

**Pregunta única:** ¿qué restricción de cada simulador explica que añadir un grupo de espresso reduzca la espera/adelante una entrega en la referencia mientras duplicar throughput espresso en M/D no cambia su contador?

## Hipótesis con resultados EXISTENTES

- **H_AGG:** M no está saturando espresso: preparación tiene un máximo nominal de 12 órdenes/h y espresso 15 órdenes/h. Se lee el **CSV nativo ya publicado** de M y se comprueba si el stock `espresso0.waiting / 0.1 h` alcanza el máximo 15/h. El delta previo de duplicar espresso debe ser cero. Esto no describe una máquina real.
- **H_REF:** la referencia agenda tareas de bebida que requieren grupos exclusivos de espresso. Si un grupo ocupado bloquea otras tareas, añadir uno debería reducir esa espera y el P90 simulado. Se instrumenta **sin alterar la planificación**: entrada a etapa, saturación del recurso, inicio del servicio, espera en pico, ocupación por grupo y P90. Sólo se reejecutan B0 y espresso +1 con los mismos pagos y recetas CONSTRUCTION ya aprobados.
- **H_CROSS:** el desacuerdo queda enteramente explicado por H_AGG+H_REF: **NO COMPROBADA**. La referencia usa eventos, recetas y recursos compartidos; M/D entradas rectangulares y pedidos agregados. *Grupo adicional* y *doblar el límite de pedidos/h* no son la misma intervención.

## Diseño mínimo

1. Fuente: mismo artifact `NEXT_ACTION.json` (run 43697007653) y sus dos días CONSTRUCTION; validar SHA de recibo.
2. Cero OMC nuevos: leer `result.json`, `manifest.json` y **CSV real** de M (run 43702148041). D reproduce esa dinámica material bajo los parámetros ensayados, no es una replicación independiente.
3. Ejecutar exclusivamente **cuatro escenarios referencia** (B0/espresso +1 × 2 cargas), con mismo dossier, recetas y pagos. Cada simulación debe reproducir exactamente el conteo y P90 publicados; de lo contrario se aborta sin conclusión.
4. Publicar por carga: bloqueo de espresso por recurso, espera acumulada, ocupación, P90, saturación del agregado y soporte o insuficiencia de cada hipótesis. No atribuir rentabilidad o causalidad externa.

**No** ejecutar nuevos mundos, verdad reservada, G3, reescribir D/M, reconstruir historia o comprar equipos. GitHub Actions calcula; el artifact público sólo conserva diagnósticos agregados, no datos POS por pedido.

El resultado puede ser: “la referencia reduce una cola de recursos mientras M no satura su etapa espresso bajo estos parámetros; el cuello de botella real sigue sin identificarse”. Si la cola no se reduce o falta la saturación postulada, dejar la hipótesis sin apoyo, sin forzar un veredicto.
