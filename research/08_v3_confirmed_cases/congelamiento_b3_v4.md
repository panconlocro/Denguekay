# Congelamiento de b3 para la V4 del paper

El 12 de noviembre de 2026 se congeló el paquete de `b3_obs` con casos confirmados de Piura y su comparador de historia y geografía. El último cierre de etiquetas del ajuste es el **17 de octubre de 2026 (SE 41)**. La SE 42 y la SE 43 permanecen fuera de la serie validada que alimentó este paquete. Se ajustaron 73 775 filas de entrenamiento por semilla. La validación de insumos superó 107 expectativas de silver y 50 de gold h2.

Se guardaron cinco semillas por brazo y los parámetros por horizonte de dispersión NB2, calibración Platt y mezcla de conteo. El ajuste usa los parámetros fijos de la comparación principal del paper, los horizontes 2, 3 y 4, y el corte de alerta 0,50. El paquete incluye la calibración de la persistencia probabilística y conserva como regla determinista el último conteo al origen contrastado con el umbral de la semana objetivo. La demo usa la semilla 17, que coincide con la convención del servicio de la V3.

El [manifiesto](manifiesto_b3_v4.json) registra las columnas, las fuentes con sus hashes y las huellas de los diez boosters y los archivos auxiliares. Los binarios y datos agregados se guardan localmente en `models/experimentos/mejora_modelo/v4_b3_confirmados/`. El constructor verificó igualdad de vectores con el archivo del paper en dos orígenes históricos y la paridad al reabrir los diez boosters.

El vector de la demo corresponde al origen nominal de la SE 41. Sus pronósticos se muestran como demostración retrospectiva. Una evaluación prospectiva usa orígenes nuevos y archiva la fecha efectiva de emisión, los insumos disponibles y los pronósticos antes de conocer los desenlaces de las semanas objetivo.

## Reproducción local

Desde la raíz, con los archivos archivados del estudio de Piura y las dependencias instaladas:

```bash
DENGUEKAY_XGB_DEVICE=cpu DENGUEKAY_XGB_NJOBS=2 \
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 \
python -B research/08_v3_confirmed_cases/code/freeze_v4.py \
  --corte 2026-10-17 \
  --geografia models/experimentos/mejora_modelo/v3_confirmados/piloto_clima/resolucion_chirts/historico/insumos/geografia_distritos.csv \
  --salida models/experimentos/mejora_modelo/v4_b3_confirmados
```
