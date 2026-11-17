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
