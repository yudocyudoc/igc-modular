# Arena cafetería Q75 — cerrar eslabón D/M de diagnóstico propio (PR50)

**Decisión única heredada de PR49:** en Q75, con máquina y personal existentes, ¿se justifica probar prioridad de leche lista o mantener la práctica? FCFS es una política **supuestamente** usada por Hydra, no una medición del local. Q75 90 s arroja −3,837 s en el P90 simulado, cinco pedidos antes y cuatro después; la decisión inicial es **no cambiar aún la práctica, leche como candidata condicionada**.

## Qué añade PR50 (sin fingir otro experimento)

PR50 recupera los ocho artefactos auténticos del PR48/49 y prepara la misma entrada Q75 autenticada: **dos baristas, dos puestos, tres grupos, una lanza W01 y un pase**, con regla de tarea ejecutable y retorno a FCFS cuando leche está bloqueada. El código original vendorizado se verifica por manifiesto y sus primitivas originales enumeran seis padres de D y seis de M. No introduce un modelo de sustitución ni cambia sus ecuaciones.

Sobre los **12 padres** se formula una **objeción de construcción G1** del evaluador: el nativo carece de asignación explícita de W01+barista y de regla que distinga `PRIORITIZE_MILK_READY` de `FCFS_READY_ASSUMED`. Esta objeción dice que **el padre concreto no puede calcular ese contraste ni el P90 por pedido**, no que toda la metodología sea incapaz de representarlo. No se inventan residuales de retiros ni observaciones de barra, y nunca se atribuye efecto nulo a la falta de representación.

Con el **bridge original CT02**, cada diagnóstico propio se registra en **Ledger/ATMS** asociado a su parent SHA256 y fuente Q75; se recupera con un corte lógico posterior, se invoca la **política original** (`d_fixed_decision` o `own_m_decision`) y se persiste la disposición. Se comprueba que el diagnóstico siga recuperable tras el registro. Los timestamps son **reloj lógico de reproducción**, nunca tiempos observados ni una nueva línea de tiempo empírica.

Esperado según política históricamente fija: **D: 6 ratificaciones** de familia, sin revisión D2 porque no hay ensayo reset compatible. **M: 6 abstenciones** de revisión porque la política M2 exige residuos medidos a 2 y 4 horas. Nada de esto responde al P90 ni demuestra superioridad. Una respuesta de cobertura no se etiqueta como generación/revisión nueva de las máquinas.

ATMS decisional `Journal` consume recibos auténticos D/M como soportes de **limitaciones representacionales**, no de una mejora de la política. Se realizan tres `what_if`: retirada de D, de M y de la premisa común (ausencia de política en esos nativos). El soporte del criterio de no intervenir todavía permanece independiente de ellas. La retirada de la premisa común invalida **ambas** conclusiones de cobertura, no vuelve verdadera ninguna predicción de leche. La autoría de las justificaciones transversales es del evaluador.

**Buffalo sigue pendiente:** su B0/R1 auténtico responde a retiros acumulados y excluía acoplamiento barista/espresso. Una llamada o revisión real Q75 requiere comprobar padre compatible y presupuesto autorizado. No se recicla `currentModel` de otro caso ni se declara que el productor haya respondido.

## Qué acredita el CI

`.github/workflows/coffee-q75-dm-own-feedback.yml` descarga únicamente ocho ZIP históricos de GitHub, verifica SHA256 y fuente, genera pre-despacho PR49, ejecuta las políticas originales con el bridge real sobre **12 padres** y publica los SQLite originales además del JSON/MD. El runner no recibe secretos de Cloudflare/R2, no invoca Modelica, no crea nuevos mundos y no despacha ninguna revisión de Buffalo. Tests negativos: W01 ausente o doble, input alterado, padre ajeno y contaminación de carril. Un CI verde acredita el código de feedback, no una mejora operativa.

## Dictamen posible y presupuesto

**Resultado parcial:** D/M recibieron cada uno su diagnóstico G1 y ejecutaron su política original. Si la decisión permanece igual, eso no permite afirmar todavía «Arena aporta cero» porque **Buffalo aún no respondió a la misma pregunta**, ni se construyeron modelos de política capaces de medir P90. No se recomienda ejecutar a ciegas 6×2 + 6×2 modelos que no distinguen ambas reglas. **Consumo real autorizado para este PR:** 0 nuevos OMC, 0 POST Cloudflare, 0 GET R2 privados; 12 llamadas de feedback, 12 llamadas a política y 12 persistencias internas sin costo de proveedor.

**Siguiente paso dentro de la misma pregunta:** preparar una nueva generación inicial Buffalo que reciba explícitamente W01 y la política, con revisión por `currentModel` y diagnóstico propio (hasta dos POST si se autorizan). A partir de su representación decidir si hay P90 representable o solo acumulados y, de ser necesario, qué ejecuciones OMC y lecturas R2 privadas están justificadas. Someter **ese presupuesto de consumo** a autorización separada y registrar la respuesta real sin desplazar la pregunta a H1/H2/H3.

**Revisor Astra:** verificar recibos CT02 por padre, recuperación antes de la decisión, prueba de carril, discrepancia entre cobertura y predicción, `what_if` transversal y estado Buffalo pendiente. Veredicto `Q75_DM_OWN_POLICY_ACCEPT` / `Q75_DM_OWN_POLICY_FIX` por HEAD. No fusionar hasta aceptación.
