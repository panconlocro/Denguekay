# ADR 0002: rama de integración `develop` y `main` como producción

- **Estado:** propuesta (fase 0 del encargo `docs/backend/prompt_api_v1.md`); se acepta al mergear su PR.
- **Fecha:** 29/10/2026.
- **Punto de partida:** `main` en `8dc1735` (merge del PR #6, `refactor/registry-and-docs`, cierre de las
  fases 4 y 5 del [ADR 0001](0001-repo-restructure.md)). `develop` se creó desde ese mismo commit.

## Contexto

Hasta ahora `main` era la única rama permanente y todo cambio entraba a ella por PR. Con el encargo de la
API v1 cambian dos cosas:

- Rosa sigue experimentando con el modelo y Nicolás empieza el frontend en paralelo; los dos necesitan
  un punto de integración estable sin que cada PR llegue a producción.
- El diseño físico del documento OE2 (sección 3) despliega la API en Render y el frontend en Vercel
  desde la rama de producción. Si `main` recibe cada PR, cada PR despliega.

## Decisión

| Rama | Papel | Recibe PR desde |
|---|---|---|
| `main` | producción: cada merge despliega (Render y Vercel, según OE2, cuando exista el despliegue) | `develop` (release) o `fix/` (hotfix) |
| `develop` | integración: aquí se juntan el backend, el frontend y el modelo | `feat/`, `fix/`, `refactor/`, `docs/`, `chore/`, `exp/` |

1. **Ramas de trabajo.** Todas las ramas `feat/`, `fix/`, `refactor/`, `docs/`, `chore/` y `exp/` salen
   de `develop` y vuelven por PR a `develop` con el CI en verde. Nadie hace commits directos en `main`
   ni en `develop`.
2. **Release.** PR `develop → main` con «Create a merge commit», cuando Rosa lo decida (por sprint o por
   entrega).
3. **Hotfix.** Rama `fix/<nombre>` desde `main` → PR a `main`; después, PR `main → develop` con merge
   commit (sin rebase) para que `develop` no pierda la corrección.
4. **Experimentos de Rosa.** `exp/<nombre>` desde `develop`; los estudios van en `research/06_<nombre>/`
   y nunca tocan `apps/`.
5. **Frontend de Nicolás.** `feat/web-<pantalla>` desde `develop`, solo dentro de `apps/web/`.
6. **Tags.** `model/vN` y `study/<nombre>` se ponen en el commit que se congela, esté en la rama que
   esté. Como todo entra con merge commit, esos commits conservan su hash cuando llegan a `develop` y a
   `main`.
7. Siguen vigentes las reglas de `CONTRIBUTING.md`: solo «Create a merge commit», nunca reescribir
   historia publicada (`rebase`, `commit --amend`, `push --force`), Conventional Commits en inglés.

## CI

`.github/workflows/backend.yml` corre en `pull_request` (cualquier rama destino) y, desde este ADR, en
`push` solo a `main` y a `develop`. Antes corría en todo `push` y en todo `pull_request`, así que cada
commit de una rama con PR abierto se probaba dos veces (el grupo de `concurrency` usa `github.ref`, que es
distinto para el push y para el PR, y no cancelaba el duplicado). Una rama sin PR no corre el CI en el
push; se puede lanzar a mano con *Run workflow* (`workflow_dispatch`).

## Configuración en GitHub (la hace Rosa en la web)

Estos pasos no se pueden hacer desde git. Se hacen en `https://github.com/panconlocro/Denguekay`, con
permisos de administración del repositorio:

1. **Rama por defecto → `develop`.** *Settings → General → Default branch*, botón de las flechas,
   elegir `develop` y confirmar. Así los PR nuevos apuntan a `develop` por defecto.
2. **Reglas de protección de `main` y `develop`.** *Settings → Rules → Rulesets → New ruleset → New
   branch ruleset* (o *Settings → Branches → Add classic branch protection rule*, si se prefiere la
   forma clásica). Una regla con *Target branches* `main` y `develop` (o una por rama), *Enforcement
   status: Active*, y marcar:
   - *Restrict deletions* (prohibir borrado);
   - *Block force pushes* (prohibir force push);
   - *Require a pull request before merging* (sin aprobaciones obligatorias si el equipo es de dos y
     cada uno mergea lo suyo; con 1 aprobación si se quiere revisión cruzada);
   - *Require status checks to pass*, agregando los cuatro checks del CI: `Python 3.12 / ubuntu-latest`,
     `Python 3.12 / windows-latest`, `Python 3.12 / macos-latest` y `Python 3.12 / PostgreSQL 18`
     (aparecen en el buscador después de que el CI haya corrido al menos una vez).
   - Si se usan *Rulesets*, en *Bypass list* no agregar a nadie, o solo a la administradora para
     emergencias.
3. **Método de merge.** *Settings → General → Pull Requests*: dejar marcado solo *Allow merge commits*
   y desmarcar *Allow squash merging* y *Allow rebase merging*.
4. **Borrar ramas mergeadas.** En la misma sección, activar *Automatically delete head branches*. No
   borra `develop` ni `main` porque están protegidas contra borrado.

## Consecuencias

- Un PR mergeado en `develop` no despliega; solo el release `develop → main` llega a producción.
- Las ramas de trabajo se crean con `git switch -c <prefijo>/<nombre> origin/develop` después de
  `git fetch`.
- Los hotfix exigen dos PR (a `main` y de `main` a `develop`).
- Mientras no exista el despliegue (encargo aparte), `main` es la rama estable de referencia y `develop`
  la de trabajo diario.
