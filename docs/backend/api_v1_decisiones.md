# API v1: inventario y decisiones (fase 1)

- **Encargo:** `docs/backend/prompt_api_v1.md`, fase 1 (diagnóstico, sin tocar código).
- **Rama:** `docs/api-v1-decisions`, desde `develop` en `57e4df0`.
- **Fecha:** 29/10/2026.
- **Estado:** **respondido por Rosa el 29/10/2026** (§3). Las respuestas mandan sobre las recomendaciones de
  la §2 cuando difieren.

Convenciones: *observación* = comprobado en el código o en los datos (con el comando o la línea);
*hipótesis* = no verificado todavía; *recomendación* = lo que propongo.

---

## 1. Inventario: lo que hoy ata la API y el serving a la v0

### 1.1 Horizontes fijos (2 y 4; h=3 «sin modelo»)

| Archivo:línea | Qué fija |
|---|---|
| `src/denguekay/features/gold.py:35` | `HORIZONS = (2, 4)`: solo hay gold para h=2 y h=4 |
| `src/denguekay/model/future_rows.py:25-26` | `build_future_rows` rechaza todo horizonte fuera de `gold.HORIZONS` |
| `src/denguekay/serving/settings.py:32-33` | `service_settings` falla si `serving.horizontes` no es subconjunto de `(2, 4)` |
| `configs/config.yaml:25` | `horizontes: [2, 4]` |
| `src/denguekay/serving/inference.py:25` | `H3_REASON = "sin modelo para h=3"` |
| `src/denguekay/serving/inference.py:153-156` | `infer` lanza `InferenceUnavailable` (409) con h=3 y `ValueError` fuera de 2/4 |
| `src/denguekay/serving/publish.py:84-88` | `publish` solo acepta 2 y 4 y exige el archivo gold de cada horizonte |
| `src/denguekay/serving/publish.py:125-126` | CLI `--horizontes` con `choices=(2, 3, 4)` y ayuda «2 y 4» |
| `apps/api/queries.py:11` | importa `H3_REASON`, `TASKS` y `select_versions` del serving |
| `apps/api/queries.py:150-154` | `no_prediction_reason`: motivo especial para h=3 |
| `apps/api/queries.py:183` | `series`: `disponible=false` fijo para h=3 |
| `apps/api/queries.py:193` | `current_predictions`: no busca corte si h=3 |
| `apps/api/queries.py:314` | `models_in_use`: motivo h=3 |
| `apps/api/routers/data.py:39, 44` | `predicciones`: docstring y atajo para h=3 |
| `apps/api/dependencies.py:18` | `Horizon`: descripción «2 o 4 con modelo; 3 responde no_disponible» (aparece en el OpenAPI) |
| `apps/api/schemas.py:216` | `SolicitudInferencia.horizonte`: descripción «3 responde 409» (en el OpenAPI) |
| `apps/api/main.py:49` | respuesta 409 descrita como «h=3, artefacto, umbrales» (en el OpenAPI) |
| `apps/api/routers/admin.py:29` | docstring de `inferencias` (en el OpenAPI) |
| `docs/backend/contrato_api.md:33-34` | contrato publicado: h=3 sin modelo |
| `docs/backend/desviaciones_oe2.md:31` | fila «Horizonte 3» |

El esquema ya admite h=3: `CHECK (horizonte IN (2, 3, 4))` en `version_modelo` y `prediccion`
(`src/denguekay/db/migrations/versions/0003_oe2_esquema_del_documento_oe2.py:206, 254`), y el parámetro
`Horizon` de la API acepta 2–4 (`apps/api/dependencies.py:18`).

### 1.2 Variantes y protocolo compacto de la v0

| Archivo:línea | Qué fija |
|---|---|
| `src/denguekay/serving/settings.py:13` | `ALLOWED_VARIANTS = {"base_4", "base_6", "base_6_poblacion_2017"}` |
| `src/denguekay/serving/settings.py:34-35` | `variantes` debe tener exactamente `clasificacion` y `regresion` |
| `configs/config.yaml:26-28` | `clasificacion: base_6_poblacion_2017`, `regresion: base_6` |
| `src/denguekay/model/future_rows.py:9, 27-31` | `compact_variants`: solo admite columnas de `base_6_poblacion_2017` |
| `src/denguekay/serving/models.py:18, 51, 59` | `compact_variants(h)[name]` define variables y entrenamiento |
| `src/denguekay/serving/protocol.py:29-73` | `load_protocol`: valida las métricas y el CSV OOS del protocolo compacto de la v0 contra el SHA-256 de gold h=2/h=4 |
| `src/denguekay/serving/protocol.py:114-122` | `variant_metrics`: forma de `metricas` (bloques del protocolo compacto) |
| `src/denguekay/serving/models.py:61-63` | `umbral_probabilidad` del bloque `calendario_2025` y `sha256_dataset` = SHA-256 de gold |

### 1.3 Dos tareas y un booster por tarea

