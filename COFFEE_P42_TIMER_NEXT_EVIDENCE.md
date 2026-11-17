# P42 — Deducción 90/30 y tres episodios de video2 pendientes

## Objetivo

Separar qué explica la simulación por estructura, qué métricas ya están en P39 y cuál es la observación mínima que falta para identificar un ciclo real de la Synesso MVP Hydra.

**No hubo nuevos modelos ni lecturas de R2.** El workflow de P42 reutiliza exclusivamente el artifact P39 original, run 43965403016 / artifact 14275986824. La película y los fotogramas de video2 no están en el ZIP histórico ni en los archivos conectados de este entorno. Por tanto no afirmamos haber revisado visualmente los segmentos.

## El mecanismo del modelo: 90/30

El dossier histórico fija una persona, 30 segundos por preparación manual de cada bebida y 90 segundos de extracción automática por bebida. En el planificador, preparar consume barista y espacio; extraer consume sólo grupo de espresso y termina con liberación automática. Preparaciones del único barista no se superponen. Por tanto sus fines tienen separación mínima de 30 segundos; el cuarto comienzo de extracción no puede ocurrir antes de que el grupo del primer comienzo termine a los 90 segundos.

**90 / 30 = 3 grupos suficientes para absorber el máximo ritmo de preparación de ESTE MODELO.** Leche y entrega pueden demorar la preparación, no acelerarla. El resultado es una consecuencia de las reglas y supuestos, NO una validación de la máquina real.

La reserva conjunta de grupo y barista durante acoplar, retirar y limpiar todavía no está representada; estas tareas carecen de tiempo y posición observados.

## Qué reinterpreta el informe P42 sin nuevas simulaciones

1. Espera cero de extracción con tres grupos; colas de preparación, leche/acabado y entrega conservadas y expresadas en minutos-tarea acumulados.
2. Misma duración total de extracción con ocupación porcentual menor porque se divide entre tres grupos, no porque la extracción se acelere.
3. P90 calculado hasta entregar todos los pedidos, incluidos los entregados después del corte.
4. Explicación de capacidad y ocupación modeladas, sin sugerencias de contratación o compra de máquina.

## Evidencia mínima de video2 que falta

Fuente HD descrita como C:/Users/admin1/Documents/igc-arena/video2/videoplayback.webm; SHA-256 previamente declarado bdf725f004a0d39929a2a0f4fdc6d7d3d066e225cdcb14b81b82384eec34169e. No existe acceso remoto a ese disco.

| ID | Grupo anotado | Ventana base de reloj video | Lectura de timer |
|---|---|---|---|
| TM-T31 | G03 | 12.000–40.011 s | 0→28 s |
| TM-T33 | G03 | 118.012–122.006 s | 28→32 s |
| TM-T12 | G01 | 640.014–668.010 s | 2→30 s |

Para cada segmento, el revisor con acceso al video original ampliará la ventana sólo hasta observar el inicio y final de LA MISMA activación o hasta documentar un extremo censurado. Registrar, o declarar explícitamente desconocido:

- Si es extracción, purga o indeterminada, con la pista visual concreta.
- Inicio y fin de uso del grupo, distinguiendo lo visto de cotas parciales.
- Trabajo manual de cargar, retirar y limpiar y recursos ocupados por cada acción.
- Otros grupos simultáneamente visibles, ocupados, habilitados o fuera de cuadro.
- Si hay trabajo realmente listo esperando mientras todos los grupos están ocupados, o grupos libres mientras el operador realiza otras tareas.

No asociar videos con pedidos sintéticos, no dividir tiempos de tandas por bebida y no usar una lectura final de 28, 30 o 32 segundos como duración total. Sin evidencia visual, conservar desconocido/censurado.

## Condiciones de un siguiente experimento

Cambiar sólo una regla o un tiempo físico cuando la observación alcance para sostenerlo; conservar tres grupos instalados, distinguir disponibilidad simultánea y separación de recursos. Si sólo se obtiene un límite temporal, declararlo como tal y no inventar los extremos. Antes de ejecutar una nueva referencia, formular predicciones rivales y presupuesto explícito. Por ahora, **ninguna nueva ejecución científica está autorizada ni es necesaria**.

La prueba del software y la comprobación de los temporizadores originales ya fueron hechas en P39; P42 es sólo explicación, extracción de métricas archivadas y preparación para revisión visual dirigida.
