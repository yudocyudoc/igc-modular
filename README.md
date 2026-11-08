# Arena modular

Una aplicación para importar datos, preparar motores, ejecutar etapas, archivar predicciones y evaluar, con conexiones reutilizables y consumo visible. La implementación está separada del repositorio histórico y conserva los originales necesarios del corte `881f92792e4a67de0eb33a04662089029c0e6918` de `yudocyudoc/IGC`.

Repositorio de continuidad: [yudocyudoc/igc-modular](https://github.com/yudocyudoc/igc-modular). No modifica PR #171/#172. El adaptador físico remoto todavía utiliza los workflows originales registrados en IGC; el CI de integración se ejecuta en este repositorio. La ejecución física conserva sus condiciones y presupuestos.

**Forma de trabajo:** gpt-web implementa; Codex/Astra revisa. El usuario fija prioridades y autoriza los lotes de consumo. El relevo técnico está en [HANDOFF.md](HANDOFF.md) y las reglas de contribución en [AGENTS.md](AGENTS.md).

## Ejecutar en GitHub

Cada push o pull request ejecuta [Arena modular - offline end-to-end](https://github.com/yudocyudoc/igc-modular/actions/workflows/ci.yml). También está disponible con **Run workflow**. Recorre la integración completa en Linux y Windows, Python 3.11 y 3.13, y conserva el informe y el JSON como artifacts. No pide secretos ni consume OMC/Buffalo.

El destino operativo es GitHub Actions. La bóveda de Windows es una opción para desarrollo local, no un requisito para ejecutar este CI. Los secretos de IGC no se trasladan automáticamente al nuevo repositorio: el puente físico actual sigue utilizando los jobs y secretos de IGC. La siguiente implementación corresponde a gpt-web: consolidar el recorrido físico en GitHub conservando los motores y la reserva, con los criterios de HANDOFF.md.

## Probar el recorrido completo de integración

Desde esta carpeta, con Python 3.11 o superior:

```powershell
python -m arena check examples/smoke.toml
python -m arena run examples/smoke.toml --out runs/smoke
python -m arena report runs/smoke
```

No necesita credenciales, instalación de dependencias, Docker, OMC ni acceso a una nube. Recorre importación → preparación D/M original → salidas de productores de prueba → lock original → evaluación original → informe.

**El resultado es `INTEGRATION_FIXTURE`, no una corrida física de D/M/B.** Los datos privados, las predicciones y los recibos de esta prueba son fixtures explícitos. Se conservan las trece plazas, incluidas las ausencias: dos pares de prueba y once plazas sin par. No se evalúa la eficacia de los motores ni se concede evidencia experimental por estos fixtures.

Cada ejecución genera `result.json`, `report.md` y `run.sqlite`. No sobrescribe una ejecución anterior. `status` muestra su estado; `resume` continúa una ejecución registrada sin crear otra corrida.

## Organización y extensión

```text
arena/
  cli.py             Interfaz de comandos
  orchestrator.py    API de aplicación: check / run / resume / status
  config.py          Configuración común del experimento
  protocols.py       Registro de protocolos y adaptación CT-03
  data.py            Importación, capacidades y proyección pública
  engines.py         Registro y preparación original de motores
  connections.py    Referencias a credenciales, sin valores en experimentos
  windows_vault.py   Bóveda nativa del usuario de Windows
  setup.py           Enlace idempotente de conexiones con GitHub
  store.py           Estado, intentos y consumo persistentes
  github.py          Adaptador de transporte REST
  remote.py          Ejecución del recorrido original en GitHub
  fixture.py         Recorrido completo de integración sin consumo externo
  reporting.py       Informe legible
  legacy.py          Acceso explícito a fuentes originales conservadas
  _vendor/           Código y recursos originales necesarios
```

Los protocolos se registran mediante `protocols.register(nombre, adaptador)`. Sus métodos son `validate`, `verify`, `backend` y `check`. El backend expone `execute(store, authorize=False)`. Un protocolo nuevo puede usar su propio backend y presupuesto sin editar el coordinador. La prueba `test_protocols.py` ejecuta esa extensión.

Los motores se registran mediante `Engines.register`; su preparación no puede reemplazar silenciosamente un motor existente. D/M conservan generadores, AST, ecuaciones y comprobaciones originales. Buffalo live se ejecuta mediante su workflow original y la ruta de proveedor existente; esta extracción no reimplementa Buffalo localmente. La fábrica y las reglas particulares CT-03 se mantienen en sus adaptadores, no en el almacenamiento ni en el transporte HTTP.

El manifiesto `_vendor/UPSTREAM_MANIFEST.json` enumera los 39 archivos originales con SHA-256 y blob Git. `python -m arena verify-upstream` comprueba su conservación. No se exige generar nuevos certificados por corrida.

## Datos parciales sin falsas trayectorias

```powershell
python -m arena ingest observaciones.csv --time-column tiempo --value-column medicion --time-unit seconds
python -m arena ingest anotaciones.json
```

La importación admite CSV y JSON; conserva campos originales, intervalos, censura y ausencia de identificación. No convierte registros en pedidos, no certifica continuidad ni imputa tiempos de servicio. Distingue admisión de una fuente de aptitud para una pregunta.

El adaptador público CT-03 necesita unidades explícitas y exactamente los cortes t0/t1/t2/t4, sin reserva. Una fuente que no cumpla eso puede seguir admitida como observación parcial. El fixture ejecutable usa los cuatro cortes fijos de `examples/public-cuts.csv`; no sustituye la admisión de un experimento nuevo con datos arbitrarios.

## Conexiones y bóveda: configurar una vez

`connections.toml` contiene referencias; nunca valores. Los experimentos no contienen secretos. La resolución utiliza las variables existentes, después la bóveda y, para GitHub, una sesión `gh` existente. Se conservan los nombres históricos `CLOUDFLARE_ACCOUNT_ID` y `CLOUDFLARE_API_TOKEN`.

En Windows se usa directamente el Administrador de credenciales del usuario mediante `CredReadW`/`CredWriteW`. No requiere instalar una bóveda ni inventar una clave maestra. En macOS/Linux está disponible el extra opcional `vault`, que utiliza el almacén nativo mediante keyring. No hay fallback a archivos de texto.

```powershell
python -m arena connections status
python -m arena connections capture
```

`status` muestra disponibilidad y origen, nunca valores. No confunde presencia con autenticación válida. `capture` guarda de una vez las variables ya suministradas y devuelve solo los nombres de entradas; no crea tokens nuevos. También se puede guardar una entrada mediante un prompt oculto:

```powershell
python -m arena connections save github token
```

La bóveda pertenece al usuario de Windows que ejecuta el proceso. No se afirma independencia frente a ese usuario o a un administrador. La prueba de lectura nativa se hizo con un nombre inexistente; no se almacenaron ni migraron credenciales reales en esta implementación.

## Reutilizar secretos de GitHub sin copiarlos de nuevo

```powershell
python -m arena connections link-github --repository yudocyudoc/IGC
```

Consulta nombres y muestra qué falta. Los secretos existentes de repositorio o environment se conservan y no requieren una copia local. La API de GitHub no devuelve sus valores.

Si realmente faltan conexiones, el mismo comando con `--apply` crea solo los environments y enlaces faltantes, usando los valores disponibles mediante las referencias de `connections.toml`. Una segunda aplicación no reemplaza secretos existentes. Para subir un secreto nuevo usa el cifrado libsodium exigido por GitHub, disponible en el extra opcional `github-setup`:

```powershell
python -m pip install '.[github-setup]'
python -m arena connections link-github --repository yudocyudoc/IGC --apply
```

La configuración comprueba todas las entradas locales necesarias antes de escribir. Si un secreto falta en todas las fuentes, informa la referencia exacta: no puede recuperar un valor que GitHub no permite leer. Esta operación no despacha workflows ni consume OMC/Buffalo.

El acceso de configuración es del coordinador. Los productores conservan la distribución de secretos de sus jobs originales; el coordinador no les envía su token GitHub, credenciales R2 ni una copia completa de la bóveda. La presencia de nombres no certifica el alcance real de los tokens.

## Recorrido físico remoto: una autorización y seguimiento automático

**Entrada única alojada en el nuevo repositorio:** una vez incorporado el workflow al branch principal, abrir [Arena CT-03 - physical single entry](https://github.com/yudocyudoc/igc-modular/actions/workflows/physical-ct03.yml) → **Run workflow**. Elegir `mode=check` para verificar acceso sin consumir OMC/Buffalo. Elegir `mode=execute` y `authorized=yes` solo para el lote físico explícitamente aprobado. Los pushes y PR **no** ejecutan el lote físico. El workflow encadena intake → productores D/M/B → lock → evaluación; conserva artefactos públicos y estado de ejecución.

**Conexión inicial del runner alojado (una sola vez):** en `igc-modular` → **Settings → Secrets and variables → Actions**, guardar un secreto de repositorio `IGC_ACTIONS_TOKEN` con un token limitado al repositorio `yudocyudoc/IGC`. El `GITHUB_TOKEN` automático de `igc-modular` no tiene permisos entre repositorios. El token remoto necesita Actions read/write, Environments read/write, Secrets read y Contents read, según los endpoints utilizados. No se copian aquí los secretos Buffalo/R2, que siguen en los environments originales de IGC. El workflow falla **antes de consumir cómputo** si falta el token o la comprobación remota falla. Un token disponible no certifica por sí solo que sus permisos funcionen.

**Límite del estado actual:** esta entrada coordina los cuatro workflows físicos todavía alojados en IGC; no los traslada ni afirma haber ejecutado CT-03. Un intento de despacho sin ID confirmado queda incierto y no se repite; el estado y los recibos que existan se archivan para conciliación. No iniciar otro `execute` para recuperar un lote interrumpido. El CI y los fixtures no requieren este token.

```powershell
python -m arena check examples/ct03.toml
python -m arena run examples/ct03.toml --out runs/ct03 --authorize
python -m arena status runs/ct03
python -m arena resume runs/ct03
```

El ejemplo fija el código `881f927`. `check` no cambia configuración ni despacha. El backend comprueba el SHA, workflows, nombres de secretos y existencia de una corrida previa; necesita un acceso GitHub que permita esas lecturas y, al ejecutar, los despachos y las variables de los environments existentes. Una sesión válida se reutiliza; un token inválido no se transforma en una solicitud de recrear credenciales Buffalo.

Una autorización cubre el lote completo. El coordinador actualiza las variables operativas previstas, despacha intake → productor → lock → evaluador, transporta IDs automáticamente y descarga solo el resultado público. La variable que reconoce la simulación del mundo se escribe después del intake exitoso. No accede al contenido privado de R2.

El flujo conserva las ejecuciones separadas y el evaluador original posterior al lock. Mantiene el máximo de **19 OMC nuevos, incluido el mundo, y 2 POST Buffalo**; la cuota separada de cuatro despachos GitHub no es consumo Buffalo. No repite los dos OMC ya ejecutados en CT-02.

Se registra la intención antes de cada despacho. Con un ID confirmado, `resume` vuelve a consultar esa ejecución. Un fallo del lote no se reintenta. Si la respuesta de un despacho se pierde y no hay un ID confirmado, se detiene con `NEEDS_RECONCILIATION`: no puede garantizarse una ejecución única repitiendo a ciegas una API sin clave de idempotencia. El mensaje indica conservar esa ejecución y consultar GitHub, no empezar otro lote.

## Consumo transparente

El informe distingue límites, intentos observados, intentos fallidos y saldo. Las llamadas fallidas cuentan. Los intentos remotos se contrastan con sus logs retenidos. Cuando falta evidencia, el consumo se marca incompleto y el saldo queda sin confirmar: no se sustituye por cero. No se inventan tokens, precios o facturación que el proveedor no haya informado.

La prueba local ya completó el recorrido con cero OMC y cero Buffalo. El transporte remoto y el enlace de secretos se probaron con dobles de API, sin modificar GitHub. No se ha ejecutado CT-03 físico desde esta extracción. La sesión `gh` disponible en la revisión anterior reportaba autenticación inválida; este código permite reutilizar una conexión válida cuando esté disponible.

## Validación y distribución

```powershell
python -m unittest discover -s tests -v
python -m pip wheel . --no-deps --no-build-isolation --no-cache-dir --wheel-dir dist
```

Las regresiones cubren CLI completo, conservación de fuentes, extensión de protocolo, datos parciales, reserva posterior al lock, cuota persistente, reanudación, despacho incierto, ocultación de credenciales y configuración idempotente. Las pruebas de escritura de bóveda y de API usan dobles; no escriben secretos reales.

El wheel incluye los originales necesarios. El CI incluido ejecuta la integración offline y las regresiones sin secretos. Para llevar esta carpeta a otro repositorio se conserva el manifiesto de origen; no se trasladan `.env`, bases de ejecuciones, secretos ni resultados privados.

Referencias técnicas: [CredReadW](https://learn.microsoft.com/en-us/windows/win32/api/wincred/nf-wincred-credreadw), [CredWriteW](https://learn.microsoft.com/en-us/windows/win32/api/wincred/nf-wincred-credwritew), [keyring](https://keyring.readthedocs.io/en/latest/), [GitHub workflow dispatch](https://docs.github.com/en/rest/actions/workflows), [cifrado de secretos para GitHub](https://docs.github.com/en/rest/guides/encrypting-secrets-for-the-rest-api).

