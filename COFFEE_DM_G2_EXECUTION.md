# Cafetería — ejecución física G2 inicial D/M

## Antecedente auténtico

- Admisión privada B0: run `43532737911`; artifact público `14088545399`.
- Original Buffalo live: run `43537333254`, **un POST real**, modelo recibido pero no admisible para el traductor G2 sin revisión semántica.
- Generación D/M sobre el **mismo B0**: run `43547506584`, SHA `ad939be28597139eb7868dfc37f3f39fa5475205`, artifact `14095080561`.
- ZIP del artifact D/M: SHA-256 `d7d91f825c4d63fe334592f282fea5acf33844ac8487f94feb8e69d86b55414c`.
- Caso común: `sha256:756d16d2824a9052f5494dd41c3eef1f0e8826537deffbfc7cd39b0ca2d2457f`.

Ninguna simulación recibe el paquete fuente sintético completo, el vínculo privado,
`R2`, datos de retiro reales o entrega observada posterior a los 60 minutos.

## Lote y política de gasto/continuación — congelada antes de despachar

- 12 candidatos iniciales: seis D (1–3 stocks, con/sin pérdida pospago)
  y seis M (Short E1 con tránsito/filtrado distintos).
- **12 invocaciones OMC como máximo**, a lo sumo una por candidato.
  Cada script contiene un `checkModel` y un `simulate`; se registran por
  separado sus estados, sin fingir que `checkModel` es una simulación.
- `Modelica`: inicio 0, final `103.237/60` horas, 64 intervalos,
  integración `euler`, formato CSV. Imagen fijada por digest y biblioteca
  Modelica Standard Library/SystemDynamics fijadas por SHA de Git.
- Un fallo individual no autoriza reintentar ese candidato; se conserva su
  recibo y se continúa a los demás iniciales dentro del techo.
  Un segundo run `workflow_dispatch` del G2 se bloquea de forma preventiva.
- Cada intento se escribe al ledger `attempts.jsonl` antes de iniciar Docker.
  Docker corre con red desactivada y sin secretos ni R2. Quedan archivados
  `.mo`, `.mos`, logs, CSV y evaluación individual; errores también.
- Validación: time 0→103.237 min, valores finitos, inventarios no negativos,
  contador monotónico, balance = `10 pedidos/h` × tiempo supuesto con
  tolerancia numérica absoluta **0.015 pedidos** (no tolerancia empírica);
  M incluye todas las colas materiales, y excluye filtros informativos.
- Proyecciones a 80, 100 y 103.237 minutos mediante el operador vigente
  `última muestra emitida en o antes del corte`, sin interpolación futura.
  Las proyecciones son **provisionales sin lock**, no scores.

## Ejecución

Este PR agrega `.github/workflows/coffee-dm-modelica.yml`, exclusivamente manual.
No se dispara automáticamente al fusionarse. Para iniciar un primer run G2,
utilizar `main`, `authorized=yes` y `max_new_omc=12`.

```bash
gh workflow run coffee-dm-modelica.yml --repo yudocyudoc/igc-modular \
  --ref main -f authorized=yes -f max_new_omc=12
```

**No repetir** si falla o si queda un intento incierto. No volver a ejecutar
la admisión B0 ni el generador D/M. Este workflow no abre la verdad reservada,
no ejecuta Buffalo ni lo revisa, no consume feedback de Ledger/ATMS, no genera
lock científico ni permite puntuar políticas S1–S5. Es la fase G2 para saber qué
candidatos son físicamente simulables; G3 y revisión de modelos van después.

## Criterio de avance

Se necesita el artifact `coffee-dm-g2-<run_id>`, logs y resultados
per-candidato. Un estado de éxito de GitHub Actions sólo confirma que el lote
se ejecutó y registró sus intentos; no que sus doce modelos hayan pasado las
compuertas físicas. El número real de `G2_PHYSICAL_PASS_NOT_G3` se lee
de `result.json`.

El siguiente circuito debe usar diagnósticos por brazo y su propio modelo
padre: Ledger/ATMS → recuperación → decisión propia → revisión real sólo si
el motor original la soporta y existe presupuesto. Nada de eso se simula
en esta fase.