| Archivo:línea | Qué fija |
|---|---|
| `src/denguekay/serving/inference.py:23` | `TASKS = ("clasificacion", "regresion")` |
| `src/denguekay/serving/inference.py:103-123` | `select_versions`: una versión activa (o experimental) por tarea; sin las dos, no hay predicción |
| `src/denguekay/serving/inference.py:172-178` | `infer`: un booster para la probabilidad y otro para los casos |
| `src/denguekay/serving/inference.py:141-142` | `_record`: `id_version_clasificador` e `id_version_regresor` |
| `src/denguekay/serving/models.py:17, 51, 54` | importa `BASE_PARAMS` (definido en `src/denguekay/model/train.py:37`) y `fit_models`, que devuelve la pareja `(regresor, clasificador)`; se elige con `[1 if clasificación else 0]` |
| `src/denguekay/serving/models.py:23, 89-93` | `PREFIXES` y `next_code`: códigos `clf-h{h}-vN` y `reg-h{h}-vN` |
| `apps/api/queries.py:121-124, 135-136` | `prediction_dtos`: busca el clasificador y el regresor; `alerta_modelo` usa `clf.umbral_probabilidad` |
| `apps/api/queries.py:305-317` | `models_in_use`: recorre `TASKS` |
| `apps/api/routers/admin.py:59-71` | activación por `(tarea, horizonte)`, una versión a la vez |
| `apps/api/schemas.py:99-100, 170, 193-194` | `id_version_clasificador`, `id_version_regresor`, `tarea: Literal[...]`, `seleccion` |
| `configs/config.yaml:32-34` y `src/denguekay/serving/settings.py:38-43` | `seleccion_experimental` por horizonte y tarea (`clf-h2-v1`, `reg-h2-v1`, …) |
| `src/denguekay/serving/parameters.py:34-46` y `src/denguekay/serving/load_data.py:229-248` | lectura y siembra de `parametro_sistema.seleccion_experimental` |

### 1.4 El artefacto es siempre un booster XGBoost en JSON

| Archivo:línea | Qué fija |
|---|---|
| `src/denguekay/serving/artifacts.py:28-30` | `serialize_booster`: `save_raw(raw_format="json")` |
| `src/denguekay/serving/artifacts.py:33-42` | `_load_booster`: `xgb.Booster`, caché `lru_cache(maxsize=8)` por SHA, fuerza `device=cpu` |
| `src/denguekay/serving/artifacts.py:45-53` | `load_booster`: lee `ruta_artefacto` y compara su SHA-256 (409 `artefacto_invalido`) |
| `src/denguekay/serving/artifacts.py:56-77` | `predict_with_version`: `DMatrix`, `counts_from_log1p` para la regresión, `[0, 1]` para la clasificación, `feature_names` del booster |
| `src/denguekay/serving/models.py:56, 58, 77-79` | `algoritmo = "xgboost"`, importancias `gain` de `get_booster()` |
| `src/denguekay/serving/models.py:96-110` | ruta `modelos/<codigo>.json` |

### 1.5 Vector de variables: solo rezagos de casos, calendario y población 2017

| Archivo:línea | Qué fija |
|---|---|
| `src/denguekay/serving/inference.py:56-67` | `panel_from_db`: lee solo `ubigeo`, semana y `casos_dengue` (sin clima) |
| `src/denguekay/serving/inference.py:70-83` | `reference_from_db`: rellena con 0 las tres fracciones socio de 2017 (`DIRECT`); el modelo solo usa `log_poblacion_censo_2017` |
| `src/denguekay/serving/inference.py:86-98` | `vectors_from_db` delega en `build_future_rows` |
| `src/denguekay/model/future_rows.py:48, 70-75` | historia y calendario + `log_poblacion_censo_2017`; sin clima ni B3 |
| `src/denguekay/serving/load_data.py:183` | el calendario de la BD empieza el 2017-01-01 |

### 1.6 Predicciones OOS del protocolo de la v0

| Archivo:línea | Qué fija |
|---|---|
| `src/denguekay/serving/inference.py:24` | `OOS_BLOCKS = ("temporada_2022", "temporada_2023", "temporada_2024", "calendario_2025")` |
| `src/denguekay/serving/inference.py:267-318` | `import_oos`: lee el CSV del protocolo compacto por `cfg.variantes` (`:286-287`), exige ambas tareas (`:281`) |
| `src/denguekay/serving/publish.py:59` | la publicación siempre importa las OOS |
| `apps/api/queries.py:91-102` | `oos_runs` / `current_cutoff`: reconocen las OOS por `detalle.origen == "oos_protocolo"` |

### 1.7 Configuración y despliegue

| Archivo:línea | Qué fija |
|---|---|
| `src/denguekay/serving/settings.py:20` y `configs/config.yaml:31` | `servir_no_validadas` solo en `config.yaml` |
| `src/denguekay/serving/settings.py:22`, `configs/config.yaml:35` y `apps/api/main.py:57` | `cors_origen`: un solo origen fijo |
| `apps/api/main.py:18, 25` | la API lee `config.yaml` al arrancar (`service_settings`), con la validación de variantes v0 |
| `apps/api/main.py:44` | `version="2.0.0"` en OpenAPI (ver C5) |
| `src/denguekay/serving/publish.py:16-33` | `publish` importa `xgboost`, el protocolo y `tracking.log_report` (que importa `mlflow` de forma diferida, `src/denguekay/model/tracking.py:68`); corre en la PC, no en la API |

