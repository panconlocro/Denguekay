"""Uniform public errors, without SQL or connection secrets."""

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException

from denguekay.serving.parameters import MissingParameter


class APIError(Exception):
    def __init__(self, estado, codigo, mensaje, detalle=None):
        self.estado, self.codigo = estado, codigo
        self.mensaje, self.detalle = mensaje, detalle


def error_response(estado, codigo, mensaje, detalle=None):
    return JSONResponse(status_code=estado, content={
        "codigo": codigo, "mensaje": mensaje, "detalle": detalle})


def register_error_handlers(app):
    """Avoid revealing credentials, sensitive inputs or internal queries."""
    @app.exception_handler(APIError)
    async def handled_error(request: Request, error: APIError):
        return error_response(error.estado, error.codigo, error.mensaje, error.detalle)

    @app.exception_handler(RequestValidationError)
    async def invalid_parameter(request: Request, error: RequestValidationError):
        fields = [{"campo": ".".join(map(str, e["loc"])), "tipo": e["type"]}
                  for e in error.errors()]
        return error_response(422, "parametro_invalido", "Parámetro inválido; revisa el contrato de la API", fields)

    @app.exception_handler(SQLAlchemyError)
    async def database_unavailable(request: Request, error: SQLAlchemyError):
        return error_response(503, "bd_no_disponible", "La base de datos no está disponible")

    @app.exception_handler(MissingParameter)
    async def missing_parameter(request: Request, error: MissingParameter):
        return error_response(503, "parametros_no_configurados", str(error))

    @app.exception_handler(HTTPException)
    async def invalid_route(request: Request, error: HTTPException):
        return error_response(error.status_code, "solicitud_invalida",
                               "Ruta o método no disponible")

    @app.exception_handler(Exception)
    async def internal_error(request: Request, error: Exception):
        return error_response(500, "error_interno", "No se pudo completar la solicitud")
