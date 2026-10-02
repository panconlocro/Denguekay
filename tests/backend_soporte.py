"""Fixtures reales y migración de una BD temporal para las pruebas del backend."""

from contextlib import contextmanager
import hashlib
import os

from alembic import command
from alembic.config import Config
import pandas as pd

from src.db.sesion import crear_motor
from src.processing.epi_sala import load_ubigeo_catalog
from src.serving.cargar_datos import DatosCarga, preparar_distritos, preparar_observaciones
from src.utils.paths import ALEMBIC_CONFIG, BACKEND_FIXTURES, DISTRITOS_COORDS, UBIGEO_CATALOG
from src.validation.calidad_gx import obtener_contexto, validar_dataframe
from src.validation.expectations_gold import expectativas_gold


@contextmanager
def entorno_bd(valor):
    """Restituye la configuración original, incluso si una prueba falla."""
    anterior = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = valor
    try:
        yield
    finally:
        if anterior is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = anterior


def migrar(motor, destino="head"):
    """Usa la misma revisión Alembic que producción; no crea tablas a mano."""
    config = Config(str(ALEMBIC_CONFIG))
    config.attributes["motor"] = motor
    if destino == "base":
        command.downgrade(config, destino)
    else:
        command.upgrade(config, destino)


def motor_temporal(carpeta):
    """SQLite aislado, con claves foráneas activas."""
    from sqlalchemy.engine import URL

    motor = crear_motor(URL.create("sqlite", database=str(carpeta / "pruebas.db")))
    migrar(motor)
    return motor


def leer_muestra():
    """Doce filas extraídas de gold real y seis filas de su fuente Sala."""
    gold = pd.read_csv(BACKEND_FIXTURES / "gold_h2_muestra.csv", dtype={"ubigeo": "string"},
                       parse_dates=["semana_inicio", "origen_inicio", "origen_cierre"])
    sala = pd.read_csv(BACKEND_FIXTURES / "sala_muestra.csv", dtype={"ubigeo": "string"})
    return gold, sala


def datos_muestra(carpeta):
    """Ejecuta GX sobre datos reales; devuelve evidencia y registros para cargar."""
    gold, sala = leer_muestra()
    calidad = validar_dataframe(
        gold, nombre_suite="backend_gold_h2", nombre_activo="backend_gold_h2",
        expectativas=expectativas_gold(2, sorted(gold.ubigeo.unique())),
        contexto=obtener_contexto(carpeta / "gx"), actualizar_docs=False)
    distritos = preparar_distritos(load_ubigeo_catalog(UBIGEO_CATALOG), pd.read_csv(DISTRITOS_COORDS))
    observaciones, corte = preparar_observaciones(gold, sala)
    archivos = [BACKEND_FIXTURES / "gold_h2_muestra.csv", BACKEND_FIXTURES / "sala_muestra.csv",
                UBIGEO_CATALOG, DISTRITOS_COORDS]
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in archivos}
    return DatosCarga(distritos, observaciones, hashes, {"exito": calidad["exito"], "suites": [calidad]}, corte)
