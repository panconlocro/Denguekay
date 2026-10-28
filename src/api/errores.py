"""Errores públicos homogéneos, sin SQL ni secretos de conexión."""

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException


class ErrorAPI(Exception):
    def __init__(self, estado, codigo, mensaje, detalle=None):
        self.estado, self.codigo = estado, codigo
        self.mensaje, self.detalle = mensaje, detalle


def respuesta_error(estado, codigo, mensaje, detalle=None):
    return JSONResponse(status_code=estado, content={
        "codigo": codigo, "mensaje": mensaje, "detalle": detalle})


def registrar_errores(app):
    """Evita revelar credenciales, entradas sensibles o consultas internas."""
    @app.exception_handler(ErrorAPI)
    async def error_controlado(request: Request, error: ErrorAPI):
        return respuesta_error(error.estado, error.codigo, error.mensaje, error.detalle)

    @app.exception_handler(RequestValidationError)
    async def parametro_invalido(request: Request, error: RequestValidationError):
        campos = [{"campo": ".".join(map(str, e["loc"])), "tipo": e["type"]}
                  for e in error.errors()]
        return respuesta_error(422, "parametro_invalido", "Parámetro inválido; revisa el contrato de la API", campos)

    @app.exception_handler(SQLAlchemyError)
    async def base_no_disponible(request: Request, error: SQLAlchemyError):
        return respuesta_error(503, "bd_no_disponible", "La base de datos no está disponible")

    @app.exception_handler(HTTPException)
    async def ruta_invalida(request: Request, error: HTTPException):
        return respuesta_error(error.status_code, "solicitud_invalida",
                               "Ruta o método no disponible")

    @app.exception_handler(Exception)
    async def error_interno(request: Request, error: Exception):
        return respuesta_error(500, "error_interno", "No se pudo completar la solicitud")
