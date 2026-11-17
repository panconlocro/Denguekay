# Pipeline de datos

Cómo se construye el panel distrito × semana: los notebooks de `pipelines/notebooks/<versión>/` (01–05: bronze;
06–10: silver → integrado; `11_gold`: gold; `99_verificacion`) y el actualizador semanal
`denguekay.pipelines.weekly_update`. Los de V4 escriben en `data/`; los de v0 a v3, en `data_anteriores/<versión>/`
(`DENGUEKAY_DATA_DIR`). Se ejecutan a propósito con `run_all`, nunca como parte de los tests.

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
