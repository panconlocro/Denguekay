"""Registro de los experimentos XGBoost en MLflow.

Todos los módulos de experimentación (``train``, ``ablacion_*`` y
``validacion_temporal_compacta``) producen un reporte con la misma forma::

    reporte["horizontes"][h]["variantes"][variante] -> folds evaluados

Este módulo recorre ese reporte **después** de que el experimento terminó y
lo registra sin alterar el protocolo estadístico ni los archivos versionados:

- un **experimento MLflow** por módulo (``denguekay/ablacion_clima``, …);
- un **run padre** por ejecución, con parámetros de XGBoost, linaje (hashes
  de gold/silver/manifiesto, commit de Git), versiones de librerías,
  resultado de Great Expectations y los archivos de salida;
- un **run hijo** por horizonte × variante, con métricas por bloque
  (``temporada_2024.cls_f1``) y la media de validación (``validacion_media.cls_f1``);
- un **run nieto** por fold (horizonte × variante × bloque), con todas las
  métricas del fold y los modelos XGBoost de ese fold cuando se guardaron.

Prefijos de métricas: ``reg_`` = regresión de casos + regla de alerta,
``cls_`` = clasificación directa de ``brote``, ``pers_`` = persistencia,
``cal_`` = calibración progresiva del umbral.

Por defecto el almacén es local: ``mlflow.db`` (SQLite) y ``mlartifacts/`` en
la raíz del repo. Para usar otro servidor basta definir ``MLFLOW_TRACKING_URI``.
Ver la interfaz con::

    mlflow ui --backend-store-uri sqlite:///mlflow.db --workers 1
"""

import json
import os
import platform
import subprocess
from pathlib import Path

import numpy as np

from src.utils.paths import MLFLOW_ARTEFACTOS, MLFLOW_DB, ROOT

# MLflow 3 imprime sugerencias para agentes de IA al importarse; no aportan aquí.
os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")

PREFIJO_EXPERIMENTO = "denguekay"
SECCIONES = {"regresion": "reg", "clasificacion": "cls", "persistencia": "pers"}
TIPOS_VALIDACION = {"validacion", "seleccion"}
CLAVES_FOLD = {"horizonte", "variante", "bloque", "regresion", "clasificacion"}
LARGO_MAXIMO_PARAM = 6000


# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------

def uri_seguimiento() -> str:
    """URI del tracking store: ``MLFLOW_TRACKING_URI`` o SQLite local en el repo."""
    return os.environ.get("MLFLOW_TRACKING_URI") or f"sqlite:///{MLFLOW_DB.as_posix()}"


def configurar_experimento(nombre: str, tracking_uri: str | None = None) -> str:
    """Fija el tracking URI y devuelve el id del experimento (lo crea si falta).

    Con el almacén local, los artefactos van a ``mlartifacts/<experimento>``
    con ruta absoluta, para que un notebook (cwd ``notebooks/``) y la CLI
    (cwd raíz) escriban en el mismo lugar.
    """
    import mlflow

    uri = tracking_uri or uri_seguimiento()
    mlflow.set_tracking_uri(uri)
    existente = mlflow.get_experiment_by_name(nombre)
    if existente is not None:
        return existente.experiment_id
    ubicacion = None
    if uri.startswith("sqlite:///"):
        base = Path(uri[len("sqlite:///"):]).resolve()
        raiz = MLFLOW_ARTEFACTOS if base == MLFLOW_DB.resolve() else base.parent / "mlartifacts"
        ubicacion = (raiz / nombre.replace("/", "_")).as_uri()
    return mlflow.create_experiment(nombre, artifact_location=ubicacion)


# ---------------------------------------------------------------------------
# Aplanado de reportes (funciones puras, testeables sin MLflow)
# ---------------------------------------------------------------------------

def _es_fold(objeto) -> bool:
    return isinstance(objeto, dict) and CLAVES_FOLD <= set(objeto)


def _numero(valor) -> float | None:
    """Convierte a float si es un número finito; ``None`` en otro caso."""
    if isinstance(valor, bool):
        return float(valor)
    if isinstance(valor, (int, float, np.integer, np.floating)):
        valor = float(valor)
        return valor if np.isfinite(valor) else None
    return None


