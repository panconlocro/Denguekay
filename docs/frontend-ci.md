# CI del frontend — soporte de fase 7

Este cambio prepara `.github/workflows/frontend.yml` sin modificar `apps/web/` ni el CI backend.
La rama `chore/web-ci` parte de `origin/develop`; en su base solo existe el README del plan:
**falta `apps/web/package.json`**. La implementación está en `feat/web-dashboard`.
El alcance de soporte se mantiene en tres archivos: el workflow, `docs/architecture.md` y esta guía.

## Entrega completa y orden de integración

La fase 7 se presenta para revisión mediante una **rama de entrega desde `origin/develop`** y un
**PR borrador hacia `develop`**. Se conserva la separación de los commits de implementación y soporte:

1. Guardar los cambios de frontend y soporte en sus ramas respectivas.
2. Crear la rama de entrega desde `origin/develop` e incorporar `feat/web-dashboard` y
   `chore/web-ci`, cada una con un merge commit (`--no-ff`). Las dos ramas originales conservan
   sus puntas e historia; no se reescriben ni se mezclan sus alcances.
3. Publicar el PR borrador desde la rama de entrega hacia `develop`. Así el checkout del PR
   contiene paquete y workflow, y permite ejecutar el CI real **sin fusionar todavía `develop`**.

El snapshot completo debe aportar `package.json`, `package-lock.json`, tipos versionados,
configuración de Playwright y `e2e/serve_api.py`. Con `hasweb=true`, se ejecuta el job completo
automáticamente en el PR. No hace falta una variable de habilitación ni otro cambio de CI.
Rosa revisará los resultados antes de decidir la integración mediante merge commit.
Hasta contar con una ejecución completa y satisfactoria del CI del PR no se afirma que esté verde;
el cierre de fase 7 requiere además la revisión de Rosa.

Como alternativa, el soporte puede entrar antes que el frontend por un PR separado a `develop`.
Mientras falte `package.json`, `detectar` publica `hasweb=false`, un aviso y un resumen; `pruebas`
queda **skipped**. No se instalan dependencias ni se simulan comprobaciones aprobadas.
Al llegar el paquete, el CI se ejecuta en su PR y en los pushes a las ramas permanentes.
La omisión previa no certifica la entrega del frontend.

No se emplean filtros por rutas: cualquier PR puede afectar el contrato o las fixtures. También
se ejecuta por push a `main`/`develop` y `workflow_dispatch`. Los PR prueban el checkout de
integración predeterminado de GitHub; no se usa `pull_request_target`.

## Qué ejecuta cuando existe el paquete

- Ubuntu, Node 22 y Python 3.12; permisos `contents: read`, sin credenciales persistidas ni secretos.
  Concurrencia por workflow/ref, cancelando la ejecución anterior. El backend conserva su workflow.
- Caché npm ligada a `apps/web/package-lock.json`; instalación estricta con `npm ci`.
  Si existe el paquete pero falta el lockfile, un script o la API de fixtures, falla: no se omiten.
- `python -m pip install -r requirements.txt`, editable `--no-deps` y `pip check`.
  Se necesitan las dependencias completas: la API temporal reutiliza `TestAPIReal`, GX y módulos
  de serving/modelo para un ajuste mínimo sobre fixtures versionadas. `requirements-api.txt`
  cubre el runtime liviano, pero no este constructor de pruebas.
- `npm run api:generate` y `git diff --exit-code -- ./src/api/schema.d.ts`: el generador consume
  `docs/backend/openapi_v1.json`; además se exige que el esquema ya esté versionado.
  El prefijo `./` también se usa en `git ls-files`: respeta la guarda de rutas de
  `tests/test_layout.py`, que escanea `.github/` y rechaza referencias al antiguo paquete.
- `npm run lint`, `npm run format:check`, `npm test` y `npm run build` (incluye `tsc -b`).
- `npx playwright install --with-deps chromium`, API temporal en `127.0.0.1:18000`, espera
  acotada de `/api/v1/salud` y `npm run test:e2e`. Si el proceso muere o no llega a salud,
  falla con su log; un trap detiene y espera el proceso al terminar, incluso tras fallos.
