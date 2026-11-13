# Arena Cafetería — P3: tres brazos, lock y verificación de archivo

**Base:** PR #8 de custodia; éste depende de PR #7. No sustituye CT-03.
**Estado:** preparación experimental **sin modelos nativos de cafetería**.

## Qué queda operativo en código

La ejecución manual `coffee-peak-custody.yml` (`mode=admit`, `authorized=yes`)
continúa con la custodia de un único B0 preseleccionado. Tras la liberación
pública, crea **tres jobs distintos** (D, B y M). Los tres verifican el mismo
SHA de la vista pública, revisan la identidad del origen vendorizado, y emiten
`submission-D.json`, `submission-B.json`, `submission-M.json` sin credenciales
R2, código del generador ni tablas truth. Cada archivo declara capacidades
`no_demostrado` para caja, preparación compartida, abandono, balances y S1–S5,
además de `status=NO_NATIVE`.

La etapa `prediction-lock` exige exactamente tres expedientes del mismo run/SHA
(ni duplicados ni archivos adicionales), los incorpora en `lock.json` y publica
un artifact v4 `coffee-lock-<run_id>` con un SHA-256 de los bytes congelados.
El job `verify-lock` vuelve a descargar ese artifact por su **ID**, comprueba
el SHA-256 local y consulta la API de GitHub para validar su origen: mismo
run, commit, rama main, `workflow_dispatch`, primer intento, ruta de workflow
prevista, ID, nombre y no expiración. El verificador **no tiene secretos R2**.

El lock actual es `mode=READINESS_ONLY`, no `SCIENTIFIC`; ningún evaluador
recupera datos reservados ni publica métricas. `coffee_score.py` contiene un
operador privado de métricas del oráculo sintético y barreras explícitas para
un futuro scoring: el lock científico, la verificación real del archivo y la
validación auténtica de los nativos deberán completarse *antes de leer R2*.
Los métodos de evaluación no están habilitados por CLI ni por workflow.

## Qué NO se presenta como logrado

- D/M siguen produciendo estructuras nativas específicas de CT-03; **no hay
  traducción validada a caja/barista/máquina/abandono**. Buffalo tampoco ha
  generado modelos de cafetería. No se invoca `OriginalD.prepare`,
  `OriginalM.prepare` o `Engine.generate` como si fueran predicciones B0.
- El lock actual solo congela la **ausencia documentada de pronósticos**.
  Un `NO_NATIVE` cuenta como resultado del diagnóstico de capacidad, pero
  **no** como un modelo que haya predicho un objetivo.
- Las métricas privadas de `coffee_score.py` distinguen: pago POS, reembolso,
  preparación lista, retiro, abandono y espera. Se fijan cortes 80, 100 y
  103.237 minutos, siempre posteriores al corte de construcción [0,60).
  **Todos los resultados del ZIP son sintéticos.** Contribución real y beneficio
  neto no son identificables sin costos operativos observados.
- No hay todavía evaluación científica con los tres nativos, políticas S1–S5
  contrafactuales o recomendación de inversión para una cafetería real.
- Tampoco se ha hecho una escritura real en R2; el ZIP requiere staging privado
  previo en un entorno autorizado, como documenta `COFFEE_CUSTODY.md`.

## Pruebas sin gasto

```shell
python -m unittest discover -s tests -p 'test_coffee*.py' -v
python -m unittest discover -s tests -v
python -m arena run examples/smoke.toml --out runs/smoke
```

`tests/test_coffee_lab.py` cubre los tres brazos independientes, no divulgación,
rechazo de pronósticos inventados, integridad y completitud del lock,
revalidación por API y rechazo de intentos/runs/artifacts ajenos. El evaluador
no abre el oráculo por efecto de un recibo de tipo readiness. La carga útil de
17 MB no se incorpora a Git; pruebas con ese archivo corren solo si está
montado como fixture local. GitHub CI prueba lo demás sin red externa.

## Pendiente para P4/P5

1. Validar adaptadores de **dominio** que traduzcan POS/presencia a los
   observables y unidades que cada productor puede representar, y evaluar
   estructura y balances de recursos, no simplemente cambiar etiquetas.
2. Ejecutar cada productor original bajo cuota autorizada; capturar nativo,
   logs, intentos y procedencia verificable. No inferir gasto cero ante error.
3. Permitir `mode=SCIENTIFIC` **solo** tras verificar recibos de modelo real y
   predicciones acopladas a esos nativos, con criterios predeclarados.
4. Habilitar el evaluador R2 después de comprobar el artifact immutable y sus
   hashes; comparar targets reservados en la misma frontera del modelo.
5. Generar contrafactuales S1–S5 con entradas exógenas realmente emparejadas,
   separar costo esperado de costo real y documentar incertidumbre.

**No modificar `arena/_vendor`, CT-03, sus cuotas o los workflows existentes.**
