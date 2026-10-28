"""Per-request sessions, write authentication and range checks."""

from datetime import date
from secrets import compare_digest
from typing import Annotated

from fastapi import Depends, Path, Query, Request, Response, Security
from fastapi.security import APIKeyHeader
from pydantic import Field, StringConstraints
from sqlalchemy import func, select

from apps.api.errors import APIError
from denguekay.db.models import Run

Ubigeo = Annotated[str, StringConstraints(pattern=r"^[0-9]{6}$"),
                   Field(description="Código distrital de seis dígitos, conservado como texto")]
Identifier = Annotated[int, Path(ge=1, description="Identificador positivo del registro guardado en la BD")]
Horizon = Annotated[int, Query(ge=2, le=4, description="Anticipación en semanas: 2 o 4 con modelo; 3 responde no_disponible")]
PageNumber = Annotated[int, Query(ge=1, description="Página, comenzando en uno")]
PageSize = Annotated[int, Query(ge=1, le=100, description="Cantidad máxima de elementos por página")]
key_header = APIKeyHeader(name="X-API-Key", auto_error=False,
    description="Clave de escritura definida en API_KEY; las lecturas son públicas")


def get_session(request: Request):
    factory = request.app.state.session_factory
    if factory is None:
        raise APIError(503, "bd_no_disponible", "La base de datos no está configurada o no está disponible")
    with factory() as session:
        yield session


DbSession = Annotated[object, Depends(get_session)]


def require_key(request: Request, key: Annotated[str | None, Security(key_header)]):
    expected = request.app.state.api_key
    if not expected:
        raise APIError(503, "escritura_no_configurada", "Falta configurar la clave de escritura de la API")
    if key is None or not compare_digest(key.encode(), expected.encode()):
        raise APIError(401, "clave_invalida", "Clave de API ausente o inválida")


def validate_range(start: date | None, end: date | None):
    if start and end and start > end:
        raise APIError(422, "rango_invalido", "desde debe ser anterior o igual a hasta")


def cached_read(request: Request, response: Response, session, build):
    """Check the database even on hits; new publications invalidate keys."""
    # Every load, inference, publication or activation creates a row in ejecucion.
    revision = tuple(session.execute(select(func.max(Run.id_ejecucion), func.max(Run.fin))).one())
    key = (str(request.url), revision)
    cache = request.app.state.cache
    directives = {p.strip().lower() for p in request.headers.get("Cache-Control", "").split(",")}
    if "no-cache" in directives or "no-store" in directives:
        response.headers["X-Cache"] = "BYPASS"
        return build()
    value = cache.get(key)
    response.headers["X-Cache"] = "HIT" if value is not None else "MISS"
    if value is None:
        value = build()
        cache.save(key, value)
    return value