def _hojas(objeto, prefijo: str = "") -> dict:
    """Aplana un dict anidado usando solo el nombre de la hoja con un prefijo."""
    salida = {}
    for clave, valor in objeto.items():
        if isinstance(valor, dict):
            salida.update(_hojas(valor, prefijo))
        else:
            salida[f"{prefijo}{clave}"] = valor
    return salida


def metricas_fold(fold: dict) -> tuple[dict[str, float], dict[str, str]]:
    """Separa un fold en métricas numéricas y parámetros descriptivos.

    ``regresion.conteos.mae`` → ``reg_mae``; ``clasificacion.alerta_directa.f1``
    → ``cls_f1``; ``calibracion.seleccion_umbral.umbral`` → ``cal_umbral``.
    """
    metricas, params = {}, {}
    for seccion, prefijo in SECCIONES.items():
        for clave, valor in _hojas(fold.get(seccion) or {}, f"{prefijo}_").items():
            numero = _numero(valor)
            if numero is not None:
                metricas[clave] = numero
    for clave, valor in _hojas(fold.get("calibracion") or {}, "cal_").items():
        numero = _numero(valor)
        if numero is not None:
            metricas[clave] = numero
        elif valor is not None:
            params[clave] = str(valor)
    for clave, valor in fold.items():
        if clave in SECCIONES or clave == "calibracion" or isinstance(valor, (dict, list)):
            continue
        if valor is not None:
            params[clave] = str(valor)
    return metricas, params


def folds_de_variante(resultado: dict) -> list[dict]:
    """Encuentra los folds de una variante sin importar cómo los nombró el módulo."""
    folds = []
    for valor in resultado.values():
        if _es_fold(valor):
            folds.append(valor)
        elif isinstance(valor, list):
            folds.extend(x for x in valor if _es_fold(x))
    return folds


def resumen_variante(folds: list[dict]) -> dict[str, float]:
    """Métricas por bloque y media de validación (nunca promedia pruebas)."""
    metricas = {}
    por_tipo_validacion = []
    for fold in folds:
        valores, _ = metricas_fold(fold)
        metricas.update({f"{fold['bloque']}.{k}": v for k, v in valores.items()})
        if fold.get("tipo") in TIPOS_VALIDACION:
            por_tipo_validacion.append(valores)
    if por_tipo_validacion:
        claves = set().union(*por_tipo_validacion)
        for clave in sorted(claves):
            valores = [m[clave] for m in por_tipo_validacion if clave in m]
            if len(valores) == len(por_tipo_validacion):
                metricas[f"validacion_media.{clave}"] = float(np.mean(valores))
        metricas["validacion_media.n_bloques"] = float(len(por_tipo_validacion))
    return metricas


def seleccionadas_por_horizonte(bloque_h: dict) -> dict[str, list[str]]:
    """Variante → enfoques en que fue elegida (``elegidas_solo_validacion`` y similares).

    Reconoce ``{"regresion": variante, "clasificacion": variante}`` y la forma
    por familia ``{"fija": {"regresion": ...}}``; en ese caso la etiqueta es
    ``fija:regresion``. Ganadoras por temporada (un nivel más) no cuentan.
    """
    variantes = set(bloque_h.get("variantes", {}))
    elegidas: dict[str, list[str]] = {}

    def es_seleccion(valor) -> bool:
        return (isinstance(valor, dict) and bool(valor) and set(valor) <= set(SECCIONES)
                and all(isinstance(v, str) and v in variantes for v in valor.values()))

    def anotar(seleccion: dict, prefijo: str = "") -> None:
        for enfoque, variante in seleccion.items():
            etiqueta = f"{prefijo}{enfoque}"
            elegidas.setdefault(variante, [])
            if etiqueta not in elegidas[variante]:
                elegidas[variante].append(etiqueta)

    for clave, valor in bloque_h.items():
        if clave == "variantes" or not isinstance(valor, dict):
            continue
        if es_seleccion(valor):
            anotar(valor)
        else:
            for familia, sub in valor.items():
                if es_seleccion(sub):
                    anotar(sub, f"{familia}:")
    return elegidas


def _texto_param(valor) -> str:
    texto = valor if isinstance(valor, str) else json.dumps(valor, ensure_ascii=False, default=str)
    return texto[:LARGO_MAXIMO_PARAM]


