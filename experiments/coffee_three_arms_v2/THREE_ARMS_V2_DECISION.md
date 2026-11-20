# Arena cafetería · PR1 v2 · reconstrucción auténtica de D/M/B y Hydra

**RETROSPECTIVA, NO CIEGA.** Los ocho artefactos son resultados auténticos ya publicados.
No se ejecutó un productor, OpenModelica, R2 privado ni un nuevo ATMS transversal.

## Las cuatro respuestas para la decisión

**Hydra sola:** no cambiar prioridades del local; observar una oportunidad
de carga con el estado simultáneo de los tres grupos, extracción, retirada
y tareas/aptitudes de los operadores. H1, H2 y H3 pueden coexistir.

**Qué aportaron los métodos:** D ratificó 6 candidatos B0, M se abstuvo de
revisar 6 candidatos por no disponer de dos observaciones tardías; Buffalo
revisó su propio padre mediante `currentModel` y produjo un nativo G1 R1.
P08 D/M añadió una hipótesis de capacidad agregada de preparación, no
una representación de competencia entre barista y grupo concreto.

**Decisión tras añadir D/M/B:** no cambia la acción ni se demuestra
otra observación operativa que distinga H1/H2/H3 frente a Hydra.
D/M P08 añaden perspectiva estructural; esto NO es confirmación independiente.

**Única observación dirigida:** cuando una bebida pueda cargarse,
registrar en una misma ventana grupos G01/G02/G03 extrayendo / libres /
esperando retirada, elegibilidad de la tarea y ocupación/aptitud manual.
Si la visibilidad es parcial, clasificar episodio indeterminado.

## Evidencia original B0: seis D, seis M y Buffalo R1

| Método | Modelo / regla | Resultado comprobado | Límite |
|---|---|---|---|
| Gramática D (original B0) | 6 modelos stock-flow; 12 G2 D/M | 6 RATIFIED | Ratificar no valida física |
| Moléculas M (Short E1 original B0) | 6 AST completos; cola acotada | 6 ABSTAINED (sin dos retiros tardíos) | Abstenerse de revisión no cancela predicción |
| Buffalo R1 | padre `sha256:5c7fc9c73a5f03849d5d…` → hijo `sha256:4dc47264883f36a0f4c1…` | 10→11 variables; 0→12 relaciones | R1 G1, no identifica recursos físicos |

**Buffalo B0:** error absoluto medio en tres cortes sintéticos = 0.894890 pedidos; un acierto del contador no valida H1/H2/H3.
La disposición B en el run inicial de feedback fue **PAQUETE PREPARADO, NO ENVIADO**;
la revisión original ocurrió **después, en otro run**. No fusionar ambos eventos.

### Artefactos de respaldo por candidato y origen

