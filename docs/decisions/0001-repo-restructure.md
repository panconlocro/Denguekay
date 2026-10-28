# ADR 0001: reestructurar el repositorio como monorepo, sin cambios de comportamiento

- **Estado:** aceptada (encargo e inventario aprobados por Rosa el 27/10/2026).
- **Fecha:** 28/10/2026, antes de mover cualquier archivo (fase 2).
- **Punto de partida:** `main` en `9758359` (tag `pre-restructure` = `3ad8312`); fase 1 mergeada en `3f19431`.

## Contexto

`main` tiene todo el trabajo: EDA, feature engineering, backend TB1 y los estudios de modelado. Las
ramas viejas se borraron y quedaron como tags: `archive/*` (12), `model/v0`–`v2`,
`study/horizon-architecture`, `study/fe-hyperparameters` y `pre-restructure`. El problema es la
organización:

- `src/modeling/` mezcla el modelo de producción con el código de cada experimento (36 módulos);
- `tests/` tiene unos 60 archivos planos;
- `notebooks/` va del 01 al 35 sin separar el pipeline de la investigación;
- no se ve dónde empieza y dónde acaba cada versión del modelo;
- el backend (`src/api`, `src/db`, `src/serving`) está mezclado con todo lo demás.

## Decisión

Separar **producto** (pipeline de datos, modelo vigente, serving, BD, API y, más adelante, el
frontend) de **investigación** (EDA y estudios), con un registro explícito de versiones de modelo,
código en inglés y **cero cambios de comportamiento**.

### Estructura objetivo (ajustada con el inventario de la fase 0)

```
Denguekay/
├── apps/
│   ├── api/                  # app FastAPI (hoy src/api); tools/: benchmark, export_openapi, smoke_test
│   └── web/                  # placeholder: README con el plan (React + Vite); sin código todavía
├── src/denguekay/            # paquete instalable (pyproject.toml; pip install -e .)
│   ├── config/               # rutas (hoy utils/paths.py), carga de config.yaml, ajustes
│   ├── data/                 # ingestion/, processing/, validation/ (GX), calendar, keys, loading, seasons
│   ├── features/             # gold, variables B3, etiqueta y umbral de brote, spatial
│   ├── model/                # E3·S4: entrenar, predecir, calibrar; configuraciones congeladas; tracking MLflow; dispositivo
│   ├── evaluation/           # protocolo, métricas, episodios, inicios, variantes, tuning, complemento de clima, aceptación, caché
│   ├── serving/              # hoy src/serving
│   ├── db/                   # modelos SQLAlchemy, sesión, migraciones Alembic
│   └── pipelines/            # actualización semanal (hoy src/update_dataset_module.py)
├── pipelines/notebooks/      # notebooks 01–09 y 10_silver_to_gold (hoy 22): siguen siendo producto
├── models/
│   ├── registry/             # versionado en git: v0/, v1/, v2/ y CHANGELOG.md
│   ├── storage/              # artefactos (no versionados; la ruta no cambia: la BD la referencia)
│   └── experimentos/         # salidas de estudios (no versionadas; los tests de reproducción leen de aquí)
├── research/
│   ├── 01_eda/                          # notebooks 10–16, src/eda, docs/eda
│   ├── 02_feature_engineering/          # 17–21 y 23, diagnóstico de clima y socio, docs/feature_engineering
│   ├── 03_first_models_and_ablations/   # 24–30, ablacion_*.py, primer XGBoost, validación compacta
│   ├── 04_horizon_architecture/         # 31, informe de arquitectura multi-horizonte
│   └── 05_fe_hyperparameters/           # 32–35 (incluye el complemento de clima)
├── tests/                    # espejo del producto: data/, features/, model/, evaluation/, serving/, db/, api/
├── data/                     # sin cambios de rutas ni de contenido
├── configs/config.yaml
├── docs/                     # architecture.md (mapa del repo), decisions/ (ADR), backend/ (OE2, contrato API)
├── mlflow.db, mlartifacts/   # se quedan en la raíz (rutas absolutas en los runs)
└── pyproject.toml, requirements, alembic.ini, README.md, CONTRIBUTING.md, CLAUDE.md, AGENTS.md
```

### Reglas del encargo

1. **Sin cambios de comportamiento.** Nada de funcionalidad nueva, ni de gold v2, ni de integración
   de la V2 en serving, ni de convertir el pipeline de notebooks a scripts (eso es el encargo de
   integración). Si algo exige un cambio de lógica, se propone a Rosa y se espera.
