# IGC Arena modular

Motores D/M/B y ejecución consolidada en GitHub. gpt-web implementa y Codex/Astra revisa. La migración y conexión inicial fueron solicitadas expresamente por el usuario; los siguientes cambios ordinarios corresponden al coder.

## Ejecutar en GitHub

Abrir [Arena native — one end-to-end run](https://github.com/yudocyudoc/igc-modular/actions/workflows/arena-run.yml) y pulsar **Run workflow**.

- **integration**: recorre importación, preparación D/M, salidas de prueba, lock y evaluación con fixtures. No necesita secretos y consume cero OMC/Buffalo. También se ejecuta automáticamente ante cambios de código.
- **live** y **authorized=yes**: autoriza una vez el lote CT-03 completo, con máximos fijos de 19 OMC nuevos y dos POST Buffalo. El SHA se congela automáticamente; el campo freeze_sha permite exigir uno específico.

Las etapas transportan archivos e IDs automáticamente. Una misma persona puede operar el experimento. No hay aprobaciones intermedias, firmas RSA ni servidores de custodia adicionales.

## Configuración inicial, una vez

En [Settings → Environments](https://github.com/yudocyudoc/igc-modular/settings/environments), cargar:

| Entorno reutilizable | Secreto | Acceso |
| --- | --- | --- |
| arena-provider | CLOUDFLARE_API_TOKEN | Workers AI Edit; sin R2 |
| arena-custodian | CT03_R2_ACCESS_KEY_ID | Conexión S3 del bucket privado |
| arena-custodian | CT03_R2_SECRET_ACCESS_KEY | Mismo acceso S3 |

La cuenta y el bucket existentes están preconfigurados como identificadores públicos en arena/resources/connections.json. No se necesitan nuevas variables de aprobación, tokens administrativos durante la corrida ni una sesión gh local para usar el botón de GitHub.

Los secretos de IGC no se pueden leer y copiar por API. Si se necesitan credenciales nuevas, se generan y cargan una vez. No se guardan en Git ni se envían por chat. El enlace opcional por API conserva las entradas ya existentes y configura únicamente las faltantes.

## Buffalo-only: diagnóstico independiente, sin alterar CT03

[Buffalo-only (1 POST)](https://github.com/yudocyudoc/igc-modular/actions/workflows/buffalo-only.yml) es un workflow **exclusivamente manual**, separado del lote cerrado CT03. Después de incorporar el PR, seleccionar la rama `main`, pulsar **Run workflow** y elegir `authorized=yes` una sola vez. No hay push/PR-trigger, reintentos, ejecución automática de D/M/OMC, nuevo custodio ni nuevo mundo.

Reutiliza **únicamente** el artefacto público `native-public-42455527897` (artifact ID 13607441674) del [CT03 cerrado](https://github.com/yudocyudoc/igc-modular/actions/runs/42455527897). Revalida procedencia, estado cerrado, identidad, y los tres archivos públicos antes de preparar la llamada. La generación utiliza `UB-IAD/sd-ai::Engine.generate` y el adaptador Cloudflare original, con **16,000 tokens máximos**, `reasoning_effort=low`, un solo POST y sin revisión `currentModel`. Usa únicamente `arena-provider/CLOUDFLARE_API_TOKEN`.

Archiva `provider-raw.json` cuando exista, `receipt.json`, uso de tokens si fue informado, evidencia de intento previo al POST, hash de solicitud, salida de motor y `result.json`, incluso ante `NO_NATIVE`. Una respuesta ausente se informa como **consumo desconocido**, nunca como cero supuesto. La ejecución no actualiza `arena-run.yml`, el lock, el score ni el denominador de 13 plazas del CT03. **0 OMC y 0 mundos nuevos.**

La compuerta de único POST **no rechaza por el mero hecho de que exista otro despacho manual**. Si se demuestra mediante los jobs y pasos de GitHub Actions que un despacho anterior fue omitido (`authorized=no`) o terminó antes de comenzar el paso de Node, puede admitirse la primera llamada real. Si el paso pagado comenzó, no está claro si llegó a comenzar, el histórico es incompleto o hubo un rerun, **se bloquea**. No se permite el reintento automático ni un segundo POST tras consumo real o incierto.

El ZIP original del CT03 mostró `message.content` vacío y `finish_reason=length` con **16,000 tokens de salida** y razonamiento separado: la generación agotó el límite sin producir el contenido de un modelo. Esto **no demuestra** que aumentar el límite resuelva el problema; la prueba aislada mantiene exactamente los 16,000 tokens originales.

## Buffalo-adjust v1 — BF-00/BF-01/BF-02 sin gasto

Se conserva **el mismo workflow** [Buffalo-only](https://github.com/yudocyudoc/igc-modular/actions/workflows/buffalo-only.yml), con un selector `mode`: `original` conserva el diagnóstico histórico de un solo POST ya utilizado; `adjust-check` ejecuta **únicamente** la preparación offline; `adjust-live` es el nuevo lote manual BF-03→BF-04→BF-05. Ninguna fase pagada se inicia desde push o PR. La autorización `adjust-live` es independiente del CT03 cerrado.

El modo `adjust-check` descarga los tres archivos públicos del CT03 cerrado y las dos respuestas originales archivadas, verifica hashes SHA-256 de seis archivos históricos y construye un solo artifact `buffalo-adjust-v1-offline-<run>` con diagnósticos BF-00, vista separada de unidades BF-01, perfil BF-02 y feedback propio. **No modifica archivos del motor, su prompt original, fuentes originales, lock ni puntuaciones CT03.** Tampoco usa secretos de Cloudflare, R2, D/M ni OMC.

El diagnóstico real reproduce el ciclo autorreferente de `input rate profile`, las tablas incompatibles en stocks/flows, el lookup aplicado a `mean flow time = 2.8` que produce 0, y el perfil lineal de masa 3.315 frente a 3.4 reales. La vista `hours → hour` es un alias de escala 1, no una reparación de ecuaciones. El perfil `buffalo-adjust-v1` se conserva con hash de bytes y no presupone un número de etapas ni parámetros del mundo.

**Capacidad BF-01 corregida (F5-01):** las instrucciones originales permiten el operador de división segura `//`, incluso cuando prohíben `IF THEN ELSE`. La expresión expandida `Z(x) = MAX(0,x) // MAX(0,x)` permite construir el pulso público exacto en `[0,2)`. Una regresión con nueve valores racionales y el **traductor Modelica original** verifica la representación, sin simular ni prescribir un modelo a Buffalo. **Límite explícito:** el exportador XMILE original sustituye `//` por `/`; no se ha demostrado equivalencia XMILE/PySD. La compatibilidad establecida es **estática nativo→Modelica**, no G2 físico ni equivalencia general de motor.

**Correcciones BF-00 (F5-02/F5-03):** las ecuaciones se validan con la gramática del traductor original, incluidos `MAX` y `//`. Una tabla auxiliar con entrada constante puede ser válida: se registra como aviso. Se rechaza específicamente el **lookup cuyo valor efectivo es cero y aparece como divisor ordinario `/`**, indicando la variable y la ecuación. No se modifica ninguna salida nativa. BF-01 archiva **dos archivos independientes**: `bf01-unit-manifest.json` con hashes/rutas y `bf01-normalized-native.json` con el nativo completo y solo los alias de unidad permitidos.

**Compuerta de gasto:** BF-03/BF-04/BF-05 ya tienen una ruta operativa independiente, pero **no se ejecutan sin `mode=adjust-live`, `authorized=yes` y `main`**, tras revisión/fusión. El modo `adjust-check` sigue consumiendo 0 POST y 0 OMC. El perfil BF-02 se vuelve a congelar con las capacidades corregidas, sin alterar `_vendor`. No se simula el nativo defectuoso ni se repara desde código para hacerlo pasar.

**Lote implementado (pendiente de revisar y fusionar este PR):** BF-03 realiza una sola revisión mediante el `Engine.generate` original con `currentModel` del artifact Buffalo-only y diagnóstico propio. Si falla o no supera G1, se detiene sin BF-04. BF-04 realiza una generación inicial independiente, sin padre y con **el mismo perfil congelado**, máximo un POST. Si supera G1, BF-05 ejecuta una sola simulación OMC de **ese candidato** con imagen/bibliotecas fijadas, Euler h=0.125, t0..8, sin usar verdad t6/t8. Máximo **2 POST + 1 OMC**, 0 DES, 0 D/M, 0 custodio, 0 mundos y ninguna reejecución. La antigua llamada Buffalo-only permanece consumida y separada. Los intentos se registran **antes** de conectar al proveedor o ejecutar OMC; un timeout no equivale a consumo cero.

**Salida:** un solo artifact `buffalo-adjust-v1-live-<run>` con el perfil, hash de padre, solicitudes efectivas, respuestas crudas cuando existan, uso de tokens reportado, nativos originales BF-03/BF-04 sin reparar, diagnósticos G1, transformación exclusivamente de unidades, fuente Modelica, script/CSV/logs OMC y resultado físico. G2 comprueba conservación material (residuo absoluto máx. 1e-9 items), no negatividad, monotonicidad de entregas, masa de entrada 3.4 y residuos de las cuatro observaciones públicas; **no** elige parámetros después de ver el CSV. t6/t8 son predicciones del modelo, no verdad reservada. No se afirma equivalencia con XMILE/PySD ni se incorpora al CT03.

**Una vez revisado e incorporado:** abrir [Arena diagnostic - buffalo-only one POST](https://github.com/yudocyudoc/igc-modular/actions/workflows/buffalo-only.yml) en Actions, rama `main`, `mode=adjust-live` y `authorized=yes`, y pulsar Run workflow **una sola vez**. Se continúa automáticamente entre fases si las compuertas pasan; si una falla, las etapas restantes no se intentan. `mode=adjust-check` continúa siendo la alternativa de cero consumo.

## Motores dentro de este repositorio

- **D**: generador original, seis alternativas, validación física y feedback propio.
- **M**: Short E1, compositor/backend, catálogo, moléculas, seis AST, política M2 y sus revisiones.
- **B**: Buffalo original Engine.generate, dependencias fijadas y ruta OpenRouter SDK → Cloudflare Workers AI ya probada.

arena/_vendor conserva las fuentes y los recursos necesarios, incluida la evidencia histórica D0/M0. El código no clona IGC ni sd-ai ni descarga sus artifacts durante una corrida. El origen histórico queda documentado, y Buffalo mantiene su licencia MIT.

Las bibliotecas estándar Modelica/SystemDynamics y la imagen OMC siguen fijadas. La migración no cambia ecuaciones, prompts, políticas, métricas o cuotas y no repite los dos OMC de CT-02.

## Arquitectura

| Módulo | Responsabilidad |
| --- | --- |
| protocols | Registro y condiciones de cada protocolo |
| data | Importación, capacidades, intervalos y censura |
| engines / runtime | Adaptadores D/M/B y workspace del runner |
| cloud | Etapas nativas del protocolo en GitHub |
| custody | Almacenamiento privado y acceso posterior al lock |
| connections / setup | Referencias reutilizables y enlace inicial |
| store / remote | Estado, cuota y seguimiento de un único despacho |
| reporting | Resultado legible y consumo explícito |

Una integración de protocolo registra validate/verify/backend/check. Los motores se añaden mediante adaptadores, conservando sus métodos. La condición particular de CT-03 no se transforma en una restricción universal de importación.

## Datos

Se admiten CSV y JSON, también como observaciones parciales. Se conservan originales, intervalos, censura, mediciones no numéricas y columnas ambiguas. La admisión de una fuente no concede aptitud para una pregunta.

No se inventan pedidos, identidad, continuidad ni tiempos de servicio. El observable público CT-03 exige cuatro cortes explícitos t0/t1/t2/t4; la reserva t6/t8 solo entra en el evaluador posterior al lock.

## Resultados y consumo

El workflow conserva fuentes, comandos, logs, intentos, estados de las trece plazas, lock, score e informes. La configuración verdadera, Modelica privado y CSV completo del mundo se conservan exclusivamente en R2.

Se muestran límites, intentos observados y saldo. Los fallos pueden consumir cuota. Si falta evidencia se marca consumo incompleto y saldo sin confirmar. No se inventan facturas o tokens que el proveedor no haya informado.

Un reporte de fallo permite localizar la etapa y los intentos sin repetir el experimento. La evaluación posterior puede reutilizar el mismo lock y los productores originales cerrados, sin nuevas llamadas físicas.

## Desarrollo opcional por CLI

La ejecución principal es GitHub; no hace falta instalar todos los motores en el equipo del usuario.

~~~powershell
python -m arena check examples/smoke.toml
python -m arena run examples/smoke.toml --out runs/smoke
python -m arena report runs/smoke
~~~

El controlador remoto opcional usa examples/ct03.toml y una conexión GitHub con permiso de despacho; ya no necesita leer secretos ni escribir variables administrativas para ejecutar. Su autorización cubre un único workflow.

La bóveda nativa de Windows sirve para desarrollo local. connections status distingue ausencia local de ausencia en Actions; capture conserva variables ya suministradas. No se exige esa bóveda en Linux/GitHub.

## Validación

[CI de plataforma](https://github.com/yudocyudoc/igc-modular/actions/workflows/ci.yml) y [CI de motores nativos](https://github.com/yudocyudoc/igc-modular/actions/workflows/native-engines-ci.yml).

Se comprueban fuentes originales, historial CT-02, regresiones de feedback/revisión y el SDK Buffalo con transporte mock, además del recorrido con fixtures y el linter de workflows. Estos controles no son una ejecución física ni un resultado científico positivo.

La corrida física queda detrás de la configuración inicial y de mode=live/authorized=yes. Durante la migración no se consumió OMC/Buffalo ni se seleccionó otro mundo.

Detalles de procedencia y límites en [ENGINE_MIGRATION.md](ENGINE_MIGRATION.md). Relevo del coder en [HANDOFF.md](HANDOFF.md); reglas en [AGENTS.md](AGENTS.md).