def parametros_variante(resultado: dict) -> tuple[dict[str, str], dict[str, float]]:
    """Columnas, selección de umbral y otros datos no-fold de una variante."""
    params, metricas = {}, {}
    for clave, valor in resultado.items():
        if _es_fold(valor) or (isinstance(valor, list) and any(_es_fold(x) for x in valor)):
            continue
        if clave == "columnas":
            params["columnas"] = _texto_param(valor)
            params["n_columnas"] = str(len(valor))
        elif isinstance(valor, dict):
            for hoja, dato in _hojas(valor, f"{clave}.").items():
                numero = _numero(dato)
                if numero is not None:
                    metricas[hoja] = numero
                elif dato is not None:
                    params[hoja] = _texto_param(dato)
        elif valor is not None:
            numero = _numero(valor)
            if numero is not None:
                metricas[clave] = numero
            else:
                params[clave] = _texto_param(valor)
    return params, metricas


# ---------------------------------------------------------------------------
# Contexto de ejecución
# ---------------------------------------------------------------------------

def _git(*args: str) -> str | None:
    try:
        salida = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return salida.stdout.strip() if salida.returncode == 0 else None


def etiquetas_entorno() -> dict[str, str]:
    """Commit de Git, plataforma y versiones que afectan la reproducibilidad."""
    import importlib.metadata as md

    etiquetas = {
        "plataforma": f"{platform.system()} {platform.release()} {platform.machine()}",
        "python": platform.python_version(),
    }
    for paquete in ("xgboost", "scikit-learn", "pandas", "numpy", "great_expectations", "mlflow"):
        try:
            etiquetas[f"version.{paquete}"] = md.version(paquete)
        except md.PackageNotFoundError:
            pass
    commit = _git("rev-parse", "HEAD")
    if commit:
        etiquetas["mlflow.source.git.commit"] = commit
        estado = _git("status", "--porcelain")
        etiquetas["git_cambios_sin_commit"] = "si" if estado else "no"
    return etiquetas


def _modelos_del_fold(salida_dir: Path, horizonte, variante: str, bloque: str) -> list[Path]:
    """Archivos ``xgb_h{h}_{variante}_{enfoque}_{bloque}.json`` guardados por el módulo."""
    return [p for enfoque in ("regresion", "clasificacion")
            if (p := salida_dir / f"xgb_h{horizonte}_{variante}_{enfoque}_{bloque}.json").exists()]


# ---------------------------------------------------------------------------
# Registro
# ---------------------------------------------------------------------------

