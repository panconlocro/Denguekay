"""Weekly emissions of the frozen V4: detection, archive, prospective follow-up and the retraining notice.

The weekly update (``denguekay.pipelines.v4_weekly``) emits the forecast of h = 2, 3 and 4 once per cutoff week. This
module holds what that needs from the database and the disk, apart from the orchestration:

- ``already_emitted``: whether a cutoff already has its three inferences of the weekly update;
- ``archive_emission``: the record of one emission (date, inputs, forecasts and origin vectors), written before the
  outcomes are known, as the prospective evaluation of ``research/08_v3_confirmed_cases/congelamiento_b3_v4.md``
  requires;
- ``record_first_emission``: copies the forecasts of an emission into ``emision_prediccion`` (insert-only) unless that
  (district, cutoff, horizon) already has its first emission; a re-emission never modifies it;
- ``prospective_frame`` and ``prospective_scores``: the first emissions that were eligible (their target week was not yet
  published by the Sala when they were emitted) and whose target week is already observed, and their Brier, observed
  outbreaks and MAE (the drift review of ``denguekay.serving.drift`` reads the same frame);
- ``retraining_due``: whether the cutoff reached the close of the next season (a notice, never a training).

It writes nothing to ``data/`` and trains nothing.
"""

from datetime import date, datetime, timezone
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import select

from denguekay.config.paths import SERVING_WEEKLY
from denguekay.db.models import EpiWeek, FirstEmission, Prediction, Run, WeeklyObservation
from denguekay.db.session import upsert
from denguekay.features.long_history import week_grid
from denguekay.serving.inference import package_of, select_versions
from denguekay.serving.inputs import build_inputs
from denguekay.serving.predictors import load_predictor

ORIGIN = "actualizacion_semanal"
HORIZONS = (2, 3, 4)
SEASON_CLOSE_WEEK = 34   # the season runs from epidemiological week 35 to week 34 (``SEASON_START_WEEK`` = 35)
EMISSIONS = SERVING_WEEKLY / "emisiones"
STAMP = "%Y%m%dT%H%M%S%fZ"   # microseconds: two emissions in the same second never share a folder
PREDICTION_COLUMNS = ["ubigeo", "horizonte", "id_semana_objetivo", "probabilidad_brote", "nivel_riesgo",
                      "casos_estimados", "casos_intervalo_inferior", "casos_intervalo_superior", "estado",
                      "motivo_no_disponible"]


def weekly_runs(sesion, cutoff):
    """Successful inferences of the weekly update for a cutoff week, as {horizon: Run} (the newest per horizon)."""
    runs = {}
    for run in sesion.scalars(select(Run).where(Run.tipo == "inferencia", Run.estado == "exitosa",
                                                Run.id_semana_corte == cutoff).order_by(Run.id_ejecucion)):
        detail = run.detalle or {}
        if detail.get("origen") == ORIGIN:   # filtered in Python: it must work on SQLite and PostgreSQL alike
            runs[detail.get("horizonte")] = run
    return runs


def already_emitted(sesion, cutoff):
    """Whether the weekly update already emitted the three horizons of this cutoff week."""
    return set(HORIZONS) <= set(weekly_runs(sesion, cutoff))


# --- archive ----------------------------------------------------------------------

def stamp(moment):
    return moment.astimezone(timezone.utc).strftime(STAMP)


def predictions_frame(sesion, cutoff, run_ids):
    rows = sesion.execute(select(*(getattr(Prediction, column) for column in PREDICTION_COLUMNS)).where(
        Prediction.id_semana_corte == cutoff, Prediction.id_ejecucion.in_(run_ids)).order_by(
        Prediction.horizonte, Prediction.ubigeo)).all()
    return pd.DataFrame(rows, columns=PREDICTION_COLUMNS)


def origin_vectors(sesion, cutoff, *, storage, servir_no_validadas):
    """Origin vectors of the package in use, as ``infer`` builds them (without the districts it cannot predict)."""
    week = sesion.get(EpiWeek, cutoff)
    versions, _ = select_versions(sesion, HORIZONS[0], servir_no_validadas)
    predictor = load_predictor(package_of(versions, storage))
    vectors, _ = predictor.vectors(build_inputs(sesion, week, predictor.required_inputs), week)
    return vectors


def frozen_comparison(hashes, manifest):
    """{file: "coincide" | "difiere"} of every input that the manifest of the frozen Release lists."""
    release = {file["ruta"]: file["sha256"] for item in manifest["paquetes"] for file in item["archivos"]}
    return {path: ("coincide" if digest == release[path] else "difiere")
            for path, digest in sorted(hashes.items()) if path in release}


STORAGE_PREFIX = "reportes/emisiones"
ARCHIVE_FILES = ("emision.json", "predicciones.csv", "vectores.csv")


