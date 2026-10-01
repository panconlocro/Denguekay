"""Validación de calidad de datos con Great Expectations (GX Core 1.x).

Las suites se definen en código (``expectations_gold.py`` y
``expectations_integrado.py``) y este módulo las ejecuta sobre los CSV del
proyecto. El contexto de GX vive en ``great_expectations/gx/``: ahí quedan las
suites, los resultados de cada validación y los Data Docs (HTML) en
``great_expectations/gx/uncommitted/data_docs/local_site/index.html``.

Estas suites **no reemplazan** las comprobaciones estrictas que ya existen
(``preparar_gold``, ``auditar_traspaso``, ``validate_complete``): las
complementan con un reporte declarativo, legible y auditable que además se
adjunta a cada corrida de MLflow. Solo leen ``data/``; nunca escriben en ella.

Uso desde la raíz del repo::

    python -m src.validation.calidad_gx            # silver integrado + gold h2/h4
    python -m src.validation.calidad_gx --sin-gold # solo silver integrado
"""

import argparse
import copy
import json
import logging
import sys
from pathlib import Path

import great_expectations as gx
import pandas as pd

from src.modeling.features import HORIZONTES
from src.processing.epi_sala import load_ubigeo_catalog
from src.utils.paths import GOLD, GX_DIR, SILVER_INTEGRADO, UBIGEO_CATALOG
from src.validation.expectations_gold import expectativas_gold
from src.validation.expectations_integrado import expectativas_integrado_gx

FUENTE_GX = "denguekay_pandas"
LOTE_COMPLETO = "dataframe_completo"
COLUMNAS_FECHA_GOLD = ["semana_inicio", "origen_inicio", "origen_cierre"]


class ValidacionDatosError(ValueError):
    """Una suite de GX falló; ``resumen`` conserva el detalle por expectativa."""

    def __init__(self, mensaje: str, resumen: dict):
        super().__init__(mensaje)
        self.resumen = resumen


def obtener_contexto(directorio: Path = GX_DIR):
    """Abre (o crea) el contexto de archivos de GX y silencia sus barras de progreso."""
    directorio = Path(directorio)
    directorio.mkdir(parents=True, exist_ok=True)
    logging.getLogger("great_expectations").setLevel(logging.WARNING)
    contexto = gx.get_context(mode="file", project_root_dir=directorio)
    try:
        from great_expectations.data_context.types.base import ProgressBarsConfig

        barras = contexto.variables.progress_bars
        if barras is None or barras.globally is not False:
            contexto.variables.progress_bars = ProgressBarsConfig(globally=False)
            contexto.variables.save()
    except Exception:  # pragma: no cover - solo cosmético
        pass
    return contexto


def ruta_data_docs(contexto) -> Path:
    """Devuelve el índice HTML local de los Data Docs."""
    return Path(contexto.root_directory) / "uncommitted" / "data_docs" / "local_site" / "index.html"


def _definicion_lote(contexto, nombre_activo: str):
    """Obtiene o crea fuente pandas, activo y lote 'dataframe completo'."""
    try:
        fuente = contexto.data_sources.get(FUENTE_GX)
    except (KeyError, ValueError, LookupError):
        fuente = contexto.data_sources.add_pandas(name=FUENTE_GX)
    try:
        activo = fuente.get_asset(nombre_activo)
    except LookupError:
        activo = fuente.add_dataframe_asset(name=nombre_activo)
    try:
        return activo.get_batch_definition(LOTE_COMPLETO)
    except (KeyError, ValueError, LookupError):
        return activo.add_batch_definition_whole_dataframe(LOTE_COMPLETO)


