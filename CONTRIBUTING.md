# Cómo contribuir a Denguekay

Reglas del proyecto y de control de versiones del equipo. Las de control de versiones rigen desde la
limpieza del 27/10/2026 (tag `pre-restructure`). La estructura de carpetas está en `docs/architecture.md`.

## Reglas del proyecto

- **Estructura:** antes de crear un archivo o una carpeta, lee `docs/architecture.md` y respétalo. Si algo
  nuevo no cabe, actualiza ese documento en el mismo cambio.
- **`data/` es de solo lectura.** Ningún análisis ni experimento escribe, borra o modifica `data/` (bronze,
  silver, reference ni gold). Si hay que corregir datos, se cambia el pipeline (notebooks 01–09 de
  `pipelines/notebooks/` y `src/denguekay/data/processing/`) y se regenera.
- **Variables derivadas:** se calculan solo en memoria, con funciones de `src/denguekay/features/` y un test
  de no fuga por perturbación, y nunca se guardan en `data/`. Gold persiste solo llaves, objetivo, etiqueta y
  las variables de la configuración vigente; si una variable entra a esa configuración, se cambia
  `src/denguekay/features/gold.py` y gold se regenera con `pipelines/notebooks/10_silver_to_gold.ipynb`.
- **`ubigeo` es texto de seis dígitos** (con ceros a la izquierda) en todo el pipeline; nunca un entero. La
  llave del panel es `(ubigeo, anio, semana)`.
- **Rutas** siempre desde `src/denguekay/config/paths.py`; nada de rutas absolutas en el código.
- **Paquete o notebook:** la lógica que se reutiliza o pasa de unas diez líneas va en
  `src/denguekay/<subpaquete>/` (o en `apps/api/`), con su test en `tests/<subpaquete>/` si no es trivial. Los
  notebooks orquestan, muestran y comentan.
- **Investigación congelada:** los estudios viven en `research/NN_<nombre>/` con un README que dice cómo
  reproducirlos desde su tag. No se vuelven a correr en `develop`, `main` ni el CI, y el producto nunca los
  importa (`tests/test_layout.py` lo comprueba).
- **Guardas de equivalencia:** la línea base de `tests/fixtures/equivalence/` nunca se regenera para que un
  test pase; si una guarda falla, hubo un cambio de comportamiento.
- **Backend:** el documento OE2 (`docs/backend/especificacion_oe2.md`, `docs/backend/ddl_oe2.sql`) es la
  fuente de verdad; toda diferencia se justifica en `docs/backend/desviaciones_oe2.md`. Las migraciones de
  `src/denguekay/db/migrations/` son la autoridad del esquema (nunca `create_all` al arrancar la API). Los
  tests usan una BD temporal, nunca la de trabajo.
- **Citas y cifras:** solo referencias reales y verificadas. Una cifra en un informe tiene que salir de
  código ejecutado; se distingue observación, hipótesis y conclusión, y no se usa lenguaje causal.
- **Archivos:** UTF-8; no se cambian los finales de línea de los archivos existentes.
- **Herramientas de IA:** la configuración personal de asistentes (`CLAUDE.md`, `AGENTS.md`, `.claude/`,
  `.codex/`) no se versiona; cada quien la mantiene en su clon.

## Ramas

Desde el 29/10/2026 hay dos ramas permanentes ([ADR 0002](docs/decisions/0002-develop-branch.md)):

- `main` = producción. Cada merge a `main` despliega (cuando exista el despliegue de OE2). Solo
  recibe PR desde `develop` (release) o desde una rama `fix/` (hotfix).
- `develop` = integración. Es la rama por defecto (una vez configurada en GitHub, ver el ADR) y de
  donde sale todo el trabajo.
- Nadie hace commits directos en `main` ni en `develop`.
- Cada cambio va en una rama corta que sale de `develop` (`git fetch` y
  `git switch -c <prefijo>/<nombre> origin/develop`), con nombre en inglés y
  kebab-case, y uno de estos prefijos:

  | Prefijo | Uso | Ejemplo |
  |---|---|---|
  | `feat/` | funcionalidad nueva | `feat/risk-map-endpoint` |
  | `fix/` | corrección de un error | `fix/ubigeo-leading-zeros` |
  | `refactor/` | reorganizar código sin cambiar su comportamiento | `refactor/serving-adapters` |
  | `docs/` | solo documentación | `docs/model-v2-report` |
  | `chore/` | mantenimiento, dependencias, CI, configuración | `chore/git-conventions` |
  | `exp/` | experimento o estudio de modelado | `exp/climate-lags` |

