# Dominio: dengue y clima (para formular hipótesis, no para citar)

Todo lo de este archivo son **hipótesis de trabajo de conocimiento general**. Sirven para formular preguntas y esperar patrones; **no son citas**. Nunca las presentes como resultado del dataset ni les inventes referencia. Si Rosa necesita citar algo, que aporte la fuente o verifícala antes con búsqueda real.

## Mecanismo general (hipótesis)
- El dengue lo transmite principalmente el mosquito *Aedes aegypti*. Su población y la velocidad de transmisión dependen de la temperatura, del agua disponible para criaderos (lluvia, pero también almacenamiento doméstico de agua) y, en menor medida, de la humedad.
- La cadena causal tiene **retrasos**: clima → población de mosquitos → casos infectados → casos notificados. Por eso se esperan efectos con rezago de semanas, no simultáneos. El rango de rezagos a explorar en EDA es 0-12 semanas (el rango se decide con los datos, no se asume).
- La relación con la temperatura suele ser **no lineal** (favorable en rangos intermedios-cálidos; desfavorable en extremos). Explora umbrales, no solo correlación lineal.
- La lluvia puede tener efectos opuestos según el contexto (crea criaderos, pero lluvias muy intensas pueden arrastrarlos; en zonas secas el almacenamiento de agua sostiene la transmisión). No supongas signo.

## Contexto regional (hipótesis a contrastar con el dataset)
- Piura es muy heterogénea: costa cálida (Piura, Sullana, Paita, Sechura, Talara) frente a sierra más fría (Huancabamba, Ayabaca). Se espera que dengue se concentre en costa/valles y sea marginal en sierra alta.
- Los años con fenómeno El Niño costero (se espera 2017 y 2023 por conocimiento general) suelen traer mucha más lluvia y calor en la costa norte del Perú. El dataset muestra dos grandes episodios de casos en 2017 y 2023 y 2017 como año de mayor precipitación: **contrástalo, no lo afirmes**.
- La inmunidad poblacional (por brotes previos) y cambios de serotipo pueden explicar que un año con buen clima no produzca brote, o al revés. El dataset no las mide: es una limitación, no una variable.

## Preguntas de dominio que el EDA sí puede responder con evidencia
¿En qué semanas epidemiológicas ocurren los picos y varían entre brotes? · ¿El brote se propaga de distrito a distrito con un desfase medible? · ¿Qué rezago del clima se asocia más con casos y es estable entre años? · ¿Los distritos con más población o menos saneamiento tienen más incidencia? · ¿Qué tan predecible es el nivel de casos 4 semanas adelante solo con su propia historia?
