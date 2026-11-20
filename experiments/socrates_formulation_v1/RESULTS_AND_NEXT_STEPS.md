# Sócrates en Arena: evaluación inicial v1 (2026-11-20)

## Pregunta
¿La configuración original de Sócrates (UB-IAD/sd-ai) reconoce antes de construir un modelo las exigencias de representación de un problema empresarial? ¿Cuándo bastaría SD, cuándo se requiere preservar eventos/recursos por entidad y cuándo falta formular la decisión?

## Procedencia y alcance
- Repositorio fuente: `UB-IAD/sd-ai`, commit **`58cfc86c8f2634401534fc89ff856f3f21c90bba`**; `agent/config/socrates.md` blob **`2bada622725411649605b4be3f0bd7c6d3d5da8b`**.
- Configuración de Sócrates: rol **Coach**, `agent_mode: manual`, `supported_modes: [sfd, cld]`; la instrucción prioriza preguntar, establecer límites, stocks, flujos y bucles antes de construir.
- Importante: el motor `engines/quantitative/engine.js::generate` **no es** el agente Sócrates. En Q75 anterior se invocó ese generador, no una sesión Sócrates.
- Prueba ejecutada: instrucciones textuales originales de Sócrates sin cambiar, con `[Model sync]` de diagrama vacío, más mensajes de usuario; modelo `@cf/thinkingmachines/inkling-2-small` por Cloudflare Workers AI. Dos mensajes por escenario; exactamente **seis POST**, una ejecución por mensaje, sin retries; 1 800 tokens máximos de salida por POST, `reasoning_effort: low`. No se solicitaron herramientas.
- **No fue una ejecución nativa completa del `agent/WebSocket.js`, `WorkerSpawner`, SDK de agentes, herramientas de generación, ni del motor de evaluaciones `AgentEvalRunner`.** No se puede generalizar a una prueba autenticada del agente completo o a otros LLM.
- El evaluador oficial incluye instrucciones adicionales `CONVERSATION_MODE_INSTRUCTION`, por lo que su uso tampoco sería idéntico a una sesión limpia: esto debe registrarse en un ensayo futuro.
- Fuente de casos y criterios previo a resultados: `cases_and_protocol.json`.

## Resultados observados

| Escenario | Primer turno | Segundo turno | Interpretación restringida |
|---|---|---|---|
| **Q75**, pregunta de priorización por tarea y P90 por pedido | Dice, sin recibir etiqueta DES: «suena a un problema de eventos discretos o de scheduling, más que a dinámica de sistemas clásica»; pregunta por decisión, definición de latencia, naturaleza sintética, elegibilidad y llegadas | Solicita secuencia de tareas/llegadas/recetas, recursos que compiten por W01, definición de ejecutabilidad y razones para medir P90 | **Señal positiva de reconocimiento del desajuste**, no rechazo formal de modelar ni selección/ejecución de un DES |
| **DYNAMIC**, acumulación, contrataciones retardadas y salida de personal | Pregunta por trabajo pendiente como acumulación y por mecanismo presión → renuncias → menor capacidad → presión; exige decidir política y comportamiento temporal | Investiga horizonte semanal, actores, ausencias, gatillo de contratación y patrones de backlog | **Señal positiva de formulación SD**, pero no llegó a ecuaciones ni comprobación dinámica |
| **VAGUE**, «la cafetería tarda mucho» | Pide precisar qué espera, cuánto y horizonte (hora, día, meses) | Tras especificar espera pospago, pregunta por roles, cola en pico y decisión concreta | **No formula un modelo prematuro**; pregunta por decisión y datos |

Los seis mensajes terminaron con `finish_reason=stop` y `success=true`. Recibos: **25 096 tokens de entrada** (incluyen repeticiones/contexto) y **1 334 de salida**, sin ejecuciones de simuladores ni nuevas lecturas de R2 privado. No se deduce costo monetario ni eficacia científica a partir del conteo de tokens.

## Criterios observables y dictamen

- **Cumple como indicio inicial:** Q75 detecta explícitamente el encuadre eventos discretos/scheduling; busca mecanismos individuales y datos; DYNAMIC sondea acumulaciones/retardos/feedback; VAGUE no se lanza a generar ecuaciones.
- **Pendiente de evaluar:** ¿Sócrates rechazaría constructivamente una petición explícita de cuantificar P90 solo con agregados? ¿Propondría realmente DES o híbrido sin desviarse de sus instrucciones? ¿Podría identificar otros métodos (estadístico, optimización, ecuaciones diferenciales) sin etiquetado previo?
- **No probado:** herramientas reales `generate_quantitative_model`, validación estructural/numérica, observación de acciones de agentes, fiabilidad estadística (n=1 caso por clase), aceptación de modelos en cliente; independencia respecto del LLM subyacente.
- **Nota de alcance:** Sócrates es un tutor SD, no figura como motor universal de elección matemática. Añadir DES antes de concluir que el agente original fracasa confundiría capacidades.

## Próxima prueba diferenciadora (no ejecutada ni autorizada)

1. Ensayar **Sesión Sócrates completa** en el agente original con backend compatible, `agent_mode: manual`, mismo commit y conversación limitada. Registrar texto + solicitudes/efectos reales de herramientas. No utilizar `Engine.generate` directamente como sustituto.
2. Presentar Q75 antes de revelar DES y, después, una petición explícita de obtener P90 con solo agregados: comprobar si da una **abstención por no identificabilidad**, si intenta forzar stock-flow o pide información necesaria.
3. Repetir el contraste con DYNAMIC y VAGUE y, solo si demuestra insuficiencia, crear **una variante Sócrates-DES**, manteniendo la original como control.
4. En la variante hipotética añadir una instrucción mínima: identificar qué mecanismos matemáticos deben preservarse, declarar cuándo un esquema SFD escalar pierde identidad de entidades y recomendar DES/híbrido **sin pretender generar o ejecutar un motor DES que no existe**.
5. Requerir un criterio independiente: reconocimiento de invariantes obligatorios (identidad por pedido, reserva atómica de W01 y barista, secuencia ejecutable), no mera aparición de la palabra «DES».

### Veredicto preliminar

**La hipótesis de que Sócrates puede ayudar a la etapa de formulación de Arena ganó plausibilidad en este ensayo de prompt. No está validada para el agente completo.** No modificar los tres brazos, ni ATMS, ni integrar un gate universal con la evidencia actual. Este experimento permanece en una rama sin PR a `main`.

## Archivos de evidencia

`cases_and_protocol.json`, `Q75_t1.json`, `Q75_t2.json`, `DYNAMIC_t1.json`, `DYNAMIC_t2.json`, `VAGUE_t1.json`, `VAGUE_t2.json`. Cada archivo guarda texto del usuario, respuesta, metadatos de la llamada, uso reportado y ausencia de reintentos.
