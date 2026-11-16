# Referencia independiente del gold V4

La referencia proviene del gold generado con el código anterior al pipeline Medallion de V4
(`scripts/regenerar_gold_v4.py` en el merge del PR #39) sobre los insumos verificados de `datos_v4.zip`.
Su SHA-256 coincidió con el CSV regenerado en macOS ARM64 durante la auditoría del 16 de noviembre de 2026.
Los hashes de Linux y Windows corresponden a la [corrida de auditoría](https://github.com/panconlocro/Denguekay/actions/runs/43925743433).

- `referencia.json` contiene los hashes del CSV y de las 34 columnas en los tres entornos. Para cada columna
  la entrada del SHA-256 es el texto de sus celdas en orden, separado y terminado con LF, codificado en UTF-8.
- `flotantes.csv.xz` contiene únicamente los valores de las columnas calculadas con aritmética aproximada,
  en el orden de las 73 775 filas de la referencia de macOS. Permite comprobar `atol=1e-12` y `rtol=0`
  para cada celda, incluso si un entorno genera un SHA-256 distinto. El orden de las filas se verifica
  con las huellas exactas de las llaves.
- La prueba del vector de la SE 41 usa `origen.csv` directamente de `modelo_v4.zip`. Su SHA-256 se
  comprueba contra el manifiesto del estudio antes de comparar los predictores y umbrales de los 65 distritos.

Se conserva esta referencia fija al cambiar el pipeline. El archivo completo de entrenamiento se regenera
en cada ejecución de la prueba y queda en `data/gold/`, fuera de Git.
