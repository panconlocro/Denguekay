# Fases del EDA — qué preguntar, qué calcular, qué decidir

Cada fase = un notebook + figuras + métricas + sección en `docs/eda/hallazgos.md` + cierre con `revisor-eda` + confirmación de Rosa. Las cifras entre paréntesis son las ya medidas en `diccionario_datos.md`: úsalas como **chequeo de cordura**, no como sustituto de recalcularlas.

## Fase 1 — Integridad y calidad (`10_eda_integridad_calidad`)
Pregunta guía: ¿puedo confiar en estos datos para analizarlos, y dónde no?
- Contrato del panel: filas = distritos × semanas (65 × 469), llave única, semanas consecutivas de 7 días por distrito, calendario epidemiológico (2020 con 53 semanas), rango de fechas.
- Nulos, tipos, duplicados de fila y **de columna** (precip ≡ lluvia), columnas constantes o casi constantes.
- Rangos físicos y consistencia interna: `temp_min ≤ temp_media ≤ temp_max`, humedad 0-100, precipitación ≥ 0, fracciones en [0, 1], pares complementarios coherentes, población > 0 y su evolución por distrito.
- Extremos: separa error de evento real (706 mm en Salitral 2017; 4.5 °C en El Carmen de la Frontera 2021). Contrasta con distrito, provincia, fecha y con el resto de distritos esa misma semana.
- Procedencia: ruptura de fuente epidemiológica en 2025; sociodemografía interpolada (verifica la linealidad y documéntala); cruce con `docs/estructuraRepo.md` sección de pendientes.
- Compara el panel con el archivo `.coverage.csv` de `silver/integrado` (qué semanas tienen casos verificados) y con las validaciones de `src/validation/expectations_integrado.py`.
- **Decisión que produce:** lista de columnas redundantes/inservibles, tratamiento propuesto del 2025 y de cada anomalía, y qué problemas deben corregirse en el pipeline (no aquí).

## Fase 2 — Variable objetivo (`11_eda_variable_objetivo`)
Pregunta guía: ¿qué es exactamente lo que queremos predecir y qué tan difícil es?
- Distribución: proporción de ceros, cola, sobredispersión (varianza/media), `log1p`, ECDF. Por año, provincia y distrito.
- Conteos vs **tasa por 100 000 hab.** (usa `poblacion`): ¿cambia el ranking de distritos? ¿qué unidad conviene al modelo?
- Concentración: curva acumulada de casos por distrito; distritos siempre en cero; distritos "silenciosos" vs "activos".
- Episodios: ¿cuántos brotes hay realmente? Duración, semana de inicio y pico, magnitud, por distrito y regional.
- **Definiciones candidatas de brote** (no elijas una: presenta 3-4 y cuantifica para cada una cuántas filas/episodios positivos resultan y qué desbalance de clases implica): umbral fijo en casos o tasa; percentil histórico por distrito; canal endémico por semana epidemiológica; aumento relativo sostenido por k semanas. Deja claro qué años/distritos aportan positivos.
- **Decisión que produce:** transformación recomendada del objetivo (conteo, tasa, `log1p`, binario), definición(es) de brote a llevar al asesor, y qué tan raro es el evento positivo.

## Fase 3 — Dinámica temporal (`12_eda_temporal`)
Pregunta guía: ¿qué estructura temporal tiene la serie y qué implica para el pronóstico a 4 semanas?
- Serie regional y por provincia; perfil estacional por semana epidemiológica y por año (superpuestos y normalizados); ¿cambia la semana del pico entre brotes?
- Autocorrelación y autocorrelación parcial de la serie regional y de distritos representativos, con énfasis en los rezagos 1-8: ¿cuánto "sabe" el pasado propio a 4 semanas?
- Estacionariedad (con cautela: 2 brotes dominan); cambios de régimen: 2017, 2023, silencio 2018-2020, ruptura de fuente 2025.
- **Implicaciones para validación:** en qué años caen los brotes y qué esquema temporal evita fuga (nunca partición aleatoria por filas). Propón folds tipo "dejar un año/brote afuera" y advierte si algún fold queda sin brotes.
- Línea base ingenua opcional (persistencia y estacional ingenua a 4 semanas) solo para dimensionar la dificultad.
- **Decisión que produce:** rango de rezagos autorregresivos a considerar, riesgo de leakage y propuesta de esquema de validación.

