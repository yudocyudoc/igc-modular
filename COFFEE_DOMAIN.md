# Arena Cafetería — contrato público pagado → retiro (PR A)

`arena/coffee_domain.py` incorpora el contrato común del plan `PLAN_ADAPTADORES_NATIVOS_CAFETERIA_V1.md` sin alterar los métodos D/B/M ni ejecutar proveedores, OpenModelica, R2, modelos o scoring. El módulo lee **únicamente** el directorio ya liberado por el custodio (`producer-public-b0.json` y `release.json`) y un JSON público con hipótesis de ingeniería; valida la frontera de `producer_boundary` antes de generar `coffee_case`.

La unidad material es **pedido pagado**, no persona ni bebida; un pago no es un retiro. La entrada inicial se reduce deliberadamente a una tasa rectangular: ventas pagadas públicas en `[0,60)` / 1 hora. Mantenerla constante después del minuto 60 **es un supuesto**, no una observación ni un pronóstico de futuros pagos. Para el B0 inicial son diez pedidos en el corte (tasa = 10 pedidos/hora); ninguna marca posterior se consulta.

Las cinco hipótesis de ejemplo en `examples/coffee_public_assumptions_v1.json` **no proceden de la cafetería ni del generador secreto**. Los números de capacidad y tiempos son valores ilustrativos para probar contratos. En particular, `response_time=0.1 horas` son **seis minutos**, el mínimo del registro actual de M, no `0.1 minutos`. Stock inicial cero tampoco significa que la tienda estuviera vacía. Para futuras calibraciones hace falta observar retiros en la propia frontera.

El observable común es `orders_picked_up_cumulative` en los minutos `80`, `100` y `103.237`. Los cuatro objetivos adicionales están condicionados a representabilidad nativa. La proyección de trazas es una **operación de ingeniería** que preserva duplicados de tiempo y toma la última observación emitida antes de cada corte; no autentica un CSV, una simulación o un nativo. Sólo D (`delivered`) y M (`deliveredTotal`) tienen una correspondencia declarativa preliminar; Buffalo requiere demostrarla a partir del nativo que genere. No se acepta `reportedDeliveryRate` de M como retiro físico.

Uso offline, después de admitir un caso con el custodio (sin ZIP ni secretos disponibles en el proceso):

```bash
python -m arena.coffee_domain \
  --public-dir /path/to/producer-public \
  --assumptions examples/coffee_public_assumptions_v1.json \
  --out /path/to/coffee-case.json
python -m unittest discover -s tests -v
```

El archivo público del caso tiene su propio SHA canónico, así como SHA de vista y de hipótesis. La etapa siguiente debe conservarlo junto con los nativos completos D/M/B y verificar el acoplamiento entre caso, parámetros, traducción y ejecución; este incremento no demuestra esas capacidades. El `READINESS_ONLY` y el cierre de verdad sintética permanecen intactos. No se produce una nueva reserva de B0.
