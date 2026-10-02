# Decisiones técnicas

## FastAPI y Pydantic v2

Se conserva el stack solicitado: rutas tipadas, validación de parámetros, modelos
de respuesta y OpenAPI. Pydantic rechaza campos extra y valores incompatibles;
las fechas se serializan en UTC. Django aportaría administración integrada, pero
no existe una necesidad de ese panel en el contrato; Flask exigiría ensamblar más
validación y documentación. La elección no acredita rendimiento por sí sola:
se mide la implementación en [los reportes de fase 4](fase4_calidad.md).
Referencia: [documentación oficial FastAPI](https://fastapi.tiangolo.com/).

## SQLAlchemy 2, Alembic y PostgreSQL

SQLAlchemy centraliza transacciones y consultas; Alembic conserva revisiones del
esquema. Se usa `JSON` portable, claves foráneas e índices SQL, sin PostGIS ni
JSONB obligatorio. SQLite permite pruebas aisladas con migraciones reales;
PostgreSQL local verifica el motor previsto para Supabase. SQLite no acredita
semántica idéntica de bloqueos concurrentes: las pruebas HTTP locales son
secuenciales y falta medir concurrencia en producción.

Una alternativa de acceso exclusivo por SDK REST de Supabase limitaría la misma
implementación en SQLite y el control transaccional de activación/republicación.
Supabase proporciona el destino gestionado propuesto; aún no se ha comprobado
una conexión remota. Referencias: [SQLAlchemy: transacciones](https://docs.sqlalchemy.org/en/20/orm/session_transaction.html),
[Alembic](https://alembic.sqlalchemy.org/en/latest/),
[conexiones Supabase](https://supabase.com/docs/guides/database/connecting-to-postgres).

## Batch y reevaluación

La publicación local ejecuta GX y reutiliza `train`, columnas/contratos, parámetros,
cortes y métricas existentes. Los GET consultan predicciones persistidas; los POST
cargan boosters desde BD y reevalúan los vectores guardados. Entrenar durante una
consulta HTTP aumentaría la duración y acoplaría el despliegue a las fuentes;
servir únicamente CSV impediría la integración API–modelo exigida.

Las versiones finales de servicio utilizan etiquetas cerradas al último origen;
las métricas importadas proceden del protocolo OOS y no evalúan ese ajuste final
como si se hubiese probado otra vez. La selección activa es una decisión de
inferencia para la demo, no una promoción a producción. Para producción se requiere
una evaluación temporal que supere los umbrales, revisión de Rosa y autorización
del despliegue. No todos los runs de MLflow pasan a producción.

## Artefactos y reproducción

El booster XGBoost JSON se guarda en `version_modelo.artefacto`, junto con columnas,
parámetros, hashes, dispositivo, plataforma y versión de XGBoost. Permite ejecutar
la API sin un volumen de datasets/modelos. Incrementa el tamaño de BD y de copias
de seguridad; los listados no exponen el booster. Un almacenamiento de objetos
separado reduciría ese tamaño, pero añade disponibilidad y credenciales externas.
Referencia: [serialización XGBoost](https://xgboost.readthedocs.io/en/stable/tutorials/saving_model.html).

Los boosters OOS originales no fueron entregados: se preservan las predicciones
de Rosa y se marcan esas versiones como no reactivables. Los modelos de servicio
nuevos son distintos ajustes; no se promete identidad numérica CPU/GPU. El helper
MMWR corrige fechas y no altera silenciosamente los resultados históricos.

## Caché y rendimiento

Caché en memoria por proceso, TTL corto y capacidad limitada; compara revisión de
carga/ejecución/activación en BD antes de reutilizar una lectura. Las escrituras
invalidan; `Cache-Control: no-cache` o `no-store` omite la caché de lecturas para
medir y diagnosticar. No elimina el booster residente. Redis permitiría compartir
la caché entre workers, a costa de otra dependencia; no se necesita para la demo
actual. El benchmark publica tiempos completos, errores y recursos omitidos.

## Seguridad y operación

Lectura pública de datos agregados; escritura con clave privada `X-API-Key` y
comparación en tiempo constante. CORS permite el origen configurado, no autentica
usuarios. El frontend público debe consumir GET; una API key privada no debe
incluirse en el bundle React. Las escrituras son operaciones técnicas desde un
cliente autorizado. Autenticación por usuario y roles sería una ampliación futura.

Las credenciales viven en `.env`/variables del entorno y no en los reportes. Los
errores uniformes evitan exponer SQL, cadenas de conexión o detalles del booster.
La base utiliza sus permisos PostgreSQL; para una exposición remota falta verificar
TLS, credenciales, configuración de Render y acceso a Supabase en fase 5. No se
incorporan datos personales. No se afirma una certificación jurídica del sistema.

## Limitaciones y decisiones pendientes

- Los modelos actuales no cumplen HU0007-4: todos se identifican como experimentales.
  `servir_no_validadas: true` permite la demo; con `false` hay valores nulos y motivo.
- Se aprobó usar 2024 para aceptación y reportar 2025 como sensibilidad separada.
  No se promedian los periodos ni se presupone que h=2 esté validado.
- Se aprobó mantener alertas visibles desde 0,50 y conservar `alerta_modelo` con el
  umbral F1. Su discrepancia permanece visible: las probabilidades no están
  acreditadas como calibradas. Falta decidir su uso operativo con Rosa.
- El corte de fuentes es 2025; recalcular no produce información nueva ni un
  pronóstico actual a fecha del servidor.
- h=3 no tiene gold/modelo: las lecturas declaran ausencia y las escrituras lo rechazan.
- Solo hay centroides en las referencias disponibles; no se fabrican polígonos.
- Deriva automatizada, optimización adicional de hiperparámetros, React, SLA remoto
  y disponibilidad del periodo de validación quedan pendientes; ver trazabilidad.
- Resultados pueden variar entre CPU/GPU. CI verifica muestras reales en CPU y
  requiere ejecución remota para acreditar Windows/Linux, además de macOS local.