El JSON adjunto incluye 12 filas de candidato con `parent_sha256`, `native_sha256`,
`g2_csv_sha256`, regla, disposición y la proyección temporal del Ledger.
- **g2**: [run 43550618982](https://github.com/yudocyudoc/igc-modular/actions/runs/43550618982), artifact `14094919865`, commit `69638301626dd482556f58eaead298a5c620d9bf`; ZIP `sha256:1f10695e4dcd27ad4f29552c3c954b4ce26efb131594b0b18076f52a26701925`
- **feedback**: [run 43561168032](https://github.com/yudocyudoc/igc-modular/actions/runs/43561168032), artifact `14100770369`, commit `227e7f20137d99d5da122ffb8a0ee93b069548c7`; ZIP `sha256:51b56dc28e5c229a280adf3f38062744992a61dc21dff48973e18f48105d10d8`
- **buffalo_initial**: [run 43537333254](https://github.com/yudocyudoc/igc-modular/actions/runs/43537333254), artifact `14090920829`, commit `399eddbc0d674e8b2370f908a75ba73e694153c3`; ZIP `sha256:70f9e9f846a33cd470b00dbaf0bf189b0b6c7a029b68bd84485f7c6bbe748265`
- **buffalo_r1**: [run 43565759793](https://github.com/yudocyudoc/igc-modular/actions/runs/43565759793), artifact `14102098459`, commit `402cfe945839ca29718c385def6aab9e846ef117`; ZIP `sha256:686db7b34ca177e055a0c4d6fbbef771368baaa412491dad2ed07c1a20a59b65`
- **buffalo_score**: [run 43686325127](https://github.com/yudocyudoc/igc-modular/actions/runs/43686325127), artifact `14150642285`, commit `00ed50a9311a0864b323492935802cbfb86e5101`; ZIP `sha256:1e06057a1d31476ca3df75a2558db8aec54ffe27652aa66db334aa780bfe81b2`

## Extensiones posteriores D/M P08: mismo resultado, soporte compartido

| Carga | Acción | D entregas continuas | M entregas continuas |
|---|---|---:|---:|
| LOWER_PAID_INPUT_Q25 | BASE | 15.742861 | 15.742861 |
| LOWER_PAID_INPUT_Q25 | PREP_CAPACITY_X2 | 15.742861 | 15.742861 |
| LOWER_PAID_INPUT_Q25 | ESPRESSO_CAPACITY_X2 | 15.742861 | 15.742861 |
| HIGHER_PAID_INPUT_Q75 | BASE | 18.248947 | 18.248947 |
| HIGHER_PAID_INPUT_Q75 | PREP_CAPACITY_X2 | 23.134332 | 23.134332 |
| HIGHER_PAID_INPUT_Q75 | ESPRESSO_CAPACITY_X2 | 18.248947 | 18.248947 |

D/M comparten el pulso rectangular de 105 minutos y capacidades nominales
de preparación/espresso/despacho 12/15/100 pedidos/h. La igualdad de
sus trayectorias **no son dos observaciones empíricas independientes**.
Ni duplicar el máximo de espresso en pedidos/h ni esa cola agregada
equivalen a habilitar un grupo físico o disputar trabajo manual.

## Referencia Hydra Q75 (90 segundos supuestos)

- 46 pedidos pagados / 53 bebidas sintéticas; horizonte `103.2370666667` min.
- FCFS P90 `3.725950` min; priorizar carga ΔP90 `+2.163` s, priorizar leche ΔP90 `-3.837` s.
- Espera de carga: `3.7995` → `2.0452` min-tarea; 9 pedidos antes/9 después bajo prioridad de carga.
- FCFS H1 señal `1.4952` min-tarea; H2 señal `2.1114` min-tarea. Son esperas de tareas, **no tiempo de reloj sumable**.
- H3 es estado representado en el motor B; el agregado publicado no permite atribuir un episodio real ni cuantificar su duración en barra.

## Alcance exacto: modelos archivados, no productores completos

Esta reconstrucción **NO ejecutó de nuevo D/M/B** ni les formuló H1/H2/H3.
El veredicto de la tabla habla exclusivamente de la representación nativa archivada:
NO codificar una variable no demuestra incapacidad del método para construirla.

**D B0:** gramática determinista `generic-conservative-chain-search/0.1`,
seis cadenas de 1–3 stocks con/sin pérdida y parámetros supuestos.
La ruta de cafetería invocó primitivas de topología, no una nueva búsqueda
ajustada a observaciones de tareas. Su MAE sintético de retiros acumulados
no identifica qué recurso originó una espera.

**M B0:** seis grafos enumerados del registro específico de cafetería
con cuatro clases distintas: accepted-source, bounded-queue, delivery-counter, first-order-report-filter.
Las alternativas varían tránsito y filtrado de reporte, no operadores
ni reservas de grupos físicos. **M P08:** una sola topología
`AcceptedSource → BoundedQueue preparación → BoundedQueue espresso →
BoundedQueue despacho → DeliveryCounter` en seis casos de parámetros.
No se probaron otras moléculas, catálogos alternativos o archivos Vensim .mdl.

**Buffalo:** B0→R1 es una revisión real y su modelo sellado,
pero de una pregunta sobre retiros acumulados. El nativo R1 no codifica
operadores ni grupos identificados. **PR1 no hizo un nuevo POST Cloudflare**
ni probó si Buffalo puede generar ese detalle bajo otra consigna.

## Capacidad de distinguir H1 / H2 / H3

**Unidad de análisis:** una oportunidad de carga sobre grupo concreto, no el contador acumulado de pedidos.
Los códigos `NOT_ENCODED_IN_ARCHIVED_NATIVE` describen el modelo
publicado; `full_method_H123_capacity_tested=false` impide extrapolarlos
a la capacidad de construcción del método completo.

| Método (versión) | H1 | H2 | H3 | ¿Se le preguntó históricamente? |
|---|---|---|---|---|
| gramática D (original B0 6-candidate stock-flow family) | NOT_ENCODED_IN_ARCHIVED_NATIVE | NOT_ENCODED_IN_ARCHIVED_NATIVE | NOT_ENCODED_IN_ARCHIVED_NATIVE | NO |
| moléculas M (Short E1 original B0) | NOT_ENCODED_IN_ARCHIVED_NATIVE | NOT_ENCODED_IN_ARCHIVED_NATIVE | NOT_ENCODED_IN_ARCHIVED_NATIVE | NO |
| Buffalo (original B0→R1 currentModel) | NOT_ENCODED_IN_ARCHIVED_NATIVE | NOT_ENCODED_IN_ARCHIVED_NATIVE | NOT_ENCODED_IN_ARCHIVED_NATIVE | NO |
| gramática D (P08 3-stage capacity extension) | AGGREGATE_ESPRESSO_PROXY_NOT_GROUP | NO_SHARED_OPERATOR | NO_RETAINED_GROUP | NO |
| moléculas M (P08 versioned BoundedQueue espresso role) | AGGREGATE_ESPRESSO_PROXY_NOT_GROUP | NO_SHARED_OPERATOR | NO_RETAINED_GROUP | NO |
| referencia Hydra (B physical + C diagnostics + policies D) | MODEL_SIGNAL_EXTRACTION_BUSY | MODEL_SIGNAL_MANUAL_BLOCK | STATE_RETAINED_AFTER_EXTRACTION_NO_OBSERVED_LOCAL_DURATION | PARTIALLY |

## Comparabilidad, memoria y atribución

**P08 vs Hydra Q75:** NO se permite restar cuantías, ni comparar P90
con flujos continuos. Cambian: case, input_profile, material_unit, horizon_min, cut_min, intervention, observable, observable_unit.
Por contraste, D P08 y M P08 sí permiten comparar la dinámica
agregada **bajo supuestos compartidos**; eso no prueba independencia.

**ATMS:** PR1 **lee** disposiciones y proyecciones históricas con
cortes `as_known_at`. No ejecuta una nueva retirada de soporte ni
atribuye a ATMS una justificación transversal inexistente.
La prueba de retirar por separado un brazo o la premisa compartida
queda para PR2; dos métodos sobre un supuesto común no equivalen a
dos confirmaciones observacionales.

**Nivel representacional:** demostrado, con límites.
**Nivel informativo:** no se demuestra una observación H1/H2/H3 adicional.
**Nivel decisional:** PENDIENTE DE CONTRASTE PROSPECTIVO INDEPENDIENTE.
No se seleccionó un modelo ganador por MAE retrospectivo.

## Procedencia de las extensiones y de Hydra

- **m_p08**: [run 43702148041](https://github.com/yudocyudoc/igc-modular/actions/runs/43702148041), artifact `14157186844`, commit `68e874821d74bb26c492625e9061716a40333dda`; ZIP `sha256:4391d036017140ec65931f0f6a1aba221c5fba81fbb1bc2e6107b8f406ae42a8`
- **d_p08**: [run 43705604955](https://github.com/yudocyudoc/igc-modular/actions/runs/43705604955), artifact `14157799232`, commit `072cd372bb020cef9cee48f70b5403fe992dbe9f`; ZIP `sha256:9fcab78e7a04afeca9fc9b4543f05df76ca58c7b2044194be540471c11120799`
- **hydra**: [run 44234407455](https://github.com/yudocyudoc/igc-modular/actions/runs/44234407455), artifact `14396368697`, commit `e2da7eeaadd7c9e361ca38090a3de25a161916f3`; ZIP `sha256:2fa54c8b64927140e918c693886a11c9fb3e69f80d8ec1b2dabdf16be12d2cb5`

## Qué queda abierto

PR47/E1 tiene autorización y ejecución separadas. Este lector no presupone
resultado privado Q75 a 30s y no convierte ninguno de los archivos
históricos en una predicción nueva o confirmación empírica independiente.
Los productores nunca respondieron prospectivamente a H1/H2/H3;
PR2 deberá formular la pregunta, preservar padres/versiones y las
disposiciones propias. Sin datos reales comparables, la decisión es
**OBSERVAR, NO CAMBIAR OPERACIÓN**.
