# Pipeline de datos

Cómo se construye el panel distrito × semana: los notebooks de `pipelines/notebooks/<versión>/` (01–05: bronze;
06–10: silver → integrado; `11_gold`: gold; `99_verificacion`) y el actualizador semanal
`denguekay.pipelines.weekly_update` (actualizador selectivo del integrado). Los de V4 escriben en `data/`; los de v0 a v3,
en `data_anteriores/<versión>/` (`DENGUEKAY_DATA_DIR`). Se ejecutan a propósito con `run_all`, nunca como parte de los tests.

> **Dos «semanales» distintos.** `weekly_update` completa filas faltantes del integrado y de la Sala dentro de estos
> pipelines por versión. La **operación del servicio con la V4** (bajar Sala, ERA5-Land, CHIRPS y Niño 1+2 sin el corte
> congelado, cargar la BD y emitir h2–h4 con archivo de cada emisión) es `python -m denguekay.pipelines.v4_weekly`, y no
> pasa por estos notebooks: ver [operación](backend/operacion.md#actualización-semanal-v4).

## Un pipeline por versión

`pipelines/notebooks/` tiene una carpeta por versión (`V0` a `V4`) con el mismo esquema de pasos: 01–05 bronze, 06–10
silver (el 10 es el integrado), 11 gold y 99 verificación. `run_all --version vN` los ejecuta en orden. V4 escribe en
`data/` con los nombres de su Release; v0 a v3 escriben en `data_anteriores/vN/` y leen el mismo `data/bronze/`.

Cómo llegan los archivos de V4 a `data/` (todos con el nombre que tienen en `datos_v4.zip`):

| Archivo | Lo produce |
|---|---|
| `data/silver/confirmados/epi_piura_semanal.csv` | `08_silver_casos`: CSV `DatosDengueV2.csv` de Drive, notificaciones de Piura con `tipo_dx = C` |
| `data/silver/confirmados/epi_sala_semanal.csv` | `05_bronze_sala`: Sala Situacional, serie CONFIRMADO, hasta el corte de `pipelines/versions.py` |
| `data/silver/meteo_semanal_distrital.csv`, `meteo_humedad_era5_land_2000_2026.csv`, `precip_chirps_v3_semanal_desde_2000.csv`, `enso_nino12_mensual.csv` | `06_silver_clima` |
| `data/silver/socio_anual.csv` | `07_silver_socio` |
| `data/silver/integrado/meteo_socio_piura_2017_2025.csv` | `09_silver_meteo_socio` |
| `data/silver/confirmados/meteo_socio_epi_piura_2017_2025.csv` y su `.coverage.csv` | `10_silver_integrado` |
| `data/gold/piura_confirmados_v4_gold.csv` y `manifest_v4.json` | `11_gold`: matriz B3 de los horizontes 2, 3 y 4 |
| `data/gold/meteo_socio_epi_piura_2017_2025_h2_gold.csv` y `manifest_fase6.json` | `11_gold`: gold h2 de confirmados |

Las diferencias frente al Release y por qué las hay están en `docs/reproducibilidad.md` §3.

Para regenerar el gold de una versión desde su silver completo (en V4, `11_gold`):

```powershell
.\.venv\Scripts\python -m denguekay.pipelines.run_all --version v2 --desde 11 --hasta 11
```

El gold conserva `casos_Dengue` como conteo junto a la etiqueta `brote` (semana distrital con casos por
encima de la media de esa semana en los cinco años previos + 1,5 DE, con un mínimo de 2 casos) y su umbral
auditable `umbral_brote_casos`. El entrenamiento excluye esas tres columnas de los predictores.

Gold persiste solo lo que debe estar en gold (regla «Variables derivadas» de `CONTRIBUTING.md`): un archivo con la alineación h=2, una fila por
distrito y semana objetivo, y 24 columnas:

- llaves, semana y origen: `ubigeo`, `anio`, `semana`, `semana_inicio`, `origen_inicio`, `origen_cierre`;
- objetivo y etiqueta: `casos_Dengue`, `umbral_brote_casos`, `brote`;
- variables de la configuración vigente: `base_6`, A3, B3 (se calcula en el origen de cada fila) y d3, las ventanas de
  temperatura de ERA5-Land de la v3. `generate_gold(columns="v2")` da las 20 columnas de la v2 (sin d3) y
  `generate_gold(columns="candidatas", horizons=(2, 4))` el gold anterior a la limpieza.

Las demás candidatas (vecinos, provincia y región, sociodemografía, población) y los otros horizontes se siguen
calculando en memoria con `build_gold`. De ahí salen las matrices de la v2 y los experimentos.

### Respaldo del gold anterior

`data/gold/respaldo_pre_b3/` guarda el gold anterior a la limpieza: h=2, h=4, su manifiesto y `SHA256SUMS.txt`. La v0
(`load_protocol`) y las herramientas del estudio 03 (`run_experiment`, `run_compact_validation`), además de
`evaluation/cache.py`, leen de ahí con los mismos hashes y dan un error explícito si falta.

**Es la única copia del gold h=4 y no está en Git: Rosa debe guardarla fuera de la PC.** `data/gold/*` está ignorado.
`build_gold` reproduce los valores de h=2 y h=4 (hay un test que lo comprueba), pero la v0 exige los archivos exactos y
sus hashes.

## Histórico epidemiológico confirmado

El paso `04_bronze_casos` de V4 descarga `DatosDengueV2.csv` de Drive y conserva los bytes de la fuente en
`data/bronze/epi/`. El paso `08_silver_casos` selecciona las notificaciones de Piura con `tipo_dx = C`
y las cuenta por UBIGEO, año y semana en `data/silver/epi_piura_semanal.csv`. Las semanas sin
notificaciones confirmadas no aparecen en este agregado.

## Actualización selectiva del dataset

El dataset integrado (`data/silver/integrado/meteo_socio_epi_piura_2017_2025.csv`)
tiene una fila por `ubigeo`, `anio` y `semana`. El
actualizador inspecciona sus filas, completa únicamente los componentes
faltantes y conserva los valores históricos ya poblados. Los datos de clima
proceden de Open-Meteo; los demográficos, del Excel y la tabla anual local;
y los nuevos casos confirmados de dengue, de la Sala Situacional MINSA/DGE.

Instala las dependencias con `scripts/setup.ps1` (Windows) o `./scripts/setup.sh` (macOS/Linux). Desde la raíz del repositorio:

```bash
.venv/bin/python -m denguekay.pipelines.weekly_update \
  --input data/silver/integrado/meteo_socio_epi_piura_2017_2025.csv \
  --output data/silver/integrado/meteo_socio_epi_piura_2017_2025.csv \
  --dry-run
```

Quita `--dry-run` para efectuar la actualización. Para escribir otro archivo,
indica una ruta distinta en `--output`. El CLI informa cuántas filas necesitan
cada componente y cuáles fuentes ejecutará. Las opciones
`--force-epidemiological`, `--force-weather` y `--force-demographic` fuerzan una
actualización explícita; requieren `--start-date` y `--end-date` con los
domingos de inicio de la primera y última semana solicitadas.

El archivo `<dataset>.coverage.csv`, junto al dataset, registra las semanas
con casos verificados. Si aún no existe, el primer uso considera los valores
ya poblados como la línea base validada. Tras ello, una fila nueva sin estado
de cobertura epidemiológica se consulta en la Sala aunque tenga un cero. Una
solicitud fallida no escribe ceros de relleno ni marca cobertura exitosa.
Las columnas climáticas y demográficas se revisan por valores faltantes.
Ejecuta una vez sin `--dry-run` sobre el snapshot actual antes de agregar
semanas nuevas, para dejar creada esa línea base de cobertura.

Si solo `casos_Dengue` falta en filas nuevas, la inspección indica
`[RUN] epidemiological`, `[SKIP] weather` y `[SKIP] demographic`.

El scraper reutilizable vive en `src/denguekay/data/ingestion/minsa_sala_scraper.py`. Sus
respuestas y exportaciones normalizadas se guardan como artefactos de ejecución
en `data/bronze/epi/sala/` y `data/silver/epi_sala_semanal.csv`; ninguno es
necesario en Git para ejecutar el actualizador. El catálogo pequeño de UBIGEO
vive en `data/reference/` y sí se versiona.

## Fuentes climáticas de la V4: producto, rezago y disponibilidad al origen (HU0002-4)

La V4 (B3) usa tres entradas de clima, siempre en la ventana de las semanas o−6 a o−2 y en el promedio de los últimos
tres meses consecutivos de Niño 1+2 (`features/b3.py`, `climate_vector`). Cada una lleva una fecha desde la que se
puede usar, y el vector de un origen solo toma lo que esa fecha deja usar al cierre del origen.

| Fuente | Producto | Cómo llega | Rezago de publicación y regla de disponibilidad |
|---|---|---|---|
| ERA5-Land | Temperatura media y humedad relativa media diarias (`temperature_2m_mean`, `relative_humidity_2m_mean`), agregadas por semana MMWR en el punto del distrito | API de archivo de Open-Meteo (`data/ingestion/openmeteo.py`, `models=era5_land`, celda de 0,1°); caché en `data/bronze/meteo/` | Open-Meteo lo actualiza a diario con unos 5 días de retraso (`ERA5_LAND_DELAY_DAYS = 5`, tomado de su documentación y registrado por el estudio 06). La semana se usa desde su inicio + 13 días, es decir, 7 días después de cerrar (`district_locations.read_v4_era5`) |
| CHIRPS v3 | Precipitación diaria `sat`, media del polígono distrital; semanal con la versión `final` (Earth Engine) o `prelim` (CHC) | `data/ingestion/chirps_ee.py` y `chirps_prelim.py`; silver con `version` y `fecha_disponible` | El CHC publica pentadas preliminares 2 días después de cada pentada (`OFFICIAL_LAG_DAYS = 2`); se usa el fin de la pentada + 5 días (`PUBLICATION_LAG_DAYS`, que cubrió el 94 % de las 130 pentadas de 2025-2026 que se midieron: mediana 2, p90 4, máximo 18 días) |
| Niño 1+2 | Anomalía mensual de la TSM (`sstoi.indices`, NOAA CPC) | `data/ingestion/enso.py`; silver `enso_nino12_mensual.csv` con `fecha_disponible` | CPC actualiza «cerca del día 10»: el mes M se usa desde el día 10 del mes M + 1 (`enso_index.PUBLICATION_DAY = 10`) |
| Open-Meteo (clima del panel) | Temperatura, precipitación y humedad diarias del panel 2017-2025 | Misma API, sin `models` | **No es una entrada de la V4.** Alimenta el panel integrado de las versiones anteriores y el EDA; B3 toma el clima de ERA5-Land y CHIRPS |

**Cómo se garantiza que solo se usan datos publicados al origen.** (1) `climate_vector` descarta la semana cuya fecha de
disponibilidad es posterior al cierre del origen y deja el promedio en `NaN` si falta alguna de las 5 semanas;
con Niño 1+2 exige tres meses consecutivos ya disponibles. (2) En el entrenamiento, `features/gold_v4.py` alinea Niño
con `merge_asof` sobre `fecha_disponible` y usa las fechas de ERA5-Land y CHIRPS. (3) Hay pruebas de no fuga por
perturbación (`tests/serving/test_v4_live.py`, `TestB3Availability`): cambiar un valor no publicado o publicar un mes
futuro de Niño no cambia el vector.

**Lo que esas reglas no garantizan (se reporta, no se corrige aquí).**

- Las fechas de ERA5-Land (+13 días) y de Niño 1+2 (día 10) son reglas conservadoras: **no se registró la fecha real en
  que se publicó cada dato pasado**. CHIRPS lleva su `fecha_disponible` por pentada con la misma convención.
- El entrenamiento usa los valores archivados al momento de descargarlos. Si una fuente revisa valores ya publicados
  (la Sala lo hizo, ver «Alcance y procedencia»; ERA5-Land y CHIRPS tienen versiones preliminar y final), un valor
  reciente puede cambiar después. **No se verificó** cuánto difieren los valores de las semanas recientes de los
  definitivos: es una hipótesis de riesgo, no una medición.
- En ERA5-Land, la columna `fecha_disponible` no está en el silver operativo; `read_v4_era5` la calcula con la regla de
  +13 días al leerlo.

## Sociodemografía: año de referencia y regla temporal (HU0003-4)

Fuente: el Excel del censo y las proyecciones del INEI (`data/bronze/socio/`), con una fila por distrito. El silver
`socio_anual.csv` (paso `07_silver_socio`, `data/processing/socio_interpolation.py`) tiene una fila por distrito y año
de 2017 a 2025.

| Variable | Año de referencia | Regla temporal |
|---|---|---|
| `poblacion` | 2017 (censo, `pob_censada_2017`) y 2018-2025 (proyección, `pob_proyectada_<año>`) | Valor del año de cada semana, sin interpolar. Desde 2026: se prolonga la pendiente 2017-2025 (`(valor 2025 − valor 2017) / 8` por año), redondeada y siempre positiva |
| Las 15 fracciones (`fraccion_rural`, `fraccion_mujeres`, `fraccion_menores_15`, `fraccion_sin_seguro`, `fraccion_analfabeta_15_mas`, `fraccion_pared_precaria`, `fraccion_piso_tierra`, `fraccion_agua_red`, `fraccion_agua_cisterna`, `fraccion_desague_red`, `fraccion_sin_saneamiento`, `fraccion_alumbrado_red`, `fraccion_hogares_refrigeradora`, `fraccion_hogares_celular`, `fraccion_hogares_lena`; columnas `<base>_2017` y `<base>_2025` del Excel) | Extremos 2017 y 2025 | Interpolación lineal año a año entre 2017 y 2025; desde 2026, extrapolación de la misma pendiente acotada a `[0, 1]`, con un registro de cada ajuste |
| Variables con un solo año (p. ej. `fraccion_menores_5`, solo 2017; `fraccion_60_mas`, solo 2025) | 2017 o 2025 | Se excluyen del dataset: no hay cómo interpolarlas ni suponerlas constantes |

La población censal de 2017 también está en `distrito.poblacion_censo_2017` (tasas y mapa). **Lo que la regla temporal no
garantiza:** la interpolación de los años 2018-2024 usa el extremo de 2025, que no estaba disponible en esos años, así
que un valor intermedio no es lo que se habría podido calcular en ese momento. **La V4 no usa variables
sociodemográficas** (sus 16 columnas son historia de casos, calendario, geografía, clima y Niño 1+2), por lo que esto no
afecta su pronóstico; sí afectaría a una versión que las incorporara.

## Alcance y procedencia

El paso `05_bronze_sala` de V4 usa la serie `CONFIRMADO` del gráfico semanal por tipo de diagnóstico y marca
`tipo_dx=C` en su silver. En la primera actualización completa reemplaza el silver anterior
de la Sala. El paso `10_silver_integrado` usa el CSV histórico hasta 2024 y la Sala desde 2025, sin sumar
conteos de ambas fuentes en el año que se solapa. Una semana posterior al corte de la Sala
queda pendiente. Ejecuta `run_all --version v4` (pasos 04, 05, 08 y 10) para construir el integrado de confirmados.

El snapshot anterior conserva los casos históricos del Excel epidemiológico
hasta 2024. Para 2025, las 3 380 filas de semanas 1–52 suman **1 114** casos
de la Sala. Sus **3** casos de semana 53 se mantienen en el artefacto de
fuente porque esa semana no corresponde a una fila completa de clima del
modelo. La trazabilidad original está en el archivo local
`trazabilidad_scraper_dengue_piura_2025.zip`.

La documentación de esa extracción señala una discrepancia no resuelta:
otro panel registró 12 067 casos para semanas 1–52 de 2025. El actualizador
usa la serie de la Sala para las nuevas consultas, sin mezclar ambos conteos.
Para la tesis, Rosa confirmó que los casos de la Sala son una fuente de verdad
válida; el cambio de procedencia se registra y no determina por sí solo el
corte de entrenamiento o prueba.

Los valores demográficos de 2017–2025 se conservan. Para filas nuevas de
2026 en adelante, se extrapola la tendencia de los extremos 2017 y 2025;
las fracciones se acotan a `[0, 1]` con un registro de cada ajuste, y la
población se redondea a un entero positivo. No se recalculan filas históricas
salvo con una opción de actualización forzada.
