# Registro de modelos · CHANGELOG

Cada versión tiene su ficha en `models/registry/<versión>/` (`ficha.md` para leer, `ficha.json` para el código
y los tests). La configuración de una versión congelada no se copia en la ficha: se carga desde el paquete
con `denguekay.model.registry.configuration("<versión>")`. Los artefactos (boosters, predicciones, cachés) no se
versionan: viven en `models/storage/` y `models/experimentos/`.

| Versión | Estado | Tag | Ficha |
|---|---|---|---|
| v2 | vigente y servida (experimental) | `model/v2` (`424a148`) | [v2/ficha.md](v2/ficha.md) |
| v1 | reemplazada por la v2 | `model/v1` (`d6bd0be`) | [v1/ficha.md](v1/ficha.md) |
| v0 | registrada (se sirvió hasta la fase 4 de la API v1) | `model/v0` (`3d59090`) | [v0/ficha.md](v0/ficha.md) |

## 2026-10-29 · v2 servida (API v1, fase 4)

- La v2 se sirve con el predictor `v2_e3_s4` (h=2, 3 y 4) como selección experimental: no cumple la HU0007-4.
  El modelo no cambió: es `CONFIG_2026` con la semilla 17, y la paridad con `frozen_configs.predict` se prueba en
  `tests/serving/test_v2_parity.py`.
- Lo nuevo es del servicio: el ajuste al corte de los datos, Platt con las temporadas cerradas 2021–2024 guardado
  como coeficientes, el intervalo de casos NB2 al 0,80 (no calibrado) e importancias SHAP por horizonte.
- Sus OOS 2022–2025 reemplazan a las de la v0 en la serie. La v0 queda registrada como predictor `v0_compact_xgb`.

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
