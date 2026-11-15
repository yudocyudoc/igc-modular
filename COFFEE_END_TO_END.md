# Un recorrido completo de cafetería

Entrada en GitHub: workflow **Coffee Arena - one complete R2 run**. El primer
merge lo ejecuta una vez. También admite un despacho manual autorizado; nunca
se reintenta un solver ni se vuelve a generar un modelo Buffalo automáticamente.
Las ejecuciones del corpus y sus resultados se generan en GitHub; las pruebas
de software usan únicamente fixtures ficticios.

Usa el ZIP original ya custodiado en R2, con su SHA `4ff97ae4…a5f`, sin un nuevo
repositorio, bucket, Release o secreto. El adaptador admite explícitamente su
contenedor `video2/`, conserva el hash original y valida el manifiesto del corpus.
La clave de partición se conserva privadamente en el mismo R2.

La ejecución admite 54 semanas sintéticas, prepara 45 semanas permitidas,
compara B0/S5 con la referencia especializada y contrasta los modelos D/M/B
originales con recogidas sintéticas. Regenera D/M, reutiliza doce simulaciones
Modelica autenticadas y permite un único intento OMC de Buffalo R1: cero POST.
Recupera feedback propio con las políticas originales y sella las predicciones
en un artifact GitHub antes de abrir la verdad en otro job.

El artifact `coffee-e2e-result-<run>` contiene `REPORT.md`, `result.json` y CSV.
El informe distingue error predictivo, fallos de brazos, efecto condicional de
S5 en la referencia y límites: los D/M/B actuales no representan esa política;
el contraste V1 es retrospectivo y no valida rentabilidad real.

La misma entrada se integra en el registro, conexiones y estado de Arena:

```sh
python -m arena run examples/coffee_end_to_end.toml --out runs/coffee --authorize
python -m arena resume runs/coffee
```

El backend sigue un bootstrap del mismo commit cuando ya existe; no exige
copiar IDs ni vuelve a despachar un intento incierto. El objeto R2 de intento
OMC es de creación única: otro commit no restablece la cuota consumida.
