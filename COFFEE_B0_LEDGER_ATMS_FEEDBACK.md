# Cafetería B0 — circuito real de feedback propio con Ledger/ATMS

## Fuentes custodiadas, todas de solo lectura

- Caso común `sha256:756d16d2824a9052f5494dd41c3eef1f0e8826537deffbfc7cd39b0ca2d2457f`
- GitHub G2 run [43550618982](https://github.com/yudocyudoc/igc-modular/actions/runs/43550618982), artifact `14094919865`, ZIP SHA-256 `1f10695e4dcd27ad4f29552c3c954b4ce26efb131594b0b18076f52a26701925`
- Original Buffalo B-LIVE-01 run [43537333254](https://github.com/yudocyudoc/igc-modular/actions/runs/43537333254), artifact `14090920829`, ZIP SHA-256 `70f9e9f846a33cd470b00dbaf0bf189b0b6c7a029b68bd84485f7c6bbe748265`
- Fuente B0 run `43532737911`, artifact `14088545399`.

El módulo `arena/coffee_feedback.py` verifica la identidad de ambos runs, sus artifacts GitHub, cada hash de ZIP, la cadena G2 de 12 intentos (modelos, logs, scripts, CSV, balances y proyecciones recomputadas), y el único native Buffalo con recibos de consumo. No se transfieren el ZIP privado de cafetería, el vínculo sintético, datos posteriores al corte ni las ecuaciones de rivales.

## Secuencia ejecutable

```text
G2 físico real D/M · B G1 original
  → verificar recibos, hashes y autenticidad de bytes
  → un diagnóstico por candidato/padre
  → SQLite F1a Ledger por brazo (D.sqlite / M.sqlite / B.sqlite)
  → ATMS justificación con dependencia de fuente + diagnóstico propio
  → recuperación memoria as-of y por lane: D | M | B
  → invocar política original de D y M con su propio padre
  → registrar disposición trazada al feedback recuperado
  → preparar paquete original Buffalo currentModel + diagnóstico propio
     (NO enviar, NO inventar decisión de LLM)
```

### D — seis candidatos

El original D es una gramática fija de topología 1, 2 o 3 stocks con/sin pérdida. La función original del puente `d_fixed_decision` devuelve `RATIFIED` y `model_revision=false`. Esa ratificación **no significa** que su estructura coincida con la cafetería, solamente que su propio método no dispone de una revisión a partir de las mediciones faltantes. Se conserva un diagnóstico G2 por padre, y la decisión queda vinculada al nodo ATMS recuperado antes de invocar la política.

### M — seis candidatos

Se invoca **la política original** `arena_m2_feedback.own_policy` mediante `own_m_decision` con el AST M verdadero. La política requiere dos residuales de observaciones tardías (2 y 4 horas en el experimento M2). En esta cafetería no existen observaciones de retiro y el horizonte es de 103.237 minutos, por lo que el resultado legítimo es `ABSTAINED / NO_TWO_LATE_CONSTRUCTION_OBSERVATIONS`. No se inventan residuales, no se reutiliza la calibración CT-03, y no se modifica el catálogo para fabricar una revisión. Los tiempos de tránsito de 1.6 horas permanecen explícitos.

### B — nativo original de un POST ya consumido

Se comprueba que `Engine.generate` devolvió un modelo con recibo real de Cloudflare, y se registra el diagnóstico estructural del propio Buffalo: traducción Modelica G1, discrepancias de paso temporal, puertos materiales y relaciones causales. El paquete prepara **`currentModel` original + diagnóstico recuperado del Ledger/ATMS** para una revisión futura con el motor original.

No se puede afirmar que Buffalo consumió ese feedback en una llamada real. **Estado: paquete listo, no enviado**. Requiere autorización específica para un nuevo POST que use `currentModel`, nunca un segundo `generate` desde cero fingiendo que es revisión.

## Límites explícitos

- 0 nuevos POST, 0 OMC y 0 lecturas R2 en esta fase.
- Los doce CSV G2 provienen de una simulación físicamente coherente, no de observaciones.
- El estado de ATMS es soporte lógico y dependencia epistémica, **no veredicto de verdad empírica**.
- No se generan nuevos modelos nativos ni una selección de ganador.
- Ningún lock científico, apertura de verdad reservada, comparación G3 o evaluación empresarial es autorizado aquí.
- Un `push` a `main` después de fusionar la implementación inicia una ejecución de solo lectura y guarda una SQLite por brazo, recibos y estados de política propios.

## Condición de avance

Antes del cierre científico final será necesario decidir qué modelos/políticas quedan como predicciones selladas; definir tratamiento explícito del abstencionismo M y el bloqueo B; construir un **nuevo lock** G2/revisión no retroactivo; y solo entonces usar el evaluador de verdad reservada. El lock READINESS_ONLY anterior no representa este resultado.


## Corrección P2 de cortes temporales y reproducción final (Astra)

**Evidencia histórica preservada:** el feedback run \`43558078534\` y ZIP
\`14099445220\` con SHA-256
\`1944596c63ffb3b75bee64f3e8e87d3c966a9c8faece8e84aafa20dea6219f8c\`
contiene 12 recibos D/M con igual timestamp para el diagnóstico y la
disposición. Astra encontró 12 \`projection_hash\` que no se reproducen con
la consulta \`as_known_at\` sobre la base **final**; B sí se reproduce.
La auditoría física G2 y la integridad de 76 eventos/revisiones no cambian.
Se mantiene el ZIP histórico; no se corrigen recibos retroactivamente.

**Reparación solo en \`arena/coffee_feedback.py\`, no en el motor vendorizado:**
un reloj lógico explícito fija tres cortes distintos de la misma iteración:
\`feedback_recorded_at=T\`,
\`retrieval_as_known_at=T+1µs\`,
\`disposition_recorded_at=T+2µs\`.
Los microsegundos son **orden lógico auditable**, no latencias medidas.
Las políticas D y M consumen exclusivamente la recuperación en el segundo
corte, anterior a las disposiciones finales.

Una vez terminadas las seis decisiones de cada brazo, el adaptador abre la
SQLite final con el Ledger original, verifica que el corte anterior tiene
cuatro revisiones verificadas (fuente, diagnóstico, regla, feedback) y que el
corte posterior contiene seis (también regla y decisión). Después vuelve a
recuperar mediante \`arena_memory/ATMS\` original y exige **igualdad exacta**
de \`item_id\`, \`as_known_at\` y \`projection_hash\` frente al recibo original
de esa ejecución. B se reabre, exige cuatro revisiones y reproduce su
proyección sin disposición. Si cualquiera falla, no se publica un
\`summary.json\` con éxito.

La nueva salida usa
\`arena.coffee-peak.own-ledger-atms-consumption/2\` y conserva los cortes,
reproducciones por candidato, conteos antes/después y hashes en el artefacto.
Las pruebas incluyen 6 D + 6 M + 1 B, casos y lanes aislados, reapertura
SQLite \`mode=ro&immutable=1\`, y una regresión negativa del mismo timestamp
que antes producía un falso recibo reproducible.

La fase no reejecuta OMC, no llama a Buffalo, no accede a R2 ni a la verdad
reservada. La nueva ejecución de solo lectura utilizará **los mismos
artefactos G2/B** y publicará un **nuevo ZIP de feedback**, sin alterar el
run histórico ni crear un lock científico.
