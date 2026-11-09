# Fase 2 — base visual e integración con demo local v2

Implementación del 04/11/2026, pendiente de revisión antes de la fase 3. El usuario autorizó continuar
y eligió expresamente «Preparar demo local de v2».

## Resultado

Se conservan los componentes, tokens, assets de Figma, navegación y cliente tipado de la base inicial.
La vista previa ahora consume una API sobre la demo local v2, con 65 distritos y horizontes 2, 3 y 4.
Las cifras llegan por HTTP; no hay fixtures en el navegador como reemplazo de una consulta fallida.

La banda de procedencia distingue `demo-v2`, `fixtures`, `api` y un entorno sin identificar. En modo
demo se comprueba `/modelos/activo`: seis versiones v2, dos tareas por horizonte, algoritmo
`xgboost_multisalida_bn` y selección experimental. Una conexión distinta bloquea las vistas de
resultados y permite reintentar. Esto evita confundir las fixtures v0 con v2; no es una certificación
criptográfica del servidor.

El entorno de fixtures declara que incluye valores alterados para probar la interfaz. El 80 % de
Piura de la primera vista previa procede de una fixture del backend, no de esta demo v2. Los scripts
de desarrollo fijan juntos el proxy y la etiqueta del entorno elegido.

## Preparación local autorizada

Se ejecutó el constructor existente, sin modificar el backend:

```bash
PYTHONPATH=src DENGUEKAY_XGB_DEVICE=cpu DENGUEKAY_XGB_NJOBS=2 \
  .venv/bin/python -u -m denguekay.serving.demo_database
```

Creó `models/serving/demo/denguekay_demo.sqlite`, migrada a `0006_v1`, y su `storage/`. Usó el gold
regenerado, la configuración v2 congelada, el ajuste de servicio, el protocolo por bloques y la
inferencia. No se ejecutaron notebooks de investigación. Los generados están ignorados por Git;
el código nuevo sigue limitado a `apps/web/`.

| Elemento                             | Resultado comprobado                                                                     |
| ------------------------------------ | ---------------------------------------------------------------------------------------- |
| Distritos / observaciones semanales  | 65 / 30 485 filas                                                                        |
| Versiones                            | `v2-clf-h2-1`, `v2-reg-h2-1`, `v2-clf-h3-1`, `v2-reg-h3-1`, `v2-clf-h4-1`, `v2-reg-h4-1` |
| Paquete                              | `v2-5c4a9ed5b69b`                                                                        |
| Gold SHA-256                         | `b5773a3436680164b646143c40912bbcdd78f9118eb2e2b7fbd13d765ae9088e`                       |
| Manifiesto SHA-256                   | `1710305158d21ca09b493174b7e863496eac00ec7754b5dc3e0ee62cfa3d30b9`                       |
| Predicciones                         | 40 560 retrospectivas OOS + 195 del último corte = 40 755                                |
| Great Expectations de la publicación | Silver 107/107; gold 42/42                                                               |
| MLflow                               | Corrida `6cee3387465e483080ff6267a5845b18`, `FINISHED`, en la carpeta de demo            |
| Model Registry de MLflow             | 0 modelos registrados en el almacén de demo                                              |

La base anterior `models/serving/fase4.sqlite` conserva el esquema antiguo: no se migró ni se usa en
esta vista previa. No se cambiaron `.env`, la configuración global ni las fichas del registro versionado.

## Datos y vigencia

El corte es **27/12/2025**, aunque la generación local se hizo el 04/11/2026. No se ingirieron datos de 2026. La interfaz muestra el corte y «Consulta histórica · objetivo pasado».

| Horizonte | Semana objetivo | Predicciones disponibles | Casos estimados regionales (API) | Probabilidad máxima | Avisos actuales |
| --------- | --------------- | ------------------------ | -------------------------------- | ------------------- | --------------- |
| 2 semanas | 2026-S01        | 65                       | 10,98                            | 9,31 %              | 0               |
| 3 semanas | 2026-S02        | 65                       | 13,12                            | 13,71 %             | 0               |
| 4 semanas | 2026-S03        | 65                       | 15,58                            | 18,14 %             | 0               |

