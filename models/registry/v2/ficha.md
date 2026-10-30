# V2 · C3+A3·E3·S4_s3 (vigente y servida)

| Campo | Valor |
|---|---|
| Estado | **Vigente y servida**: configuración congelada para la evaluación prospectiva de 2026; desde la fase 4 de la API v1 se sirve como selección experimental (`experimental: true`), con h=2, 3 y 4 |
| Tag | `model/v2` (`424a148`), congelada el 2026-10-27 |
| Configuración | `denguekay.model.frozen_configs.CONFIG_2026` (antes `CONFIGURACION_2026`); se carga con `denguekay.model.registry.configuration("v2")` |
| Reemplaza a | [V1](../v1/ficha.md) |
| Estudio | [`research/05_fe_hyperparameters`](../../../research/05_fe_hyperparameters/README.md), informe [fe_hiperparametros.md](../../../research/05_fe_hyperparameters/docs/fe_hiperparametros.md), «Encargo complementario · clima para el conteo»; tag `study/fe-hyperparameters` (`e4bc7b7`) |
| Métricas de selección | `research/05_fe_hyperparameters/docs/metricas/fe_hiperparametros.json → complemento_clima`; MLflow `fe_hiperparametros_complemento_clima` (`6afc4549fd214a1497636319b3e6844c`) |

## Configuración

La V1 más A3: `hum_rel_media_media5_h2` y `precip_total_mm_media5_h2` (clima de gold, media de 5 semanas hasta
el origen), 11 columnas. Se excluyen los 65 orígenes con nulos de arranque de A3 (semana del 2017-02-05). Todo
lo demás queda idéntico a la V1: E3 · S4_s3 · α dentro de la muestra · hiperparámetros heredados · Platt ·
p ≥ 0,50 · semilla 17.

## Servicio

Predictor `v2_e3_s4` (`denguekay.serving.predictors`), desde la fase 4 de la API v1 (`docs/backend/api_v1_decisiones.md`):

- **Paquete:** `modelos/<codigo_paquete>/manifest.json` con `booster.json` (el regresor multisalida),
  `dispersion.json` (α por horizonte) y `platt.json` (a y b por horizonte). Seis versiones (clasificación y
  regresión × h=2, 3 y 4) que apuntan al mismo manifiesto: `v2-clf-h2-1` … `v2-reg-h4-1`, algoritmo
  `xgboost_multisalida_bn`, `umbral_probabilidad` 0,50.
- **Ajuste:** `fit_e3` con todos los orígenes cuyos tres objetivos cerraron al corte de los datos (semilla 17).
  La publicación recalcula el protocolo por bloques y comprueba la huella de comportamiento cuando gold h=2 es el
  congelado.
- **Probabilidad:** NB2 con la α dentro de la muestra, `k` calculado desde los casos de la BD (no desde la columna
  redondeada) y Platt con las OOS de las temporadas cerradas 2021–2024, guardado como coeficientes.
- **Intervalo de casos:** intervalo central de la NB2(μ, α) al 0,80 (cuantiles 0,10 y 0,90). **No está
  calibrado:** Platt corrige la probabilidad, no la distribución de los casos.
- **Importancias:** |SHAP| medio por horizonte, calculado al publicar.
- **OOS:** las del protocolo (temporadas 2022–2024 y calendario 2025), calibradas; reemplazan a las de la v0 en
  la serie (M6).
- **Sin historia previa a 2017** (M4): los orígenes cuyo t+2 cae en 2021 o antes quedan no disponibles con su motivo.
- **Paridad** (`tests/serving/test_v2_parity.py`, fixtures en `tests/fixtures/v2_serving/`): el vector de la BD es
  igual al de gold + B3, exacto salvo la precipitación de A3 (≤ 1e-9; diferencia medida 5,7e-14, porque la BD la
  guarda en `numeric(7,2)`), y el modelo congelado del bloque `calendario_2025` servido desde la BD da las mismas
  predicciones que `frozen_configs.predict` + Platt.
- **Tolerancias por plataforma** (regla en `docs/architecture.md`, «Guardas y tolerancias por plataforma»):
  - en el entorno de grabación (Windows x86-64, CPU con `n_jobs=2`) todo es bit a bit, salvo la precipitación
    de A3 (medido: 0 en el serving);
  - en Linux y macOS los enteros siguen exactos;
  - los flotantes calculados (seno y coseno, `log1p`, clima de A3, umbral) usan `atol=1e-12`, porque la libm
    cambia el último bit;
  - el serving usa `rtol=1e-6, atol=1e-8`, porque XGBoost predice en float32; en macOS arm64 se vio hasta
    7,5e-9.

## Huellas

- **Histórica** (definición original): `c36d7a80d1896a203874bf271bd78f1078850e1faa381e2b17e9ba04b07d5569`
  (`424a148`).
- **De comportamiento** (decisión D1), un valor por entorno:

  | Entorno | Huella |
  |---|---|
  | `device=cpu,n_jobs=2` (CI) | `0fe5d10712d4127e9e2728d7de230b8db6bfbae364b018f2b449ccd10818e2b3` |
  | `device=cuda` | `b302d838aa402017dbcf70320cd8c061ef854e0eda50460b801d557cd709a936` |

La definición de la huella cambió en la reestructuración (28/10/2026, commit `3d54055`). La equivalencia se
demuestra con predicciones idénticas bit a bit. El modelo no cambió, ni la fecha de congelamiento, ni la
ventana del test de 2026.

## Gold

Matrices en memoria desde gold h=2 (`meteo_socio_epi_piura_2017_2025_h2_gold.csv`,
`0ff49650f0fa1043bf2ae562d401c0d84307550108ef71d427ba9a20cbd475e3`), incluidas las columnas A3, y B3 desde el
silver epidemiológico histórico.

## Métricas de selección

Comparación 20, preregistrada: se adopta F+A3 si el conteo mejora en algún horizonte sin empeorar en ninguno
(2022 y 2023) y la alerta no pierde. Se cumplió en h=2, 3 y 4. Mediana de 5 semillas, F∩A3 → F+A3:

| Temporada | h | F1 | Razón MAE | Razón RMSE |
|---|---|---|---|---|
| 2022 | 2 | 0,702 → 0,709 | 1,000 → 0,919 | 1,099 → 0,938 |
| 2022 | 3 | 0,642 → 0,594 | 1,017 → 0,883 | 1,221 → 0,922 |
| 2022 | 4 | 0,525 → 0,333 | 1,036 → 0,838 | 1,369 → 0,905 |
| 2023 | 2 | 0,852 → 0,858 | 0,884 → 0,818 | 0,991 → 0,869 |
| 2023 | 3 | 0,826 → 0,828 | 0,811 → 0,747 | 0,912 → 0,818 |
| 2023 | 4 | 0,802 → 0,811 | 0,765 → 0,708 | 0,851 → 0,779 |
| 2024 (contraste) | 4 | 0,744 → 0,749 | 1,617 → 0,951 | 2,007 → 1,011 |

El F1 de 2022 · h4 cae (0,525 → 0,333): la regla del complemento no mide ese costo en la alerta, y el informe lo
discute en «El costo en la alerta, que la regla no mide».

## HU0007-4

**No cumple.** Clasificación: las mismas 4 de 9 celdas que la V1 (2023 h2 y 2024 h2/h3/h4). Regresión: 2 de 9
(2023 h3: 0,747 / 0,818; 2023 h4: 0,708 / 0,779). El test independiente será la parte de la temporada
2025-2026 publicada después del congelamiento (`EVALUATION_2026` en `frozen_configs`).
