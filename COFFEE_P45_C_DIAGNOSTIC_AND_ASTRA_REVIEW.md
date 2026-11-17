# PR45 — Entrega C: diagnóstico causal de esperas (revisión conjunta con B)

**Plan rector:** PLAN_GPT_WEB_ARENA_DECISION_OPERATIVA_Y_CALIBRACION_2026-11-17, §6. **Alcance:** C de software y construcción; no D ni estudio del local real. **Base apilada:** PR44 B, basado en PR43 A3. **Revisor independiente solicitado:** Astra, con cierre conjunto B + C.

## Qué se agregó

1. **Instrumentación sin cambiar FCFS:** el motor físico B emite en su traza PRIVADA eventos pending_precedence, eligible, start, finish y blocked_interval. El instante de elegibilidad es el cumplimiento de la precedencia: antes de ese instante no hay espera de recursos. La duración del bloqueo se segmenta entre eventos del mismo motor y se cierra al inicio efectivo de la tarea.
2. **Bloqueadores simultáneos, sin falsa exclusividad:** cuando una tarea elegible no puede empezar, se enumeran alternativas de asignación (actor apto + recurso complementario) y los bloqueos de cada una: operador ocupado, calendario insuficiente, puesto, grupo ocupado con estado de ciclo, vapor o pase. Varios bloqueadores pueden coexistir. No se añade dos veces el mismo intervalo a la espera total de una tarea ni se asigna como causalidad exclusiva a cada actor/máquina.
3. **Estados de grupo:** para la carga, EXTRACTING se distingue de AWAITING_REMOVAL, REMOVING, limpieza y carga. Un grupo retenido después del contador NO demuestra tiempo de extracción automática.
4. **Informe de mecanismos condicionales:** arena/coffee_v2_hydra_causes_c.py verifica la partición de esperas y agrega por etapa, señales de presión, patrones de bloqueos y vínculo con la comparación A/B. El P90 sigue viniendo del motor físico y NO de sumar esperas por etapa. La ruta histórica P06/P39/P42 y las políticas no cambian.
5. **Fuente y condición:** tres pedidos **inventados** en C_FIXED_TOY_PAID_INPUT.json ejercen solamente la ruta de software. El reporte no los presenta como pedidos, ventas ni mediciones del video. A3 procede de episodios ya conocidos, no de reserva nueva.

## Interpretación por hipótesis del §6

| Hipótesis | Señal concreta en el modelo | Lectura permitida |
|---|---|---|
| Extracción limita | Carga elegible y todos los grupos habilitados en EXTRACTING, con al menos una ruta de actor disponible | Presión de ocupación por extracción en el escenario; no causalidad empírica |
| Preparación/carga limita | Tarea prepare o load elegible bloqueada por las rutas declaradas | Espera de recursos condicional, distinta de precedencia pendiente |
| Leche/entrega limita | Tarea milk/handoff elegible bloqueada por operador, vapor o pase | Señal de espera, NO efecto de cambiar su política; eso es D |
| Cuello por artefacto | Contrato histórico A3 CONTRADICTED frente a B COMPATIBLE | Diferencia de representabilidad, NO causa empírica de espera |

Los patrones son **alternativas de asignación bloqueadas**, no causas exclusivas. Las duraciones por etapa son task-minutes y pueden solaparse para tareas distintas. Las razones de presencia NO son aditivas ni sumables para producir P90.

## Verificación requerida

- La traza no imputa espera antes de elegibilidad; los intervalos bloqueados cubren el tiempo elegible→inicio, sin huecos.
- Los negativos de Astra para B (B02 sin habilidad prepare; B01 [0,20] vs B02 [21,240]) siguen rechazados; el positivo permanece factible estructuralmente, pero INDETERMINATE sobre un instante sin relojes alineados.
- El grupo no se libera al parar el contador; AWAITING_REMOVAL se identifica separadamente.
- Los casos de un grupo ocupado y dos bloqueadores preservan alternativas. No convertir una misma espera en ahorro exclusivo por actor y por grupo.
- Los resultados B y la ruta histórica se preservan; la traza no cambia la política ni entregas.
- C muestra mecanismo, magnitud y supuestos sin inferir turnos desde video ni declarar política ganadora.
- CI offline: sin OMC, R2, proveedor, nuevo video, Q25/Q75 o campaña científica.

## Archivos

- arena/coffee_v2_hydra_physical_b.py — instrumentación privada y STAGE_PREDECESSOR.
- arena/coffee_v2_hydra_causes_c.py — partición, diagnóstico, JSON/MD agregado.
- experiments/coffee_v2/C_FIXED_TOY_PAID_INPUT.json — microfixture ficticio.
- tests/test_coffee_v2_hydra_causes_c.py — regresiones.
- .github/workflows/coffee-hydra-p45-c.yml — CI offline y archivo agregado.

## Pedido concreto a Astra: cierre B y revisión C

**B, PR44:** reexaminar la corrección HEAD c850926e: aptitudes y ventanas compartidas entre planificador/evaluador, calendarios disjuntos y sin prepare, distinción factibilidad estructural / instante de video; comprobar exclusividad del grupo y decidir cierre formal.

**C, PR45:** inspeccionar instrumentación en el planificador B y agregador C; buscar falsa atribución exclusiva ante múltiples bloqueadores, huecos temporales, discrepancias de reloj, confusión extracción/retirada, clasificación causal demasiado fuerte, fugas de identificadores y cambios encubiertos de FCFS. Repetir o añadir contraejemplos. CI verde verifica software, no la cafetería real.

**Dictamen solicitado:** B_ACCEPT/B_FIX y C_ACCEPT/C_FIX por separado, con SHA, pruebas y límites. Si hay defectos, proporcionar el caso mínimo reproducible. No fusionar PR43/44/45 por su CI; no iniciar D hasta diseñar y autorizar la comparación de políticas con entradas y costos idénticos.
