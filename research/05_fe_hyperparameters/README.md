# 05 · Feature engineering e hiperparámetros sobre E3·S4_s2

- **Pregunta:** con la arquitectura y el protocolo del estudio 04 fijos, ¿qué variables (bloque A de
  gold y bloque B nuevo, en memoria) e hiperparámetros mejoran el pronóstico, en especial el de los
  inicios de brote? Más un encargo complementario: ¿mejora el clima de gold el conteo?
- **Decisión:**
  - **V1** = C3 (`base_6` + B3) · E3 · S4_s3, α dentro de la muestra, hiperparámetros heredados
    (empate en el tuning), Platt, p ≥ 0,50, semilla 17. Congelada en `d6bd0be` (tag `model/v1`).
  - **V2** = V1 + A3 (humedad y precipitación de gold, media de 5 semanas hasta el origen): mejora
    el conteo en h=2, 3 y 4 sin que la alerta pierda en ninguno. Congelada en `424a148` (tag
    `model/v2`). **Es la vigente.**
  - Detalle en [fe_hiperparametros.md](docs/fe_hiperparametros.md), secciones «Fase 5 · Síntesis del
    encargo» y «Encargo complementario · clima para el conteo».
- **Versión de modelo resultante:** V1 (reemplazada por la V2) y V2 (vigente). Ninguna se sirve
  todavía: integrar la V2 en serving es un encargo aparte.
- **Tag:** `study/fe-hyperparameters` (`e4bc7b7`). Alternativa: `pre-restructure` (`3ad8312`).

## Contenido

| Carpeta | Qué hay |
|---|---|
| `notebooks/` | 32 (variables de inicio), 33 (hiperparámetros), 34 (verificación cruzada), 35 (clima para el conteo) |
| `code/` | `experimentos_variables.py` |
| `tests/` | `test_experimentos_variables.py` |
| `docs/` | informe, `metricas/fe_hiperparametros.json` y `figuras/` |

Lo que sigue en `src/` porque lo usan las configuraciones congeladas o serving:
`configuracion_final.py`, `features_inicio.py`, `preregistro_fe.py`, `diagnostico_inicios.py`,
`hiperparametros.py`, `fe_hiperparametros.py`, `complemento_clima.py`, `diccionario_variables.py` y
`cache_experimentos.py`. Pasan al paquete en la fase 3 (decisión D4). Las predicciones de referencia
de V1 y V2 están en `models/experimentos/fe_hiperparametros/` (no versionado); las leen
`tests/test_configuracion_final.py` y las guardas de equivalencia.

Experimentos de MLflow: `denguekay/fe_hiperparametros_fase0_referencia_B`, `..._fase2a_bloque_A`,
`..._fase2b_bloque_B`, `..._fase2c_combinada`, `..._fase3_estudio`, `..._fase4_verificacion` y
`..._complemento_clima`.

## Cómo reproducir

```powershell
git worktree add ..\denguekay-fe-hp study/fe-hyperparameters
cd ..\denguekay-fe-hp
# data/ no está en git: copia (o enlaza) la carpeta data/ del repo principal.
python -m venv .venv   # entorno propio: las dependencias pueden diferir de las de main
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m jupyter nbconvert --to notebook --execute --inplace notebooks/32_modelado_fe_inicios.ipynb
```

Repite con 33, 34 y 35. Para comprobar las configuraciones congeladas sin repetir el estudio, en
`main` basta con `python -m unittest discover -s tests -p "test_configuracion_final.py"`.
