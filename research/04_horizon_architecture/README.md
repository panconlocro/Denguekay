# 04 · Arquitectura multi-horizonte (h=2, 3, 4)

- **Pregunta:** ¿qué estrategia multi-horizonte y qué formulación de la salida (conteo y
  probabilidad de brote) usar para h=2, 3 y 4, bajo un protocolo preregistrado?
- **Decisión:** **E3 + S4_s2**: un XGBoost `multi_output_tree` con `count:poisson` predice
  (t+2, t+3, t+4) desde el mismo origen; P(casos ≥ k) con binomial negativa NB2 y Platt
  cronológico; alerta con probabilidad calibrada ≥ 0,50. Es un solo modelo a desplegar en lugar de
  seis ([arquitectura_horizontes.md](docs/arquitectura_horizontes.md), «Fase 5: síntesis y
  decisión»; diseño en [diseno_arquitectura_horizontes.md](docs/diseno_arquitectura_horizontes.md)).
- **Versión de modelo resultante:** ninguna congelada; es la arquitectura sobre la que el estudio 05
  congela V1 y V2.
- **Tag:** `study/horizon-architecture` (`808c340`). Alternativa: `pre-restructure` (`3ad8312`).

## Contenido

| Carpeta | Qué hay |
|---|---|
| `notebooks/` | `31_modelado_arquitectura_horizontes` |
| `docs/` | informe, plan, `metricas/arquitectura_horizontes.json` y `figuras/` |

No tiene código propio aquí: el protocolo, las estrategias, la salida probabilística y el diagnóstico
de errores (`protocolo_arquitectura.py`, `estrategias_horizonte.py`, `salida_probabilistica.py`,
`diagnostico_arquitectura.py`) los usan V1/V2 y serving, así que siguen en `src/` y pasan al paquete
en la fase 3 (decisión D4).

Experimentos de MLflow: `denguekay/arquitectura_horizontes_fase0_semillas`, `..._fase3_curva`,
`..._fase3_estrategias` y `..._fase4_formulaciones`. Las cachés `.pkl` de
`models/experimentos/arquitectura_horizontes/cache/` no se migraron: guardan referencias a los
módulos de ese tag.

## Cómo reproducir

Los datos salen de los Releases (no de otra PC): los comandos de descarga se corren **desde un clon de `develop` con su `.venv`** (ver [docs/reproducibilidad.md](../../docs/reproducibilidad.md)) y extraen en la copia del tag con `--raiz`; cada archivo se verifica contra su SHA-256. `gold_anterior.zip` trae el gold anterior en su ruta original (`data/gold/`), con los mismos bytes que `gold/respaldo_pre_b3/` (Release de `model/v0`). El silver de la Sala del Release es el vigente: sus filas hasta 2025 son las mismas que leyó el estudio, pero trae además las semanas de 2026. Las cifras se verifican con los artefactos guardados del Release de cada estudio cuando existen.

```powershell
# Desde un clon de develop, con su .venv: la copia del tag y sus datos
git worktree add ..\denguekay-horizontes study/horizon-architecture
.\.venv\Scripts\python -m denguekay.data.ingestion.release_bundles --estudio 01_eda --raiz ..\denguekay-horizontes
.\.venv\Scripts\python -m denguekay.data.ingestion.release_bundles --estudio 03_first_models_and_ablations --solo gold_anterior.zip --raiz ..\denguekay-horizontes
.\.venv\Scripts\python -m denguekay.data.ingestion.release_bundles --estudio 04_horizon_architecture --raiz ..\denguekay-horizontes
# En la copia del tag, con su propio entorno
cd ..\denguekay-horizontes
python -m venv .venv   # entorno propio: las dependencias pueden diferir de las de main
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m jupyter nbconvert --to notebook --execute --inplace notebooks/31_modelado_arquitectura_horizontes.ipynb
```

Equipo de referencia de las cifras: GPU NVIDIA (`device="cuda"`), XGBoost 3.4.1.
