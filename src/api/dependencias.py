"""Sesiones por solicitud, autenticación de escritura y control de rangos."""

from datetime import date
from secrets import compare_digest
from typing import Annotated

from fastapi import Depends, Path, Query, Request, Response, Security
from fastapi.security import APIKeyHeader
from pydantic import Field, StringConstraints
from sqlalchemy import func, select

from src.api.errores import ErrorAPI
from src.db.modelos import ActivacionModelo, CargaDatos, EjecucionPrediccion

Ubigeo = Annotated[str, StringConstraints(pattern=r"^[0-9]{6}$"),
                   Field(description="Código distrital de seis dígitos, conservado como texto")]
Identificador = Annotated[int, Path(ge=1, description="Identificador positivo del registro guardado en la BD")]
Horizonte = Annotated[int, Query(ge=2, le=4, description="Anticipación en semanas: 2 o 4 con modelos; 3 requiere una versión disponible")]
PaginaNumero = Annotated[int, Query(ge=1, description="Página, comenzando en uno")]
TamanoPagina = Annotated[int, Query(ge=1, le=100, description="Cantidad máxima de elementos por página")]
clave_header = APIKeyHeader(name="X-API-Key", auto_error=False,
    description="Clave de escritura definida en API_KEY; las lecturas son públicas")


def obtener_sesion(request: Request):
    fabrica = request.app.state.fabrica_sesiones
    if fabrica is None:
        raise ErrorAPI(503, "bd_no_disponible", "La base de datos no está configurada o no está disponible")
    with fabrica() as sesion:
        yield sesion


Sesion = Annotated[object, Depends(obtener_sesion)]


def exigir_clave(request: Request, clave: Annotated[str | None, Security(clave_header)]):
    esperada = request.app.state.clave_api
    if not esperada:
        raise ErrorAPI(503, "escritura_no_configurada", "Falta configurar la clave de escritura de la API")
    if clave is None or not compare_digest(clave.encode(), esperada.encode()):
        raise ErrorAPI(401, "clave_invalida", "Clave de API ausente o inválida")


def validar_rango(desde: date | None, hasta: date | None):
    if desde and hasta and desde > hasta:
        raise ErrorAPI(422, "rango_invalido", "desde debe ser anterior o igual a hasta")


def validar_semana(semana: date | None):
    if semana and semana.weekday() != 6:
        raise ErrorAPI(422, "semana_invalida", "semana debe ser la fecha de inicio en domingo, con formato AAAA-MM-DD")


def lectura(request: Request, response: Response, sesion, construir):
    """Verifica la BD incluso en aciertos; nuevas publicaciones invalidan claves."""
    revision = tuple(sesion.execute(select(
        select(func.max(CargaDatos.id)).scalar_subquery(),
        select(func.max(EjecucionPrediccion.id)).where(EjecucionPrediccion.estado == "completada").scalar_subquery(),
        select(func.max(ActivacionModelo.id)).scalar_subquery())).one())
    clave = (str(request.url), revision)
    cache = request.app.state.cache
    directivas = {p.strip().lower() for p in request.headers.get("Cache-Control", "").split(",")}
    if "no-cache" in directivas or "no-store" in directivas:
        response.headers["X-Cache"] = "BYPASS"
        return construir()
    valor = cache.obtener(clave)
    response.headers["X-Cache"] = "HIT" if valor is not None else "MISS"
    if valor is None:
        valor = construir()
        cache.guardar(clave, valor)
    return valor
