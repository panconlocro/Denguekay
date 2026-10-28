# Denguekay — contexto y reglas para Claude Code

## Qué es este proyecto
Tesis de la UPC (Rosa y Nicolás): aplicación web de Machine Learning para **predecir brotes de dengue en Piura, Perú, con al menos 4 semanas de anticipación**. Metodología CRISP-DM; el **Hito 2** es Data Understanding / EDA. Stack: Python, pandas, scikit-learn, XGBoost, Great Expectations, Open-Meteo, Supabase; todo corre local en VS Code (ya no Colab). **MLflow** (seguimiento de experimentos) y **Great Expectations** (calidad de datos) están integrados en el modelado; ver `docs/modeling/mlflow_great_expectations.md`. DVC sigue descartado: no lo agregues.

Datos: panel **distrito × semana epidemiológica**, 65 distritos de Piura, 2017-2025. Fuentes: clima (Open-Meteo), sociodemografía (censo) y casos de dengue (Excel epidemiológico hasta 2024 + Sala Situacional MINSA para 2025).

## Estado del esquema medallion (no lo rompas)
```
bronze  -> crudo tal cual llegó de la fuente
silver  -> limpio, un dataset por fuente
silver/integrado -> fuentes silver unidas (meteo+socio+epi), SIN features derivadas
gold    -> dataset con feature engineering: h2 y h4 (+ manifest_fase6.json). Lo regenera el equipo (notebook 22).
```
Gold ya existe (h=2 y h=4). Solo lo regenera el equipo desde `features.py`/notebook 22; Claude propone los cambios. **Dataset de trabajo para el EDA:** `data/silver/integrado/meteo_socio_epi_piura_2017_2025.csv` (cargar siempre con `src.eda.carga.cargar_integrado()`).

## Reglas duras
1. **Estructura:** antes de crear cualquier archivo lee `docs/estructuraRepo.md` y respétalo. Si algo nuevo no cabe en esa estructura, propón el cambio a Rosa y actualiza ese documento en el mismo cambio; no inventes carpetas por tu cuenta.
2. **Los datos son de solo lectura.** Nunca escribas, borres ni modifiques nada dentro de `data/` (ni bronze, ni silver, ni reference, ni gold). Si el análisis exige corregir datos, lo **reportas y propones** el cambio en el pipeline (notebooks 03–09 / `src/processing`); no lo haces tú.
3. **Variables derivadas: solo en memoria.** En el EDA no se construyen features. En el modelado sí se calculan variables nuevas, pero solo en memoria, con funciones de `src/modeling/` y un test de no fuga por perturbación. Nunca se guardan en `data/`. Si una variable entra a la configuración final, se **propone** el cambio en `features.py` y el equipo regenera gold.
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
- Idioma (desde el 27/10/2026, ver `CONTRIBUTING.md`):
  - **Código en inglés:** identificadores (snake_case), comentarios y docstrings del código nuevo. No renombres código existente solo por el idioma.
  - **Sin cambios hasta nuevo aviso:** el esquema de BD sigue el documento OE2 (nombres en español de `docs/backend/ddl_oe2.sql`) y las columnas de los datos conservan sus nombres actuales.
  - **Documentación en español:** `docs/`, markdown de notebooks, informes, títulos y etiquetas de gráficos (con unidades: °C, mm, casos por 100 000 hab.).
- Notebooks numerados según el paso del pipeline; los del EDA usan el rango `10_eda_*` en adelante (ver la skill `eda-dengue`).
- Salidas del EDA: figuras en `docs/eda/figuras/<fase>/`, cifras clave en `docs/eda/metricas/<fase>.json`, conclusiones en `docs/eda/hallazgos.md`. Todo eso sí se versiona.

## Control de versiones (detalle en `CONTRIBUTING.md`)
- Solo `main` es permanente; no hagas commits directos en ella. Cada cambio va en una rama `feat/`, `fix/`, `refactor/`, `docs/`, `chore/` o `exp/`, con nombre en inglés y kebab-case, y entra a `main` por PR con el CI en verde.
- Commits con Conventional Commits en inglés (`feat(api): add risk map endpoint`).
- Merge siempre con «Create a merge commit». **Nunca reescribas historia publicada** (squash, rebase, `--amend`, `push --force`): los informes citan hashes.
- Tags anotados: `model/vN` al congelar una versión de modelo, `study/<nombre>` al cerrar un estudio. Las ramas anteriores a la limpieza están en los tags `archive/*`.

## Cómo se trabaja con Rosa
- Rosa trabaja **fase por fase y confirma cada una antes de seguir**. Al terminar una fase presentas el resumen y te detienes.
- Prefiere los resúmenes como texto plano en el chat, no como archivos para descargar. Escríbele en español, directo, sin relleno.
- Ante una ambigüedad que cambie el análisis (definición de brote, tratamiento del 2025, qué variables descartar) **pregunta**; no decidas en silencio.

## Herramientas del proyecto
- Skill `eda-dengue` (`.claude/skills/eda-dengue/`): método, fases y estándares del EDA. Úsala para cualquier tarea de análisis exploratorio.
- Subagente `revisor-eda` (`.claude/agents/revisor-eda.md`): auditor independiente que recalcula cada cifra citada al cierre de cada fase.


<!-- inicio: backend OE2 -->
## Backend (refactor OE2, TB1)
- **Fuente de verdad del esquema y la API:** `docs/backend/especificacion_oe2.md` y `docs/backend/ddl_oe2.sql` (copiados del documento OE2: sección 5, Anexo B y Tabla 2). El código se adapta al documento, no al revés. Toda diferencia se justifica en `docs/backend/desviaciones_oe2.md` y se le consulta a Rosa antes.
- **Alcance TB1: todo local.** PostgreSQL local + SQLite para tests, uvicorn local, artefactos en `models/storage/` mediante un adaptador local. Prohibido configurar o desplegar Supabase/Render en esta etapa.
- Stack: FastAPI + Pydantic v2, SQLAlchemy 2 + Alembic, psycopg 3. Las migraciones en `src/db/migraciones/` son la autoridad del esquema; nunca `create_all` al arrancar la API.
- Comandos (PowerShell, desde la raíz):
  - `.\.venv\Scripts\python -m alembic upgrade head`
  - `.\.venv\Scripts\python -m src.serving.cargar_datos`
  - `.\.venv\Scripts\python -m uvicorn src.api.main:app --host 127.0.0.1 --port 8000`
  - `.\.venv\Scripts\python -m coverage run --source=src/db,src/serving,src/api -m unittest discover -s tests` y `... -m coverage report -m`
- Tests en BD temporal; nunca contra la BD de Rosa. Cobertura mínima 80 %.
- Al cerrar cada fase del refactor, invoca al subagente `revisor-backend` y pega su tabla en el resumen.
<!-- fin: backend OE2 -->