def upload_archive(storage, folder, base=EMISSIONS):
    """Copy the files of an emission folder to the Storage (bucket ``reportes``) and return their logical paths.

    The path is ``reportes/emisiones/<cutoff>/<stamp>/<file>``, the same ``<cutoff>/<stamp>`` that the folder has
    under ``base``, so the archive of a runner that disappears (GitHub Actions) stays in the Storage."""
    folder = Path(folder)
    relative = folder.relative_to(base).as_posix()
    paths = []
    for name in ARCHIVE_FILES:
        path = f"{STORAGE_PREFIX}/{relative}/{name}"
        storage.save(path, (folder / name).read_bytes())
        paths.append(path)
    return paths


def archive_emission(sesion, *, cutoff, ingestion, results, load, emitted_at, reissue, last_published,
                     provisional, captures, code_fingerprint, package_version, frozen_manifest, servir_no_validadas,
                     storage, base=EMISSIONS):
    """Write ``emision.json``, ``predicciones.csv`` and ``vectores.csv`` of one emission and return their folder.

    It reads the predictions in the caller's transaction, so the file is the record of what that transaction
    commits. ``last_published`` is the last week the Sala has published (provisional ones included) and
    ``provisional`` the weeks of it that the load excluded; both are ``id_semana``."""
    week = sesion.get(EpiWeek, cutoff)
    runs = {result["horizonte"]: result for result in results}
    predictions = predictions_frame(sesion, cutoff, [result["id_ejecucion"] for result in results])
    vectors = origin_vectors(sesion, cutoff, storage=storage, servir_no_validadas=servir_no_validadas)
    first = results[0]
    record = {
        "emitida_utc": emitted_at.astimezone(timezone.utc).isoformat(),
        "id_semana_corte": cutoff,
        "fecha_corte": week.fecha_fin.isoformat(),
        "reemision": bool(reissue),
        "ultima_semana_sala_publicada": last_published,
        "semanas_provisionales_excluidas": sorted(provisional),
        "objetivos": {str(h): {"id_semana_objetivo": runs[h]["id_semana_objetivo"],
                               "publicada_provisional_en_sala": runs[h]["id_semana_objetivo"] <= last_published}
                      for h in sorted(runs)},
        "paquete": {"codigo": first["paquete"], "tipo": "v4_b3_live"},
        "versiones": {str(h): runs[h]["versiones"] for h in sorted(runs)},
        "ejecuciones": {"ingesta": ingestion["id_ejecucion"],
                        "inferencias": {str(h): runs[h]["id_ejecucion"] for h in sorted(runs)}},
        "insumos": load.hashes,
        "panel_congelado": frozen_comparison(load.hashes, frozen_manifest),
        "capturas": captures,
        "huella_codigo": code_fingerprint,
        "version_denguekay": package_version,
        "predicciones": {"filas": len(predictions),
                         "disponibles": {str(h): int((predictions.horizonte.eq(h) & predictions.estado.eq("disponible")).sum())
                                         for h in sorted(runs)}},
    }
    folder = Path(base) / str(cutoff) / stamp(emitted_at)
    folder.mkdir(parents=True, exist_ok=False)
    predictions.to_csv(folder / "predicciones.csv", index=False)
    vectors.rename_axis("ubigeo").reset_index().to_csv(folder / "vectores.csv", index=False)
    (folder / "emision.json").write_text(json.dumps(record, ensure_ascii=False, indent=2, default=str) + "\n",
                                         encoding="utf-8")
    return folder


# --- first emission and prospective follow-up -----------------------------------------

FIRST_EMISSION_KEY = ["ubigeo", "id_semana_corte", "horizonte"]


def record_first_emission(sesion, results, *, last_published, emitted_at):
    """Insert the forecasts of an emission into ``emision_prediccion`` unless they already have a first emission.

    ``results`` are the inferences of the emission (``infer``), ``last_published`` the last week (``id_semana``) the Sala
    had published when it was emitted and ``emitted_at`` the instant of the emission. It runs in the caller's
    transaction (the one that emits), so the first emission and the emission commit together. Insert-only: a cutoff that
    is emitted again keeps its first rows; it returns how many rows this call inserted and how many already existed."""
    run_ids = [result["id_ejecucion"] for result in results]
    rows = sesion.execute(select(Prediction).where(Prediction.id_ejecucion.in_(run_ids))).scalars().all()
    records = [{"ubigeo": row.ubigeo, "id_semana_corte": row.id_semana_corte, "horizonte": row.horizonte,
                "id_semana_objetivo": row.id_semana_objetivo, "probabilidad_brote": row.probabilidad_brote,
                "nivel_riesgo": row.nivel_riesgo, "casos_estimados": row.casos_estimados, "estado": row.estado,
                "motivo_no_disponible": row.motivo_no_disponible, "id_ejecucion": row.id_ejecucion,
                "fecha_emision": emitted_at, "ultima_semana_sala_publicada": last_published,
                "procedencia": "emision"} for row in rows]
    upsert(sesion, FirstEmission.__table__, records, FIRST_EMISSION_KEY, update=())
    inserted = len(sesion.execute(select(FirstEmission.ubigeo).where(FirstEmission.id_ejecucion.in_(run_ids))).all())
    return {"insertadas": inserted, "ya_existian": len(records) - inserted}