## Fase 4 — Espacial (`13_eda_espacial`)
Pregunta guía: ¿el dengue en Piura es un fenómeno regional homogéneo o local, y hay propagación entre distritos?
- Ranking de distritos por casos y por tasa; mapa de burbujas con `lat/lon` (sin choropleth salvo que haya límites en el repo).
- Heterogeneidad por provincia; costa vs sierra.
- Sincronía: matriz de correlación entre series de distritos (sobre `log1p` o tasa), agrupamiento jerárquico; ¿hay conglomerados naturales?
- Propagación: desfase entre picos de distritos vecinos durante 2017 y 2023 (¿quién arranca primero?).
- Autocorrelación espacial (p. ej. I de Moran con pesos por distancia calculada a mano con numpy; no agregues librerías nuevas sin consultar).
- **Decisión que produce:** si vale la pena usar información de vecinos como predictor, qué distritos/provincias tratar aparte o descartar, y si se necesita un modelo global o por grupos.

## Fase 5 — Clima y casos (`14_eda_clima`)
Pregunta guía: ¿qué variables climáticas y a qué rezago se asocian con los casos, de forma estable?
- Distribución y estacionalidad de cada variable; diferencias entre provincias; extremos ya tratados en fase 1.
- Redundancia entre variables climáticas (`temp_*`, `et0_total`, `radiacion_total`, precip≡lluvia): matriz de Spearman y agrupamiento; cuáles aportan información distinta.
- **Función de correlación cruzada** clima→casos con rezagos 0-12 semanas: (a) serie regional, (b) por provincia, (c) dentro de distrito. Repite sobre **anomalías** (quita estacionalidad) y compara con la versión cruda.
- Forma de la relación: casos medios (o `log1p`) por deciles de cada variable clave al rezago más informativo; busca umbrales y no linealidades; interacción temperatura × humedad/lluvia.
- Robustez: sensibilidad dejando un año afuera (en particular 2017 y 2023) y comparación años de brote vs años sin brote. Intervalos por remuestreo por bloques (años/distritos), no por filas.
- **Decisión que produce:** variables climáticas candidatas, ventanas de rezago candidatas (con su nivel de confianza), transformaciones sugeridas y advertencias de dependencia de pocos episodios.

## Fase 6 — Sociodemografía (`15_eda_sociodemografico`)
Pregunta guía: ¿las condiciones sociodemográficas explican diferencias entre distritos, y cuáles son redundantes?
- Recuerda: son anuales e interpoladas → análisis **de corte transversal entre 65 distritos** (n bajo). Usa 2017 y 2025 (años observados) para no analizar artefactos.
- Relación de cada variable con incidencia acumulada por 100 000 hab. (Spearman con intervalo por bootstrap) y por provincia; cuidado con la falacia ecológica y con que costa/sierra confunde.
- Colinealidad entre las 15 `fraccion_*` (matriz, agrupamiento, VIF); pares casi complementarios (`fraccion_sin_saneamiento` vs `fraccion_desague_red`).
- Población como exposición: ¿la incidencia depende del tamaño del distrito? ¿estabilidad de tasas en distritos pequeños?
- **Decisión que produce:** subconjunto reducido de variables sociodemográficas y cómo usarlas (no como series temporales), o su descarte fundamentado.

## Fase 7 — Síntesis (`16_eda_sintesis`)
Pregunta guía: ¿qué decidimos y qué queda pendiente para el feature engineering?
- Tabla hallazgo → decisión (feature engineering / definición de objetivo / validación / corrección de datos / pregunta al asesor), priorizada.
- Variables: mantener, descartar, transformar; rezagos candidatos; agregaciones sugeridas; tratamiento de 2025.
- Riesgos: leakage, dependencia de 2 brotes, subregistro 2025, sobredispersión, desbalance.
- Limitaciones y preguntas abiertas para el asesor y para DIRESA (p. ej. discrepancia de casos de 2025).
- Escribe `docs/eda/informe_eda.md` (resumen ejecutivo + hallazgos por fase + decisiones + limitaciones) en español, apto para el capítulo de Data Understanding de la tesis, **sin citas inventadas**.
