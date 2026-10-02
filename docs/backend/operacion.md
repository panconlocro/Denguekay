# Operación del backend

## Alcance disponible: fases 1–2

Esquema relacional, carga validada, versiones XGBoost de servicio y publicación
batch con historial. La inferencia carga boosters desde la BD. La API y su
activación/recalculado HTTP corresponden a la fase 3. Se comprobó PostgreSQL
local; no se ha desplegado ni comprobado una conexión a Supabase.

## Variables de entorno

Copiar `.env.example` como `.env`, ignorado por Git. `DATABASE_URL` es
obligatoria; las variables del entorno tienen prioridad sobre `.env`.
`API_KEY` queda reservada para proteger escrituras de la API en la fase 3.
No pegar credenciales en comandos compartidos ni en documentación.

Para PostgreSQL usar el formato
`postgresql+psycopg://usuario:clave@servidor:puerto/base`. En una conexión
Supabase configurar SSL con `?sslmode=require` y usar la cadena y el puerto
proporcionados por el proyecto. Una clave con caracteres especiales debe
estar codificada como parte de la URL. No se requieren PostGIS ni JSONB.

Para probar con SQLite usar `DATABASE_URL=sqlite:///models/serving/backend.db`
en `.env` y crear primero `models/serving/`. No existe una conexión automática
a una BD alternativa cuando falta configuración.

## Instalar, migrar y cargar

Ejecutar desde la raíz del repo. En macOS:

```bash
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -c "from src.utils.paths import SERVING_MODELS; SERVING_MODELS.mkdir(parents=True, exist_ok=True)"
.venv/bin/alembic upgrade head
.venv/bin/python -m src.serving.cargar_datos
.venv/bin/python -m src.serving.publicar --horizontes 2 4
.venv/bin/python -m unittest discover -s tests
```

En PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -c "from src.utils.paths import SERVING_MODELS; SERVING_MODELS.mkdir(parents=True, exist_ok=True)"
.\.venv\Scripts\alembic.exe upgrade head
.\.venv\Scripts\python.exe -m src.serving.cargar_datos
.\.venv\Scripts\python.exe -m src.serving.publicar --horizontes 2 4
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

La carga exige los dos gold, el integrado y su cobertura, el histórico, la
Sala, el catálogo, los centroides y `manifest_fase6.json`. Usa
`auditar_traspaso` y `validar_entradas_modelado`; no hay opción para omitir
esas validaciones. Verifica además la correspondencia de casos 2025 con la
Sala y el calendario MMWR compartido. Las semanas de Sala que no aparecen
en gold no se incorporan silenciosamente.

Una transacción inserta/actualiza distritos y observaciones junto con su
auditoría. Si falla, se revierte todo el lote. La huella incluye los SHA256
de nueve archivos y la revisión de la transformación. Repetir la misma
carga devuelve `reutilizada: true`, mantiene las fechas de actualización y
no crea otra ejecución. Ejecuciones concurrentes con la misma huella se
protegen por unicidad: una puede ser rechazada y se reintenta tras terminar
la otra. La carga se realiza localmente; la API desplegada leerá desde BD.

Los casos cero se conservan como cero. Una observación nula requiere motivo;
la carga completa actual exige casos poblados por las validaciones existentes.
No se fabrican semanas ausentes. Las etiquetas y umbrales de brote vienen de
gold, sin recalcularse.

## Publicar inferencia

`publicar` incluye la carga; ejecutar `cargar_datos` antes es opcional. Hace
las validaciones GX, contrasta hashes, fechas, etiquetas y métricas OOS con
el protocolo compacto, ajusta modelos mediante `train.ajustar_modelos` y
registra runs normales en MLflow. No usa el Model Registry. Requiere las
dependencias MLflow/GX del repo; el backend desplegado usará la BD y no
necesitará una copia del `mlflow.db` local para inferir.

Si falta `models/experimentos/validacion_temporal_compacta/predicciones_por_bloque.csv`,
ejecuta el módulo compacto existente con salida en
`models/serving/protocolo_regenerado/`, incluida su evaluación correspondiente.
Ese entrenamiento puede tardar más y producir variaciones CPU/GPU; no
sobrescribe las métricas de Rosa en `docs/modeling/metricas/`.