def _resumir(resultado, *, nombre_suite: str, nombre_activo: str, filas: int, docs: Path) -> dict:
    """Convierte el resultado del checkpoint en un dict serializable."""
    validaciones = list(resultado.run_results.values())
    if len(validaciones) != 1:
        raise RuntimeError("Se esperaba una sola validación por checkpoint")
    validacion = validaciones[0]
    estadisticas = validacion.statistics
    fallidas = []
    for item in validacion.results:
        if item.success:
            continue
        config = item.expectation_config
        kwargs = {k: v for k, v in config.kwargs.items() if k in {"column", "column_list", "column_A", "column_B"}}
        detalle = item.result or {}
        fallidas.append({
            "expectativa": config.type,
            **kwargs,
            "inesperados": detalle.get("unexpected_count"),
            "porcentaje_inesperado": detalle.get("unexpected_percent"),
            "muestra": [str(x) for x in (detalle.get("partial_unexpected_list") or [])[:10]],
            "valor_observado": None if "observed_value" not in detalle else str(detalle["observed_value"])[:500],
            "excepcion": (item.exception_info or {}).get("exception_message") if item.exception_info else None,
        })
    return {
        "suite": nombre_suite,
        "activo": nombre_activo,
        "filas": int(filas),
        "exito": bool(validacion.success),
        "evaluadas": int(estadisticas["evaluated_expectations"]),
        "exitosas": int(estadisticas["successful_expectations"]),
        "fallidas_n": int(estadisticas["unsuccessful_expectations"]),
        "porcentaje_exito": float(estadisticas["success_percent"] or 0.0),
        "fallidas": fallidas,
        "data_docs": str(docs),
    }


def validar_dataframe(
    datos: pd.DataFrame, *, nombre_suite: str, expectativas: list,
    nombre_activo: str, contexto=None, lanzar: bool = True,
    actualizar_docs: bool = True,
) -> dict:
    """Registra la suite (el código es la fuente de verdad) y valida ``datos``.

    Si ``lanzar`` es verdadero y alguna expectativa falla, levanta
    ``ValidacionDatosError`` con el resumen completo.
    """
    contexto = contexto or obtener_contexto()
    suite = contexto.suites.add_or_update(
        gx.ExpectationSuite(name=nombre_suite, expectations=[copy.copy(e) for e in expectativas]))
    definicion = contexto.validation_definitions.add_or_update(
        gx.ValidationDefinition(name=nombre_suite, data=_definicion_lote(contexto, nombre_activo), suite=suite))
    acciones = [gx.checkpoint.UpdateDataDocsAction(name="actualizar_data_docs")] if actualizar_docs else []
    checkpoint = contexto.checkpoints.add_or_update(gx.Checkpoint(
        name=f"checkpoint_{nombre_suite}", validation_definitions=[definicion],
        actions=acciones, result_format={"result_format": "SUMMARY"}))
    resultado = checkpoint.run(batch_parameters={"dataframe": datos})
    resumen = _resumir(resultado, nombre_suite=nombre_suite, nombre_activo=nombre_activo,
                       filas=len(datos), docs=ruta_data_docs(contexto))
    if lanzar and not resumen["exito"]:
        detalle = "; ".join(
            f"{f['expectativa']}({f.get('column') or f.get('column_list') or ''}): {f['inesperados']}"
            for f in resumen["fallidas"][:8])
        raise ValidacionDatosError(
            f"La suite GX '{nombre_suite}' falló {resumen['fallidas_n']} de "
            f"{resumen['evaluadas']} expectativas: {detalle}. Ver {resumen['data_docs']}", resumen)
    return resumen


def ubigeos_catalogo(catalog_path: Path = UBIGEO_CATALOG) -> list[str]:
    """Lista de UBIGEO de seis dígitos del catálogo versionado de Piura."""
    return sorted(load_ubigeo_catalog(Path(catalog_path))["ubigeo"].astype(str))


def leer_gold(gold_dir: Path, horizonte: int, stem: str = SILVER_INTEGRADO.stem) -> tuple[pd.DataFrame, Path]:
    """Lee gold igual que los módulos de entrenamiento (ubigeo como texto)."""
    archivo = Path(gold_dir) / f"{stem}_h{horizonte}_gold.csv"
    gold = pd.read_csv(archivo, dtype={"ubigeo": "string"}, parse_dates=COLUMNAS_FECHA_GOLD)
    return gold, archivo


