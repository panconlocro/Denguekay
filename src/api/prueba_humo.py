"""Prueba de humo TB1: una llamada HTTP real a cada endpoint de la Tabla 2 y evidencia en Markdown.

Uso (con uvicorn levantado): ``python -m src.api.prueba_humo --url http://127.0.0.1:8000``.
La clave de escritura se lee de API_KEY (entorno o .env) y nunca se escribe en la evidencia.
"""

import argparse
from datetime import datetime, timezone
import json
import os
import platform
from importlib.metadata import version

import httpx
from dotenv import load_dotenv

from src.utils.paths import ENV_FILE, EVIDENCIA_BACKEND

DESTINO = EVIDENCIA_BACKEND / "evidencia_tb1.md"


def resumir(ruta, cuerpo):
    """Extracto legible y sin secretos de cada respuesta."""
    if not isinstance(cuerpo, dict):
        return str(cuerpo)[:300]
    if "codigo" in cuerpo and "mensaje" in cuerpo:
        return f"codigo={cuerpo['codigo']}; mensaje={cuerpo['mensaje']}"
    if ruta.startswith("/salud"):
        return (f"estado={cuerpo['estado']}; conexion_bd={cuerpo['conexion_bd']}; "
                f"fecha_corte_datos={cuerpo['fecha_corte_datos']}; ultima_ejecucion={cuerpo['ultima_ejecucion']}")
    if ruta.startswith("/mapa-riesgo"):
        estados = [f["properties"]["estado"] for f in cuerpo["features"]]
        return (f"type={cuerpo['type']}; features={len(cuerpo['features'])}; "
                f"disponibles={estados.count('disponible')}; experimental={cuerpo['experimental']}; "
                f"corte={cuerpo['semana_corte']['id_semana'] if cuerpo['semana_corte'] else None}")
    if ruta.startswith("/tablero"):
        return (f"distritos={cuerpo['distritos']}; con_prediccion={cuerpo['distritos_con_prediccion']}; "
                f"niveles={cuerpo['niveles_riesgo']}; alertas_activas={cuerpo['alertas_activas']}; "
                f"experimental={cuerpo['experimental']}; casos_estimados_region={cuerpo['casos_estimados_region']['valor']}")
    if ruta.startswith("/series"):
        con_pred = sum(e["prediccion"] is not None for e in cuerpo["elementos"])
        return (f"distrito={cuerpo['distrito']}; semanas={len(cuerpo['elementos'])} ({cuerpo['desde']} a {cuerpo['hasta']}); "
                f"semanas_con_prediccion={con_pred}")
    if ruta.startswith("/modelos/activo"):
        return "; ".join(f"{m['codigo']} ({m['seleccion']}, cumple_umbrales={m['cumple_umbrales']})" for m in cuerpo["elementos"])
    if "elementos" in cuerpo:
        texto = f"total={cuerpo['total']}; disponible={cuerpo['disponible']}"
        if cuerpo["elementos"] and "probabilidad_brote" in cuerpo["elementos"][0]:
            e = next((x for x in cuerpo["elementos"] if x["disponible"]), cuerpo["elementos"][0])
            texto += (f"; ejemplo {e['ubigeo']} corte={e['semana_corte']['id_semana']} objetivo={e['semana_objetivo']['id_semana']} "
                      f"p={e['probabilidad_brote']} nivel={e['nivel_riesgo']} casos={e['casos_estimados']} "
                      f"experimental={e['experimental']}")
        return texto
    if "predicciones" in cuerpo and "id_ejecucion" in cuerpo:
        return (f"id_ejecucion={cuerpo['id_ejecucion']}; corte={cuerpo['id_semana_corte']}; objetivo={cuerpo['id_semana_objetivo']}; "
                f"predicciones={cuerpo['predicciones']}; disponibles={cuerpo['disponibles']}; "
                f"experimental={cuerpo['experimental']}; versiones={cuerpo['versiones']}")
    return json.dumps(cuerpo, ensure_ascii=False, default=str)[:300]


