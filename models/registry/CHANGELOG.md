# Registro de modelos · CHANGELOG

Cada versión tiene su ficha en `models/registry/<versión>/` (`ficha.md` para leer, `ficha.json` para el código
y los tests). La configuración de una versión congelada no se copia en la ficha: se carga desde el paquete
con `denguekay.model.registry.configuration("<versión>")`. Los artefactos (boosters, predicciones, cachés) no se
versionan: viven en `models/storage/` y `models/experimentos/`.

| Versión | Estado | Tag | Ficha |
|---|---|---|---|
| v2 | vigente (no servida todavía) | `model/v2` (`424a148`) | [v2/ficha.md](v2/ficha.md) |
| v1 | reemplazada por la v2 | `model/v1` (`d6bd0be`) | [v1/ficha.md](v1/ficha.md) |
| v0 | servida hoy (experimental) | `model/v0` (`3d59090`) | [v0/ficha.md](v0/ficha.md) |

## 2026-10-28 · Registro creado (reestructuración, fase 4)

- Se crea el registro con las fichas de v0, v1 y v2 ([ADR 0001](../../docs/decisions/0001-repo-restructure.md)).
- Las métricas de selección de v0 pasan de `docs/modeling/metricas/` a `v0/validacion_temporal_compacta.json`
  (decisión D5; mismo contenido). Las predicciones OOS de v0 siguen en `models/experimentos/` porque son un
  artefacto no versionado.
- La huella de v1 y v2 pasa a ser de comportamiento (decisión D1). Las huellas anteriores quedan como
  históricas en cada ficha. Ningún modelo cambió.

## 2026-10-27 · v2 vigente

- v2 = v1 + clima de gold (A3), adoptada por el complemento de clima (comparación 20). Reemplaza a v1.

## 2026-10-27 · v1 congelada

- Configuración final del estudio de feature engineering e hiperparámetros (C3·E3·S4_s3), congelada para la
  evaluación prospectiva de 2026.

## 2026-10 · v0 servida

- Backend TB1: cuatro XGBoost experimentales E1·S1 (clf/reg, h=2 y h=4), elegidos por la validación temporal
  compacta del estudio 03. Ninguno cumple la HU0007-4; se sirven como `experimental: true`.