### 1.8 Tests y herramientas que fijan este comportamiento

Cambiarán en las fases 2–4, sin tocar la línea base de `tests/fixtures/equivalence/`.

| Archivo | Líneas con h=3, (2, 4), variantes o códigos `clf-`/`reg-` |
|---|---|
| `tests/api/test_api.py` | 51, 121, 135–222, 231–313, 331, 376–413 |
| `tests/serving/test_inference.py` | 99, 105, 118, 167, 174, 236, 251, 256 |
| `tests/serving/test_publish.py` | 54–123 |
| `tests/serving/test_protocol.py` | 24–56 |
| `tests/serving/test_future_rows.py` | 21, 24 |
| `tests/serving/test_policies.py` | 31, 74 |
| `tests/serving/test_load_data.py` | 67 |
| `tests/db/test_oe2_schema.py` | 54, 57, 234, 258, 270 |
| `tests/api/test_benchmark.py` | 112, 118 |
| `apps/api/tools/smoke_test.py` | 65–69, 107 |
| `apps/api/tools/benchmark.py` | 105, 110, 146 |
| `tests/test_equivalence.py:41-44` | guarda «el contrato de `openapi.json` no cambia» (se reemplaza en la fase 2) |

### 1.9 Observaciones sobre los datos (verificadas en esta fase, solo lectura)

Las calculé con `.\.venv\Scripts\python` sobre `SILVER_INTEGRATED`, gold h=2 y `SILVER_EPI_HISTORICAL`.
No escribí nada en `data/`.

1. **La humedad de la BD no reproduce A3 bit a bit.** `hum_rel_media` en silver tiene más de dos decimales
   (diferencia máxima con su redondeo a 2 decimales: 0,00429). La BD la guarda en `numeric(5,2)`, como pide el
   DDL (`ddl_oe2.sql:61`, migración `:166`, `load_data.py:35-36, 122`). Si A3 se calcula con los valores
   redondeados, `hum_rel_media_media5_h2` difiere de gold en hasta **0,00429**. `precip_total_mm` sí es exacta
   (diferencia 1,1e-13). Con los valores de silver, la media de 5 semanas coincide con gold en 2,8e-14: no es
   bit a bit por el orden de las sumas, pero queda muy por debajo de 1e-9. Afecta a M5 y a la fase 4.
2. **El umbral de brote redondeado cambia k en 32 filas.** `observacion_semanal.umbral_brote_casos` es
   `numeric(10,2)` (`load_data.py:166`). En gold h=2, `floor(umbral)` cambia al redondear a 2 decimales en
   32 de 30 485 filas. La v2 usa `k = max(⌊umbral⌋ + 1, 2)`, así que el k de la semana objetivo **no** debe
   leerse de esa columna: debe recalcularse con la regla de brote desde los casos (ver M4).
3. **Historia previa a 2017.** `epi_piura_semanal.csv` tiene 81 196 filas de 662 ubigeos de todo el país
   (2000–2024), solo de semanas con casos. Para los 65 distritos del panel hay 4 523 filas anteriores a 2017.
   Faltan del todo 3 distritos (`200204`, `200205`, `200209`); Rosa ya verificó que nunca tuvieron casos y que
   la ausencia vale cero. **Antes de 2017** faltan además otros 8 (11 en total: `200204`, `200205`, `200206`,
   `200208`, `200209`, `200303`, `200305`, `200307`, `200308`, `200403`, `200502`), que sí tienen filas desde
   2017. Con la regla actual («sin registro = cero») sus años 2000–2016 valen cero. Solo importa si se
   reconstruyen orígenes de 2017–2021 (ver M4).
4. **Platt y α.** `frozen_configs.predict` (`:120-125`) devuelve la probabilidad NB2 **sin calibrar**. Platt se
   aplica después, en `evaluation.protocol.calibrate_chronologically` (`protocol.py:113-137`), con las OOS de
   los bloques anteriores. La α es dentro de la muestra, por horizonte (`probabilistic_output.py:295-297`).
5. **Roles de la BD.** `rol_pipeline` no tiene INSERT en `prediccion`, `alerta` ni `parametro_sistema`
   (migración `:315-319`). Aun así, la publicación escribe en las tres (`import_oos`, `infer` y la siembra de
   `seleccion_experimental`). Hoy funciona porque todo corre con el dueño de la BD local. Ver D2.
6. **Gold y la v0.** `load_protocol` exige que el SHA-256 de gold h=2/h=4 coincida con las métricas guardadas
   de la v0 (`serving/protocol.py:46-53`). Si se regenera gold h=2 (por ejemplo, para agregar B3), la
   publicación de la v0 se rechaza hasta rehacer su protocolo. Ver M7.

---

## 2. Decisiones

Cada decisión trae una **recomendación** y su porqué. Al final hay una tabla para anotar la respuesta.

### Contrato (lo que ve el frontend)

