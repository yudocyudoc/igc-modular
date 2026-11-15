# Arena V2.1 — P11: resultados y cálculos SOLO EN GITHUB

**Control del propietario, 14/15 noviembre 2026.** Toda ejecución de datos, cálculo científico, resultado e informe deben generarse en GitHub, **nunca en el entorno del asistente**.

## Corrección obligatoria de procedencia

Las cifras de P11 publicadas anteriormente en el chat y en un comentario del PR #28 procedían de un cálculo hecho fuera de GitHub. Se corrigió ese comentario. **Esos números no son evidencia oficial y no deben usarse para cerrar P11/P12 ni apoyar una decisión.**

Los checks verdes del PR #28 prueban el código con **fixtures ficticios**, no el ZIP auténtico. La implementación no es una ejecución GitHub real hasta que exista un run privado con hashes, logs, artifact y atestación. El PR permanece en draft.

## GitHub público versus custodia privada

`yudocyudoc/igc-modular` es **público**. Nunca subir a él el ZIP auténtico, truth, la clave HMAC o la SQLite privada; tampoco adjuntarlos como artifact de sus Actions públicos.

Se incorpora el workflow reusable `.github/workflows/coffee-v2-p11-private-replay.yml`, que **sólo** acepta un repositorio GitHub invocante **PRIVATE** y verifica su privacidad antes de descargar archivos. No corre automáticamente en el PR público.

El workflow reutiliza código público fijado al commit `50b146e2aa1eabd4fab260ab8914b989aae4bb4f` y exige este hash exacto del ZIP: `dd18a787a1ac3dcd065fe54bff9a2f567d945c60d16e7a646444dacaa6ffbef9`.

## Preparación del repositorio privado en GitHub

El propietario necesita configurar **un repositorio PRIVATE de GitHub** para la custodia (este PR no lo crea ni copia datos automáticamente):

1. En **Releases** del repositorio privado, subir el ZIP original como asset llamado exactamente `paquete_sintetico_pico_v1.zip`; conservar el tag exacto.
2. En **Settings → Secrets and variables → Actions**, establecer un secreto persistente `P11_CUSTODY_HMAC_KEY_B64` con al menos **32 bytes aleatorios** en base64. No publicarlo ni regenerarlo para cada corrida: de lo contrario cambia la partición P12.
3. Crear en el repositorio privado el archivo `.github/workflows/coffee-p11-run.yml` con este contenido:

~~~yaml
name: Arena V2.1 P11 — auténtico, privado
on:
  workflow_dispatch:
    inputs:
      source_release_tag:
        description: Tag exacto del Release privado con el ZIP fijado
        type: string
        required: true
permissions:
  contents: read

jobs:
  run-p11:
    uses: yudocyudoc/igc-modular/.github/workflows/coffee-v2-p11-private-replay.yml@0f3752d639ad60aefe371b29c67ea78715e02002
    with:
      source_release_tag: ${{ inputs.source_release_tag }}
    secrets:
      P11_CUSTODY_HMAC_KEY_B64: ${{ secrets.P11_CUSTODY_HMAC_KEY_B64 }}
~~~

La referencia al workflow reusable está fijada por **commit SHA**, no por rama móvil. Si cambia el workflow, revisar la nueva versión y actualizar explícitamente ese SHA. El repositorio privado debe permitir usar workflows reutilizables de repositorios públicos.

4. En **Actions → Arena V2.1 P11 → Run workflow**, proporcionar el tag exacto de ese Release privado.

## Ejecución GitHub y evidencia exigida

El propio GitHub runner privado:
- comprueba repositorio PRIVATE y ZIP original por SHA antes de utilizarlo;
- recupera la clave desde su secreto GitHub y crea el catálogo de custodia P01/P02;
- genera las vistas autorizadas P02/P05/P12 en un directorio efímero **privado**, excluyendo EVALUATION y reserva V1;
- ejecuta P11 B0/S5 con el protocolo y dossier fijados en el commit;
- genera `paired-sensitivity.csv`, `economics-conditional.csv`, `p11-conditional-summary.json`, `REVIEW.md`, `receipt.json` y `github-run-attestation.json`;
- publica esos archivos **sólo en el repositorio privado** como Actions artifact `coffee-p11-github-private-evidence` (retención 30 días), con Job Summary y URL del run;
- elimina del runner los archivos temporales: ZIP, clave y SQLite.

**No** publica el ZIP, perfiles POS individuales, verdad, clave o catalogación privada. El run debe ser revisado independientemente antes de llamar oficiales a sus cifras.

La configuración económica sigue siendo **ilustrativa**; una ejecución reproducible en GitHub no prueba rentabilidad, saturación ni causalidad empresarial. El generador sintético usa la forma visual de 104 minutos, por lo que tampoco convierte automáticamente el ensayo en G3 independiente.

**Estado hasta ejecutar este workflow:** `P11_CODIGO_CON_FIXTURES_APROBADOS / P11_GITHUB_CORPUS_REAL_PENDIENTE`.