- La rama se borra después del merge (GitHub lo hace solo).
- **Release:** PR `develop → main` con merge commit, cuando Rosa lo decida (por sprint o entrega).
- **Hotfix:** `fix/<nombre>` desde `main` → PR a `main`; luego PR `main → develop` con merge commit.
- **Experimentos:** `exp/<nombre>` desde `develop`; cada estudio va en una carpeta nueva
  `research/NN_<nombre>/` (el siguiente número libre) y nunca toca `apps/`.
- **Frontend de Nicolás:** `feat/web-<pantalla>` desde `develop`, solo dentro de `apps/web/`.

## Commits

- Se usa [Conventional Commits](https://www.conventionalcommits.org/es/v1.0.0/)
  en inglés: `tipo(alcance opcional): descripción en imperativo`.
  Ejemplos: `feat(api): add risk map endpoint`, `fix(serving): keep ubigeo as string`.
- Tipos: `feat`, `fix`, `refactor`, `docs`, `chore`, `test`, `perf`, `ci`, `build`.
- Un commit por cambio lógico. Si el cambio rompe un contrato (API, esquema, artefactos),
  se marca con `!` (`feat(api)!: ...`) y se explica en el cuerpo del mensaje.

## Pull requests

- Todo entra a `develop` (o, en un release o hotfix, a `main`) por un PR, y solo se mergea con
  el CI en verde (`.github/workflows/backend.yml`: la suite completa en Linux, Windows y macOS,
  más las pruebas sobre PostgreSQL). El CI corre en cada PR y en cada push a `main` y `develop`.
- **Siempre con «Create a merge commit».** Nunca «Squash and merge» ni «Rebase and merge»:
  los informes y preregistros citan hashes concretos (por ejemplo, `d6bd0be` o `424a148`),
  y esos dos métodos crean commits nuevos y dejan esas citas sin destino en `develop` y `main`.
- Por la misma razón, la historia publicada no se reescribe: nada de `rebase`,
  `commit --amend` ni `push --force` sobre commits que ya estén en el remoto.

## Tags

Los tags son anotados (`git tag -a`) y se suben con `git push origin <tag>`.

`model/vN` y `study/<nombre>` se ponen en el commit que se congela, esté en la rama que esté; los merge
commits conservan ese hash al llegar a `develop` y a `main`. `api/vX.Y.Z` se pone después del release, en el
merge commit de `main`.

| Tag | Cuándo se crea | Apunta a |
|---|---|---|
| `model/vN` | al congelar una versión de modelo | el commit que congela la configuración |
| `study/<nombre>` | al cerrar un estudio (nombre en inglés y kebab-case) | el último commit del estudio |
| `api/vX.Y.Z` | en cada release `develop → main` que cambia la API; `X.Y.Z` es la versión del contrato (`info.version`, `X-Version-Contrato`) | el merge commit del release en `main` |
| `archive/<rama>` | antes de borrar una rama histórica | la punta de la rama |

Tags vigentes: `model/v0` (backend TB1, `3d59090`), `model/v1` (`d6bd0be`), `model/v2` (`424a148`),
`model/v3` (`6894012`), `model/v4` (`305005c`, congelada para el paper), `study/horizon-architecture`
(`808c340`), `study/fe-hyperparameters` (`e4bc7b7`), `study/model-improvement` (`6894012`),
`api/v1.1.0`, `pre-restructure` (`3ad8312`) y `restructure-done` (`8dc1735`, cierre del ADR 0001).
Las ramas anteriores a la limpieza viven como `archive/*`, con `/` cambiado por `-` en el
nombre. Para recuperar una: `git switch -c experiment/model-architecture archive/experiment-model-architecture`.

## Idioma

- **Código en inglés** desde el 27/10/2026: identificadores, comentarios y docstrings
  del código nuevo. El código existente no se renombra solo por el idioma.
- **Sin cambios hasta nuevo aviso:** el esquema de base de datos sigue el documento OE2
  (`docs/backend/especificacion_oe2.md`, `docs/backend/ddl_oe2.sql`), y las columnas de los
  datos (`data/`, gold, silver) mantienen sus nombres actuales.
- **Documentación en español:** `docs/`, el markdown de los notebooks, los informes y
  las etiquetas de los gráficos.

## Antes de abrir un PR

```powershell
.\.venv\Scripts\python -m unittest discover -s tests
```

Las pruebas de PostgreSQL corren en local solo si `DENGUEKAY_PG_PRUEBAS_URL` apunta a
una base desechable cuyo nombre contenga «prueba». En el CI siempre corren.

Durante la reestructuración, un PR de `refactor/` solo entra si `tests/test_equivalence.py` pasa
completo en local (las predicciones de V1 y V2 necesitan los datos, que no están en el CI).
