# Denguekay

## Actualización selectiva del dataset

El dataset del modelo tiene una fila por `ubigeo`, `anio` y `semana`. El
actualizador inspecciona sus filas, completa únicamente los componentes
faltantes y conserva los valores históricos ya poblados. Los datos de clima
proceden de Open-Meteo; los demográficos, del Excel y la tabla anual local;
y los nuevos casos de dengue, de la Sala Situacional MINSA/DGE.

Instala las dependencias con `./run_setup.sh`. Desde la raíz del repositorio:

```bash
.venv/bin/python -m src.update_dataset_module \
  --input data/gold/dataset_modelo_piura_2017_2025.csv \
  --output data/gold/dataset_modelo_piura_2017_2025.csv \
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

El scraper reutilizable vive en `src/ingestion/scrape_minsa_dengue.py`. Sus
respuestas y exportaciones normalizadas se guardan como artefactos de ejecución
en `data/bronze/epi/sala/` y `data/silver/epi_sala_semanal.csv`; ninguno es
necesario en Git para ejecutar el actualizador. El catálogo pequeño de UBIGEO
vive en `data/reference/` y sí se versiona.

## Alcance y procedencia

El snapshot actual conserva los casos históricos del Excel epidemiológico
hasta 2024. Para 2025, las 3 380 filas de semanas 1–52 suman **1 114** casos
de la Sala. Sus **3** casos de semana 53 se mantienen en el artefacto de
fuente porque esa semana no corresponde a una fila completa de clima del
modelo. La trazabilidad original está en el archivo local
`trazabilidad_scraper_dengue_piura_2025.zip`.

La documentación de esa extracción señala una discrepancia no resuelta:
otro panel registró 12 067 casos para semanas 1–52 de 2025. El actualizador
usa la serie de la Sala para las nuevas consultas, sin mezclar ambos conteos.

Los valores demográficos de 2017–2025 se conservan. Para filas nuevas de
2026 en adelante, se extrapola la tendencia de los extremos 2017 y 2025;
las fracciones se acotan a `[0, 1]` con un registro de cada ajuste, y la
población se redondea a un entero positivo. No se recalculan filas históricas
salvo con una opción de actualización forzada.
