# V4 · b3_obs con casos confirmados

| Campo | Valor |
|---|---|
| Estado | Congelada para la evaluación del paper |
| Ámbito | Piura, por distrito y semana epidemiológica |
| Fecha de congelamiento | 12 de noviembre de 2026 |
| Último cierre de etiquetas | SE 41 de 2026, 17 de octubre |
| Horizontes | 2, 3 y 4 semanas desde el corte de datos |
| Comparador sin clima | `historia_geo` |
| Semillas | 17, 29, 41, 53 y 67 por brazo |

La [especificación del congelamiento](../../../research/08_v3_confirmed_cases/congelamiento_b3_v4.md)
documenta el ajuste, los artefactos locales y su reproducción. El [manifiesto](../../../research/08_v3_confirmed_cases/manifiesto_b3_v4.json)
contiene las variables, los parámetros y las huellas de los archivos.

Los paquetes descargables se describen en la [guía de reproducción de V4](../../../docs/modeling/reproducir_v4.md).

## Datos

Los insumos exactos están en `datos_v4.zip` del Release de `model/v4`; su manifiesto es
[`manifiesto_datos.json`](manifiesto_datos.json) (SHA-256 completos). `run_all --version v4` los regenera con estos mismos
nombres en `data/`.

| Archivo | Filas | SHA-256 (16 primeros) |
|---|---|---|
| `data/silver/confirmados/epi_piura_semanal.csv` | 10 240 | `6b5b62e8fbc4a395` |
| `data/silver/confirmados/epi_sala_semanal.csv` | 6 240 | `ff3354ca19cf9ab9` |
| `data/silver/confirmados/meteo_socio_epi_piura_2017_2025.csv` | 30 485 | `ad0a9917d1542dd7` |
| `data/silver/confirmados/meteo_socio_epi_piura_2017_2025.coverage.csv` | 30 485 | `865f1338d5758a17` |
| `data/silver/meteo_humedad_era5_land_2000_2026.csv` | 91 000 | `3e91e57f31fa47af` |
| `data/silver/precip_chirps_v3_semanal_desde_2000.csv` | 91 000 | `e4cd57a5927cadc2` |
| `data/silver/enso_nino12_mensual.csv` | 538 | `3250fdfa62fb930f` |
| `data/gold/meteo_socio_epi_piura_2017_2025_h2_gold.csv` | 30 485 | `0bbf34a8825d9a66` |
| `data/gold/manifest_fase6.json` | — | `024c654f9b5a5cf3` |
| geografía de B3 (`geografia_distritos.csv`) | 65 | `b56bacee763b9c7a` |

La Sala llega hasta la SE 43 de 2026 (2 semanas provisionales) y las etiquetas, hasta el 17 de octubre de 2026. El gold de
entrenamiento (`piura_confirmados_v4_gold.csv`, 73 775 filas) se regenera con
`python -m denguekay.features.gold_v4 --desde-release`.

## Entorno del congelamiento

Registrado en `resultados.json` de `datos_v4.zip` (`configuracion`): `Darwin 24.6.0 arm64` (macOS en Apple Silicon),
Python 3.12.13, XGBoost 3.4.1, pandas 3.0.6, NumPy 2.5.3, CPU con 2 hilos (`device: cpu`, `n_jobs: 2`). El código era
el commit `bea6f20` con cambios sin commitear.

## Gold B3 por plataforma

El CSV no es idéntico byte a byte entre plataformas. Según los hashes por columna de `referencia.json`, macOS y Windows
difieren solo en `semana_epi_seno` y `semana_epi_coseno`; macOS y Linux, además, en `propia_pendiente_4` y
`propia_log_casos_temporada_anterior`. La referencia independiente (`tests/fixtures/v4_gold/`) lo compara con tolerancia
de 1 × 10⁻¹² por celda.

| Plataforma | SHA-256 del CSV (16 primeros) |
|---|---|
| macOS ARM64 | `63148b7144eebe74` |
| Linux x86-64 | `3797b7a853fd8405` |
| Windows x86-64 | `bd86c94d68f008d0` |

## Aceptación (HU0007-4, US v1.4)