En `config/config.yaml`, `serving` configura variantes, horizontes, intervalos
de riesgo, alerta visible, criterio de aceptación y disponibilidad. Horizonte
3 admite configuración, pero su publicación se rechaza hasta contar con gold
y contrato. Con `servir_no_validadas: false`, la función de disponibilidad
rechaza versiones experimentales; los endpoints aplicarán esa regla en fase 3.

La aceptación comprueba **2024** y conserva **2025** como sensibilidad, sin
promediarlos. Las versiones de servicio conservan el JSON del booster en BD;
las versiones OOS históricas de clasificación/regresión no tienen booster y
son **no reactivables**, según lo aprobado. Sus predicciones siguen consultables.
La persistencia se guarda como referencia, con su regla y sus métricas.

La publicación genera un objetivo por horizonte desde el último cierre.
No extiende el panel con observaciones inventadas: los pasos intermedios de
calendario existen solo en memoria con casos ausentes. Una fila incompleta
queda en `ejecucion_prediccion.resumen.no_disponibles`, con distrito y motivo.

Identidad de ejecución: fuentes, protocolo, configuración, código, parámetros,
XGBoost y plataforma. Repetirlos devuelve `reutilizada: true` sin otra versión,
predicción, alerta ni run. Otra identidad crea una ejecución y conserva el
historial. Solo puede existir una versión activa por horizonte/tipo.

Las versiones, predicciones y cambios de alertas se confirman en una sola
transacción. Si falla, la ejecución queda `fallida`, sin confirmar ese lote,
y se puede reintentar. Una ejecución `en_proceso` impide otra publicación
idéntica. Si el proceso fue interrumpido abruptamente, comprobar que terminó
y revisar sus artefactos antes de marcar esa ejecución como fallida en BD;
el CLI no fuerza el desbloqueo de un proceso que podría seguir activo.

Los artefactos locales quedan en `models/serving/ejecuciones/<huella>/`:
reporte de servicio, evaluación temporal importada, JSON de modelos, vectores
futuros y resumen. La BD permite reevaluar sin acceso a esa carpeta.

Alertas visibles: riesgo Alto/Muy alto, desde 0,50. `alerta_modelo` conserva
el umbral F1 del protocolo, que puede ser distinto. Al publicar otro lote se
retiran alertas activas de esos horizontes; las alertas retrospectivas se
importan retiradas con motivo explícito, sin inventar fechas de avisos pasados.

## Verificación de la carga

Consultar `carga_datos` para hashes, resultado de GX, corte y número de filas.
Comprobar que `(ubigeo, anio, semana)` es único y que `ubigeo` conserva seis
dígitos. `fecha_corte_datos` es el sábado de cierre de la última semana
observada; `fecha_actualizacion` es el instante UTC de escritura. Ninguna
de esas fechas se interpreta como una actualización automática del panel.

Las geometrías se guardan como NULL con un motivo explícito: los archivos
disponibles contienen centroides. El mapa podrá usar esos puntos en la fase
3, declarando la ausencia de polígonos.

## Respaldo y reversión

Respaldar PostgreSQL antes de cualquier operación que modifique el esquema.
`alembic downgrade base` **elimina las tablas**; solo se prueba en bases
temporales vacías y no es el mecanismo de rollback de modelos. Los registros
históricos de versiones, predicciones y alertas tienen claves foráneas sin
borrado en cascada. La migración 0002 conserva la carga previa; su downgrade
se comprueba solo en una BD temporal vacía, porque 0001 no admite boosters
históricos nulos. La activación transaccional con auditoría ya existe; su
exposición HTTP y reevaluación controlada se implementarán en fase 3.

Para reproducir la verificación local de SQLite de fase 2, usar
`DATABASE_URL=sqlite:///models/serving/fase2.sqlite`. Es un archivo físico
local bajo `models/serving/`; no se sube a Git. Las pruebas unitarias usan
archivos temporales separados y los eliminan al terminar. Consultar los
resultados medidos en `fase2_inferencia.md` y `fase2_verificacion_*.json`.

La verificación post-despliegue y el guion de demo quedan pendientes de la
fase 5 y de su aprobación.
