# Regla de brote (HU0004-1, HU0004-2 y HU0004-5)

Este documento define qué significa «brote» en Denguekay, con qué parámetros se calcula, qué ocurre cuando faltan datos y
cómo se cambia. Las cifras salen de los manifiestos de gold y de los informes de los estudios 02 y 07, y se recalcularon
en esta sesión (sección 6).

## 1. Qué es y qué no es

Una **semana distrital de brote** es una fila `(ubigeo, anio, semana)` cuyos casos superan el nivel habitual de esa misma
semana en ese distrito. La etiqueta `brote` (0/1) y el umbral `umbral_brote_casos` que la acompaña son lo que el modelo
aprende a predecir con 2, 3 y 4 semanas de anticipación.

**Es una regla operativa de vigilancia, no un umbral clínico ni epidemiológico validado.** No distingue la gravedad de
los casos, no equivale a una declaración de brote por la autoridad de salud y no está atribuida a la OMS: es una
adaptación del canal endémico estacional (sección 8) que el equipo eligió y documentó. Quienes usen la etiqueta o el nivel
de riesgo deben leerlos como «semana con más casos de lo habitual en ese distrito», no como un diagnóstico.

## 2. Parámetros

| Parámetro | Valor | Dónde vive |
|---|---|---|
| Años previos de referencia | 5 (los 5 años anteriores a la semana evaluada) | `OUTBREAK_RULE["anios_previos"]` (`features/long_history.py`); `parametro_sistema.regla_brote.anios_previos` |
| Multiplicador de la desviación | 1,5 | `OUTBREAK_RULE["multiplicador"]`; `parametro_sistema.regla_brote.k_desviaciones` |
| Desviación estándar | muestral (`ddof = 1`) | `features/outbreak_label.py` |
| Comparación | desigualdad estricta: `casos > umbral` | `features/outbreak_label.py` |
| Mínimo de casos | 2 (`casos >= 2`) | `OUTBREAK_RULE["minimo_casos"]`; `parametro_sistema.regla_brote.minimo_casos` |

`parametro_sistema.regla_brote` vale `{"anios_previos": 5, "k_desviaciones": 1.5, "minimo_casos": 2}` (semilla de la
migración `0003_oe2` y valor que el predictor de la V4 exige). Los mismos tres valores están en el manifiesto de gold
(`regla_brote`, con el SHA-256 de la historia usada) y en el `paquete.json` del modelo.

## 3. Cálculo

Para un distrito, un año `A` y una semana epidemiológica `s`:

1. Se toman los casos del distrito en la semana `s` de cada uno de los 5 años `A − 5, …, A − 1`.
2. `umbral = media + 1,5 × DE muestral` de esos 5 valores.
3. La semana es de brote si `casos > umbral` **y** `casos >= 2`.

Ejemplo (valores de referencia 1, 2, 3, 4 y 5): media 3, DE muestral 1,5811, umbral 5,3717; 5 casos no son brote y 6 sí.
Si los 5 años previos son cero, el umbral es 0: 1 caso no es brote (no llega al mínimo) y 2 casos sí.

El umbral de una fila usa **solo años anteriores**: no mira su propio año ni los posteriores. `umbral_brote_casos` queda
en gold y en la base de datos para poder auditar cada etiqueta.

### Semana 53

Los años con semana 53 (por ejemplo 2020, en el panel) la suman a la semana 52 al construir la referencia, y una fila de
la semana 53 usa la referencia de la semana 52. La fila conserva su semana original (53).

### Semanas sin registro y estado de cobertura

- En la historia anterior al panel (`epi_piura_semanal.csv`, 2000 a 2016) solo hay filas con casos: 3 624 filas, todas con
  al menos 1 caso, en 50 de los 65 distritos. Una distrito-semana que no aparece se trata como **cero** al calcular la
  referencia. Eso significa «sin registro», **no** «cero notificado»; el manifiesto de gold lo declara
  (`ausencia_historica`).
- En el panel 2017–2025 cada una de las 30 485 distrito-semanas tiene valor, y el archivo de cobertura
  (`meteo_socio_epi_piura_2017_2025.coverage.csv`) marca las 30 485 con `source = verified`.
- En la base de datos, cada observación semanal lleva `estado_cobertura` (`verificado`, `sin_registro` o `pendiente`), de
  modo que una consulta distingue un cero verificado de una ausencia.

## 4. Si falta historia

