"""Aplicación FastAPI desplegable: lee modelos y datos exclusivamente desde la BD."""

from contextlib import asynccontextmanager
import os
from time import perf_counter

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.cache import CacheLecturas
from src.api.errores import registrar_errores
from src.api.esquemas import ErrorRespuesta
from src.api.routers import datos, modelos, referencia, vigilancia
from src.db.configuracion import ConfiguracionBDInvalida
from src.db.sesion import crear_fabrica_sesiones, crear_motor
from src.serving.configuracion import configuracion_servicio
from src.utils.paths import ENV_FILE


def crear_app(motor=None, cfg=None, clave_api=None, ttl_cache=10):
    """Inyecta motores reales para pruebas; sin URL no crea una BD alternativa."""
    load_dotenv(ENV_FILE, override=False)
    cfg = cfg or configuracion_servicio()

    @asynccontextmanager
    async def vida(app):
        propio = motor is None
        elegido = motor
        if propio:
            try:
                elegido = crear_motor()
            except ConfiguracionBDInvalida:
                elegido = None
        app.state.fabrica_sesiones = crear_fabrica_sesiones(elegido) if elegido is not None else None
        try:
            yield
        finally:
            if propio and elegido is not None:
                elegido.dispose()
            app.state.cache.limpiar()

    app = FastAPI(title="Denguekay: pronóstico distrital de dengue", version="1.0.0",
        description="API de datos agregados de Piura. El corte de datos distingue los pronósticos históricos de la fecha actual. "
                    "Las versiones experimentales se identifican explícitamente; una versión activa no acredita validación.",
        lifespan=vida, responses={estado: {"model": ErrorRespuesta, "description": texto} for estado, texto in (
            (401, "Clave de escritura ausente o inválida"), (404, "Recurso inexistente"),
            (409, "Modelo o vectores incompatibles para reevaluar"), (422, "Parámetro inválido"),
            (503, "Base de datos o escritura no disponible"), (500, "Error interno controlado"))})
    app.state.cfg = cfg
    app.state.clave_api = os.environ.get("API_KEY", "") if clave_api is None else clave_api
    app.state.cache = CacheLecturas(ttl=ttl_cache)
    app.state.fabrica_sesiones = crear_fabrica_sesiones(motor) if motor is not None else None
    registrar_errores(app)
    app.add_middleware(CORSMiddleware, allow_origins=[cfg.cors_origen],
        allow_methods=["GET", "POST"], allow_headers=["Content-Type", "X-API-Key"],
        expose_headers=["X-Tiempo-Respuesta-ms", "X-Cache"])

    @app.middleware("http")
    async def medir_respuesta(request, siguiente):
        inicio = perf_counter()
        respuesta = await siguiente(request)
        respuesta.headers["X-Tiempo-Respuesta-ms"] = f"{(perf_counter() - inicio) * 1000:.3f}"
        return respuesta

    for router in (referencia.router, datos.router, vigilancia.router, modelos.router):
        app.include_router(router, prefix="/api/v1")
    from src.api.openapi import especificacion
    app.openapi = lambda: especificacion(app)
    return app


app = crear_app()
