# Dataset de trabajo — hechos verificados y trampas

Archivo: `data/silver/integrado/meteo_socio_epi_piura_2017_2025.csv` (cargar con `src.eda.carga.cargar_integrado()`). Cifras medidas sobre el snapshot actual; si algo no coincide, **avisa a Rosa antes de seguir** (el dataset pudo cambiar).

## Estructura
- **30 485 filas × 35 columnas** = 65 distritos × 469 semanas (2017-01-01 a 2025-12-21). Sin nulos, sin duplicados en la llave `(ubigeo, anio, semana)`.
- `semana_inicio` es **domingo**. **2020 tiene 53 semanas** (el resto 52); 2025 llega solo hasta la semana 52.
- 8 provincias: Piura 10 distritos, Ayabaca 10, Morropón 10, Huancabamba 8, Sullana 8, Paita 7, Sechura 6, Talara 6.
- `ubigeo` = string de 6 dígitos. `distrito_key` = nombre normalizado en mayúsculas sin tildes (llave de cruce entre fuentes).

## Columnas
| Grupo | Columnas |
|---|---|
| Identificación/geo | `provincia, distrito, distrito_key, ubigeo, lat, lon` |
| Tiempo | `anio, semana, semana_inicio` |
| Clima (semanal, Open-Meteo) | `temp_media, temp_max, temp_min` (°C), `precip_total_mm, lluvia_total_mm` (mm), `hum_rel_media` (%), `viento_max`, `radiacion_total`, `et0_total` |
| Sociodemográfico (anual) | `poblacion` + 15 columnas `fraccion_*` (rural, mujeres, menores_15, sin_seguro, analfabeta_15_mas, pared_precaria, piso_tierra, agua_red, agua_cisterna, desague_red, sin_saneamiento, alumbrado_red, hogares_refrigeradora, hogares_celular, hogares_lena) |
| Objetivo | `casos_Dengue` (entero, casos semanales por distrito) |

## Trampas conocidas (verifícalas y repórtalas, no las "arregles")
1. **`precip_total_mm` y `lluvia_total_mm` son idénticas** en el 100 % de las filas → redundantes; no son dos señales.
2. **Sociodemografía anual, no semanal.** Es constante dentro de cada distrito-año. Las 15 `fraccion_*` son **interpolación lineal** entre 2017 y 2025 (solo esos dos años son observados; el ajuste lineal es exacto en todos los distritos), así que su variación 2018-2024 es un artefacto, no dato real. `poblacion` sí cambia año a año sin ser lineal (proyección). Consecuencia: aportan **diferencias entre distritos**, no dinámica temporal.
3. **Ruptura de fuente en 2025.** Los casos hasta 2024 vienen del Excel epidemiológico; 2025 viene de la Sala Situacional MINSA (1 114 casos en semanas 1-52; 3 casos de la semana 53 quedaron fuera del panel). La documentación de la extracción reporta una **discrepancia sin resolver** con otro panel (12 067 casos para 2025). No compares 2025 con años previos sin esa advertencia, y trata 2025 como posible subregistro hasta que se aclare.
4. **Casos extremadamente sesgados:** ~78 % de las filas son 0; media ≈ 5.7, máximo 2 084, varianza/media ≈ 360 (sobredispersión fuerte). 3 distritos suman cero casos en todo el periodo (Lagunas, Montero, Sicchez). Los 5 distritos con más casos (Piura, Castilla, Sullana, Veintiséis de Octubre, Pariñas) concentran ≈ 54 % del total.
5. **Casos por año (total regional):** 2017: 44 275 · 2018: 525 · 2019: 70 · 2020: 125 · 2021: 4 072 · 2022: 12 151 · 2023: 79 304 · 2024: 32 246 · 2025: 1 114. Total 173 882. Dos episodios dominan; 2018-2020 son casi silencio epidemiológico.
6. **Extremos climáticos a investigar antes de tildar de error:** `temp_media` mínima 4.5 °C (El Carmen de la Frontera, Huancabamba, 2021-08-01; `temp_min` 0.4 °C) — Huancabamba es sierra, pero verifica si es plausible; `precip_total_mm` máxima 706 mm en una semana (Salitral, 2017-03-05, coincide con 2017, el año más lluvioso del panel). Temperatura media por provincia: sierra (Huancabamba ≈ 15 °C, Ayabaca ≈ 19 °C) muy distinta de costa (Sullana/Piura ≈ 24 °C): **el clima no es homogéneo en Piura**.
7. **Sin altitud ni polígonos distritales** en el dataset: solo `lat/lon` (centroides). Mapas = puntos/burbujas; no dibujes choropleths a menos que exista un archivo de límites en el repo.

## Lo que el dataset NO trae (no lo inventes)
Serotipo, hospitalizaciones/muertes, fumigación/control vectorial, índice aédico, movilidad, altitud, población por edad semanal. Cualquier mención debe ser hipótesis o limitación.