2. **Guardas de equivalencia**, fijadas en la fase 1 y comprobadas al cerrar cada fase:
   - la suite de producto completa en verde (con PostgreSQL);
   - V1 y V2 reproducen **bit a bit** sus predicciones de referencia (`test_configuracion_final` y
     `tests/test_equivalence.py`);
   - el contrato de `docs/backend/openapi.json` no cambia;
   - `alembic upgrade head` sobre una BD vacía da el mismo esquema que hoy;
   - la API arranca con uvicorn y pasa `prueba_humo`.
3. **Contratos que no se renombran:** tablas y columnas de la BD (OE2), campos del contrato de la
   API, columnas de los datasets en `data/`, nombres de los artefactos ya registrados en la BD y la
   ruta `models/storage/`. El resto del código del producto (paquetes, módulos, funciones, clases,
   variables, docstrings y comentarios) pasa a **inglés**. Documentación, notebooks, informes y
   textos visibles para el usuario quedan en **español**.
4. **`data/` es de solo lectura.** No se mueve ni se regenera nada ahí. Los notebooks 01–09 escriben
   en `data/`, así que no se ejecutan: se verifica que sus imports resuelven.
5. **Investigación congelada.** Los notebooks 10–35 no se vuelven a correr en `main`; sus resultados
   ya están en informes, métricas, figuras y MLflow. Su código, tests y notebooks se mueven a
   `research/<estudio>/` **tal como están**: no se adaptan, no corren en el CI y no se garantiza que
   importen. Cada README de estudio dice cómo reproducirlo desde su tag. Lo que el producto o los
   estudios futuros necesitan es **producto** y pasa al paquete con nombres en inglés y tests. Los
   estudios futuros irán en `research/06_.../` y usarán el paquete.
6. **Dependencias en un solo sentido:** `research/` puede importar `denguekay`; `denguekay` y
   `apps/` nunca importan `research/` (lo verifica un test).
7. **Git:** una rama y un PR por fase (`refactor/<fase>`), merge commit, sin co-autor, `git mv` para
   conservar el historial, commits chicos (un subpaquete por commit en la fase 3). Nunca se trabaja
   sobre `main` ni se mergea un PR sin Rosa.
8. Cada fase avisa qué rutas cambiaron para quien tenga trabajo local.
9. **Cada fase deja el repo coherente:** en la misma fase se actualizan `CLAUDE.md`, `AGENTS.md`,
   `estructuraRepo.md`, subagentes, skills y CI en lo que toque a las rutas que cambian. La fase 5
   solo agrega documentación nueva.

### Fases

| Fase | Rama | Contenido |
|---|---|---|
| 0 | — | Inventario sin cambios en el repo |
| 1 | `refactor/package-layout` | `pyproject.toml`, guardas automatizadas y línea base (mergeada en `3f19431`) |
| 2 | `refactor/research-archive` | Investigación a `research/` con README por estudio; sus tests salen del CI |
| 3 | por definir | Producto a `src/denguekay/` y `apps/api/`, en inglés, un subpaquete por commit; test de dependencias en un solo sentido |
| 4 | por definir | `models/registry/v0`–`v2` con ficha y `CHANGELOG.md`; la configuración V2 se carga desde el paquete |
| 5 | por definir | Higiene de la raíz, `docs/architecture.md`, README nuevo y `apps/web/README.md` |
| Cierre | — | Guardas completas, `revisor-backend` y tag `restructure-done` tras el último merge |

### Tags que reproducen cada estudio (verificados en la fase 0)

| Estudio | Tag | Commit |
|---|---|---|
| `01_eda` | `archive/EDA` | `4444382` |
| `02_feature_engineering` | `archive/feature-engineering` | `c9ca044` |
| `03_first_models_and_ablations` | `archive/training` (completo: notebooks 24–30 y su código) | `573219d` |
| `04_horizon_architecture` | `study/horizon-architecture` | `808c340` |
| `05_fe_hyperparameters` | `study/fe-hyperparameters` | `e4bc7b7` |
| Cualquiera | `pre-restructure` (alternativa válida) | `3ad8312` |

`train.py` y `seguimiento_mlflow.py` cambiaron después de `archive/training` (corrección del
calendario de 2025, horizontes generalizados y deduplicación en MLflow). `archive/training` reproduce
el estudio 03 tal como se corrió; `pre-restructure`, con el código corregido.