Todos los resultados del corte son experimentales y tienen intervalo nominal del 80 %. La selección
experimental de una versión difiere de su campo individual `experimental`: la clasificación figura
con `cumple_umbrales: true`, la regresión con `false`, y el par se sirve como experimental. El texto
genérico de la API «ningún modelo cumple todavía los umbrales» no refleja esta distinción; la
integración no lo interpreta como una evaluación adicional.

La huella local es `43051b903a80d7d02d89630da20e034b175ffbd73644a820f8909fdad4d3e523`.
`huella_coincide_con_congelada` es `null`: no se certifica igualdad bit a bit con el entorno de
referencia. Esta demo no sustituye la aprobación del modelo ni un despliegue operacional.

## Ejecución

Desde la raíz, con la demo preparada:

```bash
.venv/bin/python apps/web/tools/serve_demo.py
```

Escucha en `127.0.0.1:18001`. No prepara modelos al arrancar ni usa `DATABASE_URL` para elegir la base.
Abre SQLite en modo de lectura y pasa una clave de escritura vacía. Si falta la demo, falla
explícitamente sin crear una base vacía. Las escrituras SQL se rechazan; los endpoints administrativos
responden 503 por escritura no configurada.

Desde `apps/web/`, en otra terminal:

```bash
npm run dev:demo:v2
```

Abrir [la vista previa](http://127.0.0.1:5173). Para fixtures, iniciar `e2e/serve_api.py` en 18000 y usar
`npm run dev:fixtures`. `npm run dev` sigue admitiendo una API configurada por entorno.

## Verificación

- ESLint, TypeScript, build y formato aprobados; 12 pruebas unitarias aprobadas.
- 4 recorridos Playwright con v2: escritorio y móvil, tres horizontes, comparación del primer distrito
  con la API, 65 predicciones, mapa, navegación, intervalos y serie de Piura; rechazo de otra versión
  y recuperación por reintento.
- 8 recorridos con fixtures: filtros, navegación, assets, avisos, horizonte no disponible y 503.
- 9 guardas de estructura y contrato OpenAPI aprobadas tras preparar los archivos en el índice.
- 39 comprobaciones HTTP con TestClient: lecturas por horizonte, versiones e importancias; aviso
  inexistente con 404 y los dos endpoints administrativos con 503.
- Manifiesto y archivos del paquete verificados por SHA-256 con `load_package`.
- Escritura SQL rechazada. Hashes de demo, base antigua, gold e integrado iguales antes y después
  de las comprobaciones HTTP.
- Capturas inspeccionadas a 1440 y 390 px; recorrido sin desbordamiento horizontal.

Evidencia local: `models/serving/demo/verificacion_frontend.json`. Reporte de publicación:
`models/serving/ejecuciones/a68cdf77ec05f5343b05552a70edd89842eeef1830914cbe19083ddbd7880e5b/`.
Capturas: `/private/tmp/denguekay-web-review.WFWIBR/desktop-demo-v2.png` y
`/private/tmp/denguekay-web-review.WFWIBR/mobile-demo-v2.png`.

## Límites y siguiente fase

Este cierre valida la base y su integración. Las pantallas conservan su implementación inicial y las
entregas específicas pendientes. Serie regional e incidencia siguen ausentes del contrato. No se
añadieron datos para llenar esos componentes, ni avisos artificiales a la demo; los escenarios con
avisos se prueban con fixtures. Las limitaciones de backend y de la suite Python general registradas
en `VALIDACION.md` siguen pendientes. Esta fase no certifica toda la suite en verde. La siguiente fase
es completar el tablero con esta fuente real, tras la revisión del usuario.
