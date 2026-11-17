# P44 — Entrega B: modelo físico versionado para revisión conjunta con A

**Propósito:** Representar recursos y ocupación que el modelo histórico P06/P39 no podía expresar. Este PR se basa en la rama de PR43 A; NO sustituye ni fusiona el modelo histórico. La decisión de preparación, leche o entrega pertenece a C/D y sigue pendiente.

## B1 — Ciclo del grupo

La ruta de una bebida se modela explícitamente:

prepare fuera del grupo (actor + puesto) → load (actor + grupo, adquisición atómica) → extract_auto (mismo grupo, actor liberado) → AWAITING_REMOVAL (contador final pero grupo retenido) → remove (actor + grupo retenido) → clean opcional (actor + grupo retenido) → FREE → milk si corresponde → handoff tras terminar todas las bebidas.

El grupo conserva su ID G01/G02/G03 en todos los estados, se mantiene reservado en la espera de retirada y sólo queda libre al terminar la acción de retirada o limpieza opcional. El escenario base NO impone limpieza tras cada bebida; una opción explícita permite probarla como supuesto. La carga no puede reservar sólo el grupo mientras espera actor.

## B2 — B01 y B02 sin inventar calendarios

Los actores B01/B02 y los puestos puesto_izquierdo/puesto_derecho son recursos exclusivos y distinguibles. La actividad observada de dos operadores está limitada a muestras puntuales: el modelo admite esas concurrencias, pero NO afirma que las personas trabajen permanentemente en ese horario ni que posean todas las aptitudes. Ventanas de disponibilidad 0–240 minutos y lista de aptitudes del dossier son supuestos visibles y modificables. Un operador fuera de su ventana o no apto no puede tomar esa etapa; tampoco puede trabajar en dos tareas a la vez.

Los grupos instalados son tres. Su habilitación continua simultánea es un supuesto de escenario, no una observación. Vapor (W01) y pase (PASS01) también tienen exclusividad explícita y número declarado, no equipos nuevos inferidos.

## B3 — Precedencia contra política

La secuencia de una bebida es conservadora; permite trabajo automático y manual de bebidas DIFERENTES en paralelo si los recursos lo admiten. La precedencia de leche tras liberar el grupo se declara como supuesto y NO se infiere de una vinculación por ticket real del video. El despacho B es exclusivamente FCFS_READY_ASSUMED; las políticas alternativas de preparación, leche y entrega aún no se implementan. Instrumentar causas de espera corresponde a C.

## B4 — Ruta histórica intacta

El módulo B es arena/coffee_v2_hydra_physical_b.py, nuevo motor de evento con estados explícitos y grupo persistente: la diferencia de estructura frente al motor anterior es intencional, identificable y NO una modificación silenciosa. Reutiliza las funciones públicas de entrada POS synthetic paid_gate, validador numérico y percentil de arena/coffee_v2_reference.py. El motor previo, su dossier original y tests permanecen sin modificar.

Dossier B: experiments/coffee_v2/HYDRA_TWO_OPERATORS_PHYSICAL_B_ASSUMPTIONS.json. Los tiempos son TODOS ASSUMED_NOT_CALIBRATED; los 90 s automáticos continúan como ejemplo histórico, nunca como estimación basada en T31/T33/T12. La parada del contador NO mide la liberación física. No se fuerza tiempo 0 para etapas manuales desconocidas.

El puente A3 llama a evaluate_cases con capacidades derivadas del motor B; se espera que las muestras de dos trabajadores sean representables y que exista un estado posterior al contador. Esa factibilidad NO es validación independiente, pues las muestras motivaron el diseño. No se enlazan pedidos sintéticos al video.

## Casos de aceptación y alcance

Los tests sintéticos deben demostrar: carga conjunta y exclusiva; dos trabajadores y dos puestos simultáneos, pero no dos trabajadores en un solo puesto; tiempo después del contador con grupo todavía ocupado; limpieza opcional; mismo grupo hasta la liberación; trabajo manual y automático en paralelo de bebidas diferentes; aptitud y disponibilidad declaradas; etapa leche después de liberar grupo; no publicar IDs de pedidos en informes agregados; resultados históricos reproducibles por la ruta anterior. Las pruebas regresivas P06/P39/P42 y A3 se ejecutan junto a las nuevas.

El workflow de PR sólo ejecuta pruebas minúsculas inventadas y comprobaciones de representabilidad de los episodios previamente revisados. No ejecuta Q25/Q75, OMC, proveedor, R2 ni una comparación científica de políticas. Imágenes/filas completas del video no se publican.

**Para Astra:** verificar invariancia real de reserva de grupo tras fin de extracción, adquisición atómica load, roles/puestos/calendario, consistencia de capacidades descritas vs motor, regresión histórica y límites de inferencia. Revisar A (PR43) y B (PR44) juntos antes de fusionar; C/D fuera del alcance.
