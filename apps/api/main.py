"""Deployable FastAPI application: it reads models and data only from the database."""

from contextlib import asynccontextmanager
import os
from time import perf_counter

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.api.cache import ReadCache
from apps.api.contract import CONTRACT_HEADER, CONTRACT_VERSION
from apps.api.errors import register_error_handlers
from apps.api.schemas import ErrorRespuesta
from apps.api.routers import admin, data, models, reference, surveillance
from denguekay.db.settings import InvalidDatabaseSettings
from denguekay.db.session import create_session_factory, make_engine
from denguekay.serving.storage import storage_from_environment
from denguekay.serving.settings import service_settings
from denguekay.config.paths import ENV_FILE


def create_app(engine=None, cfg=None, api_key=None, cache_ttl=10, storage=None):
    """Inject real engines for tests; without a URL it does not create an alternative database."""
    load_dotenv(ENV_FILE, override=False)
    cfg = cfg or service_settings()

    @asynccontextmanager
    async def lifespan(app):
        owned = engine is None
        chosen = engine
        if owned:
            try:
                chosen = make_engine()
            except InvalidDatabaseSettings:
                chosen = None
        app.state.session_factory = create_session_factory(chosen) if chosen is not None else None
        try:
            yield
        finally:
            if owned and chosen is not None:
                chosen.dispose()
            app.state.cache.clear()

    # info.version is the contract version (semver); /salud reports the application version (decision C5).
    app = FastAPI(title="Denguekay: pronóstico distrital de dengue", version=CONTRACT_VERSION,
        description="API del documento OE2 (Tabla 2) sobre datos agregados de Piura. Contrato v1, independiente del "
                    "modelo: los horizontes disponibles salen de la BD (GET /configuracion). Las predicciones de "
                    "versiones que no cumplen los umbrales se marcan experimental: true (demo; desviación temporal "
                    "documentada). Cada respuesta lleva la versión del contrato en X-Version-Contrato.",
        lifespan=lifespan, responses={estado: {"model": ErrorRespuesta, "description": text} for estado, text in (
            (401, "Clave de escritura ausente o inválida"), (404, "Recurso inexistente"),
            (409, "Solicitud no atendible con los datos o modelos (horizonte sin modelo, artefacto, umbrales)"),
            (422, "Parámetro inválido"),
            (503, "Base de datos, parámetros o escritura no disponibles"), (500, "Error interno controlado"))})
    app.state.cfg = cfg
    app.state.api_key = os.environ.get("API_KEY", "") if api_key is None else api_key
    app.state.cache = ReadCache(ttl=cache_ttl)
    app.state.storage = storage or storage_from_environment(cfg.almacenamiento)
    app.state.session_factory = create_session_factory(engine) if engine is not None else None
    register_error_handlers(app)
    app.add_middleware(CORSMiddleware, allow_origins=list(cfg.cors_origenes),
        allow_methods=["GET", "POST"], allow_headers=["Content-Type", "X-API-Key", "Cache-Control"],
        expose_headers=["X-Tiempo-Respuesta-ms", "X-Cache", CONTRACT_HEADER])

    @app.middleware("http")
    async def time_response(request, call_next):
        start = perf_counter()
        response = await call_next(request)
        response.headers["X-Tiempo-Respuesta-ms"] = f"{(perf_counter() - start) * 1000:.3f}"
        response.headers[CONTRACT_HEADER] = CONTRACT_VERSION
        return response

    for router in (reference.router, data.router, surveillance.router, models.router, admin.router):
        app.include_router(router, prefix="/api/v1")
    from apps.api.openapi import specification
    app.openapi = lambda: specification(app)
    return app


app = create_app()
