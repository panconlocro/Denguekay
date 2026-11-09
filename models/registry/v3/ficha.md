# V3 · L + 5a + d3 · E3 · S4_s3 (vigente y servida)

| Campo | Valor |
|---|---|
| Estado | **Vigente y servida**: configuración congelada el 2026-11-09 al cerrar el estudio 06. Se sirve como selección experimental con el predictor `v3_l5a_d3` (paquete entrenado fuera de la BD con la serie desde 2000). La [V2](../v2/ficha.md) queda reemplazada y registrada |
| Tag | `model/v3` |
| Configuración | `denguekay.model.frozen_configs.CONFIG_V3`; se carga con `denguekay.model.registry.configuration("v3")` |
| Reemplaza a | [V2](../v2/ficha.md) (como configuración vigente) |
| Retadora | b3 (clima completo: humedad, lluvia, temperatura y Niño 1+2), congelada para la evaluación prospectiva 2026–27 |
| Protocolo | [docs/modeling/protocolo_v3.md](../../../docs/modeling/protocolo_v3.md). **No es el protocolo de la V2** |
| Reproducir | [docs/modeling/reproducir_v3.md](../../../docs/modeling/reproducir_v3.md) |
| Estudio | [`research/06_model_improvement`](../../../research/06_model_improvement/README.md), informe [mejora_modelo.md](../../../research/06_model_improvement/docs/mejora_modelo.md); tag `study/model-improvement` |

## Configuración

- **Base:** la V1 (`base_6` + B3), entrenada con orígenes desde 2005 en vez de 2017 (L).
- **Clima (d3):** 4 ventanas de temperatura media de ERA5-Land: semana del origen y medias de o−1..o−4,
  o−5..o−8 y o−9..o−12. En total son 13 columnas.
- **Conteo publicado (5a):** `w · μ + (1 − w) · persistencia`, con `w` por horizonte y bloque ajustada con las
  predicciones fuera de muestra (OOS) anteriores ya cerradas.
- **Hiperparámetros:** los del trial 191 del ajuste (`V3_HYPERPARAMETERS`): 1055 árboles, profundidad 8,
  learning_rate 0,0122, etc.
- **Igual que la V1:** E3 multisalida, `count:poisson` con margen de persistencia, NB2 con α dentro de la
  muestra, Platt por horizonte, p ≥ 0,50 y semilla 17.

## Cómo se eligió

1. **Base d3:** la eligió Rosa **con contexto** (2026-11-08), por el objetivo de anticipar brotes en años de
   Niño. Por la regla `SEASON_2026`, solo se adoptaba b3.
2. **Hiperparámetros:** el ajuste preregistrado (`HP_TUNING`) corrió 255 trials de TPE (se alcanzó el tope
   de 10 h). La candidata (trial 191) ganó el Brier en h2 y h3 frente a L + 5a + d3 con los hiperparámetros
   heredados, empató en h4, en la alerta y en el conteo, y fue mejor en 24 de 24 celdas fuera de temporada.
   Rosa la adoptó el 2026-11-09.
3. Cifras en `research/06_model_improvement/docs/metricas/ajuste_hp.json` y `.../metricas/v3.json`.

## Huella

De comportamiento (semilla 17, bloques 2008–2026 del estudio 06): **`device=cuda`**
`99a0b26dc4a453feea5ddc71d3438b7006e64d2ba5e12caa646f8035040494de`. Solo se grabó en GPU (RTX 5060, driver
621.01, XGBoost 3.4.1 con CUDA 13.3). En CPU las predicciones no son bit a bit iguales a las de GPU.

## Predicciones de referencia y datos

- `models/experimentos/mejora_modelo/v3/predicciones_v3.csv.gz` (V3) y `predicciones_l5a_sin_clima.csv.gz`
  (L + 5a con los mismos hiperparámetros, comparador pareado sin clima). Tienen 5 semillas y todos los bloques;
  las columnas están en el protocolo.
- La guarda G41 pasa: la corrida de cierre reproduce `ajuste_hp/predicciones_candidata.csv.gz` con diferencia
  máxima 0,0.
- Los datos de entrada, las predicciones y los comparadores están en el Release de `model/v3`
  (`datos_v3.zip`, `predicciones_v3.zip` y `comparadores_v3.zip`), con SHA-256 en
  [manifiesto_datos.json](manifiesto_datos.json). Se descargan con
  `python -m denguekay.data.ingestion.release_bundles`.

## Limitaciones

- **Antelación:** en contra en 2, 1 y 3 de 6 temporadas (h2, h3, h4) frente a los hiperparámetros heredados,
  y a favor en ninguna.
- **2022 · h4:** el Brier empeora un 2,65 % frente a los hiperparámetros heredados.
- **2026 se usó para elegir.** La prueba independiente es solo lo que se publique después del 2026-11-09.
- **Diagnóstico frente a la persistencia** (hecho con los hiperparámetros heredados, no recalculado): el conteo
  se queda corto en los picos y la probabilidad se subestima en `posterior_2026`.
- **HU0007-4:** no evaluada por celda. Al publicar (prueba de punta a punta del 2026-11-09 en una SQLite temporal),
  los umbrales de `parametro_sistema` (bloque `temporada_2024`) se cumplen en clasificación h2, h3 y h4 y no se
  cumplen en regresión. Como la activación es por pares, se sirve como selección experimental.
- **Intervalo del conteo:** NB2 central alrededor del conteo publicado, sin calibrar (pendiente R17).

## Servicio

- **Predictor `v3_l5a_d3`:** el vector se arma desde la BD: casos desde 2017 y `temp_media_era5_land_c` de las 13
  semanas hasta el origen (migración `0007_v3`).
- **Paquete:** `booster.json`, `dispersion.json`, `platt.json` y `mezcla.json`, ajustado fuera de la BD.
  - Sin BD: `python -m denguekay.serving.predictors.v3_l5a_d3 --salida <carpeta>`.
  - Publicación: `python -m denguekay.serving.publish --seleccionar-experimental`.
- **Paridad:** el bloque `temporada_2026` reajustado reproduce las predicciones congeladas (0,0 en GPU). El vector
  servido es igual al de la serie larga (`tests/serving/test_v3_parity.py`).
