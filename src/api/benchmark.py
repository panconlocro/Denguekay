"""Medición reproducible p50/p95 contra la API y la BD real, sin resultados simulados."""

import argparse
from collections import Counter
from datetime import datetime, timezone
from importlib.metadata import version
import json
import math
import os
import platform
from time import perf_counter
from urllib.parse import urlsplit

import httpx
from dotenv import load_dotenv

from src.utils.paths import API_BENCHMARK_JSON, BACKEND_DOCS, ENV_FILE, MODELS, ROOT


def percentil(valores, proporcion):
    """Interpola posiciones (n−1)*p sin sustituir mediciones fallidas por ceros."""
    orden = sorted(valores)
    if not orden or not 0 <= proporcion <= 1:
        raise ValueError("El percentil requiere mediciones y una proporción entre cero y uno")
    posicion = (len(orden) - 1) * proporcion
    abajo, arriba = math.floor(posicion), math.ceil(posicion)
    return orden[abajo] + (orden[arriba] - orden[abajo]) * (posicion - abajo)


def leer_json(cliente, ruta):
    """La selección de ejemplos requiere respuestas reales exitosas."""
    respuesta = cliente.get("/api/v1" + ruta)
    if respuesta.status_code != 200:
        raise ValueError("La API no permite descubrir recursos reales; comprueba BD y migraciones")
    return respuesta.json()


def descubrir_casos(cliente, horizontes):
    """Selecciona ubigeo, alertas y versiones existentes; nunca usa IDs inventados.

    Cada caso es (método, ruta, cuerpo JSON). La activación solo se mide si hay
    una versión que cumpla los umbrales (si no, responde 409 por diseño).
    """
    salud = leer_json(cliente, "/salud")
    distritos = leer_json(cliente, "/distritos?tamano_pagina=1")["elementos"]
    if not distritos:
        raise ValueError("El benchmark requiere distritos y una carga real de datos")
    ubigeo = distritos[0]["ubigeo"]
    casos = [("GET", "/salud", None), ("GET", "/distritos", None), ("GET", f"/distritos/{ubigeo}", None),
             ("GET", "/observaciones", None), ("GET", "/modelos/activo", None)]
    omitidos = []
    for h in horizontes:
        for ruta in (f"/predicciones?horizonte={h}", f"/mapa-riesgo?horizonte={h}",
                     f"/series/{ubigeo}?horizonte={h}", f"/tablero/resumen?horizonte={h}",
                     f"/alertas?horizonte={h}"):
            casos.append(("GET", ruta, None))
        casos.append(("POST", "/admin/inferencias", {"horizonte": h}))
    alerta = leer_json(cliente, "/alertas?tamano_pagina=1")["elementos"]
    if alerta:
        casos.append(("GET", f"/alertas/{alerta[0]['id_alerta']}", None))
    else:
        omitidos.append({"ruta": "/alertas/{identificador}", "motivo": "No hay alertas guardadas para medir un detalle real"})
    en_uso = [v for v in leer_json(cliente, "/modelos/activo")["elementos"] if v["horizonte"] in horizontes]
    if not en_uso:
        raise ValueError("No hay versiones en uso para los horizontes solicitados")
    for v in en_uso:
        casos.extend([("GET", f"/modelos/{v['id_version']}", None), ("GET", f"/modelos/{v['id_version']}/variables", None)])
    omitidos.append({"ruta": "/admin/modelos/{version}/activar",
                     "motivo": "Activar cambia el estado de una versión y exige cumple_umbrales; se prueba en los tests"})
    return casos, omitidos, salud, en_uso


def medir_caso(cliente, metodo, ruta, modo, repeticiones, calentamiento, clave_api, limite, cuerpo=None):
    """Incluye transporte, ejecución y recepción completa del cuerpo; exige HTTP 200."""
    cabeceras = {"Cache-Control": "no-cache"} if modo == "sin_cache_lecturas" else {}
    if metodo == "POST":
        cabeceras["X-API-Key"] = clave_api
    duraciones, estados, caches, errores = [], Counter(), Counter(), 0
    for indice in range(calentamiento + repeticiones):
        inicio = perf_counter()
        try:
            respuesta = cliente.request(metodo, "/api/v1" + ruta, headers=cabeceras, json=cuerpo)
            # httpx/TestClient entregan el cuerpo recibido; no se usa solo la cabecera del servidor.
            _ = respuesta.content
            tiempo = (perf_counter() - inicio) * 1000
            estado = respuesta.status_code
            cache = respuesta.headers.get("X-Cache", "SIN_CABECERA")
        except httpx.HTTPError:
            tiempo, estado, cache = (perf_counter() - inicio) * 1000, None, "ERROR_TRANSPORTE"
        if indice < calentamiento:
            continue
        duraciones.append(tiempo)
        estados[str(estado) if estado is not None else "error_transporte"] += 1
        caches[cache] += 1
        errores += estado != 200
    p50, p95 = percentil(duraciones, .5), percentil(duraciones, .95)
    return {"metodo": metodo, "ruta": ruta, "cuerpo": cuerpo, "modo": modo,
        "repeticiones": repeticiones, "calentamiento": calentamiento,
        "duraciones_ms": duraciones, "p50_ms": p50, "p95_ms": p95,
        "max_ms": max(duraciones), "http": dict(estados), "cache": dict(caches),
        "errores": errores, "disponible": True, "motivo": None,
        "cumple_sla": errores == 0 and p95 < limite * 1000}


