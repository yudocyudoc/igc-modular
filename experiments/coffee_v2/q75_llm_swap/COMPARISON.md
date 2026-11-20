# Q75 · sustitución de proveedor LLM (dos POST, sin reintentos)

**Alcance:** prueba exploratoria sin modificación del prompt, esquema JSON, límites ni parámetros de generación originales. Cuerpo del POST extraído del [run auténtico 44672512041](https://github.com/yudocyudoc/igc-modular/actions/runs/44672512041), archivo `provider/cloudflare-effective-request.json`.

**SHA-256 del cuerpo de la solicitud:** `b98b5776bfd184b46dc754d4e8ed5ba8f25df72309195afc46fbcad65deb3b3b`. Se usó el **mismo cuerpo** para ambos modelos; cambió exclusivamente la ruta modelo de Cloudflare. No se invocó el SDK `Engine.generate` en estos dos POST; se transmitió directamente al proveedor la petición efectiva que dicho motor produjo anteriormente. Por ello esta prueba compara proveedores ante la **misma pregunta nativa de Buffalo**, no toda la ruta del SDK nuevamente.

| Modelo | Intentos | Resultado |
|---|---:|---|
| `@cf/google/gemma-4-26b-a4b-it` | 1 | HTTP 408, Cloudflare 3046: `Request timeout`. Sin respuesta de modelo. No volver a intentar con este presupuesto. |
| `@cf/thinkingmachines/inkling-2-small` | 1 | Respuesta HTTP exitosa, `success=true`, `finish_reason=stop`, JSON decodificable. 6116 tokens entrada, 11304 salida. |

## Primera lectura de Inkling 2 Small

- Devuelve una construcción SD con **37 variables**: 7 stocks, 6 flujos, 24 auxiliares, y **39 relaciones causales**.
- Conserva explícitamente 46 pedidos, 53 bebidas, 33 con leche, una sola W01, 2 baristas, 2 puestos de preparación, 3 grupos, un pase y sin limpieza por bebida.
- Se abstiene de inventar un P90 por pedido y dice que su representación es una **aproximación agregada**, no un despachador exacto. Representa la prioridad mediante `milk_policy_weight` y `milk_policy_bias`, no mediante selección FCFS/LECHE de tareas ejecutables con bloqueo de W01.
- **Problema estructural objetivo:** el stock `milk backlog` declara `inflows: ["remove flow"]`, sin separación por mezcla; y `ready handoff` también tiene `inflows: ["remove flow","milk flow"]`. La salida de retirada alimenta simultáneamente ambas colas y el flujo de leche después añade entregas de nuevo: **no es una bifurcación conservativa 33/20**. Aunque la explicación afirma la bifurcación correcta, la estructura efectiva no la ejecuta. No simular ni inferir efecto operativo de este modelo sin revisión.
- Su propia fórmula `milk_flow = milk_backlog * milk_fraction / milk_time * wand_availability * milk_policy_bias` no acredita una reserva atómica de W01 ni la excepción de tareas manuales ejecutables con W01 ocupada.
- Por tanto: **se obtuvo una respuesta estructural válida como JSON, pero todavía no un modelo válido para el contraste Q75**.

## Frontera

No hay nueva ejecución de OMC, validación de política por pedido, revisión Buffalo, retroalimentación ATMS ni R2 privado. El uso y coste de Gemma quedan indeterminados tras timeout. El estudio de capacidades multimodales o papel de Inkling como experto/revisor sería **otra fase**, no inferible de esta salida textual. El experimento de prioridad de leche vs FCFS sigue abierto.

Archivos asociados: `gemma4_response.json` e `inkling_response.json`, ambos con el resultado crudo del proveedor y sus recibos.
