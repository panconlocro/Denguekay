# Referencia congelada del artículo

Esta carpeta contiene los insumos que usa `01_reproduction_check` para cotejar las tablas II y S16 y la sensibilidad a excluir 2026. La ruta `PAPER_BUNDLE` se define en [src/denguekay/config/paths.py](../../../src/denguekay/config/paths.py) y apunta a `reproducibility/` dentro de esta carpeta.

## Procedencia

- Los cuatro archivos de [reproducibility/](reproducibility/README.md) son copias exactas de `tablas_paper_v4.zip`, publicado en el [Release model/v4](https://github.com/panconlocro/Denguekay/releases/tag/model/v4). SHA-256 del ZIP: `d513c4baa0ab954a8a8c2a281480abf1054be48e586b48c22514b4d5b90e37f8`.
- `main.tex` y `supplement.tex` son copias sin cambios de las fuentes del artículo revisado que los autores usaron en la corrida original del estudio 09 (`denguekay_paper_latex_revisado`). Se incluyen aquí porque el ZIP del Release no contiene esos textos. Son referencias para comparar las cifras; esta carpeta no incluye las imágenes ni la bibliografía necesarias para compilar el artículo completo.
- [SHA256SUMS](SHA256SUMS) registra los hashes de los seis archivos congelados. Además, [manifest.json](reproducibility/manifest.json) registra el hash y las 61 230 filas de `predictions.csv.gz`, las temporadas, los horizontes, las semillas y los hashes de los archivos fuente de predicciones.

Las predicciones son agregados por distrito, semana y horizonte. Este paquete reconstruye estadísticas a partir de probabilidades ya calculadas; el reentrenamiento requiere los insumos y protocolos del estudio.

## Verificación

Desde la raíz del repositorio, con Python 3.12 disponible como `python` (o `py -3.12` en Windows):

```bash
python research/09_epidemics_revision/paper/reproducibility/reproduce.py --main-tex research/09_epidemics_revision/paper/main.tex --supplement-tex research/09_epidemics_revision/paper/supplement.tex --out models/experimentos/revision_epidemics/reproduced_paper
```

Solo se necesita la biblioteca estándar. El script valida el archivo comprimido y las filas, coteja las cifras con las fuentes `.tex` y escribe las tablas y `metrics.json` en la carpeta indicada. No modifica los archivos de referencia ni `data/`.
