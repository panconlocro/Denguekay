# Denguekay — contexto y reglas para Claude Code

## Qué es este proyecto
Tesis de la UPC (Rosa y Nicolás): aplicación web de Machine Learning para **predecir brotes de dengue en Piura, Perú, con al menos 4 semanas de anticipación**. Metodología CRISP-DM; el **Hito 2** es Data Understanding / EDA. Stack: Python, pandas, scikit-learn, XGBoost, Great Expectations, Open-Meteo, Supabase; todo corre local en VS Code (ya no Colab). **MLflow** (seguimiento de experimentos) y **Great Expectations** (calidad de datos) están integrados en el modelado; ver `docs/modeling/mlflow_great_expectations.md`. DVC sigue descartado: no lo agregues.

Datos: panel **distrito × semana epidemiológica**, 65 distritos de Piura, 2017-2025. Fuentes: clima (Open-Meteo), sociodemografía (censo) y casos de dengue (Excel epidemiológico hasta 2024 + Sala Situacional MINSA para 2025).

## Estado del esquema medallion (no lo rompas)
```
bronze  -> crudo tal cual llegó de la fuente
silver  -> limpio, un dataset por fuente
silver/integrado -> fuentes silver unidas (meteo+socio+epi), SIN features derivadas
gold    -> SOLO el dataset con feature engineering ya aplicado. HOY ESTÁ VACÍO.
```
Por indicación del asesor de tesis, gold no se toca hasta que el equipo haga el feature engineering. **Dataset de trabajo para el EDA:** `data/silver/integrado/meteo_socio_epi_piura_2017_2025.csv` (cargar siempre con `src.eda.carga.cargar_integrado()`).

## Reglas duras
1. **Estructura:** antes de crear cualquier archivo lee `docs/estructuraRepo.md` y respétalo. Si algo nuevo no cabe en esa estructura, propón el cambio a Rosa y actualiza ese documento en el mismo cambio; no inventes carpetas por tu cuenta.
2. **Los datos son de solo lectura.** Nunca escribas, borres ni modifiques nada dentro de `data/` (ni bronze, ni silver, ni reference, ni gold). Si el análisis exige corregir datos, lo **reportas y propones** el cambio en el pipeline (notebooks 03–09 / `src/processing`); no lo haces tú.
3. **Nada de feature engineering.** No construyas ni guardes lags, medias móviles, tasas, dummies ni ninguna columna derivada como parte del dataset. Para *analizar* puedes calcular lags o tasas en memoria dentro de un notebook; nunca se persisten en `data/`. El EDA recomienda, el feature engineering (fase posterior, decidida por el equipo) implementa.
4. **`ubigeo` es string de 6 dígitos** (con ceros a la izquierda) en todo el pipeline. Nunca lo castees a int.
5. **Rutas** siempre desde `src/utils/paths.py`. Nada de rutas absolutas ni `C:\...` en código.
6. **`src/` vs `notebooks/`:** si la lógica se reutiliza o pasa de ~10 líneas, va en `src/` (para EDA: `src/eda/`) con un test simple en `tests/` si tiene lógica no trivial. El notebook orquesta, muestra y comenta.
7. **Citas y referencias:** solo reales y verificadas. Prohibido inventar autores, títulos, cifras de la literatura o URLs. Si no puedes verificar una afirmación de dominio, márcala como *hipótesis* o pídele la fuente a Rosa.
8. **Honestidad estadística:** no afirmes algo que no esté calculado en una celda ejecutada. Distingue observación / hipótesis / conclusión. Con pocos brotes (años 2017 y 2023 concentran la mayor parte de los casos) no generalices ni uses lenguaje causal.

## Entorno
- Windows + PowerShell. Python del proyecto: `.venv\Scripts\python` (`.\.venv\Scripts\python -m pip install -r requirements.txt`). Corre los módulos desde la raíz del repo: `python -m src...`.
- Los archivos del repo usan **CRLF**; no cambies finales de línea de archivos existentes. Codificación UTF-8 (hay tildes y ñ).
- Tests: `python -m unittest discover -s tests` (o `python -m unittest tests.test_<nombre>`).
- Ejecutar un notebook de punta a punta: `python -m jupyter nbconvert --to notebook --execute --inplace notebooks/<archivo>.ipynb`.

## Convenciones
- Idioma: **español** en markdown de notebooks, comentarios, docstrings, títulos y etiquetas de gráficos (con unidades: °C, mm, casos por 100 000 hab.). Identificadores en snake_case como el resto del repo.
- Notebooks numerados según el paso del pipeline; los del EDA usan el rango `10_eda_*` en adelante (ver la skill `eda-dengue`).
- Salidas del EDA: figuras en `docs/eda/figuras/<fase>/`, cifras clave en `docs/eda/metricas/<fase>.json`, conclusiones en `docs/eda/hallazgos.md`. Todo eso sí se versiona.

## Cómo se trabaja con Rosa
- Rosa trabaja **fase por fase y confirma cada una antes de seguir**. Al terminar una fase presentas el resumen y te detienes.
- Prefiere los resúmenes como texto plano en el chat, no como archivos para descargar. Escríbele en español, directo, sin relleno.
- Ante una ambigüedad que cambie el análisis (definición de brote, tratamiento del 2025, qué variables descartar) **pregunta**; no decidas en silencio.

## Herramientas del proyecto
- Skill `eda-dengue` (`.claude/skills/eda-dengue/`): método, fases y estándares del EDA. Úsala para cualquier tarea de análisis exploratorio.
- Subagente `revisor-eda` (`.claude/agents/revisor-eda.md`): auditor independiente que recalcula cada cifra citada al cierre de cada fase.