La ejecución **se detiene** y dice qué años faltan; no rellena ni supone datos:

- `label_seasonal_outbreak` (etiquetado de gold): `ValueError: Faltan años de historia en los distritos del panel: [..]`.
- `future_outbreak_threshold` (umbral de semanas objetivo, también el que usa el servicio): `ValueError: Faltan años de
  historia: [..]`; también se detiene si el último año del panel no cubre la semana de referencia.
- El predictor de la V4 no calcula nada si la regla que hay en `parametro_sistema` difiere de la del paquete congelado
  (`InferenceUnavailable: La regla de brote en la BD difiere del paquete congelado V4`).

Pruebas: `tests/features/test_outbreak_label.py`
(`test_el_etiquetado_se_detiene_e_indica_los_anios_de_historia_que_faltan`,
`test_el_umbral_de_semanas_objetivo_se_detiene_si_falta_historia_anterior_al_panel`).

## 5. Cómo se cambia la configuración y cómo queda identificada

Cambiar la regla **cambia la etiqueta**, así que obliga a reetiquetar y a entrenar de nuevo: el procedimiento de
[`reentrenamiento.md`](reentrenamiento.md) lo trata como reentrenamiento extraordinario («cambio de la regla de brote»).
Según el repositorio:

1. Se propone el cambio en `OUTBREAK_RULE` (`features/long_history.py`) y en los parámetros del gold
   (`features/gold.py` y `features/gold_v4.py`); el equipo regenera gold con el paso `11_gold` de la versión. Nada se
   modifica a mano en `data/`.
2. El gold regenerado guarda la regla en su manifiesto (`regla_brote`) y el modelo nuevo la guarda en su `paquete.json`.
3. `parametro_sistema.regla_brote` es la regla que la base entrega al predictor. Como el rol del pipeline solo puede
   actualizar la fila `seleccion_experimental`, el cambio de esta regla debe hacerse con una migración de Alembic.
4. La versión nueva lleva su ficha en `models/registry/`, su Release de datos con manifiesto y su entrada en el
   `CHANGELOG.md`. Mientras la base y el paquete no coincidan, el servicio no emite (sección 4).

La configuración vigente queda identificada por: el valor de `parametro_sistema.regla_brote`, el `regla_brote` del
manifiesto de gold, el del `paquete.json` y la ficha de la versión.

## 6. Semanas de brote por año (regla principal)

Fuente: `positivos_brote_por_anio` del manifiesto de gold (`data/gold/manifest_fase6.json`, leído sin modificarlo) sobre el
panel confirmado de la V4, 2017–2025, 30 485 distrito-semanas, regla 5 años · 1,5 DE · mínimo 2. Esta sesión recalculó la misma cifra con `label_seasonal_outbreak` desde `epi_piura_semanal.csv` y el panel confirmado
(coincide en los nueve años); un revisor independiente (subagente `revisor-modelado`) la recalculó sin leer el código de modelado y coincide en los nueve años y en el total.

| Año | Distrito-semanas | Semanas de brote |
|---:|---:|---:|
| 2017 | 3 380 | 528 |
| 2018 | 3 380 | 4 |
| 2019 | 3 380 | 0 |
| 2020 | 3 445 | 1 |
| 2021 | 3 380 | 226 |
| 2022 | 3 380 | 357 |
| 2023 | 3 380 | 1 397 |
| 2024 | 3 380 | 504 |
| 2025 | 3 380 | 3 |
| **Total** | **30 485** | **3 020** |

Observación: los brotes se concentran en 2017, 2021, 2022, 2023 y 2024; 2018, 2019, 2020 y 2025 casi no tienen. Con tan
pocos años de brote no se generaliza la frecuencia ni se interpreta causalmente. Las semanas de 2026 se etiquetan con la
Sala Situacional y la misma regla, y no están en este manifiesto.

## 7. Análisis de sensibilidad (estudio 07)

El estudio 07 (`research/07_outbreak_label_sensitivity/`, informe `docs/informe.md`) varió un parámetro por vez y
comparó la V3 con su referencia pareada sin clima. **Se hizo sobre la V3, con casos notificados (las versiones v0 a v3 usan casos notificados, según el registro de modelos),
no sobre la V4 con casos confirmados**, y no se repitió con la V4.

