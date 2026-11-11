# Sensibilidad predictiva al rango diurno de CHIRTS

Protocolo fijado el 11 de noviembre de 2026 antes de puntuar las variantes. Atiende la parte predictiva del comentario 8. Se conserva el diseño retrospectivo de resolución de CHIRTS y se usa la misma grilla nativa de 0,05°, la misma máscara y la misma ponderación distrital por población. [Diseño de resolución](protocolo_resolucion_chirts.md)

Se añaden dos brazos a la base de historia, geografía, lluvia, humedad y Niño 1+2.

- **Punto medio.** Promedio de la máxima y mínima diarias, con la misma agregación por distrito y ventana de cinco semanas que los extremos.
- **Punto medio y rango.** El mismo punto medio más la diferencia Tmax − Tmin, con los mismos pesos, días y semanas. Ambas transformaciones lineales pueden calcularse después de promediar porque los extremos comparten la máscara, los pesos y la ventana. El punto medio de los extremos estima el nivel térmico diario. La media de las 24 horas es otro estadístico.

El contraste principal añade el rango al punto medio. Como contraste secundario, se compara punto medio y rango frente al modelo archivado con Tmax y Tmin. Ambos pares codifican la misma información térmica. Cualquier diferencia predictiva en el segundo contraste refleja cómo los árboles aprovechan la representación. También se reporta el contraste del punto medio frente al bloque archivado sin temperatura.

Se fijan la etiqueta, las cinco semillas, el calendario de 20 bloques con soporte común y los hiperparámetros heredados. Se conservan el rezago climático de dos semanas, los cortes de entrenamiento y Platt cronológico. Se verifican los insumos y los cierres de etiqueta contra el archivo de resolución. El criterio principal es la diferencia de Brier a h4, con h2 y h3 como secundarios y precisión promedio como diagnóstico. Se toma la mediana de la diferencia entre semillas por temporada, se da igual peso a las seis temporadas históricas y se repite el resumen omitiendo cada temporada. Las comparaciones describen el aporte incremental en este diseño retrospectivo.
