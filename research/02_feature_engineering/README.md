# 02 · Feature engineering y construcción de gold

- **Pregunta:** ¿qué variables, disponibles al origen del pronóstico y sin fuga, y qué etiqueta de
  brote se usan para modelar h=2 y h=4?
- **Decisión:** gold h=2 y h=4 con 34 candidatas y la etiqueta `brote`: casos de la semana objetivo
  estrictamente mayores que la media de la misma semana distrital de los cinco años previos + 1,5 DE,
  con un mínimo provisional de 2 casos. El manifiesto `data/gold/manifest_fase6.json` documenta el
  linaje. Fases en [fases_feature_engineering.md](docs/fases_feature_engineering.md); traspaso al modelado en
  [fase7_sintesis_traspaso.md](docs/fase7_sintesis_traspaso.md); alternativas de la etiqueta en
  [revision_definicion_brote.md](docs/revision_definicion_brote.md).
- **Versión de modelo resultante:** ninguna; gold es la entrada de V0, V1 y V2.
- **Tag:** `archive/feature-engineering` (`c9ca044`). Alternativa: `pre-restructure` (`3ad8312`).

## Contenido

| Carpeta | Qué hay |
|---|---|
| `notebooks/` | 17–21 (contrato objetivo, historia y calendario, vecinos, clima, sociodemografía) y 23 (síntesis) |
| `code/` | `diagnostico.py`, `diagnostico_clima.py` y `diagnostico_socio.py` (ablaciones lineales de diagnóstico) |
| `docs/` | plan, fases 1–7, corrección del calendario, revisión de la definición de brote, `metricas/` y la referencia PDF |

**No está aquí el notebook 22** (`22_fe_integracion`): regenera gold, así que es parte del pipeline
(decisión D3). Tampoco las funciones que construyen gold (`features.py`, `etiqueta_brote.py`,
`clima.py`, `historia_calendario.py`, `vecinos_jerarquia.py`, `sociodemografia.py`): son producto.

## Cómo reproducir

Los datos salen de los Releases (no de otra PC): los comandos de descarga se corren **desde un clon de `develop` con su `.venv`** (ver [docs/reproducibilidad.md](../../docs/reproducibilidad.md)) y extraen en la copia del tag con `--raiz`; cada archivo se verifica contra su SHA-256. `gold_anterior.zip` trae el gold anterior en su ruta original (`data/gold/`), con los mismos bytes que `gold/respaldo_pre_b3/` (Release de `model/v0`). El silver de la Sala del Release es el vigente: sus filas hasta 2025 son las mismas que leyó el estudio, pero trae además las semanas de 2026. Las cifras se verifican con los artefactos guardados del Release de cada estudio cuando existen.

```powershell
# Desde un clon de develop, con su .venv: la copia del tag y sus datos
git worktree add ..\denguekay-fe archive/feature-engineering
.\.venv\Scripts\python -m denguekay.data.ingestion.release_bundles --estudio 01_eda --raiz ..\denguekay-fe
.\.venv\Scripts\python -m denguekay.data.ingestion.release_bundles --estudio 03_first_models_and_ablations --solo gold_anterior.zip --raiz ..\denguekay-fe
# En la copia del tag, con su propio entorno
cd ..\denguekay-fe
python -m venv .venv   # entorno propio: las dependencias pueden diferir de las de main
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m jupyter nbconvert --to notebook --execute --inplace notebooks/17_fe_contrato_objetivo.ipynb
```

Repite con 18 a 21 y 23. El notebook 22 de esa copia **escribe gold en `data/`**: no lo corras sobre
un `data/` que quieras conservar (la copia del tag tiene el suyo).