| Escenario | Multiplicador | Años previos | Mínimo de casos |
|---|---:|---:|---:|
| Principal | 1,5 DE | 5 | 2 |
| A | 2,0 DE | 5 | 2 |
| B | 1,5 DE | 3 | 2 |

Conteos del informe, en las 20 410 filas objetivo de `h = 4` de las seis temporadas de decisión (2010, 2015, 2016, 2022,
2023 y 2026, bloque `temporada_2026`):

| Escenario | Semanas elevadas | Prevalencia | Cambios frente al principal | Pasa a positiva | Pasa a negativa |
|---|---:|---:|---:|---:|---:|
| Principal | 2 745 | 13,45 % | 0 | 0 | 0 |
| A (+2 DE) | 2 604 | 12,76 % | 141 | 0 | 141 |
| B (3 años) | 2 991 | 14,65 % | 468 | 357 | 111 |

Resultado (del informe): el veredicto de Brier entre la V3 y su referencia sin clima es **empate en los tres horizontes
bajo las tres definiciones**; hay sensibilidad por temporada (con 3 años de historia, la comparación de `h = 2` en 2022
pasa de favorecer a la V3 a favorecer al modelo sin clima). Lo que sí muestra esta tabla es cuántas etiquetas cambian al
mover la regla: +2 DE quita 141 semanas elevadas (5,1 % de las 2 745 del principal) y 3 años de historia cambia 468.

Para la comparación de mínimos y multiplicadores sobre el integrado del estudio 02 (no recalculada con los casos
confirmados de la V4), ver `research/02_feature_engineering/docs/revision_definicion_brote.md`; esa revisión fue la que
llevó al mínimo provisional de 2 casos (elimina 742 positivos de un solo caso frente al mínimo de 1).

## 8. Fundamento y referencias

La regla es una adaptación del **canal endémico estacional** de vigilancia: comparar la semana actual con la misma semana
de años previos y marcar lo que supera la banda superior. Lo que el repositorio documenta de cada fuente:

- **Benedum CM, Shea KM, Jenkins HE, Kim LY, Markuzon N (2020).** Weekly dengue forecasts in Iquitos, Peru; San Juan,
  Puerto Rico; and Singapore. *PLoS Neglected Tropical Diseases* 14(10): e0008710. DOI:
  <https://doi.org/10.1371/journal.pntd.0008710>. Lo que el repositorio recoge del estudio: casos semanales por encima de
  la media más 1,5 desviaciones estándar, con la media estimada con los datos de entrenamiento de cada lugar y una serie
  por lugar. *Por verificar: que el 1,5 DE se defina en el artículo tal como lo resume este documento (nadie lo ha
  contrastado con el texto original).*
- **OMS / TDR, guía de dengue de 2009, capítulo 3.3.1, p. 73** (cita de la revisión del estudio 02): comparar la semana o
  el mes con la media histórica de la misma semana o mes en los 5–7 años previos; superar media + 2 DE activa una alerta
  de brote, como aproximación de vigilancia. Enlace:
  <https://iris.who.int/bitstream/handle/10665/44188/9789241547871_eng.pdf?sequence=1>. *Por verificar: que ese capítulo
  y esa página describan el canal con +2 DE.*
- **World Health Organization (2016).** Technical handbook for dengue surveillance, dengue outbreak prediction/detection
  and outbreak response ("model contingency plan"). Ginebra: OMS (TDR). ISBN 978 92 4 154973 8. Enlace:
  <https://www.who.int/publications/i/item/9789241549738>; PDF:
  <https://iris.who.int/bitstream/handle/10665/250240/9789241549738-eng.pdf?sequence=1>. Sección 3.2.4 (cita del
  protocolo del estudio 07): canal tradicional de 5 años con +2 DE. *Por verificar: que la sección 3.2.4 sea la que
  describe el canal con +2 DE.*
- **Por verificar:** el estudio 02 y el estudio 07 citan dos documentos distintos de la OMS (2009 y 2016) para la misma
  idea del canal con +2 DE. Falta confirmar con el texto de cada uno qué sección lo describe; hasta entonces este
  documento no atribuye a la OMS ningún valor de la regla de Denguekay.

Decisiones del proyecto (no de esas fuentes): aplicar la regla **por distrito y misma semana epidemiológica**, usar 1,5 DE
(elección de Rosa), exigir un mínimo de 2 casos (provisional, tras revisar la sensibilidad) y sumar la semana 53 a la 52.
Ninguna cifra de estas referencias se usa como umbral clínico.
