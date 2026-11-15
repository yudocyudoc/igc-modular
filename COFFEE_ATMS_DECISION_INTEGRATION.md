# Arena Cafetería — integración ATMS decisional (PR #31, no PR #30)

## Numeración y alcance

En GitHub el **PR #30 ya fue usado y fusionado** para recuperar Buffalo G2 desde CSV sellado. Esta mejora ATMS se abre como **PR #31**, sobre main posterior a #30.

**Decisión de arquitectura:** ATMS no es un predictor ni un selector OR/AND únicamente. El proyecto exige soportes alternativos y mínimos, dependencias contextuales, conflictos explícitos, retractación, restitución, recuperación histórica y explicación. Esta entrega aporta una **proyección decisional ATMS acotada a la referencia de cafetería S5**. **No declara implementado el ATMS canónico completo del plan IGC v1.1**, no sustituye el motor F0 de IGC ni las SQLite del Ledger/ATMS histórico de D/M/B. La integración cruzada definitiva con un único ledger canónico/ontología LinkML es una siguiente fase; evitar dos fuentes de verdad es una condición explícita antes de graduar esta proyección a plataforma.

## Lo que conecta ahora

1. **Antes de ejecutar P11:** `arena/coffee_e2e.py::run_decision` crea un journal ATMS desde el dossier versionado P07 y el protocolo P11 (ambos ya verificables), **antes** de `decision.compare`. Guarda `atms-predecision.json` en el artifact GitHub del job de referencia y su SHA se inscribe en `p11-conditional-summary.json`.
2. **Soporte condicional:** las cuatro premisas de una simulación S5 son fuente de construcción, mismas entradas/recursos, handoff transferible **como hipótesis del modelo**, y apoyo existente **en el dossier asumido**, no personal medido. ATMS deriva `S5_CONDITIONAL_SIMULATABLE`, pero NO `S5_REAL_FEASIBLE` ni `S5_REAL_ECONOMIC_BENEFIT`; las justificaciones exigen información real no presente.
3. **Después del sello y de la evaluación:** `arena/coffee_e2e.py::final_report` exige coincidencia con el SHA del snapshot previo y consume **sólo** agregados P11 y estado de representabilidad D/M/B declarado en el evaluador. Añade una revisión con soporte del beneficio **nominal modelado** cuando exista; preserva que D/M/B no modelan S5 y **no crea** recomendación empresarial. Publica `ATMS_DECISION.json` con snapshot posterior, nuevas revisiones, nodos afectados, huecos de soporte y explicación, como parte del artifact final de GitHub.
4. **Reruns anteriores:** el run del PR #29 no disponía de snapshot ATMS predecisional. El informe retrospectivo anuncia `LEGACY_RUN_NO_PREDECISION_ATMS_NOT_RETROACTIVELY_CLAIMED`, sin inventar que ATMS intervino en la decisión histórica.
5. **Consumo y seguridad:** no se vuelve a descargar truth ni ejecutar D/M/B, OMC, modelos nuevos, proveedores ni mundos para probar este PR. El CI trabaja sólo con fixtures. El workflow principal ya exporta todo el directorio de referencia y del informe: la incorporación del archivo ATMS no requiere un nuevo pipeline ni otro gasto. GitHub es el único entorno para cálculos/pruebas.

## Semántica que sí se implementó

`arena/decision_atms.py` define journal de eventos **append-only**, con identidad, SHA de fuente, ámbito `COFFEE_CONSTRUCTION_DECISION`, tiempo de conocimiento `recorded_at` y tiempo de validez `valid_from` separados. Entradas: supuestos, justificaciones AND, soportes OR, nogoods explícitos por conjuntos de supuestos, retract y restore. Un snapshot `as_known_at / valid_at` recompone etiquetas como antichain de entornos mínimos consistentes (sin falsos soportes por ciclos autofundados). La edición del historial está prohibida; la retirada o restitución produce eventos nuevos. La proyección es recalculada totalmente, no depende de un caché incremental. El SHA histórico usa **el prefijo de eventos visible**, no revisiones futuras.

Límites conservadores: 160 eventos, 24 supuestos, 256 entornos por nodo y 160 rondas de cierre; si se exceden, se lanza `COMBINATORIAL_LIMIT_REACHED` / `FIXPOINT_LIMIT_REACHED`: **no se publica una conclusión completa basada en un resultado truncado**. Esta es una política fail-closed de la vertical mínima, no la semántica final de respuesta parcial del servicio ATMS IGC completo.

Las consultas `snapshot`, `explain` y `what_if` permiten saber qué entornos mínimos sostienen una proposición, qué justificaciones están activas, qué antecedentes faltan y qué nodos cambiarían en una bifurcación efímera por retractación/restauración. `what_if` no modifica el journal canónico ni publica la rama como evidencia. No infieren que dos textos sean contradicciones ni convierten desacuerdos en nogood; se requiere una regla explícita. Tampoco etiquetan un respaldo lógico como verdad del negocio.

## Prueba de retirada, restitución y cortes

`tests/test_decision_atms.py` ejecuta exclusivamente en GitHub:

- dos justificaciones alternativas (A o B) para X, ambas unidas a C para Y;
- nogood explícito B+C: elimina sólo la ruta conflictiva de Y;
- retractar A: Y deja de sostenerse; X sobrevive por B;
- restaurar A: Y vuelve a tener soporte A+C;
- consultar el prefijo histórico antes de la retractación, **sin filtración de revisiones futuras**;
- ciclo sin premisa: no crea soporte espontáneo;
- ámbito distinto de construcción y SHA de procedencia inválido: se rechazan;
- un caso S5 con simulación admisible pero apoyo y rentabilidad reales sin soporte;
- evaluación posterior sellada con ganancia nominal simulada y brazos originales sin S5: **no** aparece ganancia real por deducción;
- falta de snapshot previo o hash alterado: falla cerrado en informes nuevos;
- corrida histórica sin ATMS previo: estado explícito, sin reescribir la historia.

## Criterio de aceptación

Un CI verde acredita sólo **correctitud de la proyección ATMS y del contrato de integración** con datos ficticios. No prueba que ATMS ya sea la memoria canónica transversal de IGC ni que la cafetería gane más dinero. Para graduar la capacidad se requiere después un contrato de persistencia del Ledger canónico, consultas de múltiples fuentes/hipótesis y pruebas de la retractación sobre dependencias reales con permisos y bitemporalidad completos, sin contaminar las vías.

**Próxima acción científica:** preparar una campaña prospectiva donde el mismo ATMS admita y retire soporte de una hipótesis de intervención con nuevas observaciones instrumentadas; comparar el comportamiento posterior de los modelos sin reutilizar la verdad de evaluación como conocimiento previo.
