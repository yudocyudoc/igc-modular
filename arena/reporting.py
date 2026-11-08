"""Readable result and consumption view; never resolves connections or secret values."""
from pathlib import Path


def write_report(result, root):
    run = result["run"]
    score = result.get("fixture_score", result.get("score", {}))
    lines = [f"# Arena · {run['experiment']}", "", f"Estado: **{run['status']}**.",
             f"Tipo de evidencia: `{result['evidence_kind']}`.", ""]
    if result["evidence_kind"] == "INTEGRATION_FIXTURE":
        lines += ["Prueba de integración con fixtures. No ejecutó OMC ni Buffalo y no constituye un resultado científico.", ""]
    lines += ["| Recurso | Límite | Intentos observados | Registro completo | Saldo |",
              "| --- | ---: | ---: | --- | ---: |"]
    for name, item in run["consumption"].items():
        remaining = item["remaining"] if item["remaining"] is not None else "Sin confirmar"
        lines.append(f"| {name} | {item['limit']} | {item['observed_attempts']} | {'Sí' if item['complete'] else 'No'} | {remaining} |")
    lines += ["", "Coste monetario: no confirmado; no se calcula una factura a partir del número de llamadas.", "",
              "| Etapa | Estado | Ejecución |", "| --- | --- | --- |"]
    for item in run["stages"]:
        url = item["detail"].get("url")
        link = f"[Ver ejecución]({url})" if url else "Local"
        lines.append(f"| {item['name']} | {item['state']} | {link} |")
    if score.get("candidate_denominator") is not None:
        lines += ["", f"Plazas conservadas: **{score['candidate_denominator']}**.",
                  f"Pares disponibles: **{score.get('paired_available', 'No informado')}**."]
    lines += ["", "Detalle estructurado: `result.json`. Estado y consumo persistidos en `run.sqlite`.", ""]
    out = Path(root)/"report.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    return out