def registrar_reporte(
    experimento: str, reporte: dict, *, metricas_path: Path, salida_dir: Path,
    gold_dir: Path | None = None, calidad_datos: dict | None = None,
    descripcion: str | None = None, tracking_uri: str | None = None,
    registrar_datasets: bool = True,
) -> str:
    """Registra un reporte ya calculado en MLflow y devuelve el id del run padre."""
    import mlflow

    metricas_path, salida_dir = Path(metricas_path), Path(salida_dir)
    nombre_experimento = f"{PREFIJO_EXPERIMENTO}/{experimento}"
    experiment_id = configurar_experimento(nombre_experimento, tracking_uri)

    params_padre = {}
    etiquetas_padre = {"experimento": experimento, **etiquetas_entorno()}
    for clave, valor in reporte.items():
        if clave in {"horizontes", "parametros"}:
            continue
        if isinstance(valor, str) and clave.startswith("sha256"):
            etiquetas_padre[clave] = valor
        elif not isinstance(valor, dict):
            params_padre[clave] = _texto_param(valor)
    params_padre.update({f"xgb.{k}": _texto_param(v) for k, v in reporte.get("parametros", {}).items()})
    for h, bloque_h in reporte["horizontes"].items():
        for clave, valor in bloque_h.items():
            if clave == "variantes" or isinstance(valor, (dict, list)):
                continue
            if clave.startswith("sha256"):
                etiquetas_padre[f"h{h}.{clave}"] = str(valor)
            else:
                params_padre[f"h{h}.{clave}"] = _texto_param(valor)
    if calidad_datos is not None:
        etiquetas_padre["calidad_datos.exito"] = "si" if calidad_datos.get("exito") else "no"
    if descripcion:
        etiquetas_padre["mlflow.note.content"] = descripcion

    with mlflow.start_run(experiment_id=experiment_id, run_name=f"{experimento}",
                          tags=etiquetas_padre) as padre:
        mlflow.log_params(params_padre)
        if calidad_datos is not None:
            mlflow.log_dict(calidad_datos, "calidad_datos/great_expectations.json")
            for nombre, suite in calidad_datos.get("suites", {}).items():
                mlflow.log_metric(f"gx.{nombre}.porcentaje_exito", suite["porcentaje_exito"])
                mlflow.log_metric(f"gx.{nombre}.fallidas", suite["fallidas_n"])
        if metricas_path.exists():
            mlflow.log_artifact(str(metricas_path), "reporte")
        if gold_dir is not None:
            manifiesto = Path(gold_dir) / "manifest_fase6.json"
            if manifiesto.exists():
                mlflow.log_artifact(str(manifiesto), "linaje")
            if registrar_datasets:
                _registrar_datasets(reporte, Path(gold_dir))
        if salida_dir.exists():
            for archivo in sorted(salida_dir.iterdir()):
                if archivo.is_file() and not archivo.name.startswith("xgb_"):
                    mlflow.log_artifact(str(archivo), "salidas")

        for h, bloque_h in reporte["horizontes"].items():
            elegidas = seleccionadas_por_horizonte(bloque_h)
            for variante, resultado in bloque_h.get("variantes", {}).items():
                folds = folds_de_variante(resultado)
                params_v, metricas_v = parametros_variante(resultado)
                etiquetas_v = {"horizonte": str(h), "variante": variante, "nivel": "variante"}
                if variante in elegidas:
                    etiquetas_v["seleccionada_en_validacion"] = ",".join(elegidas[variante])
                with mlflow.start_run(experiment_id=experiment_id, run_name=f"h{h} · {variante}",
                                      nested=True, tags=etiquetas_v):
                    mlflow.log_params({"horizonte": str(h), "variante": variante, **params_v})
                    mlflow.log_metrics({**metricas_v, **resumen_variante(folds)})
                    for fold in folds:
                        metricas_f, params_f = metricas_fold(fold)
                        etiquetas_f = {"horizonte": str(h), "variante": variante,
                                       "bloque": fold["bloque"], "tipo": str(fold.get("tipo")),
                                       "nivel": "fold"}
                        with mlflow.start_run(experiment_id=experiment_id,
                                              run_name=f"h{h} · {variante} · {fold['bloque']}",
                                              nested=True, tags=etiquetas_f):
                            mlflow.log_params(params_f)
                            mlflow.log_metrics(metricas_f)
                            for modelo in _modelos_del_fold(salida_dir, h, variante, fold["bloque"]):
                                mlflow.log_artifact(str(modelo), "modelos")
        run_id = padre.info.run_id
    print(f"MLflow: run {run_id} en '{nombre_experimento}' ({uri_seguimiento()})")
    return run_id


def _registrar_datasets(reporte: dict, gold_dir: Path) -> None:
    """Asocia cada gold usado al run padre (pestaña *Datasets* de MLflow)."""
    import warnings

    import mlflow
    import pandas as pd

    for h, bloque_h in reporte["horizontes"].items():
        archivo = gold_dir / str(bloque_h.get("archivo_gold", ""))
        if not archivo.is_file():
            continue
        datos = pd.read_csv(archivo, dtype={"ubigeo": "string"})
        with warnings.catch_warnings():
            # Avisos de MLflow sobre inferencia de esquema que no aplican aquí.
            warnings.simplefilter("ignore", UserWarning)
            dataset = mlflow.data.from_pandas(
                datos, source=archivo.resolve().as_uri(), name=archivo.name, targets="brote")
            mlflow.log_input(dataset, context=f"gold_h{h}")


def registrar_o_avisar(experimento: str, reporte: dict, **kwargs) -> str | None:
    """Registra en MLflow; si falla, avisa sin perder las salidas ya escritas.

    El experimento ya guardó su JSON, predicciones y modelos antes de llamar
    aquí, así que un problema de MLflow no invalida la corrida.
    """
    try:
        return registrar_reporte(experimento, reporte, **kwargs)
    except Exception as error:  # noqa: BLE001 - se informa y se continúa
        print(f"AVISO: no se pudo registrar '{experimento}' en MLflow: {error!r}. "
              "Las métricas y modelos se guardaron igual en docs/ y models/.")
        return None
