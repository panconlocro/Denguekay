"""Reproducible p50/p95 measurement against the real API and database, without simulated results."""

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

from denguekay.config.paths import API_BENCHMARK_JSON, BACKEND_DOCS, ENV_FILE, MODELS, ROOT


def percentile(values, proportion):
    """Interpolate positions (n−1)*p without replacing failed measurements with zeros."""
    ordered = sorted(values)
    if not ordered or not 0 <= proportion <= 1:
        raise ValueError("El percentil requiere mediciones y una proporción entre cero y uno")
    position = (len(ordered) - 1) * proportion
    low, high = math.floor(position), math.ceil(position)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def read_json(client, path):
    """Choosing examples requires real successful responses."""
    response = client.get("/api/v1" + path)
    if response.status_code != 200:
        raise ValueError("La API no permite descubrir recursos reales; comprueba BD y migraciones")
    return response.json()


def discover_cases(client, horizons):
    """Select existing ubigeo, alerts and versions; it never uses made-up IDs.

    Each case is (method, path, JSON body). Activation is only measured if there is
    a version that meets the thresholds (otherwise it answers 409 by design).
    """
    health = read_json(client, "/salud")
    districts = read_json(client, "/distritos?tamano_pagina=1")["elementos"]
    if not districts:
        raise ValueError("El benchmark requiere distritos y una carga real de datos")
    ubigeo = districts[0]["ubigeo"]
    cases = [("GET", "/salud", None), ("GET", "/distritos", None), ("GET", f"/distritos/{ubigeo}", None),
             ("GET", "/observaciones", None), ("GET", "/modelos/activo", None)]
    skipped = []
    for h in horizons:
        for path in (f"/predicciones?horizonte={h}", f"/mapa-riesgo?horizonte={h}",
                     f"/series/{ubigeo}?horizonte={h}", f"/tablero/resumen?horizonte={h}",
                     f"/alertas?horizonte={h}"):
            cases.append(("GET", path, None))
        cases.append(("POST", "/admin/inferencias", {"horizonte": h}))
    alert = read_json(client, "/alertas?tamano_pagina=1")["elementos"]
    if alert:
        cases.append(("GET", f"/alertas/{alert[0]['id_alerta']}", None))
    else:
        skipped.append({"ruta": "/alertas/{identificador}", "motivo": "No hay alertas guardadas para medir un detalle real"})
    in_use = [v for v in read_json(client, "/modelos/activo")["elementos"] if v["horizonte"] in horizons]
    if not in_use:
        raise ValueError("No hay versiones en uso para los horizontes solicitados")
    for v in in_use:
        cases.extend([("GET", f"/modelos/{v['id_version']}", None), ("GET", f"/modelos/{v['id_version']}/variables", None)])
    skipped.append({"ruta": "/admin/modelos/{version}/activar",
                     "motivo": "Activar cambia el estado de una versión y exige cumple_umbrales; se prueba en los tests"})
    return cases, skipped, health, in_use


def measure_case(client, method, path, mode, repetitions, warmup, api_key, limit, body=None):
    """Include transport, execution and full reception of the body; HTTP 200 is required."""
    headers = {"Cache-Control": "no-cache"} if mode == "sin_cache_lecturas" else {}
    if method == "POST":
        headers["X-API-Key"] = api_key
    durations, statuses, caches, errors = [], Counter(), Counter(), 0
    for index in range(warmup + repetitions):
        start = perf_counter()
        try:
            response = client.request(method, "/api/v1" + path, headers=headers, json=body)
            # httpx/TestClient deliver the received body; the server header alone is not used.
            _ = response.content
            elapsed = (perf_counter() - start) * 1000
            estado = response.status_code
            cache = response.headers.get("X-Cache", "SIN_CABECERA")
        except httpx.HTTPError:
            elapsed, estado, cache = (perf_counter() - start) * 1000, None, "ERROR_TRANSPORTE"
        if index < warmup:
            continue
        durations.append(elapsed)
        statuses[str(estado) if estado is not None else "error_transporte"] += 1
        caches[cache] += 1
        errors += estado != 200
    p50, p95 = percentile(durations, .5), percentile(durations, .95)
    return {"metodo": method, "ruta": path, "cuerpo": body, "modo": mode,
        "repeticiones": repetitions, "calentamiento": warmup,
        "duraciones_ms": durations, "p50_ms": p50, "p95_ms": p95,
        "max_ms": max(durations), "http": dict(statuses), "cache": dict(caches),
        "errores": errors, "disponible": True, "motivo": None,
        "cumple_sla": errors == 0 and p95 < limit * 1000}


