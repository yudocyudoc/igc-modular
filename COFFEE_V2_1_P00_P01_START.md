# Arena cafetería V2.1 — P00/P01: primer corte de evidencia (sin nuevas campañas)

**Plan rector:** `HOJA_DE_RUTA_ARENA_CAFETERIA_V2_1_DECISIONES_Y_VALIDACION.md`,
§17.1 y §17.3. Este PR inicia P00/P01; **no declara concluido P01** hasta
inspeccionar el video completo y el catálogo del paquete privado mediante su
custodio. Tampoco adelanta P02/P05, crea un solver, selecciona Sx o abre G3.

## P00 — historia auténtica congelada

`arena/coffee_v2_start.py` fija ocho artefactos GitHub con run ID, commit,
ruta de workflow, nombre de artifact y SHA-256. El pipeline verifica cada
identidad mediante APIs read-only `actions:read`: no selecciona el último
run, no descarga la verdad y no sobreescribe ninguna evidencia.

| Fase | Run | Resultado conservado |
| --- | --- | --- |
| Custodia B0 pública | 43532737911 | Solo release público, sin verdad |
| Buffalo original | 43537333254 | Un POST, G1 bloqueado |
| D/M nativos | 43547506584 | Seis D y seis M originales |
| Modelica intento 1 | 43548909533 | 12 OMC, 0 simulaciones; bug de lanzamiento |
| Modelica recuperación | 43550618982 | 12 OMC, 12 G2 físicos, no G3 |
| Feedback histórico | 43558078534 | Defecto `as-of` P2, preservado |
| Feedback corregido | 43561168032 | 13/13 recuperaciones ATMS reproducidas |
| Buffalo revisión R1 | 43565759793 | Un POST real, G1 admisible y traducible, no G2 |

El pipeline también lee **solamente** los ZIP originales públicos
`coffee-public`, `coffee-b-live` y `coffee-b-review`, con SHA íntegro.
La auditoría R1 compara bytes del padre y revisión, conteos, tipos de puertos,
paso temporal, respuesta G1, y vuelve a examinar la solicitud auténtica
del SDK para demostrar que incorporó el `currentModel` original.
No publica modelos, prompts, identificadores de pagos ni respuestas de
proveedor. Una auditoría independiente posterior de Codex/Astra sigue siendo
un control distinto; la verificación ejecutable de este PR no la suplanta.

Contabilidad histórica: 24 invocaciones OMC; un POST inicial de Buffalo y un
POST de revisión R1. Es **consumo observado**, no conciliación monetaria.
El lock de *readiness* anterior no es lock científico posterior a modelos.
La comparación con resultados reservados V1 permanece cerrada.

## P01 — inventario público comprobado y pendientes de custodia

- 10 pagos POS sintéticos en `[0,60)` minutos, cada uno con timestamp;
  V1 los redujo a una tasa constante de 10 pedidos/h.
- 13 partidas, con `CAFE-EXT` y `CAFE-LECHE`, verificadas junto a su pedido,
  pero no utilizadas por V1 para estimar tiempos/recursos por receta.
- 60 resúmenes de `[minuto,minuto+1)` con proxies de presencia y marcas de
  cola. V1 **no los usó** para calibrar capacidad. Esos tracklets no equivalen
  a llegadas, personas únicas o retiros.
- 5 parámetros de ingeniería públicos, no medidos. Los 12 pedidos/h de
  capacidad supuesta no se saturan por una entrada constante de 10 pedidos/h.
- La ventana total nominal es 103.237 min; `[60,103.237]` permanece reservado
  según el contrato V1, no disponible para ajustar una nueva referencia.

El plan V2.1 menciona `video2/README.md`, 6195 muestras y una grabación
de 01:43:14.224: aquí son **afirmaciones documentales, no verificación de
archivos por bytes**. Las 54 semanas sintéticas también requieren inventario
por un custodio; **no** son 54 semanas reales ni muestras independientes.

### Matriz de decisión orientada a mecanismo

La matriz publicada `p01-consumption.csv` separa campos admitidos de
campos realmente usados en las ecuaciones V1. Ejemplos:

| Datos disponibles | Consumo en modelos V1 | Posible utilidad V2 |
| --- | --- | --- |
| 10 pagos | 10 agregados a media | Perfil de entrada, no llegadas |
| 10 timestamps de pagos | 0 usados como perfil | Concentración temporal y colas |
| 13 partidas | 0 usadas como carga de recursos | Arquetipos de producción |
| 60 bins visuales | 0 usados para calibración | Presencia, revisión dirigida |
| Capacidad 12/h | supuesto fijo | Acotar con tiempos de recurso |
| Retiros después de corte | 0, privados | Evaluación posterior a lock |

La clasificación `INSUFFICIENT_QUALITY` para los proxies expresa que no
sustentan inferencias de servicio; **no declara inutilidad del video completo**.
El material físico necesita inventario semántico adicional.

### Resultado inicial: medir antes de elegir S2/S5

Dos explicaciones rivales siguen siendo compatibles con el material:

- Límite por operador: trabajo manual del barista compite con otras tareas;
  una reasignación S5 podría importar.
- Límite de máquina: equipo ocupado mientras el trabajo manual compatible
  puede solaparse; un recurso adicional S2 podría importar.

**Ninguna es un diagnóstico observado ni una recomendación.** La primera
ficha `p01-mechanisms.json` pide timestamps emparejados de inicio/fin manual
y ocupación de máquina, task ID local, zonas/oclusiones, tareas simultáneas y
recursos, con criterios explícitos para decidir si la medición discrimina
mecanismos. De no ser posible, el estado legítimo es `MEASURE_FIRST`.

## Salidas estructuradas

El workflow de solo lectura `.github/workflows/coffee-v2-p00-p01.yml`
se inicia automáticamente una vez cuando este incremento se fusiona en
`main`, y puede consultarse sin repetir ningún gasto pagado.

- `p00-v1-status.json`: run/artifact/sha, registro y auditoría R1.
- `p01-sources.json`: cobertura temporal, semántica, admitida y consumida.
- `p01-consumption.csv`: campo → operador → parámetro → mecanismo → decisión.
- `p01-mechanisms.json`: incertidumbres y ficha `MEASURE_FIRST`.
- `REVIEW.md`: lectura ligera sin IDs privados.
- `receipt.json`: estado de avance, alcance, hashes de salidas y presupuestos 0.

Todos los archivos están redactados a partir de conteos, nombres y estados,
**sin filas POS, ni tokens de cliente/pedido, ni contenido reservado**. Un
`success` certifica esta auditoría pública, **no P01 total ni una
recomendación empresarial validada**.

## Condición de continuación

P01 sólo queda completo cuando un inventario con acceso autorizado registre,
por variable y por intervalo, qué fue extraído del video2 completo, qué
archivos fueron supersedidos y qué eventos requieren revisión; más conteos,
escenarios/replicas y duplicaciones del paquete sintético, sin transferir
verdad de evaluación al productor. Esta etapa **no pide repetir la extracción**.

P02/P05 mínimos y la primera elección B0/Sx esperan a ese diagnóstico; no
se construye anticipadamente un simulador completo ni una UI.
