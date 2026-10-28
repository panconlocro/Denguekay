"""Fixtures reales y migración de una BD temporal para las pruebas del backend."""

from contextlib import contextmanager
import hashlib
import os

from alembic import command
from alembic.config import Config
from sqlalchemy.engine import make_url
import pandas as pd

from src.db.sesion import crear_motor
from src.processing.epi_sala import load_ubigeo_catalog
from src.utils.paths import ALEMBIC_CONFIG, BACKEND_FIXTURES, DISTRITOS_COORDS, UBIGEO_CATALOG


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


def url_pg_pruebas():
    """URL de la BD PostgreSQL desechable, o None si no está configurada.

    Se exige que el nombre de la base contenga «prueba» para no tocar nunca la
    BD local de la aplicación. La URL no se imprime.
    """
    valor = os.environ.get("DENGUEKAY_PG_PRUEBAS_URL", "").strip()
    if not valor:
        return None
    url = make_url(valor)
    if url.drivername in {"postgres", "postgresql"}:
        url = url.set(drivername="postgresql+psycopg")
    if url.get_backend_name() != "postgresql" or "prueba" not in (url.database or ""):
        raise ValueError("DENGUEKAY_PG_PRUEBAS_URL debe apuntar a una BD PostgreSQL de pruebas")
    return url


def motor_temporal(carpeta):
    """SQLite aislado, con claves foráneas activas."""
    from sqlalchemy.engine import URL

    motor = crear_motor(URL.create("sqlite", database=str(carpeta / "pruebas.db")))
    migrar(motor)
    return motor


def leer_csv(nombre):
    datos = pd.read_csv(BACKEND_FIXTURES / nombre, dtype={"ubigeo": "string"})
    for c in ("semana_inicio", "origen_inicio", "origen_cierre"):
        if c in datos:
            datos[c] = pd.to_datetime(datos[c])
    return datos


def leer_muestra():
    """Filas reales de 3 distritos: silver (casos y clima), cobertura, gold (etiqueta) y Sala."""
    gold = pd.concat([leer_csv("gold_h2_muestra.csv"), leer_csv("gold_temporal_h2_muestra.csv")])
    gold = gold.drop_duplicates(["ubigeo", "anio", "semana"]).reset_index(drop=True)
    return {"silver": leer_csv("silver_muestra.csv"), "cobertura": leer_csv("cobertura_muestra.csv"),
            "gold": gold, "sala": leer_csv("sala_muestra.csv")}


def datos_muestra(carpeta, seleccion_experimental=None):
    """Ejecuta GX sobre gold real y prepara el lote de carga OE2 desde las fixtures."""
    # Importación diferida: evita cargar GX al importar este módulo.
    from src.processing.epi_sala import load_ubigeo_catalog
    from src.serving.cargar_datos import preparar_desde_tablas
    from src.validation.calidad_gx import obtener_contexto, validar_dataframe
    from src.validation.expectations_gold import expectativas_gold

    muestra = leer_muestra()
    calidad = validar_dataframe(
        muestra["gold"], nombre_suite="backend_gold_h2", nombre_activo="backend_gold_h2",
        expectativas=expectativas_gold(2, sorted(muestra["gold"].ubigeo.unique())),
        contexto=obtener_contexto(carpeta / "gx"), actualizar_docs=False)
    archivos = [BACKEND_FIXTURES / n for n in ("silver_muestra.csv", "cobertura_muestra.csv", "gold_h2_muestra.csv",
                                             "gold_temporal_h2_muestra.csv", "sala_muestra.csv")]
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in archivos + [UBIGEO_CATALOG, DISTRITOS_COORDS]}
    return preparar_desde_tablas(load_ubigeo_catalog(UBIGEO_CATALOG), pd.read_csv(DISTRITOS_COORDS),
                                 muestra["silver"], muestra["cobertura"], muestra["gold"], muestra["sala"],
                                 hashes, {"exito": calidad["exito"], "suites": [calidad]}, seleccion_experimental)