def prospective_frame(sesion):
    """One row per eligible first emission whose target week already has an observation loaded.

    Eligible: the first emission of the (district, cutoff, horizon), available, and emitted while its target week was
    not yet published by the Sala (``id_semana_objetivo`` after ``ultima_semana_sala_publicada``; unknown counts as not
    eligible). Nothing about the lead time or the start of the target week enters. Columns: ``horizonte``,
    ``id_semana_objetivo``, ``p`` (probability), ``casos_estimados``, ``brote`` and ``casos`` (observed)."""
    query = select(FirstEmission.horizonte, FirstEmission.id_semana_objetivo, FirstEmission.probabilidad_brote,
                   FirstEmission.casos_estimados, WeeklyObservation.brote, WeeklyObservation.casos_dengue).join(
        WeeklyObservation, (WeeklyObservation.ubigeo == FirstEmission.ubigeo)
        & (WeeklyObservation.id_semana == FirstEmission.id_semana_objetivo)).where(
        FirstEmission.estado == "disponible", WeeklyObservation.brote.is_not(None),
        FirstEmission.ultima_semana_sala_publicada.is_not(None),
        FirstEmission.id_semana_objetivo > FirstEmission.ultima_semana_sala_publicada)
    return pd.DataFrame(sesion.execute(query).all(),
                        columns=["horizonte", "id_semana_objetivo", "p", "casos_estimados", "brote", "casos"])


def prospective_scores(sesion):
    """Per horizon: ``n``, observed outbreaks, the sum of the probabilities, Brier and MAE of the cases.

    It takes ``prospective_frame``. It interprets nothing and sets no threshold (the drift review is
    ``denguekay.serving.drift``)."""
    frame = prospective_frame(sesion)
    scores = {}
    for horizon in HORIZONS:
        part = frame[frame.horizonte.eq(horizon)]
        cases = part.dropna(subset=["casos_estimados", "casos"])
        scores[str(horizon)] = {
            "n": int(len(part)),
            "brotes_observados": int(part.brote.astype(int).sum()),
            "suma_probabilidades": round(float(part.p.sum()), 4),
            "brier": None if part.empty else round(float(np.mean((part.p.astype(float) - part.brote.astype(int)) ** 2)), 6),
            "mae_casos": None if cases.empty else round(float(np.mean(np.abs(
                cases.casos_estimados.astype(float) - cases.casos.astype(float)))), 4),
        }
    return scores


# --- annual retraining notice --------------------------------------------------------

def season_close(labels_cutoff):
    """Close (the Saturday) of epidemiological week 34 of the first year whose close is after ``labels_cutoff``."""
    labels_cutoff = pd.Timestamp(labels_cutoff)
    for year in range(labels_cutoff.year, labels_cutoff.year + 3):
        grid = week_grid(year, year)
        close = grid.loc[grid.semana.eq(SEASON_CLOSE_WEEK), "semana_inicio"].iloc[0] + pd.Timedelta(days=6)
        if close > labels_cutoff:
            return close.date()
    raise ValueError("No hay cierre de temporada posterior al corte de las etiquetas")


def labels_cutoff_of_v4(options=None):
    """Last label close of the model in use: the cutoff of the refit package that ``paquete_dir`` names, or the
    ``corte_etiquetas`` of the frozen V4 card."""
    if options and options.get("paquete_dir"):
        from denguekay.config.paths import ROOT

        package = json.loads((ROOT / options["paquete_dir"] / "paquete.json").read_text(encoding="utf-8"))
        return date.fromisoformat(package["corte"])
    from denguekay.model import registry

    return date.fromisoformat(registry.card("v4")["corte_etiquetas"])


def retraining_due(sesion, cutoff, *, labels_cutoff=None, options=None):
    """Whether the cutoff week reached the close of the season that follows the labels of the frozen model.

    It only informs: the weekly update never trains. ``cutoff`` is an ``id_semana``."""
    labels_cutoff = labels_cutoff or labels_cutoff_of_v4(options)
    close = season_close(labels_cutoff)
    week = sesion.get(EpiWeek, cutoff)
    return {"reentrenamiento_anual_pendiente": bool(week.fecha_fin >= close),
            "cierre_temporada": close.isoformat(), "corte_etiquetas_modelo": labels_cutoff.isoformat()}


def now_utc():
    return datetime.now(timezone.utc)