**C1. Horizontes.**
*Recomendación:* la API acepta 2, 3 y 4, como el DDL. Los horizontes **disponibles** salen de la BD: los que
tienen una versión activa o en la selección experimental. Un horizonte sin modelo responde como hoy h=3, con
`disponible: false` y un motivo genérico «sin modelo para h=N». `POST /admin/inferencias` responde 409 con
`inferencia_no_disponible` (mismo código de hoy).
*Por qué:* el frontend no debe saber qué modelo existe. Con la v2, h=3 tendrá modelo sin cambiar el contrato.
El único cambio visible son los textos de las descripciones del OpenAPI (§1.1), que hoy mencionan h=3.

**C2. `GET /api/v1/configuracion` (extensión).**
*Recomendación:* una lectura pública y en caché, con:
`horizontes_disponibles`, `horizonte_por_defecto`, `cortes_riesgo` (de `parametro_sistema`), `niveles`
(código y etiqueta), `leyenda` (la misma de `/mapa-riesgo`), `semana_corte_vigente` por horizonte,
`experimental` y `nota`, y `version_contrato`.
*Por qué:* así el frontend no tiene nada en código duro y la leyenda sale de una sola fuente.
*Pregunta extra:* ¿el horizonte por defecto es **4** (el objetivo de la tesis, «al menos 4 semanas») o 2? Mi
recomendación es 4, guardado como clave nueva `horizonte_por_defecto` en `parametro_sistema` (sembrada por una
migración, sin desviación de tabla).

**C3. Incertidumbre de casos.**
*Recomendación:* en `PrediccionRespuesta` (y en `properties` del mapa), campos opcionales y anulables
`casos_intervalo_inferior`, `casos_intervalo_superior` y `nivel_intervalo` (0,80). Valen `null`, con motivo, si
el modelo no los da (la v0 no los da). Se guardan en **dos columnas nuevas y anulables de `prediccion`**
(migración y desviación de OE2) y los escribe el predictor.
*Por qué:* agregarlos ahora evita romper el contrato después. Guardarlos (en vez de calcularlos al leer) mantiene
la regla «la API solo conoce tablas»: calcular cuantiles NB2 al leer obligaría a la API a conocer α y
`scipy`.
*Alternativa:* no exponerlos en v1 y agregarlos después como cambio aditivo (minor). Es posible, pero el
frontend tendría que rediseñar la ficha del distrito.
*Pregunta extra:* ¿el nivel es 0,80 o 0,90?

**C4. Geometría del mapa.**
*Recomendación:* tipar `features` en el esquema como GeoJSON (RFC 7946), con `geometry` de tipo `Point`,
`Polygon` o `MultiPolygon`. Hoy se sirve `Point` (centroide, `queries.py:228, 237`); los polígonos llegarán
cuando haya una fuente con licencia (según el encargo, Tabla 35 de OE2; esa tabla no está en
`especificacion_oe2.md`, así que no la verifiqué).
*Por qué:* hoy `features` es `list[dict]` sin tipar (`schemas.py:148`). Tiparlo ya permite generar tipos
TypeScript útiles, y aceptar polígonos desde v1 evita un cambio que rompa el contrato.

**C5. Versión del contrato.**
*Observación:* hoy `info.version` es **`"2.0.0"`** (`apps/api/main.py:44`), y `/salud` lo devuelve como
`version_api`. Pasar a `"1.0.0"` parecería un retroceso.
*Recomendación:* separar las dos versiones:
- `info.version = "1.0.0"`: la versión del **contrato** v1, con semver documentado en `contrato_api.md`
  (cambio aditivo = minor; cambio que rompe = `/api/v2` y `feat(api)!`).
- cabecera `X-Version-Contrato: 1.0.0` en todas las respuestas;
- `version_api` de `/salud` sigue siendo la versión de la aplicación.

Lo pregunto porque el encargo pide `1.0.0` y hay una `2.0.0` publicada.
*Alternativa:* conservar `2.0.0` como versión del contrato y numerar desde ahí.

**C6. Fuera de v1 (confirmar).**
*Recomendación:* quedan fuera la explicación por distrito (SHAP o similar), la autenticación de usuarios
finales y las escrituras desde el navegador. Las únicas escrituras siguen siendo `/admin/*` con `X-API-Key`,
llamadas desde GitHub Actions o la PC, nunca desde el frontend.
*Por qué:* nada de eso está en la Tabla 2. Agregarlo después es aditivo.

### Motor y esquema

**M1. Puerto `Predictor`.**
*Recomendación:* en `src/denguekay/serving/predictors/`:

```
class Predictor(Protocol):
    kind: str                          # "v0_compact_xgb", "v2_e3_s4", ...
    horizons: tuple[int, ...]
    required_inputs: frozenset[str]    # {"casos", "clima", "poblacion", "calendario", "regla_brote"}
    def predict(inputs: ServingInputs, cutoff: EpiWeek, horizons) -> DataFrame
        # ubigeo, horizonte, probabilidad_brote, casos_estimados,
        # casos_intervalo_inferior, casos_intervalo_superior, motivo_no_disponible
```

Habría un registro `{kind: clase}` y una fábrica `load(manifest, storage)`. `inference.infer` construye
`ServingInputs` una vez, pide al predictor solo lo que declara en `required_inputs` y escribe `prediccion` y
`alerta` como hoy.
*Por qué:* la API y `infer` solo dependen del puerto; un modelo nuevo se suma con una clase y su test.