Evaluación retrospectiva fuera de muestra por bloques de temporada: las semanas distritales de `temporada_2022` a
`temporada_2026` (16 965 filas por horizonte, 2 478 semanas elevadas) se agregan en el bloque `temporadas_2022_2026`,
con las predicciones archivadas de **una sola semilla** (17; el paquete trae boosters de cinco semillas pero un único
archivo de predicciones, así que no se midió la variación entre semillas) (`oos_b3_s17.csv.gz` del paquete congelado, calculadas igual que los
bloques por temporada de `demo_b3_v4.archived_predictions`).

Umbrales (migración `0009_v4`, `parametro_sistema.umbrales_aceptacion`): clasificador con Recall ≥ 0,65, Precision ≥ 0,60
y F1 ≥ 0,70 con p ≥ 0,50; regresor con MAE y RMSE ≤ 90 % de los de la persistencia. Un horizonte es operativo solo si
ambas tareas cumplen.

| h | Recall | Precision | F1 | MAE / persistencia | RMSE / persistencia | Cumple |
|---|---|---|---|---|---|---|
| 2 | 0,769 | 0,824 | 0,795 | 0,868 | 0,861 | sí |
| 3 | 0,723 | 0,827 | 0,772 | 0,824 | 0,819 | sí |
| 4 | 0,666 | 0,820 | 0,735 | 0,806 | 0,787 | sí |

**Cómo leerlo.** Los umbrales se revisaron el 17/11/2026, **después de ver los resultados** de la V4 (antes eran
Recall ≥ 0,80, razón ≥ 0,85 y el bloque `temporada_2024`). Por eso este cumplimiento es retrospectivo y no es una
evaluación independiente: la evaluación independiente es la prospectiva 2026-27 (emisiones semanales archivadas por
`v4_weekly`). El cumplimiento del agregado descansa en las temporadas 2022 a 2024, que reúnen el 94 % de las semanas elevadas
del bloque (2 335 de 2 478); las de 2025 y 2026 suman 143. Revisión independiente de las cifras (17/11/2026), por
temporada individual (informativo, p ≥ 0,50, h2 / h3 / h4):

| Temporada | Recall | F1 | MAE / persistencia |
|---|---|---|---|
| 2022 | 0,617 / 0,529 / 0,446 | 0,695 / 0,643 / 0,582 | 0,887 / 0,820 / 0,776 |
| 2023 | 0,816 / 0,752 / 0,700 | 0,854 / 0,826 / 0,799 | 0,792 / 0,735 / 0,712 |
| 2024 | 0,834 / 0,829 / 0,788 | 0,807 / 0,798 / 0,771 | 0,948 / 0,933 / 0,921 |
| 2025 | 0,526 / 0,561 / 0,456 | 0,508 / 0,538 / 0,426 | 1,282 / 1,471 / 1,727 |
| 2026 | 0,512 / 0,442 / 0,314 | 0,638 / 0,580 / 0,439 | 1,100 / 1,135 / 1,136 |

Solo 2023 cumple todos los umbrales por sí sola; 2025 y 2026 no los cumplen (en 2025 el modelo es peor que la
persistencia). Sin 2023 el agregado falla la razón de error en los tres horizontes. El margen del h4 es corto
(Recall 0,666 frente a 0,65). Por eso «validado» significa aquí **«cumple los umbrales, de forma retrospectiva y con una
semilla»**: no se generaliza ni se lee como efecto causal. La v3 y las anteriores no traen el bloque agregado y quedan
`experimental`. El detalle por temporada sigue en las métricas de cada versión.

## Metadatos de publicación (19/11/2026)

La publicación de la V4 registra, además del paquete, las importancias SHAP por horizonte y la partición temporal de la
evaluación (`reproducibilidad.particion_temporal`); el modelo y sus predicciones no cambian y quedan **pendientes de
republicar en producción**. La matriz de entrenamiento se reconstruye con los insumos del Release y debe dar las 73 775
filas, las 16 columnas de `b3_obs` y las dispersiones NB2 del paquete (`refit_v4.frozen_training_matrix`); el clasificador
y el regresor de un horizonte comparten booster, así que sus importancias son idénticas. El corte de ajuste de cada bloque
es el primer origen de su temporada (coincide con el `ajustes.csv` del archivo del estudio en todos los bloques); el bloque
agregado `temporadas_2022_2026` publica la regla y el corte de cada temporada, no una fecha única.
