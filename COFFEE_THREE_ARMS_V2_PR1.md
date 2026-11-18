# Arena IGC Cafetería — Plan v2 — PR1 auténtico

**Ámbito:** entrega 1 del plan de tres brazos v2; reconstrucción RETROSPECTIVA de la gramática D, moléculas M, Buffalo y referencia Hydra. No es un nuevo experimento ciego ni una ejecución de modelos.

## Pregunta común H1/H2/H3

En una oportunidad de carga, ¿qué distingue: **H1** (todos los grupos utilizables extrayendo), **H2** (grupo libre pero sin persona apta disponible) y **H3** (grupo retenido después de extracción, pendiente de retirada)? Los estados pueden coexistir en grupos distintos. Para atribuir H3 a la espera de una bebida hay que descartar otros grupos utilizables; un timer detenido no verifica retirada.

La pregunta no fue planteada retrospectivamente a los productores históricos. La interpretación H1/H2/H3 pertenece al evaluador; no representa una nueva disposición D/M/B.

## Archivos y reconstrucción auténtica

El lector `arena/coffee_three_arms_readback_v2.py` consume ocho ZIP **públicos** originales de GitHub Actions, fijados por run, artifact, SHA de commit y SHA-256 de los bytes ZIP. Rechaza archivos manipulados antes de leer modelos. Publica un informe Markdown y JSON:

- `experiments/coffee_three_arms_v2/THREE_ARMS_V2_DECISION.md`
- `experiments/coffee_three_arms_v2/THREE_ARMS_V2_READBACK.json`

El primer run de CI vuelve a descargar los ocho ZIP desde GitHub, ejecuta las regresiones y exige que ambos informes sean **idénticos byte por byte** a los archivos versionados. Publica un artefacto con MD/JSON legibles. No funciona exclusivamente con fixtures.

**D/M originales B0:** seis candidatos por brazo, 12 CSV auténticos, modelos D y AST/Modelica M, diagnósticos G2, disposición individual y proyección de Ledger/ATMS. D ratifica seis; M se abstiene seis veces por no tener dos observaciones de retiro tardías. La abstención se refiere a **revisión**, no a generación o simulación.

**Buffalo:** modelo original B0, paquete de feedback inicial NO ENVIADO, luego revisión auténtica R1 mediante currentModel en ejecución distinta; se verifican SHA padre/hijo, diagnóstico G1, modelo modificado y resultado del CSV sellado en B0 sintético. No equivale a evidencia sobre trabajadores reales.

**D/M P08:** extensiones versionadas y seis simulaciones históricas por brazo. Las moléculas usan AcceptedSource, BoundedQueue y DeliveryCounter. Capacidades 12/15/100 pedidos/h y pulso rectangular compartido. La concordancia numérica **no son dos confirmaciones empíricas independientes**. No representan grupos físicos y trabajo manual compartido.

**Hydra Q75:** 46 pagos, 53 bebidas, extracción automática 90s no calibrada, 4 políticas. Se reproducen los efectos P90, las señales de extracción ocupada y carga manual bloqueada. Retención del grupo tras timer terminando es una propiedad del simulador físico; no se atribuyen minutos reales de H3 observados.

## Corrección metodológica tras la auditoría de alcance

**No se ha probado la capacidad máxima de los métodos.** PR1 examinó nativos históricos, no ejecutó una nueva búsqueda D, catálogo molecular alternativo ni llamada nueva a Cloudflare Buffalo. Los códigos de la matriz `NOT_ENCODED_IN_ARCHIVED_NATIVE` describen exclusivamente las variables y estados de esos modelos archivados, no establecen `METHOD_CANNOT_MODEL_H123`. Cada fila añade `full_method_H123_capacity_tested=false` y el JSON publica `coverage_audit`.

La gramática D original B0 usó las primitivas deterministas de `generic-conservative-chain-search/0.1`, una familia restringida de 1–3 stocks en cadena con/sin pérdida. El adaptador de cafetería evitó llamar `generate()` porque ese contrato exige observaciones de entregas que no estaban disponibles. Su buen error de predicción en retiros agregados sintéticos no demuestra identificación de causas físicas.

M original B0 usó **cuatro clases** de E0: `accepted-source`, `bounded-queue`, `delivery-counter` y `first-order-report-filter`, en **seis composiciones** restringidas por `registry.coffee.v1.json`; las diferencias opcionales fueron tránsito y filtrado de señal. M P08 usó **una topología** de `AcceptedSource`, tres `BoundedQueue` y `DeliveryCounter` en **seis combinaciones de carga/parámetro**, no seis nuevas estructuras. No se inspeccionaron otros catálogos, moléculas Vensim `.mdl` ni todas las posibles composiciones para H1/H2/H3. Una cola continua no contiene por sí misma asignación a un operador o grupo.

El Buffalo archivado es B0 original y revisión R1 con `currentModel`, dos ejecuciones auténticas anteriores que no se repitieron en PR1. El modelo R1 expresa pedidos pagados, espera y retiros acumulados (11 variables, 12 relaciones) sin identificación individual de baristas, grupos y fases de retirada. Eso **no prueba que Buffalo sea incapaz de generar otro modelo** ante evidencia y consigna H1/H2/H3.

El siguiente experimento de cobertura tendría que formular la nueva pregunta a los métodos completos, declarar bibliotecas y familias candidatas, comprobar representabilidad y después, si está autorizado, ejecutar nuevas propuestas y revisiones. Ese trabajo queda fuera de PR1 y requiere presupuesto/autoridad independiente.

## Conclusiones operativas

**Hydra sola:** no cambiar política; observar una única oportunidad de carga con estado simultáneo G01/G02/G03, elegibilidad de tarea, operador apto, extracción y retirada.

**Hydra más D/M/B:** mismo curso de acción; aportación representacional real de capacidades agregadas y comportamiento de revisión, pero **no hay una observación adicional H1/H2/H3 demostrada** por los productores históricos. La primera lectura es no ciega. El valor decisional permanece **PENDIENTE DE CONTRASTE PROSPECTIVO INDEPENDIENTE**.

El JSON separa casos **B0, P08 y Q75**, métodos y versiones, así como dependencias compartidas. Se prohíbe restar flujos continuos P08 contra entregas discretas o P90 Hydra. Un buen MAE de retiros acumulados sintéticos no verifica el mecanismo de carga; no se selecciona un ganador a posteriori.

## Seguridad y siguientes fases

La ejecución CI usa únicamente permisos de lectura de contenidos y Actions. **0 POST de proveedor; 0 OMC nuevo; 0 GET privado R2; 0 nuevos mundos.** No se ha ejecutado en PR1 una consulta ATMS transversal ni un experimento real. PR2 incorporará la pregunta común, diagnóstico y feedback propio por productor, con prueba de retirar soporte individual y premisa compartida. Cualquier gasto o acceso privado tendrá presupuesto y autorización separados.

PR47/E1 conserva su autorización independiente; el resultado privado Q75 a 30s no se supone disponible en esta reconstrucción.

**Revisión Astra solicitada:** integridad de 8 artefactos; comparación no ciega; 12 padres y 13 puntuaciones públicas; etiquetas de versión; H1/H2/H3 como interpretación no atribuida al productor; dependencia común D/M; informe Markdown/JSON reproducible. Veredicto THREE_ARMS_V2_PR1_ACCEPT o THREE_ARMS_V2_PR1_FIX.