def run_benchmark(client, *, horizons=(2, 4), repetitions=20,
                      warmup=2, include_writes=False, api_key="", limit=5):
    """Every successful write keeps a run; use a scratch database."""
    if repetitions < 2 or warmup < 0 or limit <= 0 or not math.isfinite(limit):
        raise ValueError("Se requieren al menos dos repeticiones, calentamiento no negativo y límite positivo")
    if not horizons or len(set(horizons)) != len(horizons) or any(h not in (2, 4) for h in horizons):
        raise ValueError("El benchmark exige horizontes únicos con modelos reales: 2 y/o 4")
    if include_writes and not api_key:
        raise ValueError("Configura API_KEY para medir los endpoints de escritura")
    cases, skipped, health, in_use = discover_cases(client, horizons)
    results = []
    for method, path, body in cases:
        if method == "POST" and not include_writes:
            skipped.append({"ruta": path, "motivo": "Escritura no medida; usar --incluir-escrituras en una BD de ensayo"})
            continue
        modes = ("sin_cache_lecturas", "cache_habilitada") if method == "GET" else ("escritura",)
        for mode in modes:
            results.append(measure_case(client, method, path, mode, repetitions,
                warmup if method == "GET" else 0, api_key, limit, body))
    final_health = read_json(client, "/salud")
    return {"fecha_medicion": datetime.now(timezone.utc).isoformat(),
        "fecha_corte_datos": health["fecha_corte_datos"],
        "ultima_ejecucion_inicial": health["ultima_ejecucion"],
        "ultima_ejecucion_final": final_health["ultima_ejecucion"],
        "limite_sla_segundos": limit, "horizontes": list(horizons),
        "repeticiones": repetitions, "calentamiento": warmup,
        "incluye_escrituras": include_writes, "resultados": results,
        "no_medidos": skipped, "cumple_sla_medido": all(r["cumple_sla"] for r in results),
        "cobertura_completa": not skipped,
        "cumple_sla_completo": not skipped and all(r["cumple_sla"] for r in results),
        "versiones_en_uso": [{k: v[k] for k in ("id_version", "codigo", "horizonte", "tarea", "seleccion", "experimental")}
            for v in in_use],
        "entorno": {"python": platform.python_version(), "plataforma": platform.platform(),
            "dependencias": {p: version(p) for p in ("fastapi", "httpx", "SQLAlchemy", "xgboost", "coverage")}},
        "nota": "Carga secuencial, sin incluir arranque del proceso. Sin cache de lecturas no elimina la caché residente del booster. No sustituye medición remota ni prueba de concurrencia"}


def main(argv=None):
    """CLI without secrets in its output; by default it measures reads on DATABASE_URL."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", help="URL del servidor, sin /api/v1; al omitirla usa TestClient y DATABASE_URL reales")
    parser.add_argument("--horizontes", nargs="+", type=int, default=[2, 4])
    parser.add_argument("--repeticiones", type=int, default=20)
    parser.add_argument("--calentamiento", type=int, default=2)
    parser.add_argument("--incluir-escrituras", action="store_true", help="Agrega ejecuciones reales; usar una copia de la BD")
    parser.add_argument("--salida", default=str(API_BENCHMARK_JSON.relative_to(ROOT)), help="Archivo JSON de mediciones; ruta relativa al repo")
    options = parser.parse_args(argv)
    load_dotenv(ENV_FILE, override=False)
    salida = ROOT / options.salida
    if salida.is_absolute() and (not salida.resolve().is_relative_to(MODELS)
                               and not salida.resolve().is_relative_to(BACKEND_DOCS)):
        parser.error("La salida debe estar en models/ o docs/backend/; nunca en data/")
    arguments = dict(horizons=tuple(options.horizontes), repetitions=options.repeticiones,
        warmup=options.calentamiento, include_writes=options.incluir_escrituras,
        api_key=os.environ.get("API_KEY", ""))
    try:
        if options.url:
            parts = urlsplit(options.url)
            if parts.scheme not in ("http", "https") or not parts.netloc or parts.username or parts.password:
                raise ValueError("La URL debe ser HTTP(S), sin credenciales")
            with httpx.Client(base_url=options.url.rstrip("/"), timeout=30) as client:
                report = run_benchmark(client, **arguments)
            report["transporte"] = "HTTP real"
        else:
            from fastapi.testclient import TestClient
            from apps.api.main import create_app  # uses DATABASE_URL and models/storage
            with TestClient(create_app()) as client:
                report = run_benchmark(client, **arguments)
            report["transporte"] = "ASGI TestClient contra BD real; sin red HTTP"
        salida.parent.mkdir(parents=True, exist_ok=True)
        salida.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    except (ValueError, httpx.HTTPError) as error:
        print("No se pudo medir: " + str(error))
        return 1
    print(json.dumps({"archivo": str(salida.relative_to(ROOT)),
        "casos_medidos": len(report["resultados"]), "no_medidos": len(report["no_medidos"]),
        "maximo_p95_ms": max(r["p95_ms"] for r in report["resultados"]),
        "cumple_sla_medido": report["cumple_sla_medido"],
        "cumple_sla_completo": report["cumple_sla_completo"]}, ensure_ascii=False))
    return 0 if report["cumple_sla_medido"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