**M2. Paquete de modelo.**
*Recomendación:* `modelos/<codigo_paquete>/manifest.json` y sus archivos en Storage (el bucket ya existe). El
manifiesto declara:
- `tipo_predictor`, `version_manifiesto`, `version_minima_denguekay`, `horizontes` y `variables`;
- `archivos`: ruta y SHA-256 de cada uno (boosters JSON; `platt.json` con los coeficientes `a, b` por
  horizonte; `dispersion.json` con α por horizonte; la regla de k);
- `metricas`, `cumple_umbrales` por tarea y horizonte, y la huella de comportamiento (D1 del ADR 0001).

`version_modelo.sha256_artefacto` pasa a ser el SHA-256 del manifiesto, y `ruta_artefacto` su ruta. Al cargar
el paquete se verifica el manifiesto y cada archivo (409 `artefacto_invalido`), con caché por SHA.
*Por qué:* la v2 no es un solo booster: necesita α y Platt por horizonte, y un modelo futuro puede necesitar
otros archivos. Un manifiesto con un hash por archivo conserva la garantía de hoy (lo que se carga es
exactamente lo publicado) sin que la BD conozca el formato de cada modelo. Es el «paquete único» que ya
proponía la §8 de `desviaciones_oe2.md`.
*Detalle:* Platt se guarda como coeficientes y se aplica con la logística. Así la API no necesita
`scikit-learn` al ejecutar (pensando en la fase 5). La paridad con `LogisticRegression.predict_proba` se
comprueba en el test de la fase 4.

**M3. Encaje en `version_modelo`.**
*Antecedente:* la §8 de `desviaciones_oe2.md` («Propuesta pendiente (no implementada): modelo multi-salida
E3·S4_s2») ya propone esta misma opción (a) para el modelo multi-salida del estudio de arquitectura. Sigue sin
aprobar. La v2 es E3·S4_s3 (con `base_margin`), pero el encaje es el mismo, así que M3 **parte de esa
propuesta** y solo señala dónde la ajusta.
*Recomendación:* opción (a), sin cambiar el esquema: una fila por `(tarea, horizonte)`, todas apuntando al
mismo manifiesto. La v2 son 6 filas (clasificación y regresión × h=2, 3 y 4), con `algoritmo =
'xgboost_multisalida_bn'` y la clave `grupo_artefacto` en `reproducibilidad`, como en la §8. La activación y la
selección experimental se hacen **por horizonte y en pareja**: las dos tareas de un horizonte en la misma
transacción. `POST /admin/modelos/{version}/activar` mantiene su contrato y activa también la fila hermana.
*Por qué:* `prediccion` ya tiene `id_version_clasificador` e `id_version_regresor`, y el índice
`ux_version_activa (tarea, horizonte)` sigue valiendo. Una tabla `paquete_modelo` (b) sería una desviación de
OE2 sin ganancia para el frontend.
*Ajustes respecto de la §8:*
- `grupo_artefacto` = código del paquete (M2), y `ruta_artefacto` apunta al manifiesto, no a un solo archivo.
- El umbral de brote de las semanas objetivo se calcula en memoria con la regla de `outbreak_label`, como dice
  la §8, desde `casos_dengue` de la BD (§1.9.2).

*Detalles a confirmar:*
- En la v2 la «clasificación» **es** la probabilidad derivada del conteo (NB2 + Platt): no hay clasificador.
  ¿Lo confirmas?
- `umbral_probabilidad` de la v2 = 0,50 (`protocol.ALERT_THRESHOLD`, igual que la §8); en la v0 era el umbral F1
  del bloque. Así `alerta_modelo` no cambia de significado. ¿De acuerdo?
- Importancias (`importancia_variable`): la §8 propone **SHAP medio por horizonte** de la salida
  correspondiente (`probabilistic_output.shap_importance_by_horizon`, `:348`). Recomiendo mantenerlo, porque da
  una importancia distinta por horizonte y no la misma `gain` para las 6 filas. La misma importancia sirve a la
  fila de clasificación y a la de regresión de un horizonte, porque salen del mismo regresor. ¿De acuerdo?
- `codigo` tiene como máximo 20 caracteres: propongo `v2-clf-h2-1`, `v2-reg-h4-1`, etc., en lugar de
  `clf-h2-vN`.
- Al aprobar M3, la §8 de `desviaciones_oe2.md` pasa de «propuesta pendiente» a desviación aprobada (adaptada a
  S4_s3) en la fase 3.

**M4. Historia anterior a 2017 para B3 y la regla de brote.**
*Observación:* para servir el corte vigente (semanas objetivo de 2026) no hace falta historia previa a 2017:
- la temporada anterior de B3 es la 2025;
- «semanas desde el último caso» tiene tope 52;
- el umbral de brote de la semana objetivo usa los 5 años previos (2021–2025), que ya están en la BD.

La historia previa solo hace falta para reconstruir orígenes de las temporadas 2017–2021, donde B3 y el umbral
usan años previos a 2017.
*Recomendación:* opción (c), **no cargar la historia en la BD**:
- el predictor v2 calcula el umbral de la semana objetivo con `outbreak_label.future_outbreak_threshold`
  desde `observacion_semanal.casos_dengue` (no desde la columna redondeada, §1.9.2);
