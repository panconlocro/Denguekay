# 04 · Arquitectura multi-horizonte (h=2, 3, 4)

- **Pregunta:** ¿qué estrategia multi-horizonte y qué formulación de la salida (conteo y
  probabilidad de brote) usar para h=2, 3 y 4, bajo un protocolo preregistrado?
- **Decisión:** **E3 + S4_s2**: un XGBoost `multi_output_tree` con `count:poisson` predice
  (t+2, t+3, t+4) desde el mismo origen; P(casos ≥ k) con binomial negativa NB2 y Platt
  cronológico; alerta con probabilidad calibrada ≥ 0,50. Es un solo modelo a desplegar en lugar de
  seis ([arquitectura_horizontes.md](docs/arquitectura_horizontes.md), «Fase 5: síntesis y
  decisión»; encargo en [plan_arquitectura_horizontes.md](docs/plan_arquitectura_horizontes.md)).
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

```powershell
git worktree add ..\denguekay-horizontes study/horizon-architecture
cd ..\denguekay-horizontes
# data/ no está en git: copia (o enlaza) la carpeta data/ del repo principal.
python -m venv .venv   # entorno propio: las dependencias pueden diferir de las de main
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m jupyter nbconvert --to notebook --execute --inplace notebooks/31_modelado_arquitectura_horizontes.ipynb
```

Equipo de referencia de las cifras: GPU NVIDIA (`device="cuda"`), XGBoost 3.4.1.
