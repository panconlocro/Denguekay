# Cómo contribuir a Denguekay

Reglas de control de versiones del equipo. Rigen desde la limpieza del 27/10/2026
(tag `pre-restructure`). La estructura de carpetas está en `docs/estructuraRepo.md`.

## Ramas

- `main` es la única rama permanente. Nadie hace commits directos en `main`.
- Cada cambio va en una rama corta que sale de `main`, con nombre en inglés y
  kebab-case, y uno de estos prefijos:

  | Prefijo | Uso | Ejemplo |
  |---|---|---|
  | `feat/` | funcionalidad nueva | `feat/risk-map-endpoint` |
  | `fix/` | corrección de un error | `fix/ubigeo-leading-zeros` |
  | `refactor/` | reorganizar código sin cambiar su comportamiento | `refactor/serving-adapters` |
  | `docs/` | solo documentación | `docs/model-v2-report` |
  | `chore/` | mantenimiento, dependencias, CI, configuración | `chore/git-conventions` |
  | `exp/` | experimento o estudio de modelado | `exp/climate-lags` |

- La rama se borra después del merge.

## Commits

- Se usa [Conventional Commits](https://www.conventionalcommits.org/es/v1.0.0/)
  en inglés: `tipo(alcance opcional): descripción en imperativo`.
  Ejemplos: `feat(api): add risk map endpoint`, `fix(serving): keep ubigeo as string`.
- Tipos: `feat`, `fix`, `refactor`, `docs`, `chore`, `test`, `perf`, `ci`, `build`.
- Un commit por cambio lógico. Si el cambio rompe un contrato (API, esquema, artefactos),
  se marca con `!` (`feat(api)!: ...`) y se explica en el cuerpo del mensaje.

## Pull requests

- Todo entra a `main` por un PR, y solo se mergea con el CI en verde
  (`.github/workflows/backend.yml`: la suite completa en Linux, Windows y macOS,
  más las pruebas sobre PostgreSQL).
- **Siempre con «Create a merge commit».** Nunca «Squash and merge» ni «Rebase and merge»:
  los informes y preregistros citan hashes concretos (por ejemplo, `d6bd0be` o `424a148`),
  y esos dos métodos crean commits nuevos y dejan esas citas sin destino en `main`.
- Por la misma razón, la historia publicada no se reescribe: nada de `rebase`,
  `commit --amend` ni `push --force` sobre commits que ya estén en el remoto.

## Tags

Los tags son anotados (`git tag -a`) y se suben con `git push origin <tag>`.

| Tag | Cuándo se crea | Apunta a |
|---|---|---|
| `model/vN` | al congelar una versión de modelo | el commit que congela la configuración |
| `study/<nombre>` | al cerrar un estudio (nombre en inglés y kebab-case) | el último commit del estudio |
| `archive/<rama>` | antes de borrar una rama histórica | la punta de la rama |

Tags vigentes: `model/v0` (backend TB1, `3d59090`), `model/v1` (`d6bd0be`),
`model/v2` (`424a148`, vigente), `study/horizon-architecture` (`808c340`),
`study/fe-hyperparameters` (`e4bc7b7`) y `pre-restructure` (`3ad8312`).
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
