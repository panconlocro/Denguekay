# 01 · Análisis exploratorio (EDA, Hito 2)

- **Pregunta:** ¿cómo es el panel distrito × semana epidemiológica de Piura (2017–2025), qué
  problemas de origen tiene y qué condiciona el pronóstico de brotes con 4 semanas de anticipación?
- **Decisión:** recomendaciones para el feature engineering y el modelado, en
  [informe_eda.md](docs/informe_eda.md) (sección «Decisiones recomendadas»). Detalle por fase en
  [hallazgos.md](docs/hallazgos.md); problemas y decisiones pendientes en
  [problemas_y_decisiones.md](docs/problemas_y_decisiones.md).
- **Versión de modelo resultante:** ninguna (no entrena modelos).
- **Tag:** `archive/EDA` (`4444382`). Alternativa: `pre-restructure` (`3ad8312`).

## Contenido

| Carpeta | Qué hay |
|---|---|
| `notebooks/` | `10_eda_integridad_calidad` a `16_eda_sintesis` |
| `code/` | el paquete `src/eda` tal como estaba |
| `tests/` | los tests de `src/eda` |
| `docs/` | informe, hallazgos, problemas y decisiones, `metricas/<fase>.json` y `figuras/<fase>/` |

`carga.py`, `temporal.py` y `espacial.py` (y sus tests) son **copias**: el producto usa
`cargar_integrado`, `asignar_temporada` y `distancias_km`/`pesos_*`, así que los originales siguen en
`src/eda/` hasta que la fase 3 los pase al paquete (`data.loading`, `data.seasons` y
`features.spatial`, decisión D4).

## Cómo reproducir

Los datos salen de los Releases (no de otra PC): los comandos de descarga se corren **desde un clon de `develop` con su `.venv`** (ver [docs/reproducibilidad.md](../../docs/reproducibilidad.md)) y extraen en la copia del tag con `--raiz`; cada archivo se verifica contra su SHA-256. `gold_anterior.zip` trae el gold anterior en su ruta original (`data/gold/`), con los mismos bytes que `gold/respaldo_pre_b3/` (Release de `model/v0`). El silver de la Sala del Release es el vigente: sus filas hasta 2025 son las mismas que leyó el estudio, pero trae además las semanas de 2026. Las cifras se verifican con los artefactos guardados del Release de cada estudio cuando existen.

En una copia de trabajo aparte, para no tocar `main`:

```powershell
# Desde un clon de develop, con su .venv: la copia del tag y sus datos
git worktree add ..\denguekay-eda archive/EDA
.\.venv\Scripts\python -m denguekay.data.ingestion.release_bundles --estudio 01_eda --raiz ..\denguekay-eda
# En la copia del tag, con su propio entorno
cd ..\denguekay-eda
python -m venv .venv   # entorno propio: las dependencias pueden diferir de las de main
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m jupyter nbconvert --to notebook --execute --inplace notebooks/10_eda_integridad_calidad.ipynb
```

Repite con los notebooks 11 a 16 en orden. Escriben figuras y métricas en `docs/eda/` de esa copia,
leen `data/silver/integrado/` y no escriben en `data/`.