- declara que no sirve orígenes cuya regla o B3 necesitan años previos a 2017 (motivo explícito, `null`);
- los tests de paridad de la fase 4 usan orígenes de la temporada 2022 en adelante (bloques 2022–2025).

Impacto en el DDL: ninguno.
*Alternativas:* (a) cargar esas semanas en `observacion_semanal`. Obliga a extender `semana_epidemiologica`
hasta el año 2000, a crear un valor nuevo en `fuente_casos_t` y a decidir cómo se ven en `/observaciones` filas
sin clima, de una fuente con solo semanas con casos. (b) Una tabla nueva de referencia `historia_casos`
(desviación). Ambas solo sirven para reconstruir el pasado, y ninguna hace falta para el frontend.

**M5. Clima de A3.**
*Observación:* `observacion_semanal` tiene `hum_rel_media_pct` y `precip_total_mm` semanales, que alcanzan
para la media de 5 semanas hasta el origen. Pero la humedad está en `numeric(5,2)`, y A3 calculada desde la BD
difiere de gold en hasta 0,00429 (§1.9.1). Con eso, la paridad de predicciones ≤ 1e-9 de la fase 4 **no** se
puede cumplir.
*Opciones:*
- (a) **Entrenar el paquete de servicio con el clima redondeado como lo guarda la BD.** La paridad de
  variables entre BD y entrenamiento queda exacta por construcción, sin sesgo entrenamiento/servicio. La
  paridad con `frozen_configs.predict` (que usa gold) pasa a ser aproximada y se reporta con su diferencia
  medida.
- (b) Cambiar `hum_rel_media_pct` a `double precision`: es una desviación del DDL de OE2 y una migración.
  Los valores son medias semanales de datos diarios con decimales periódicos, así que ni `numeric(7,4)`
  alcanzaría 1e-9.
- (c) Aceptar la diferencia: la paridad de variables con tolerancia 5e-3 en la humedad y la de predicciones
  con una tolerancia medida, documentada.

*Recomendación:* **(b)**. Es la única opción que mantiene la exigencia del encargo (paridad ≤ 1e-9) y que sirve
exactamente el modelo congelado. El costo es una desviación chica y documentable: una columna, del mismo
tipo de dato que ya usa silver. (a) cambia en silencio el modelo que se sirve respecto del evaluado; (c)
debilita la prueba que evita el sesgo entrenamiento/servicio. Como cambia el DDL, la decisión es tuya.

**M6. Qué se sirve.**
*Recomendación:* la v2 como selección experimental (h=2, 3 y 4; no cumple la HU0007-4, así que queda
`candidata` con `experimental: true`). La v0 se conserva como predictor registrado `v0_compact_xgb`, para
reproducir lo que ya está en la BD y para la prueba de no regresión de la fase 3.
*Pregunta extra:* las OOS de la v0 que hoy se importan como cortes pasados (`import_oos`), ¿se mantienen en la
BD después de servir la v2? ¿O la v2 publica sus propias OOS (bloques 2022–2025) para que la serie histórica
del frontend corresponda al modelo servido? Recomiendo lo segundo. Se guardarían en `prediccion` igual que hoy
(desviación «b» de OE2, ya aprobada).

**M7. B3 en gold.**
*Observación:* gold h=2 tiene A3 (`*_media5_h2`) pero no B3. La v2 se entrena con gold h=2 más B3 en memoria
(`frozen_configs.origins`, `:100-117`). Regenerar gold h=2 cambia su SHA-256: rompe la validación de la v0
(`serving/protocol.py:46-53`, §1.9.6) y la cita del gold en la ficha de la v2.
*Propuesta (no ejecutada, regla 3 de `CLAUDE.md`):* en `src/denguekay/features/gold.py`, agregar a gold h=2 las
tres columnas B3 (`propia_semanas_desde_ultimo_caso`, `propia_pendiente_4`,
`propia_log_casos_temporada_anterior`) con `features.onset_features`, leyendo `SILVER_EPI_HISTORICAL` para la
temporada 2016, y con su suite de Great Expectations.
*Recomendación:* que la fase 4 **no espere** ese gold. Debe entrenar como el estudio (gold h=2 + B3 en memoria,
con las mismas funciones de `denguekay.features`), que es lo que reproduce la configuración congelada. El cambio
de gold se decide aparte, junto con rehacer el protocolo de la v0 o retirarla.

### Despliegue y trabajo del frontend

**D1. Datos para Nicolás.**
*Recomendación:* (a) en la fase 2, un comando reproducible que genera una BD de demostración **SQLite** con
las migraciones (`alembic upgrade head`), `load_data` y la publicación. Corre en la PC de Rosa, escribe en una
ruta de `models/` o de la carpeta temporal (nunca en `data/`) y se comparte fuera de Git. (b) Una API de
desarrollo en Render con Supabase queda para el encargo de despliegue.
*Por qué:* SQLite es un solo archivo y no exige que Nicolás instale PostgreSQL. La API ya funciona sobre SQLite
(tests y CI).
*Pregunta extra:* ¿el archivo de demostración puede contener los datos agregados reales de Piura (casos por
distrito y semana, sin datos personales)? Son los mismos que ya están en el fixture versionado
`tests/fixtures/backend/`, pero completos.

