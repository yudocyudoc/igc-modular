# Relevo a gpt-web: implementación en GitHub

El usuario acordó que **gpt-web sea coder y Codex/Astra revisor**, por costes. El repositorio de desarrollo es `yudocyudoc/igc-modular`. La plataforma de ejecución es GitHub Actions. Esta publicación inicial entrega la extracción modular y su integración offline; no afirma que CT-03 físico se haya ejecutado aquí.

## Punto de partida comprobado

- Origen: `yudocyudoc/IGC`, PR #172, corte `881f92792e4a67de0eb33a04662089029c0e6918`.
- 39 fuentes/recursos originales conservados, con manifiesto; generadores D/M originales, contratos públicos, lock y evaluador reutilizados.
- 32 pruebas locales aprobadas; wheel construido e integración completada desde el paquete instalado.
- El CI de este repositorio ejecuta integración en Linux/Windows y Python 3.11/3.13. Publica `result.json` y `report.md`; no necesita secretos y consume cero OMC/Buffalo.
- La integración usa fixtures explícitos: trece plazas, dos pares de prueba, once plazas sin par. No es un resultado científico.
- El backend `github` encadena los cuatro workflows físicos existentes en **IGC**. Sus nombres, rama y SHA están limitados al adaptador CT-03; todavía no constituye un ejecutor físico independiente dentro de igc-modular.
- No se han movido secretos entre repositorios ni seleccionado un nuevo mundo. La bóveda Windows está implementada y se comprobó una lectura de entrada inexistente; no se migraron credenciales reales.
- El enlace por API reutiliza secretos existentes y configura solo enlaces faltantes. Las escrituras y el transporte se probaron con dobles; el cifrado opcional PyNaCl y una subida real de secretos no se ejecutaron en el entorno local.

## Próxima entrega del coder

Un recorrido físico operable desde GitHub mediante **un único despacho**, que prepare los datos, ejecute los productores originales, cierre predicciones y entregue evaluación e informe de consumo. Reutilizar el código existente mediante adaptadores; no reescribir los métodos científicos ni copiar toda la secuencia de PR #172.

1. Confirmar la CI de esta publicación. Corregir únicamente fallos reproducibles que impidan su ejecución.
2. Decidir dentro del PR cómo ejecutar las etapas físicas desde Actions usando los adaptadores. El coordinador debe resolver IDs y transferencias; el usuario no debe copiarlos ni administrar aprobaciones entre etapas. La política de custodia queda dentro del adaptador, con jobs separados cuando se necesite aislamiento de datos.
3. Mantener las conexiones fuera de los experimentos. Usar primero los secretos y rutas ya probados de IGC; el puente existente permite conservarlos durante la transición. Si se porta el ejecutor al nuevo repositorio, automatizar una vinculación inicial y acreditar exactamente qué acceso falta, sin pedir recrear Buffalo ni tratar la ausencia de una copia local como ausencia del secreto en GitHub.
4. La configuración y comprobación de accesos debe completarse antes de consumir solver/proveedor. No ejecutar OMC para comprobar un secreto ni utilizar inferencia pagada como prueba de autenticación.
5. Validar primero el recorrido completo de integración y sus fallos relevantes. Después, con la autorización experimental vigente, ejecutar el lote físico y conservar comandos, fuentes, resultados y logs. No declarar completada la migración física con mocks o CI offline.

No hace falta otra auditoría general antes de implementar. Los cambios del coder se entregan en PR para revisión concreta de Codex/Astra.

## Condiciones científicas que conserva CT-03

- Máximo de **19 OMC nuevos, incluido el único mundo**, y **2 POST Buffalo**; los dos OMC técnicos CT-02 ya ejecutados no se repiten.
- Trece plazas: seis D, seis M y una B. Conservar ausencias y fallos en el denominador.
- Productores: datos comunes t0/t1/t2/t4, modelos propios y feedback propio. Evaluador: reserva t6/t8 después del lock archivado.
- Buffalo conserva `UB-IAD/sd-ai::Engine.generate` y la ruta Workers AI ya probada. No reparar sus modelos desde Arena ni introducir otro motor.
- Conservar ecuaciones, solver, bibliotecas, métricas y reglas de parada fijadas. La modularización no concede G2/G3 ni modifica condiciones de activación.
- Si ya existe un intake o productor real, continuar su evidencia; no seleccionar otro mundo ni crear otro lote para superar un bloqueo de software.

## Resultado exigible al siguiente PR

Un comando o despacho reproducible; integración completa en GitHub; evidencia física cuando haya autorización y acceso efectivos; informe de consumo; errores accionables; ninguna gestión manual de IDs entre etapas. Mantener explícitos los límites pendientes y distinguir ejecución remota real de transporte simulado.
