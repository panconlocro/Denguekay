# Registro de modelos · CHANGELOG

Cada versión tiene su ficha en `models/registry/<versión>/` (`ficha.md` para leer, `ficha.json` para el código
y los tests). La configuración de una versión congelada no se copia en la ficha: se carga desde el paquete
con `denguekay.model.registry.configuration("<versión>")`. Los artefactos (boosters, predicciones, cachés) no se
versionan: viven en `models/storage/` y `models/experimentos/`.

| Versión | Estado | Tag | Ficha |
|---|---|---|---|
| v4 | congelada para el paper | `model/v4` | [v4/ficha.md](v4/ficha.md) |
| v3 | vigente y servida (experimental) | `model/v3` | [v3/ficha.md](v3/ficha.md) |
| v2 | reemplazada por la v3 (sigue registrada como `v2_e3_s4`) | `model/v2` (`424a148`) | [v2/ficha.md](v2/ficha.md) |
| v1 | reemplazada por la v2 | `model/v1` (`d6bd0be`) | [v1/ficha.md](v1/ficha.md) |
| v0 | registrada (se sirvió hasta la fase 4 de la API v1) | `model/v0` (`3d59090`) | [v0/ficha.md](v0/ficha.md) |

## 2026-11-17 · Comando de reentrenamiento de la V4

- `python -m denguekay.model.refit_v4` vuelve a ajustar el **mismo modelo** (la V4: `b3_obs`, semilla 17, misma
  configuración) con datos nuevos y deja un paquete en una carpeta nueva; se sirve con la opción `paquete_dir` de
  `serving.paquete.opciones`. **No cambia la versión** ni requiere ficha, Release ni tag nuevos.
- Verificado contra la V4 con su corte (17/10/2026): variables de entrenamiento idénticas, pesos de mezcla y calibración de
  la persistencia iguales, Platt dentro de 5 × 10⁻⁵; el booster no es idéntico bit a bit (depende del número de hilos).
  Detalle en [reentrenamiento.md](../../docs/modeling/reentrenamiento.md).

## 2026-11-17 · Umbrales de aceptación de la US v1.4 (HU0007-4)

- La migración `0009_v4` fija `parametro_sistema.umbrales_aceptacion` en Recall ≥ 0,65, Precision ≥ 0,60, F1 ≥ 0,70 y
  razón de error ≤ 0,90 sobre el bloque `temporadas_2022_2026` (semanas distritales de `temporada_2022` a
  `temporada_2026` agregadas). Las métricas de cada versión V4 llevan ese bloque.
- Con esos umbrales las seis versiones de la V4 (clasificación y regresión en h2, h3 y h4) quedan `validado` (retrospectivo,
  una semilla; el agregado descansa en las temporadas 2022–2024); v0 a v3
  no traen el bloque y quedan `experimental`. Los umbrales se revisaron **después de ver los resultados**; la evaluación
  independiente es la prospectiva 2026-27. No cambia el modelo ni sus boosters.
