# Cafetería Arena V2.1 — P02/P05 mínimo: tiempo público y operadores observacionales

La hoja de ruta V2.1 solicita conservar relojes, eventos POS, productos,
operadores observacionales y partición temporal antes de calibrar o elegir
B0/Sx. Esta entrega implementa **solo el mínimo público de construcción**
sobre el B0 congelado, NO el catálogo SQLite completo de P02 ni la
calibración ni todos los operadores futuros de P05.

## Fuente y frontera

La única entrada es el artifact público B0 original run 43532737911,
artifact 14088545399, SHA-256
872cf83210a54c88563a13130c3cec819bf1a978db93d6b08610634f282c42d2.
El adaptador existente arena.coffee_dm_campaign.acquire autentica GitHub,
descarga los dos archivos liberados y reconstruye el caso
sha256:756d16d2824a9052f5494dd41c3eef1f0e8826537deffbfc7cd39b0ca2d2457f
mediante arena.coffee_domain.build_case. Sin ZIP de origen, vínculos
privados, R2 ni truth de evaluación.

La construcción autorizada es **[0,60) minutos** del horizonte histórico
103.237 minutos. Se conserva la regla de intervalos semiabiertos:
un pago exactamente en el minuto 5 pertenece a [5,10), nunca a [0,5).
Los minutos **[60,103.237] son desconocidos/reservados**, ni cero ni
extrapolación de 10/h.

## Datos y dos operadores fijados antes de mirar resultados G3

- P02-PAID-POS-HALFOPEN-BINS/1: cuenta exclusivamente registros de pago,
  preserva su tiempo original para asignarlos a bins de **5 min**
  (primario) y **15 min** (descriptivo). La tasa de cada bin es conteo
  × 60 / ancho en minutos; es una tasa *equivalente del intervalo*, no
  una medición de demanda máxima o capacidad de servicio.
- P05-VIDEO-PRESENCE-WEIGHTED-MEAN/1: agrega 60 proxies por minuto
  con su número de segundos de muestreo. Los promedios son tracklets
  visibles y marcas de cola; NO llegadas, clientes únicos, retiros ni
  capacidad física identificada.
- Las 13 partidas sintéticas conservan tipo y cantidad como contexto,
  sin equiparar bebida, pedido, operación y carga manual/máquina.
- Los operadores son **versionados** y separables de los motores originales.
  No reescriben el caso B0 de V1 ni el generador D/M/B.

## Contraste reproducible de entradas del mismo B0

V1 transformó los diez pagos en entrada **constante 10 pedidos/hora**.
Los tiempos POS públicos originales muestran que cinco minutos tienen
concentración mucho mayor.

| Intervalo de 5 minutos | Pagos sintéticos |
| --- | ---: |
| 00–05 | 1 |
| 05–10 | 0 |
| 10–15 | 1 |
| 15–20 | **4** |
| 20–25 | 1 |
| 25–30 | 0 |
| 30–35 | 1 |
| 35–40 | 0 |
| 40–45 | 0 |
| 45–50 | 0 |
| 50–55 | 2 |
| 55–60 | 0 |

El máximo local 4 pagos/5min equivale a **48 pagos/hora** en ese bin.
Esto evidencia concentración **sintética** de pagos, no una saturación
observada de la cafetería, ni relación causal con una máquina/barista.
La entrada 10/h de V1 es una hipótesis útil para controlar modelos,
pero pierde esta variabilidad y no informa tiempos de servicio.

## Ejecución reproducible

El módulo arena/coffee_v2_pos_profile.py produce:

- p02-p05-public-profiles.json: bins, operadores, cantidades y semántica;
- pos-observations-5min.csv y pos-observations-15min.csv;
- REVIEW.md legible;
- receipt.json con SHA de cada salida.

Los IDs de POS, pedidos, filas, tracklets y timestamps individuales se usan
solo dentro del proceso y NO aparecen en las salidas publicadas. GitHub Actions
workflow coffee-v2-p02-p05.yml recupera el release autenticado con
actions:read; sube solamente el directorio **output**, nunca los archivos
públicos en bruto ni los reservados. Las pruebas verifican conservación,
bordes, tipos, exclusión futura, contaminación de identidades y
adulteraciones. El brazo D, M y B no reciben aún la nueva entrada.

**Presupuesto:** 0 OMC, 0 POST, 0 R2, 0 mundos, 0 G3 y 0 locks.
Esta entrega es un operador de datos, no un resultado empresarial.

## Próximos pasos

Para alimentar una referencia de dominio se requiere definir el estado
inicial y proceso físico según la evidencia: tareas, recursos exclusivos,
concurrencia manual/automática y unidades. Las marcas de video originales
aún no validan intervalos de servicio, por lo que S2/S5 siguen siendo
hipótesis rivales y la decisión honesta sigue siendo MEASURE_FIRST.

Un siguiente ensayo de ablation **constante versus temporal** tendrá
escenarios y presupuestos predefinidos; no usar la reserva V1 para escoger
post hoc el operador con mejor resultado.