**D2. Roles en Supabase (solo diseño).**
*Recomendación:*
- La API se conecta con un usuario `LOGIN` que **hereda** `rol_api` (`GRANT rol_api TO denguekay_api`); la
  publicación desde la PC o desde GitHub Actions usa otro que hereda `rol_pipeline`. Ninguno es dueño de las
  tablas ni superusuario, para que el RLS (`servicio_*`, migración `:320-322`) aplique.
- **Falta de permisos (§1.9.5):** `rol_pipeline` no puede escribir `prediccion`, `alerta` ni
  `parametro_sistema`, pero la publicación lo hace. Propongo que la publicación solo registre versiones,
  importancias y archivos en Storage, y que las predicciones vigentes las genere la API
  (`POST /admin/inferencias`), como en el ciclo semanal que describe el encargo (GitHub Actions llama a ese
  endpoint; no figura en `especificacion_oe2.md`). Para las OOS del paquete (M6) haría falta
  `INSERT` en `prediccion` para `rol_pipeline`, como desviación «f» ampliada. `seleccion_experimental` se
  sembraría desde una migración, no desde `load_data`.
- *Hipótesis por verificar en la fase 5:* que en Supabase las tablas de `public` con RLS activo y sin
  políticas para `anon` y `authenticated` quedan cerradas a la API REST automática. Lo verifico en la
  documentación oficial antes de escribir `despliegue.md`; no lo doy por hecho.

### Guardas

**G1. Reemplazo de la guarda del OpenAPI.**
*Observación:* `tests/test_equivalence.py:41-44` (`TestOpenAPIContract`) exige que el contrato generado sea igual
a `docs/backend/openapi.json`. C1–C5 lo cambian a propósito (descripciones de h=3, campos nuevos, versión), así
que esa guarda fallará en la fase 2.
*Recomendación:* en la fase 2, reemplazarla por la guarda del contrato v1. Un test compara el OpenAPI generado
(sin ejemplos de la BD) con `docs/backend/openapi_v1.json`, y si difiere, falla con un mensaje que explica cómo
proceder: si es aditivo, subir la minor y regenerar; si rompe, no se permite en `/api/v1`. La línea base de
`tests/fixtures/equivalence/` (predicciones V1/V2, esquemas, prueba de humo) no se toca.
*Por qué:* el encargo lo prevé como excepción, pero exige tu aprobación explícita.

---

## 3. Respuestas de Rosa (29/10/2026)

Todas las decisiones están respondidas. Las que cambian el esquema (C3, M5) o los permisos (D2) se
documentan en `desviaciones_oe2.md` y en la lista de cambios al documento OE2 (fase 6) en la fase que las
implementa.

| # | Pregunta | Recomendación | Respuesta | Fase |
|---|---|---|---|---|
| C1 | ¿Horizontes 2, 3 y 4, con los disponibles leídos de la BD? | Sí | **Sí** | 2 |
| C2 | ¿`GET /configuracion`? ¿Horizonte por defecto 4 o 2? | Sí; 4, en `parametro_sistema` | **Sí; horizonte por defecto 4, guardado en `parametro_sistema`** | 2 |
| C3 | ¿Intervalos de casos en v1, guardados en dos columnas nuevas de `prediccion`? ¿Nivel 0,80 o 0,90? | Sí, en columnas; 0,80 | **Sí, intervalos en v1 con nivel 0,80; desviación documentada** | 2 (contrato), 3 (columnas) |
| C4 | ¿Tipar el GeoJSON y admitir `Point`, `Polygon` y `MultiPolygon`? | Sí | **Sí** | 2 |
| C5 | ¿`info.version = 1.0.0` como versión del contrato (hoy es 2.0.0) y `X-Version-Contrato`? | Sí, separando contrato y aplicación | **Sí: versión del contrato 1.0.0 con cabecera `X-Version-Contrato`, separada de la versión de la aplicación** | 2 |
| C6 | ¿Fuera de v1: explicación por distrito, autenticación de usuarios y escrituras desde el navegador? | Sí | **Sí, quedan fuera de v1** | — |
| M1 | ¿Puerto `Predictor` con `required_inputs` y registro de tipos? | Sí | **Sí** | 3 |
| M2 | ¿Paquete con manifiesto y SHA-256 por archivo, y Platt guardado como coeficientes? | Sí | **Sí, Platt como coeficientes** | 3 |
| M3 | ¿Opción (a) de la §8 de desviaciones, adaptada a S4_s3, con activación por horizonte en pareja? ¿La clasificación de la v2 = NB2 + Platt? ¿`umbral_probabilidad` 0,50? ¿Importancias SHAP por horizonte? ¿Códigos `v2-clf-h2-1`? | (a); sí; sí; sí; sí | **Sí a todo:** 6 filas; activación por horizonte en pareja; la clasificación de la v2 es NB2 + Platt, sin clasificador; `umbral_probabilidad` 0,50; SHAP por horizonte **calculado al publicar, no en la API**; códigos `v2-clf-h2-1`. La §8 de `desviaciones_oe2.md` pasa a aprobada en la fase 3 | 3, 4 |
| M4 | ¿Sin cargar la historia previa a 2017 en la BD (opción c), con paridad desde la temporada 2022? | (c) | **Sí, opción (c): no se carga historia previa a 2017; paridad desde la temporada 2022** | 4 |
| M5 | ¿Humedad: (a) entrenar con el clima redondeado, (b) `double precision` o (c) tolerancia? | (b) | **(b): `hum_rel_media_pct` pasa a `double precision` con su migración; se documenta en `desviaciones_oe2.md` y en la lista de cambios al documento OE2** | 3 |
| M6 | ¿v2 experimental y v0 como predictor registrado? ¿La v2 publica sus propias OOS? | Sí; sí | **Sí; la v2 publica sus propias OOS 2022–2025, que reemplazan a las de la v0 en la serie** | 4 |
| M7 | ¿La fase 4 entrena con gold + B3 en memoria, sin esperar un gold nuevo? | Sí | **Sí; el cambio en `gold.py` queda como propuesta aparte** | 4 |
| D1 | ¿BD de demostración SQLite en la fase 2? ¿Puede llevar los datos agregados reales? | Sí; sí | **Sí: SQLite con los datos agregados reales de Piura, generada con un comando en la PC de Rosa. El archivo no se versiona en Git: se comparte fuera del repo (Drive o un Release)** | 2 |
| D2 | ¿Usuarios LOGIN que heredan `rol_api` y `rol_pipeline`, con la inferencia vigente hecha por la API? | Sí | **Sí** | 3 (permisos), 5 (diseño de despliegue) |
| G1 | ¿Reemplazar en la fase 2 la guarda `TestOpenAPIContract` por la del contrato v1 (`openapi_v1.json`)? | Sí | **Sí; la línea base de equivalencia no se toca** | 2 |