def ejecutar_benchmark(cliente, *, horizontes=(2, 4), repeticiones=20,
                      calentamiento=2, incluir_escrituras=False, clave_api="", limite=5):
    """Todas las escrituras exitosas conservan una ejecución; usar una BD de ensayo."""
    if repeticiones < 2 or calentamiento < 0 or limite <= 0 or not math.isfinite(limite):
        raise ValueError("Se requieren al menos dos repeticiones, calentamiento no negativo y límite positivo")
    if not horizontes or len(set(horizontes)) != len(horizontes) or any(h not in (2, 4) for h in horizontes):
        raise ValueError("El benchmark exige horizontes únicos con modelos reales: 2 y/o 4")
    if incluir_escrituras and not clave_api:
        raise ValueError("Configura API_KEY para medir los endpoints de escritura")
    casos, omitidos, salud, en_uso = descubrir_casos(cliente, horizontes)
    resultados = []
    for metodo, ruta, cuerpo in casos:
        if metodo == "POST" and not incluir_escrituras:
            omitidos.append({"ruta": ruta, "motivo": "Escritura no medida; usar --incluir-escrituras en una BD de ensayo"})
            continue
        modos = ("sin_cache_lecturas", "cache_habilitada") if metodo == "GET" else ("escritura",)
        for modo in modos:
            resultados.append(medir_caso(cliente, metodo, ruta, modo, repeticiones,
                calentamiento if metodo == "GET" else 0, clave_api, limite, cuerpo))
    salud_final = leer_json(cliente, "/salud")
    return {"fecha_medicion": datetime.now(timezone.utc).isoformat(),
        "fecha_corte_datos": salud["fecha_corte_datos"],
        "ultima_ejecucion_inicial": salud["ultima_ejecucion"],
        "ultima_ejecucion_final": salud_final["ultima_ejecucion"],
        "limite_sla_segundos": limite, "horizontes": list(horizontes),
        "repeticiones": repeticiones, "calentamiento": calentamiento,
        "incluye_escrituras": incluir_escrituras, "resultados": resultados,
        "no_medidos": omitidos, "cumple_sla_medido": all(r["cumple_sla"] for r in resultados),
        "cobertura_completa": not omitidos,
        "cumple_sla_completo": not omitidos and all(r["cumple_sla"] for r in resultados),
        "versiones_en_uso": [{k: v[k] for k in ("id_version", "codigo", "horizonte", "tarea", "seleccion", "experimental")}
            for v in en_uso],
        "entorno": {"python": platform.python_version(), "plataforma": platform.platform(),
            "dependencias": {p: version(p) for p in ("fastapi", "httpx", "SQLAlchemy", "xgboost", "coverage")}},
        "nota": "Carga secuencial, sin incluir arranque del proceso. Sin cache de lecturas no elimina la caché residente del booster. No sustituye medición remota ni prueba de concurrencia"}


def main(argv=None):
    """CLI sin secretos en salida; por defecto mide lecturas sobre DATABASE_URL."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", help="URL del servidor, sin /api/v1; al omitirla usa TestClient y DATABASE_URL reales")
    parser.add_argument("--horizontes", nargs="+", type=int, default=[2, 4])
    parser.add_argument("--repeticiones", type=int, default=20)
    parser.add_argument("--calentamiento", type=int, default=2)
    parser.add_argument("--incluir-escrituras", action="store_true", help="Agrega ejecuciones reales; usar una copia de la BD")
    parser.add_argument("--salida", default=str(API_BENCHMARK_JSON.relative_to(ROOT)), help="Archivo JSON de mediciones; ruta relativa al repo")
    opciones = parser.parse_args(argv)
    load_dotenv(ENV_FILE, override=False)
    salida = ROOT / opciones.salida
    if salida.is_absolute() and (not salida.resolve().is_relative_to(MODELS)
                               and not salida.resolve().is_relative_to(BACKEND_DOCS)):
        parser.error("La salida debe estar en models/ o docs/backend/; nunca en data/")
    argumentos = dict(horizontes=tuple(opciones.horizontes), repeticiones=opciones.repeticiones,
        calentamiento=opciones.calentamiento, incluir_escrituras=opciones.incluir_escrituras,
        clave_api=os.environ.get("API_KEY", ""))
    try:
        if opciones.url:
            partes = urlsplit(opciones.url)
            if partes.scheme not in ("http", "https") or not partes.netloc or partes.username or partes.password:
                raise ValueError("La URL debe ser HTTP(S), sin credenciales")
            with httpx.Client(base_url=opciones.url.rstrip("/"), timeout=30) as cliente:
                reporte = ejecutar_benchmark(cliente, **argumentos)
            reporte["transporte"] = "HTTP real"
        else:
            from fastapi.testclient import TestClient
            from src.api.main import crear_app  # usa DATABASE_URL y models/storage
            with TestClient(crear_app()) as cliente:
                reporte = ejecutar_benchmark(cliente, **argumentos)
            reporte["transporte"] = "ASGI TestClient contra BD real; sin red HTTP"
        salida.parent.mkdir(parents=True, exist_ok=True)
        salida.write_text(json.dumps(reporte, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    except (ValueError, httpx.HTTPError) as error:
        print("No se pudo medir: " + str(error))
        return 1
    print(json.dumps({"archivo": str(salida.relative_to(ROOT)),
        "casos_medidos": len(reporte["resultados"]), "no_medidos": len(reporte["no_medidos"]),
        "maximo_p95_ms": max(r["p95_ms"] for r in reporte["resultados"]),
        "cumple_sla_medido": reporte["cumple_sla_medido"],
        "cumple_sla_completo": reporte["cumple_sla_completo"]}, ensure_ascii=False))
    return 0 if reporte["cumple_sla_medido"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