- Detalle y cifras: [v4/ficha.md](v4/ficha.md#aceptación-hu0007-4-us-v14).

## 2026-11-17 · Actualización semanal de la V4

- `python -m denguekay.pipelines.v4_weekly` actualiza cada semana las fuentes que cambian (Sala Situacional, ERA5-Land,
  CHIRPS y Niño 1+2) en `data/silver/operativo/`, sin el corte congelado, las carga en la BD y emite h2, h3 y h4 con el
  paquete **congelado** `v4_b3_live`, archivando cada emisión (fecha, insumos, pronósticos y vectores). **No cambia el
  modelo ni se reentrena**: la V4 sigue siendo la del tag `model/v4`.
- Política de reentrenamiento: anual, por temporada, a mano ([reentrenamiento.md](../../docs/modeling/reentrenamiento.md)).
  Es un criterio operativo; no se evaluó reentrenar con mayor frecuencia.
- Operación y programación: [docs/backend/operacion.md](../../docs/backend/operacion.md#actualización-semanal-v4).

## 2026-11-15 · Pipeline de datos V4

- `run_all --version v4 --verificar` construye el integrado de confirmados y el gold B3 de h2–h4, y coteja
  los insumos con los manifiestos congelados. La reproducción exacta usa los insumos del Release `model/v4`.
- `v4_b3_live` puede cargar el integrado y las observaciones generadas por el pipeline. La publicación
  conserva el booster y las métricas congeladas. Pasos y resultados en la [guía de V4](../../docs/modeling/reproducir_v4.md).

## 2026-11-12 · v4 congelada para el paper

- `b3_obs` y el comparador `historia_geo` se ajustaron sobre casos confirmados de Piura hasta la SE 41 de 2026.
- La ficha enlaza el manifiesto con las huellas de los diez boosters y los insumos.

## 2026-11-09 · v3 servida (feat/serve-v3)

- La v3 se sirve con el predictor `v3_l5a_d3` como selección experimental (no se evaluó la HU0007-4).
- **Ajuste fuera de la BD:** con la serie desde 2000. El comando sin BD es
  `python -m denguekay.serving.predictors.v3_l5a_d3 --salida <carpeta>`; la publicación es
  `python -m denguekay.serving.publish --seleccionar-experimental`.
- **Paquete:** booster, α, Platt y la `w` de la mezcla 5a, por horizonte.
- **Paridad:** el bloque `temporada_2026` reajustado reproduce las predicciones congeladas (diferencia 0,0 en GPU).
- **Esquema:** migración `0007_v3` con `observacion_semanal.temp_media_era5_land_c` (desviación OE2 9).
- **Gold** suma las 4 columnas de d3; hay que regenerarlo con el notebook 10. La v0 sigue leyendo
  `gold/respaldo_pre_b3`.
- La v2 queda reemplazada y registrada (`v2_e3_s4`); sus OOS dejan la serie y entran las de la v3.
- Con d3, el SHA-256 del archivo gold h2 cambia, pero las 20 columnas de la v2 quedan iguales bit a bit. La ficha de
  la v2 suma `sha256_columnas_v2` (digest de contenido de esas columnas), con el que `v2_e3_s4.prepare` sigue
  reconociendo su gold y comparando su huella. Sin esto, la guarda `test_v2_parity` fallaba con el gold
  regenerado. No se regeneró ninguna línea base.

## 2026-11-09 · v3 vigente

- v3 = L + 5a + d3 con los hiperparámetros del trial 191 (estudio 06, `research/06_model_improvement`):
  - L: la V1 entrenada desde 2005;
  - 5a: el conteo publicado se mezcla con la persistencia;
  - d3: 4 ventanas de temperatura media de ERA5-Land.
- Configuración `CONFIG_V3`; huella de comportamiento en GPU `99a0b26d…494de`.
- Protocolo propio: `docs/modeling/protocolo_v3.md`, que no es el de la v2.
- b3 queda congelada como retadora para la evaluación prospectiva 2026–27.
- La v2 sigue siendo la servida hasta que la v3 entre a serving.
- Los datos y las predicciones de referencia van en el Release de `model/v3`, con su manifiesto en
  `v3/manifiesto_datos.json`.

## 2026-11-02 · Gold limpio con B3

- Ningún modelo cambió. `data/gold/` pasa a tener un solo archivo con la alineación h=2 y 20 columnas: llaves, objetivo,
  etiqueta y las variables de la v2 (`base_6`, A3 y B3). Las demás candidatas se calculan en memoria con `build_gold`.
- Gold h=2: `a5d16663d4030b891d0fbbca81b4a0abfe478e11eb3bb85a9f59d49dc4eb27a3`. Sus 17 columnas previas son idénticas
  bit a bit a las del gold anterior, y B3 es idéntica a `frozen_configs.origins`. La v2 sigue calculando B3 en memoria.
- La v0 y el estudio 03 leen el gold anterior (h=2, h=4 y manifiesto) de `data/gold/respaldo_pre_b3/`, con los mismos
  hashes. Es la única copia y hay que guardarla fuera de la PC.

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
