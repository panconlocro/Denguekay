"""TB1 smoke test: one real HTTP call to each endpoint of Table 2 and evidence in Markdown.

Usage (with uvicorn running): ``python -m apps.api.tools.smoke_test --url http://127.0.0.1:8000``.
The write key is read from API_KEY (environment or .env) and is never written to the evidence.
"""

import argparse
from datetime import datetime, timezone
import json
import os
import platform
from importlib.metadata import version

import httpx
from dotenv import load_dotenv

from denguekay.config.paths import ENV_FILE, BACKEND_EVIDENCE

DESTINATION = BACKEND_EVIDENCE / "evidencia_tb1.md"


def summarize(path, body):
    """Readable excerpt of each response, without secrets."""
    if not isinstance(body, dict):
        return str(body)[:300]
    if "codigo" in body and "mensaje" in body:
        return f"codigo={body['codigo']}; mensaje={body['mensaje']}"
    if path.startswith("/salud"):
        return (f"estado={body['estado']}; conexion_bd={body['conexion_bd']}; "
                f"fecha_corte_datos={body['fecha_corte_datos']}; ultima_ejecucion={body['ultima_ejecucion']}")
    if path.startswith("/mapa-riesgo"):
        statuses = [f["properties"]["estado"] for f in body["features"]]
        return (f"type={body['type']}; features={len(body['features'])}; "
                f"disponibles={statuses.count('disponible')}; experimental={body['experimental']}; "
                f"corte={body['semana_corte']['id_semana'] if body['semana_corte'] else None}")
    if path.startswith("/tablero"):
        return (f"distritos={body['distritos']}; con_prediccion={body['distritos_con_prediccion']}; "
                f"niveles={body['niveles_riesgo']}; alertas_activas={body['alertas_activas']}; "
                f"experimental={body['experimental']}; casos_estimados_region={body['casos_estimados_region']['valor']}")
    if path.startswith("/series"):
        with_prediction = sum(e["prediccion"] is not None for e in body["elementos"])
        return (f"distrito={body['distrito']}; semanas={len(body['elementos'])} ({body['desde']} a {body['hasta']}); "
                f"semanas_con_prediccion={with_prediction}")
    if path.startswith("/modelos/activo"):
        return "; ".join(f"{m['codigo']} ({m['seleccion']}, cumple_umbrales={m['cumple_umbrales']})" for m in body["elementos"])
    if "elementos" in body:
        text = f"total={body['total']}; disponible={body['disponible']}"
        if body["elementos"] and "probabilidad_brote" in body["elementos"][0]:
            e = next((x for x in body["elementos"] if x["disponible"]), body["elementos"][0])
            text += (f"; ejemplo {e['ubigeo']} corte={e['semana_corte']['id_semana']} objetivo={e['semana_objetivo']['id_semana']} "
                      f"p={e['probabilidad_brote']} nivel={e['nivel_riesgo']} casos={e['casos_estimados']} "
                      f"experimental={e['experimental']}")
        return text
    if "predicciones" in body and "id_ejecucion" in body:
        return (f"id_ejecucion={body['id_ejecucion']}; corte={body['id_semana_corte']}; objetivo={body['id_semana_objetivo']}; "
                f"predicciones={body['predicciones']}; disponibles={body['disponibles']}; "
                f"experimental={body['experimental']}; versiones={body['versiones']}")
    return json.dumps(body, ensure_ascii=False, default=str)[:300]


def run(client, key):
    """Call each endpoint of Table 2; activation uses a real version from the database."""
    write_headers = {"X-API-Key": key}
    calls = [("GET", "/salud", None), ("GET", "/distritos", None),
                ("GET", "/predicciones?horizonte=4", None), ("GET", "/predicciones?horizonte=2", None),
                ("GET", "/series/200101?horizonte=4", None), ("GET", "/tablero/resumen?horizonte=4", None),
                ("GET", "/mapa-riesgo?horizonte=4", None), ("GET", "/alertas?horizonte=4", None),
                ("GET", "/modelos/activo", None), ("POST", "/admin/inferencias", {"horizonte": 4}),
                ("POST", "/admin/inferencias", {"horizonte": 3})]
    results = []
    for method, path, body in calls:
        r = client.request(method, "/api/v1" + path, json=body, headers=write_headers if method == "POST" else None)
        results.append({"metodo": method, "ruta": path, "cuerpo": body, "http": r.status_code,
                           "ms": r.headers.get("X-Tiempo-Respuesta-ms"), "resumen": summarize(path, r.json())})
    in_use = client.get("/api/v1/modelos/activo").json()["elementos"]
    if in_use:
        path = f"/admin/modelos/{in_use[0]['id_version']}/activar"
        r = client.post("/api/v1" + path, headers=write_headers)
        results.append({"metodo": "POST", "ruta": path, "cuerpo": None, "http": r.status_code,
                           "ms": r.headers.get("X-Tiempo-Respuesta-ms"), "resumen": summarize(path, r.json())})
    without_key = client.post("/api/v1/admin/inferencias", json={"horizonte": 4})
    results.append({"metodo": "POST", "ruta": "/admin/inferencias (sin X-API-Key)", "cuerpo": {"horizonte": 4},
                       "http": without_key.status_code, "ms": without_key.headers.get("X-Tiempo-Respuesta-ms"),
                       "resumen": summarize("", without_key.json())})
    return results


def markdown(results, url, motor_bd):
    rows = "\n".join(f"| {r['metodo']} | `{r['ruta']}`{' ' + json.dumps(r['cuerpo']) if r['cuerpo'] else ''} | "
                      f"{r['http']} | {r['ms']} | {r['resumen'].replace('|', '/')} |" for r in results)
    return f"""# Evidencia TB1: prueba de humo local

Generado por `python -m apps.api.tools.smoke_test` el {datetime.now(timezone.utc).isoformat(timespec='seconds')}.
Servidor: uvicorn en `{url}`; BD: {motor_bd}. Sin credenciales: la clave X-API-Key no se registra.

Entorno: Python {platform.python_version()}, {platform.platform()}; fastapi {version('fastapi')},
SQLAlchemy {version('SQLAlchemy')}, psycopg {version('psycopg')}, xgboost {version('xgboost')}.

| Método | Ruta | HTTP | ms (servidor) | Resumen de la respuesta |
|---|---|---|---|---|
{rows}

Notas:
- Las versiones de modelo no cumplen los umbrales de aceptación: se sirven como `experimental: true`
  (desviación temporal, `docs/backend/desviaciones_oe2.md`). Por eso la activación responde 409
  `no_cumple_umbrales`, que es el comportamiento exigido por el CHECK del DDL.
- `POST /admin/inferencias` con h=3 responde 409 («sin modelo para h=3»); sin `X-API-Key`, 401.
"""


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000", help="Servidor uvicorn, sin /api/v1")
    parser.add_argument("--motor-bd", default="PostgreSQL local (DATABASE_URL de .env)", help="Descripción de la BD, sin credenciales")
    options = parser.parse_args(argv)
    load_dotenv(ENV_FILE, override=False)
    key = os.environ.get("API_KEY", "")
    if not key:
        raise SystemExit("Define API_KEY (entorno o .env) para probar las escrituras")
    with httpx.Client(base_url=options.url.rstrip("/"), timeout=120) as client:
        results = run(client, key)
    DESTINATION.parent.mkdir(parents=True, exist_ok=True)
    DESTINATION.write_text(markdown(results, options.url, options.motor_bd), encoding="utf-8")
    for r in results:
        print(r["http"], r["metodo"], r["ruta"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
