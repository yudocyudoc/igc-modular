# Colaboración

## Roles acordados con el usuario

- **gpt-web: coder.** Implementa las funcionalidades y correcciones en ramas/PR de este repositorio.
- **Codex/Astra: revisor.** Revisa implementación, evidencia, resultados, consumo y fidelidad al protocolo. No toma el desarrollo ordinario ni duplica la implementación, salvo petición expresa del usuario. La publicación inicial y la migración/conexión nativa de motores fueron solicitadas expresamente. Tras esa entrega se retoma el rol de revisor.
- **Usuario:** prioridades y autorización de consumo experimental. La autorización de un lote no se vuelve a pedir entre sus etapas.

## Prioridad de producto

Conseguir una ejecución física completa en GitHub, mediante una entrada única, con resultados y consumo visibles. El CI con fixtures comprueba integración del software; no demuestra ejecución física ni eficacia científica.

## Reglas de implementación

1. Mantener módulos separados para protocolos, datos, motores, ejecución, conexiones, estado/consumo e informes. Añadir un protocolo o backend mediante sus adaptadores, sin incorporar condiciones particulares al coordinador común.
2. Conservar los motores y métodos originales. No editar `arena/_vendor/` para hacer pasar una prueba ni regenerar su manifiesto para esconder deriva. Documentar cualquier actualización de origen con su commit y comprobaciones pertinentes.
3. Admitir observaciones parciales conservando intervalos, censura y ausencia de identidad. La aptitud para una pregunta se decide por separado. No inventar pedidos, continuidad, tiempos de servicio ni números ausentes.
4. Reutilizar conexiones y secretos existentes. No pedir su recreación ni introducir nuevos environments por experimento sin necesidad técnica demostrada. No guardar valores en Git, artifacts, argv, informes o chat.
5. Ejecutar en GitHub Actions. La bóveda local del sistema operativo es opcional; no convertirla en requisito del runner de GitHub. Conservar la separación de datos entre custodio, productores y evaluador mediante los jobs/adaptadores adecuados; una misma persona puede operar todo.
6. Mostrar intentos, fallos y cuota restante. Si falta evidencia, marcar consumo desconocido o incompleto; no declarar cero. Un intento fallido puede consumir presupuesto.
7. Mantener el lock anterior a abrir la reserva. No introducir firmas RSA, archivistas externos, nuevos servicios de bóveda o autorizaciones entre etapas para este piloto.
8. No reintentar automáticamente proveedor o solver ni repetir un despacho incierto. Seguir una ejecución con ID confirmado está permitido y no consume otro experimento.
9. No abrir grillas, PM, DES, nuevos mundos ni experimentos para sortear un resultado negativo. La migración de software no autoriza nuevo gasto experimental.
10. Validar con `python -m unittest discover -s tests -v` y el recorrido de integración de `examples/smoke.toml`. Escoger comprobaciones proporcionadas a cada cambio; las pruebas existentes aprobadas no justifican auditorías generales repetidas.

## Entrega de un PR

Indicar qué comportamiento cambia, cómo reproducirlo, validación ejecutada y consumo real. Separar explícitamente fixtures, API simulada y ejecución física. El siguiente paso debe resolver un bloqueo concreto o aportar evidencia, no añadir otra capa de certificados.
