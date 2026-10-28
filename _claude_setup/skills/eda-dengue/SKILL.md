---
name: eda-dengue
description: Análisis exploratorio (EDA) del panel distrito-semana de dengue en Piura (Denguekay), antes del feature engineering. Úsala para cualquier pedido de EDA, exploración, calidad de datos, análisis de casos/clima/sociodemografía o "Data Understanding" de la tesis.
---

# EDA de dengue en Piura

Objetivo del EDA: **entender el dataset lo suficiente para decidir bien el feature engineering, la definición de brote y el esquema de validación** de un modelo que predice brotes con ≥4 semanas de anticipación. Un EDA bueno no es una colección de gráficos: es una cadena de preguntas respondidas con evidencia, cada una terminando en una decisión o en una duda concreta para el asesor.

Antes de empezar lee, en este orden: `CLAUDE.md`, `docs/estructuraRepo.md`, `references/diccionario_datos.md` (hechos ya verificados del dataset y sus trampas), `references/dominio_dengue.md` y la fase que toque en `references/fases_eda.md`.

## Contrato de trabajo
- **Una fase a la vez.** Ejecuta una fase, presenta el resumen y **detente hasta que Rosa confirme**. No adelantes fases ni "aprovechando que estás".
- **Solo lectura sobre `data/`.** Carga con `src.eda.carga.cargar_integrado()`. No escribas en `data/`, no toques gold, no agregues columnas derivadas al dataset. Lags, tasas y anomalías se calculan en memoria solo para analizar.
- **No arregles datos.** Si encuentras un problema, va a la lista "Problemas y propuestas de corrección" de `docs/eda/hallazgos.md` con evidencia y una propuesta; Rosa decide.
- **No hagas feature engineering ni modelado.** Puedes cuantificar qué lags o transformaciones *parecen* útiles; no los implementas como features ni entrenas modelos. Una línea base ingenua (persistencia, estacional) solo para dimensionar la dificultad está permitida si la fase lo pide.

## Estándares de calidad (lo que separa un EDA bueno de uno malo)
1. **Pregunta primero.** Cada bloque de análisis empieza con una celda markdown que dice qué se quiere saber y qué se esperaría ver (hipótesis). Sin pregunta no hay gráfico.
2. **Cada figura cierra con una frase de hallazgo con cifras** calculadas en código (f-string sobre valores reales, nunca escritas a mano) y con su "entonces qué" para el modelado. Pocas figuras buenas > muchas mediocres: máximo ~6-8 por fase.
3. **Es un panel, no 30 000 filas independientes.** Toda relación se mira en tres niveles: agregado regional, por distrito/provincia y por año. Si el patrón agregado no se sostiene por dentro, dilo (paradoja de Simpson). Prohibido reportar solo correlaciones "globales" de filas mezcladas.
4. **Ceros y cola pesada.** `casos_Dengue` tiene ~78 % de ceros y varianza ≫ media. Nunca un histograma crudo solo: usa `log1p`, ECDF, proporción de ceros, tasa por 100 000 hab. Correlación con Spearman o sobre transformaciones; jamás Pearson sobre conteos crudos como única evidencia.
5. **Estacionalidad como confusor.** Clima y casos son estacionales; una correlación cruda es en gran parte calendario. Repite la relación sobre anomalías (valor − climatología por semana epi y distrito) o dentro de distrito, y compara.
6. **Pocos brotes, mucha cautela.** Casi todos los casos vienen de 2017 y 2023 (y de unos pocos distritos). Toda relación clima-casos debe traer sensibilidad "dejando un año afuera" y advertir si depende de uno o dos episodios. Nada de causalidad ni de "el modelo funcionará".
7. **Tiempo importa.** Para un pronóstico a 4 semanas, cualquier relación se examina con rezagos (0-12 semanas) y **sin usar información futura**. Señala riesgos de fuga de información (leakage) que verás en el feature engineering.
8. **Observación ≠ hipótesis ≠ conclusión.** Etiquétalas. Las explicaciones de dominio (El Niño costero, biología del *Aedes*) son hipótesis a menos que estén verificadas; no inventes citas ni cifras de literatura (ver `CLAUDE.md`).
9. **Anomalía no es error.** Antes de llamar error a un valor extremo, contrástalo con el contexto (distrito, altitud/provincia, fecha, evento). Reporta ambos lados.
10. **Reproducible.** Notebook ejecutable de arriba abajo (`nbconvert --execute`), sin rutas absolutas, semillas fijas, funciones reutilizables en `src/eda/`. Sin auto-profilers (ydata-profiling, sweetviz) como sustituto del análisis, ni pairplots de todas las variables.
11. **Gráficos de tesis.** Español, ejes con unidades, título que dice el mensaje, paleta de `src/eda/estilo.py` (Okabe-Ito, un color = un significado), una idea por figura, guardado con `guardar_figura()`.

## Entregables por fase
- Notebook `notebooks/1X_eda_<tema>.ipynb` ya ejecutado (salidas guardadas). Numeración: `10_eda_integridad_calidad`, `11_eda_variable_objetivo`, `12_eda_temporal`, `13_eda_espacial`, `14_eda_clima`, `15_eda_sociodemografico`, `16_eda_sintesis`.
- Figuras en `docs/eda/figuras/<fase>/` y cifras clave en `docs/eda/metricas/<fase>.json` (vía `guardar_figura` / `guardar_metricas`). **Toda cifra que aparezca en `hallazgos.md` debe estar en ese JSON.**
- Una sección nueva al final de `docs/eda/hallazgos.md` con este formato por hallazgo:
  `Hallazgo N — <título>` · **Evidencia** (cifra + figura) · **Interpretación** (observación/hipótesis) · **Implicación para el modelado** · **Confianza** (alta/media/baja y por qué) · **Pendiente / pregunta**.
  Cierra cada sección con "Lo que este análisis NO permite concluir" y "Problemas y propuestas de corrección" (si hubo).
- Funciones reutilizables en `src/eda/` (+ test simple en `tests/` si tienen lógica no trivial). Si agregas carpetas o archivos que `docs/estructuraRepo.md` no contempla, actualízalo.

## Cierre de cada fase (obligatorio, en este orden)
1. Ejecuta el notebook completo de cero y confirma que no falla.
2. Corre los tests (`python -m unittest discover -s tests`).
3. Invoca el subagente **`revisor-eda`** indicándole la fase; corrige lo que marque como FAIL o explica por qué lo mantienes.
4. Presenta a Rosa, **en texto plano en el chat** (no como archivo): los 3-6 hallazgos más importantes con su cifra, los problemas de datos hallados, las decisiones que necesitas de ella y una pregunta para el asesor si aplica. Máximo ~20 líneas. Luego **detente y espera confirmación**.
