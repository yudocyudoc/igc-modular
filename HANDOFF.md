# Relevo: gpt-web coder / Codex-Astra revisor

Repositorio de desarrollo y ejecución: yudocyudoc/igc-modular. La migración y conexión solicitadas expresamente al revisor están implementadas; los cambios ordinarios siguientes los realiza gpt-web en PR y Codex/Astra los revisa.

## Estado útil

- Los motores D/M/B, sus dependencias de código y la evidencia histórica D0/M0 están dentro de este repositorio.
- arena-run.yml ofrece un solo despacho para el recorrido completo en GitHub.
- No hay dependencia operativa de IGC ni sd-ai. Se conservan sus referencias solo como procedencia. Las dependencias estándar/npm se instalan según las versiones fijadas.
- integration usa fixtures y cero consumo. live exige una autorización de lote y conserva 19 OMC nuevos incluido el mundo, dos POST y trece plazas.
- La reserva permanece en R2; el artifact inmutable y el cierre de productores se verifican antes de leerla.
- Los checks de acceso se ejecutan antes de seleccionar el mundo. Un fallo de acceso no es permiso para ejecutar otro experimento ni para crear otro servicio de custodia.
- Se requieren tres valores secretos iniciales en dos entornos, descritos en README. Las credenciales no se volvieron a pedir por etapa ni se fingió su copia desde IGC.
- La conexión de edición disponible no permite escribir Actions secrets; una vez configurados se reutilizan. Un operador puede llevar todo el flujo.

## Siguiente acción

Con las tres credenciales cargadas, seleccionar live/authorized=yes en el workflow y ejecutar el lote si conserva la autorización experimental correspondiente. No añadir otro coordinador ni otra auditoría general. No presentar una corrida de integración como física.

Si aparece un error, localizar el job y su evidencia, corregir solo el defecto reproducible y conservar intentos y cuota. No reiniciar un mundo o proveedor fallido para conseguir un resultado favorable. El evaluador puede volver a operar sobre el mismo lock cerrado sin nueva física.

## Reglas que siguen vigentes

Motores, ecuaciones, solver, bibliotecas, métricas y condiciones científicas originales. No abrir grillas, PM, DES ni otro mundo para eludir resultados. No alterar denominadores, sustituir fallos por ceros ni reparar nativos Buffalo desde Arena. La fuente video2 sigue siendo observación parcial cuando no acredita identidad/continuidad; la migración no cambia esa conclusión.

## Qué entregar

El enlace de ejecución y resultado físico cuando haya ocurrido; consumo real y límites, o el error preciso con su evidencia. Separar fixtures, SDK con transporte mock, ejecución física y validez científica. Mantener los PR acotados y revisables.