def ejecutar(cliente, clave):
    """Llama a cada endpoint de la Tabla 2; la activación usa una versión real de la BD."""
    escritura = {"X-API-Key": clave}
    llamadas = [("GET", "/salud", None), ("GET", "/distritos", None),
                ("GET", "/predicciones?horizonte=4", None), ("GET", "/predicciones?horizonte=2", None),
                ("GET", "/series/200101?horizonte=4", None), ("GET", "/tablero/resumen?horizonte=4", None),
                ("GET", "/mapa-riesgo?horizonte=4", None), ("GET", "/alertas?horizonte=4", None),
                ("GET", "/modelos/activo", None), ("POST", "/admin/inferencias", {"horizonte": 4}),
                ("POST", "/admin/inferencias", {"horizonte": 3})]
    resultados = []
    for metodo, ruta, cuerpo in llamadas:
        r = cliente.request(metodo, "/api/v1" + ruta, json=cuerpo, headers=escritura if metodo == "POST" else None)
        resultados.append({"metodo": metodo, "ruta": ruta, "cuerpo": cuerpo, "http": r.status_code,
                           "ms": r.headers.get("X-Tiempo-Respuesta-ms"), "resumen": resumir(ruta, r.json())})
    en_uso = cliente.get("/api/v1/modelos/activo").json()["elementos"]
    if en_uso:
        ruta = f"/admin/modelos/{en_uso[0]['id_version']}/activar"
        r = cliente.post("/api/v1" + ruta, headers=escritura)
        resultados.append({"metodo": "POST", "ruta": ruta, "cuerpo": None, "http": r.status_code,
                           "ms": r.headers.get("X-Tiempo-Respuesta-ms"), "resumen": resumir(ruta, r.json())})
    sin_clave = cliente.post("/api/v1/admin/inferencias", json={"horizonte": 4})
    resultados.append({"metodo": "POST", "ruta": "/admin/inferencias (sin X-API-Key)", "cuerpo": {"horizonte": 4},
                       "http": sin_clave.status_code, "ms": sin_clave.headers.get("X-Tiempo-Respuesta-ms"),
                       "resumen": resumir("", sin_clave.json())})
    return resultados


def markdown(resultados, url, motor_bd):
    filas = "\n".join(f"| {r['metodo']} | `{r['ruta']}`{' ' + json.dumps(r['cuerpo']) if r['cuerpo'] else ''} | "
                      f"{r['http']} | {r['ms']} | {r['resumen'].replace('|', '/')} |" for r in resultados)
    return f"""# Evidencia TB1: prueba de humo local

Generado por `python -m src.api.prueba_humo` el {datetime.now(timezone.utc).isoformat(timespec='seconds')}.
Servidor: uvicorn en `{url}`; BD: {motor_bd}. Sin credenciales: la clave X-API-Key no se registra.

Entorno: Python {platform.python_version()}, {platform.platform()}; fastapi {version('fastapi')},
SQLAlchemy {version('SQLAlchemy')}, psycopg {version('psycopg')}, xgboost {version('xgboost')}.

| Método | Ruta | HTTP | ms (servidor) | Resumen de la respuesta |
|---|---|---|---|---|
{filas}

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
    opciones = parser.parse_args(argv)
    load_dotenv(ENV_FILE, override=False)
    clave = os.environ.get("API_KEY", "")
    if not clave:
        raise SystemExit("Define API_KEY (entorno o .env) para probar las escrituras")
    with httpx.Client(base_url=opciones.url.rstrip("/"), timeout=120) as cliente:
        resultados = ejecutar(cliente, clave)
    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    DESTINO.write_text(markdown(resultados, opciones.url, opciones.motor_bd), encoding="utf-8")
    for r in resultados:
        print(r["http"], r["metodo"], r["ruta"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