## Decisiones del inventario (D1–D6)

**D1. Huella de las configuraciones congeladas.** Hoy `configuracion_final.huella()` es el SHA-256
del JSON de la configuración más el texto de cinco módulos (`estrategias_horizonte`,
`features_inicio`, `hiperparametros`, `protocolo_arquitectura`, `salida_probabilistica`); mover o
traducir esos módulos la cambia aunque las predicciones no cambien.
- Las huellas actuales se guardan como **históricas** en la ficha del registro y en el test:
  V1 `88ed2a43b0171a0878b99122b70109be61b27d5d4d29a2b93eae55066fd8f945` (`d6bd0be`) y
  V2 `c36d7a80d1896a203874bf271bd78f1078850e1faa381e2b17e9ba04b07d5569` (`424a148`).
- La nueva `fingerprint()` es **de comportamiento**: SHA-256 del JSON de la configuración + SHA-256
  de las predicciones de referencia en orden canónico (semilla 17), no del código fuente. Ningún
  refactor futuro la cambia si las predicciones son idénticas.
- En la ficha y en `fe_hiperparametros.md`, en la sección del congelamiento, queda escrito: la
  definición de la huella cambió en la reestructuración (fecha y commit); la equivalencia con la
  configuración congelada se demuestra con predicciones idénticas bit a bit; el modelo no cambió.
- No cambia la fecha de congelamiento ni la ventana del test de 2026.
- *Nota de la fase 1:* XGBoost es determinista para un dispositivo y un número de hilos fijos, pero
  CPU y CUDA (y distinto `n_jobs` en CPU) dan bits distintos. La huella de las predicciones de
  referencia debe fijar el dispositivo y los hilos; se concreta en la fase 4.

**D2. Contrato de la API.** Los handlers (de los que salen los `operationId`) y los esquemas
Pydantic de la API conservan sus nombres en español, porque forman parte del contrato. Las clases del
ORM pasan a inglés; sus atributos (las columnas) no se tocan.

**D3. Notebook 22.** Es producto: regenera gold. Pasa a `pipelines/notebooks/10_silver_to_gold.ipynb`.

**D4. Módulos de estudio que usa el producto.** Pasan completos al paquete `diagnostico_arquitectura`,
`diagnostico_inicios`, `preregistro_fe` y `complemento_clima`. De `src/eda`, solo
`cargar_integrado`, `asignar_temporada` y `distancias_km`/`pesos_*` pasan a `data.loading`,
`data.seasons` y `features.spatial`, con tests. La duplicación con la copia congelada en
`research/01_eda` es aceptable.

**D5. Salidas del estudio 03 que lee serving (V0).**
`docs/modeling/metricas/validacion_temporal_compacta.json` y
`models/experimentos/validacion_temporal_compacta/predicciones_por_bloque.csv` quedan en su lugar en
la fase 2 y se mueven a `models/registry/v0/` en la fase 4.

**D6. Huella de publicación.** `publicar.hashes_codigo()` calcula el hash del código de serving, db,
modeling, validation y utils. Después de la fase 3, la primera publicación no reutilizará la ejecución
anterior y creará versiones nuevas; es lo esperado, porque el código cambió de lugar. Se documenta en
la ficha de V0 y en `docs/backend/operacion.md`.

### Otros ajustes aceptados

- `mlflow.db` y `mlartifacts/` se quedan en la raíz: los 20 experimentos y sus runs guardan
  `artifact_location` absolutos (`file:///C:/Users/Rosa/.../mlartifacts/...`).
- Las cachés `.pkl` de investigación (`models/experimentos/arquitectura_horizontes/cache/`) no se
  migran: guardan referencias a módulos y se regeneran desde el tag del estudio.
- Un test busca restos de `src.`/`src/` en el producto al cierre de la fase 3 (además de los imports,
  hay referencias en texto: el subproceso del notebook 09, `cache_experimentos.CODIGO_EXTRA` y las
  llaves de `test_serving_operacion`).

## Consecuencias

- Cada fase deja la suite y las guardas en verde. Si una guarda falla, hubo un cambio de
  comportamiento; la línea base de `tests/fixtures/equivalence/` no se regenera.
- La investigación deja de correr en el CI; reproducirla exige su tag.
- Quien tenga trabajo local en el backend debe rehacer sus rutas después de la fase 3 (cada resumen
  de fase lista las rutas que cambian).