- Playwright arranca su Vite en 5174, con dos workers y perfiles escritorio/móvil. Su configuración
  retiene trazas y capturas de fallos. La rama frontend incorpora axe y recorridos de accesibilidad
  para seis vistas; su ejecución queda pendiente del snapshot integrado. Si el job falla, se
  conservan `test-results/`,
  `playwright-report/` si existe, log de API y respuesta de salud durante 14 días. No se archivan
  la BD temporal, storage, modelos ni datos del proyecto.

Se usan `actions/checkout@v7`, `actions/setup-python@v7` y `actions/upload-artifact@v7`, como
en el workflow backend existente, y `actions/setup-node@v6` con Node 22 y `cache-dependency-path`,
según su [documentación oficial](https://github.com/actions/setup-node/blob/v6/README.md).
Se conservan esos majors solicitados; no se selecciona automáticamente un major posterior.

## Aislamiento y alcance de la evidencia

El entorno fija `VITE_DATA_SOURCE=fixtures`, `WEB_TEST_SOURCE=fixtures`,
`VITE_API_BASE_URL=/api/v1`, `API_PROXY_TARGET=http://127.0.0.1:18000`,
`DATABASE_URL=""`, `API_KEY=""`, `DENGUEKAY_XGB_DEVICE=cpu` y `DENGUEKAY_XGB_NJOBS=2`.
Las variables `VITE_*` son públicas y no contienen claves.

`apps/web/e2e/serve_api.py` crea una SQLite y storage temporales mediante `TestAPIReal`;
valida muestras y ajusta/publica pequeños modelos v0 con h=2 y h=4. El estado sin modelo en
h=3 también es parte de la prueba. Algunas predicciones se alteran expresamente para ejercitar
avisos. El navegador consume HTTP; las fixtures no se importan al bundle.

Este perfil comprueba integración y comportamiento de interfaz. No valida métricas de v2,
no prepara la demo, no ejecuta investigación congelada ni entrenamiento productivo, no lee
silver/gold completos ni escribe `data/`. No se usa la BD ni el storage del entorno real.
El perfil local `demo-v2` es independiente: abre una demo previamente preparada en
`models/serving/demo/`, por el puerto 18001 y `WEB_TEST_SOURCE=demo-v2`; queda fuera de este CI.

## Validar el workflow localmente sin copiar el frontend

Desde la raíz, con PyYAML disponible en el entorno Python del proyecto:

```bash
python - <<'PY'
from pathlib import Path
import runpy
import subprocess
import yaml

source = Path(".github/workflows/frontend.yml").read_text()
workflow = yaml.load(source, Loader=yaml.BaseLoader)
guards = runpy.run_path("tests/test_layout.py")
assert not guards["LEGACY_PATH"].search(source)
assert not guards["LEGACY_MODULE"].search(source)
blocks = 0
for job in workflow["jobs"].values():
    for step in job["steps"]:
        if "run" in step:
            subprocess.run(["bash", "-n"], input=step["run"], text=True, check=True)
            blocks += 1
print(f"YAML leído; {blocks} bloques Bash comprobados; rutas compatibles con las guardas.")
print("Paquete frontend presente:", Path("apps/web/package.json").is_file())
PY
if command -v actionlint >/dev/null 2>&1; then
  actionlint .github/workflows/frontend.yml
else
  echo "actionlint no disponible; validación específica de Actions pendiente"
fi
git diff --check
```

Esto comprueba sintaxis; no ejecuta los pasos ni emula GitHub Actions. La rama de soporte no
copia `apps/web/`: el paquete llega al snapshot de entrega mediante el merge de la rama frontend.
Repetir estas comprobaciones sobre ese snapshot y ejecutar la secuencia siguiente. Revisar
`npm run test:e2e -- --list` para confirmar que `accessibility.spec.ts` entra en el perfil
de fixtures y cubre las seis vistas, además de los recorridos funcionales.

## Comandos locales pendientes con el frontend integrado

Ejecutar en un checkout que ya tenga el paquete. Usar un entorno Python 3.12 del proyecto y
Node 22. En macOS, XGBoost requiere OpenMP; `playwright --with-deps` corresponde al runner Linux.
Desde la raíz del repositorio:

```bash
export DATABASE_URL="" API_KEY=""
export DENGUEKAY_XGB_DEVICE=cpu DENGUEKAY_XGB_NJOBS=2 MPLBACKEND=Agg
export VITE_DATA_SOURCE=fixtures WEB_TEST_SOURCE=fixtures
export VITE_API_BASE_URL=/api/v1 API_PROXY_TARGET=http://127.0.0.1:18000
python -m pip install -r requirements.txt
python -m pip install -e . --no-deps
python -m pip check
cd apps/web
npm ci
git ls-files --error-unmatch ./src/api/schema.d.ts
npm run api:generate
git diff --exit-code -- ./src/api/schema.d.ts
npm run lint
npm run format:check
npm test
npm run build
npx playwright install --with-deps chromium
```

Después, desde la raíz, en una terminal con el mismo entorno Python:

```bash
python apps/web/e2e/serve_api.py
```

En otra terminal, con las variables anteriores y desde la raíz:

```bash
curl --fail http://127.0.0.1:18000/api/v1/salud
cd apps/web
npm run test:e2e
```

Detener la API con Ctrl+C al terminar. En GitHub Actions, el arranque, la espera y la limpieza
ocurren en el mismo paso para conservar el PID y el trap. Ante un fallo de navegador,
`npx playwright show-trace test-results/<caso>/trace.zip` permite revisar la traza descargada.

El manual ya generado va en `apps/web/public/manual-usuario.pdf`; sus fuentes compartidas están
en `apps/web/src/content/help.json` y el generador en `apps/web/tools/build_manual.py`.
Regenerarlo requiere `reportlab` y `pypdf`, más revisión visual; este CI no lo regenera.
Los SVG locales y su procedencia van en `apps/web/public/assets/` y su `README.md`.

## Evidencia de este cambio de soporte

La comprobación local se limita a la estructura del workflow, sintaxis de sus bloques Bash,
ruta de omisión con el paquete realmente ausente, whitespace y alcance del diff. Los comandos
de instalación, generación del contrato, lint, formato, pruebas, build y E2E anteriores quedan
**pendientes** hasta disponer del snapshot frontend. Tampoco se ejecutó el workflow en GitHub.
No hay resultado verde del frontend que pueda atribuirse a este worktree.

Resultados locales del soporte:

- PyYAML 6.0.3: lectura sin claves duplicadas, eventos, permisos, output y condición comprobados.
- `bash -n`: los 10 bloques `run` pasan sin ejecutar sus comandos.
- Detector ejecutado desde este worktree: `hasweb=false`, aviso y resumen de omisión comprobados.
- `test_layout.py`: pasan sus seis pruebas usando el paquete de este worktree mediante `PYTHONPATH`.
  Como el workflow nuevo aún no está en el índice, también se aplicaron directamente sus dos
  expresiones de detección al archivo nuevo: sin coincidencias prohibidas.
- `git diff --check` sin errores; backend y `apps/web/` sin cambios.
- `actionlint` no está instalado; esa validación queda pendiente.

En el checkout de implementación se ejecutó la suite completa tras instalar Optuna y el paquete
editable: **465 pruebas, 4 fallos, 30 omisiones y 0 errores**. Se identificaron tres fallos de
igualdad de flotantes en gold y uno de predicciones congeladas en CPU. El log local está en
`/private/tmp/denguekay-phase7-python.log`. Ese resultado no demuestra un CI verde.
Los fallos y omisiones deben contrastarse con los resultados y logs del snapshot de entrega.

La revisión visual, accesibilidad y demo v2 conservan sus verificaciones correspondientes;
este soporte no las da por aprobadas ni cierra por sí solo la fase 7. El PR borrador reúne el
snapshot para comprobarlo en GitHub; la fusión hacia `develop` requiere revisión y CI satisfactorio.