### Precisiones de la fase 2 (29/10/2026, aprobadas por Rosa)

- **Guardas del ADR 0001 (amplía G1).** Se versionan por contrato:
  - la guarda de esquema del ADR 0001 se mantiene y comprueba la cabeza `0003_oe2`;
  - la prueba de humo del ADR 0001 (`smoke.json`, 15 rutas) deja de correr y queda como historia en el tag
    `restructure-done`;
  - hay líneas base nuevas en `tests/fixtures/contract_v1/`, una por migración nueva y una prueba de humo
    v1 (16 rutas), que se graban una vez y nunca se regeneran.

  Detalle en la sección «Consecuencias» de `docs/decisions/0001-repo-restructure.md`.
- **Siembra de `horizonte_por_defecto` (C2).** Migración `0004_v1`, de solo datos (`INSERT` en
  `parametro_sistema`, valor 4), como las semillas de la 0003. Si falta el parámetro, la API responde 503
  `parametros_no_configurados`. Su línea base de esquema está en `tests/fixtures/contract_v1/`.

### Precisiones de la fase 3 (29/10/2026, aprobadas por Rosa)

- **P1. Versiones v0 viejas de la BD local.** Sin cargador de compatibilidad: las versiones con un
  booster suelto se descartan y se republica con el código nuevo (D6 ya crea versiones nuevas). Pasos en
  `docs/backend/operacion.md` («Dejar la BD local al día después de la migración 0005»). La demo se
  regenera al cerrar la fase.
- **P2. Nivel del intervalo.** `parametro_sistema.nivel_intervalo_casos` = 0,80, sembrado por la 0005.
  El manifiesto de cada paquete registra el nivel con que calcula sus intervalos, y la inferencia rechaza
  (409) un paquete con un nivel distinto. Cambiar el parámetro obliga a volver a inferir.
- **P3. Publicación (D2).** `publish` solo registra el paquete, las versiones y las OOS; `--inferir`
  corre la inferencia vigente para uso local, y la demo lo usa.
- **P4. `seleccion_experimental`.** Se siembra como hasta ahora (desde `config.yaml` al cargar datos); se
  revisa en la fase 4.
- **Guardas (regla de Rosa para las fases 3 y 4).** El smoke v1 y las demás guardas del contrato son
  independientes del modelo servido. Los fixtures del smoke quedan congelados (solo h=2 y h=4). Datos de
  prueba de otro modelo van en fixtures nuevos y aparte. Si una guarda falla por un cambio de modelo, se
  detiene el trabajo y se explica; no se regenera.

## 4. Pendiente fuera de este encargo

- **Los 8 distritos sin historia antes de 2017 (§1.9.3)** (`200206`, `200208`, `200303`, `200305`, `200307`,
  `200308`, `200403`, `200502`): **pendiente de verificar por Rosa.** No cambia nada en este encargo (con M4,
  opción c, la API no usa historia previa a 2017). Sí afecta a la etiqueta de brote de 2017–2021 y a B3 del
  modelo, que hoy tratan esos años como cero.
- **B3 en gold (M7):** propuesta de cambio en `src/denguekay/features/gold.py`, que se decide aparte junto con
  el protocolo de la v0.