def validar_gold_gx(
    gold_dir: Path = GOLD, *, horizontes=HORIZONTES, contexto=None,
    catalog_path: Path = UBIGEO_CATALOG, lanzar: bool = True,
) -> dict[str, dict]:
    """Valida cada gold por horizonte con su suite ``gold_h{h}``."""
    contexto = contexto or obtener_contexto()
    ubigeos = ubigeos_catalogo(catalog_path)
    salida = {}
    for h in horizontes:
        gold, archivo = leer_gold(gold_dir, h)
        resumen = validar_dataframe(
            gold, nombre_suite=f"gold_h{h}", expectativas=expectativas_gold(h, ubigeos),
            nombre_activo=f"gold_h{h}", contexto=contexto, lanzar=lanzar)
        resumen["archivo"] = archivo.name
        salida[f"gold_h{h}"] = resumen
    return salida


def validar_integrado_gx(
    silver_path: Path = SILVER_INTEGRADO, *, contexto=None,
    catalog_path: Path = UBIGEO_CATALOG, lanzar: bool = True,
) -> dict:
    """Valida el panel silver integrado (sin features) con su suite."""
    contexto = contexto or obtener_contexto()
    silver_path = Path(silver_path)
    datos = pd.read_csv(silver_path, dtype={"ubigeo": "string"}, parse_dates=["semana_inicio"])
    resumen = validar_dataframe(
        datos, nombre_suite="silver_integrado",
        expectativas=expectativas_integrado_gx(ubigeos_catalogo(catalog_path)),
        nombre_activo="silver_integrado", contexto=contexto, lanzar=lanzar)
    resumen["archivo"] = silver_path.name
    return resumen


def validar_entradas_modelado(
    *, gold_dir: Path = GOLD, silver_path: Path | None = None,
    directorio_gx: Path = GX_DIR, lanzar: bool = True,
) -> dict:
    """Valida las entradas de un experimento antes de entrenar.

    Siempre valida gold h2 y h4; también silver integrado cuando el
    experimento lo lee (``silver_path``). Devuelve un resumen apto para
    adjuntarse a MLflow.
    """
    contexto = obtener_contexto(directorio_gx)
    suites = {}
    if silver_path is not None:
        suites["silver_integrado"] = validar_integrado_gx(silver_path, contexto=contexto, lanzar=lanzar)
    suites.update(validar_gold_gx(gold_dir, contexto=contexto, lanzar=lanzar))
    return {
        "herramienta": f"great_expectations {gx.__version__}",
        "exito": all(s["exito"] for s in suites.values()),
        "suites": suites,
        "data_docs": str(ruta_data_docs(contexto)),
    }


def main() -> None:
    """CLI: ``python -m src.validation.calidad_gx``. Sale con código 1 si algo falla."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--silver", type=Path, default=SILVER_INTEGRADO)
    parser.add_argument("--gold-dir", type=Path, default=GOLD)
    parser.add_argument("--sin-gold", action="store_true", help="Valida solo silver integrado")
    parser.add_argument("--json", type=Path, default=None, help="Ruta opcional para guardar el resumen")
    args = parser.parse_args()
    contexto = obtener_contexto()
    suites = {"silver_integrado": validar_integrado_gx(args.silver, contexto=contexto, lanzar=False)}
    if not args.sin_gold:
        suites.update(validar_gold_gx(args.gold_dir, contexto=contexto, lanzar=False))
    for nombre, r in suites.items():
        estado = "OK   " if r["exito"] else "FALLA"
        print(f"[{estado}] {nombre}: {r['exitosas']}/{r['evaluadas']} expectativas ({r['filas']} filas)")
        for f in r["fallidas"]:
            print(f"         - {f['expectativa']} {f.get('column') or f.get('column_list') or ''}: "
                  f"{f['inesperados']} inesperados, muestra={f['muestra'][:5]}")
    print(f"Data Docs: {ruta_data_docs(contexto)}")
    if args.json:
        args.json.write_text(json.dumps(suites, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    sys.exit(0 if all(r["exito"] for r in suites.values()) else 1)


if __name__ == "__main__":
    main()
