"""Quality and completeness report of the integrated silver of the V4 (HU0005-4 and HU0005-5, US v1.4).

Read-only: it reads the confirmed integrated panel (``data/silver/confirmados/meteo_socio_epi_piura_2017_2025.csv`` and
its ``.coverage.csv``), the confirmed notifications of the bronze CSV and the Sala silver, and writes a JSON and a
Markdown report to ``docs/backend/evidencia/`` (never to ``data/``). It corrects nothing: a run that does not meet the
criterion is recorded as ``no conforme`` with the affected variables.

HU0005-5 criterion
- Completeness >= 95 %, measured on the integrated silver before imputing: rows with every mandatory column non-null
  among the expected rows (65 districts x the weeks of the period). A missing row counts as incomplete.
- No more than 5 % of the original records are discarded.
- The coverage of the source is reported by district. Structural nulls of lags do not count: the integrated silver has
  no derived columns, and only the mandatory columns enter the measure.

HU0005-4: summary of coverage, missing values, duplicates, discarded observations and transformations.

Mapping of the criterion's mandatory columns to the columns of the V4 panel: ubigeo -> ``ubigeo``, year -> ``anio``,
week -> ``semana``, week start -> ``semana_inicio``, cases -> ``casos_Dengue``, temperature -> ``temp_media``,
precipitation -> ``precip_total_mm``, humidity -> ``hum_rel_media`` and population -> ``poblacion``.

Discarded records. The original records are the confirmed Piura notifications of the bronze CSV for the years before
the Sala (``SALA_FIRST_YEAR``) and the confirmed Piura counts of the Sala silver from that year, inside the years of the
panel. A record is discarded when it does not end up in the panel (for example, a Sala week outside the model calendar).
The notifications that are not confirmed (probable cases) and the other departments are excluded by the definition of the
V4, not discarded, and are reported apart.
"""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re

import pandas as pd

from denguekay.config.paths import (BACKEND_EVIDENCE, BRONZE_EPI_CSV, DATA, UBIGEO_CATALOG, V4_PANEL_WEATHER,
                                    V4_RELEASE_HISTORY, V4_RELEASE_INTEGRATED, V4_RELEASE_SALA, V4_SOCIO)
from denguekay.data.keys import normalize
from denguekay.data.processing import epi_sala
from denguekay.data.processing.case_source import has_source_record
from denguekay.data.processing.epi_cases import RAW_COLUMNS, deduplicate_cases_with_report
from denguekay.data.processing.epi_sala import SALA_FIRST_YEAR, load_ubigeo_catalog
from denguekay.data.processing.merge import V4_NAME_ALIASES, diagnose_unmatched_districts
from denguekay.data.validation.climate_provenance import climate_sources
from denguekay.data.validation.duplicates import duplicate_key_report

MANDATORY = {"ubigeo": "ubigeo", "año": "anio", "semana": "semana", "inicio de semana": "semana_inicio",
             "casos": "casos_Dengue", "temperatura": "temp_media", "precipitación": "precip_total_mm",
             "humedad": "hum_rel_media", "población": "poblacion"}
COMPLETENESS_MIN = 0.95
DISCARD_MAX = 0.05
REPORT_NAME = "calidad_datos_v4"

TRANSFORMATIONS = (
    {"paso": "Casos confirmados del CSV (hasta 2024)", "modulo": "data/processing/epi_cases.py",
     "descripcion": "Se filtran las notificaciones de Piura con tipo_dx = C, se valida UBIGEO, año y semana (un valor "
                    "inválido detiene el proceso, no se descarta) y se cuentan por UBIGEO, año y semana; las filas "
                    "repetidas se suman."},
    {"paso": "Casos confirmados de la Sala (desde 2025)", "modulo": "data/processing/epi_sala.py",
     "descripcion": "Series distrito-año de la Sala Situacional normalizadas por semana epidemiológica; las semanas "
                    "fuera del calendario del modelo se conservan en el silver de la Sala y no se asignan a otra semana."},
    {"paso": "Unión con el panel", "modulo": "data/processing/merge.py",
     "descripcion": "Los casos se unen al panel de clima y sociodemografía por UBIGEO, año y semana; el relleno "
                    "selectivo marca en el archivo de cobertura qué ceros están verificados."},
    {"paso": "Clima semanal", "modulo": "data/processing/weekly_aggregation.py",
     "descripcion": "Los valores diarios se agregan por semana epidemiológica y distrito."},
    {"paso": "Sociodemografía anual", "modulo": "data/processing/socio_interpolation.py",
     "descripcion": "Las fracciones con valores en 2017 y 2025 se interpolan entre ambos extremos."},
)


def expected_grid(frame, districts):
    """The expected (ubigeo, semana_inicio) rows: every district x every week between the first and the last start."""
    weeks = pd.date_range(frame.semana_inicio.min(), frame.semana_inicio.max(), freq="W-SUN")
    return pd.MultiIndex.from_product([sorted(districts), weeks], names=["ubigeo", "semana_inicio"])


def prepare_panel(frame):
    """The panel with ``ubigeo`` as a 6-digit string and the week start as a date."""
    panel = frame.copy()
    panel["ubigeo"] = panel["ubigeo"].astype("string").str.zfill(6)
    panel["semana_inicio"] = pd.to_datetime(panel["semana_inicio"])
    return panel


def completeness(panel, districts):
    """Completeness of the mandatory columns over the expected rows, and the missing share of each variable."""
    grid = expected_grid(panel, districts)
    columns = list(MANDATORY.values())
    unique = panel.drop_duplicates(["ubigeo", "semana_inicio"]).set_index(["ubigeo", "semana_inicio"])
    present = unique.reindex(grid)[[c for c in columns if c not in ("ubigeo", "semana_inicio")]]
    present["ubigeo"] = grid.get_level_values("ubigeo")
    present["semana_inicio"] = grid.get_level_values("semana_inicio")
    complete = present[columns].notna().all(axis=1)
    expected = len(grid)
    missing_rows = expected - int(grid.isin(unique.index).sum())
    by_variable = {}
    for label, column in MANDATORY.items():
        nulls = int(present[column].isna().sum())
        by_variable[column] = {"criterio": label, "nulos": nulls, "completitud": round(1 - nulls / expected, 6)}
    ratio = float(complete.sum()) / expected
    return {"filas_esperadas": expected, "filas_presentes": int(len(unique)), "filas_ausentes": missing_rows,
            "filas_completas": int(complete.sum()), "completitud": round(ratio, 6),
            "minimo": COMPLETENESS_MIN, "cumple": bool(ratio >= COMPLETENESS_MIN), "por_variable": by_variable,
            "periodo": {"desde": str(grid.get_level_values("semana_inicio").min().date()),
                        "hasta": str(grid.get_level_values("semana_inicio").max().date()),
                        "semanas": int(grid.get_level_values("semana_inicio").nunique()),
                        "distritos": int(grid.get_level_values("ubigeo").nunique())}}


def coverage_by_district(panel, history, sala, districts):
    """Per district: weeks of the period present, complete rows, non-null share per variable and the share of weeks
    with a case record in the effective source (``casos_verificados``; None without the history)."""
    grid = expected_grid(panel, districts)
    weeks = grid.get_level_values("semana_inicio").nunique()
    variables = [c for c in MANDATORY.values() if c not in ("ubigeo", "semana_inicio")]
    panel = panel.drop_duplicates(["ubigeo", "semana_inicio"])
    complete = panel[list(MANDATORY.values())].notna().all(axis=1)
    verified = has_source_record(panel, history, sala) if history is not None else None
    result = {}
    for ubigeo in sorted(districts):
        mask = panel.ubigeo.eq(ubigeo)
        result[ubigeo] = {
            "semanas_presentes": int(mask.sum()), "semanas_esperadas": int(weeks),
            "filas_completas": int(complete[mask].sum()),
            "completitud": round(float(complete[mask].sum()) / weeks, 6),
            "casos_verificados": round(float(verified[mask].sum()) / weeks, 6) if verified is not None else None,
            "no_nulos": {column: round(float(panel.loc[mask, column].notna().sum()) / weeks, 6)
                         for column in variables}}
    return result


def duplicates(panel):
    """Rows that repeat the key (ubigeo, anio, semana), and rows that repeat (ubigeo, semana_inicio)."""
    return {"llave_ubigeo_anio_semana": int(panel.duplicated(["ubigeo", "anio", "semana"]).sum()),
            "llave_ubigeo_semana_inicio": int(panel.duplicated(["ubigeo", "semana_inicio"]).sum())}


def cases_with_source_record(panel, history, sala):
    """How many district-weeks have a case count in the source and how many got a zero in the merge.

    ``merge_with_epi`` assigns 0 to the district-weeks of the covered years without notifications (the coverage file of
    the Release marks them verified; the database loads them as ``sin_registro`` with 0 cases). The integrated silver
    therefore has no null cases, so this is the only view of the cases before that assignment."""
    n, with_record = len(panel), int(has_source_record(panel, history, sala).sum())
    return {"filas": n, "con_registro_de_casos_en_la_fuente": with_record, "cero_asignado_en_la_union": n - with_record,
            "proporcion_con_registro": round(with_record / n, 6),
            "nota": "Las semanas de un distrito sin notificaciones reciben cero en la unión (relleno selectivo; el "
                    "archivo de cobertura del Release las marca verificadas; la BD las carga como `sin_registro` con 0 casos). La completitud de `casos` del panel es 100 % por "
                    "construcción; esta es la proporción con un conteo en la fuente antes de esa asignación. Es un "
                    "criterio de lectura a confirmar: un cero verificado de vigilancia no se trata como dato faltante."}


PANEL_DUPLICATE_RULE = ("El panel integrado exige una fila por llave (ubigeo, anio, semana): la validación del panel "
                        "se detiene si una llave se repite")


def epidemiological_duplicates(panel, history, sala):
    """Result of the repeated-key control of each epidemiological source (HU0001-3).

    The weekly counts of the history add up their repeated rows (``deduplicate_cases``); the Sala and the integrated
    panel stop on a repeated key, so a repeated key there is a non-conformity."""
    controls = []
    if history is not None:
        controls.append(deduplicate_cases_with_report(
            history, "Histórico confirmado (CSV epidemiológico, hasta 2024)")[1])
    controls.append(duplicate_key_report(sala, source="Sala Situacional confirmada (desde 2025)",
                                         rule=epi_sala.DUPLICATE_RULE))
    controls.append(duplicate_key_report(panel, source="Panel integrado de la V4", rule=PANEL_DUPLICATE_RULE))
    return controls


def territorial_correspondence(panel, catalog_codes, meteo=None, socio=None):
    """Districts without correspondence or ambiguous between the sources of the integrated silver (HU0003-2).

    The panel is compared with the UBIGEO catalogue. When the weather and census silver are available, the districts
    of each are matched by ``distrito_key`` after the documented name aliases, as the merge does."""
    codes, in_panel = set(catalog_codes), set(panel.ubigeo.astype(str))
    result = {"distritos_catalogo": len(codes), "distritos_panel": len(in_panel),
              "en_panel_sin_catalogo": sorted(in_panel - codes), "en_catalogo_sin_panel": sorted(codes - in_panel),
              "ubigeo_con_formato_invalido": sorted(u for u in in_panel if not re.fullmatch(r"\d{6}", u)),
              "alias_de_nombres_aplicados": dict(V4_NAME_ALIASES), "meteo_vs_socio": None}
    if meteo is not None and socio is not None:
        weather = meteo.assign(distrito=meteo.distrito.replace(V4_NAME_ALIASES))
        weather["distrito_key"] = weather.distrito.map(normalize)
        result["meteo_vs_socio"] = diagnose_unmatched_districts(weather, socio, echo=False)
    problems = [result["en_panel_sin_catalogo"], result["en_catalogo_sin_panel"],
                result["ubigeo_con_formato_invalido"], *(result["meteo_vs_socio"] or {}).values()]
    result["cumple"] = not any(problems)
    return result


def read_confirmed_notifications(path, first_year, last_year):
    """Piura confirmed notifications per year of the bronze CSV, plus the counts excluded by definition."""
    raw = pd.read_csv(path, usecols=RAW_COLUMNS, dtype="string", encoding="utf-8-sig")
    department = raw["departamento"].str.strip().str.upper()
    diagnosis = raw["tipo_dx"].str.strip().str.upper()
    year = pd.to_numeric(raw["ano"], errors="coerce")
    inside = department.eq("PIURA") & year.between(first_year, last_year)
    confirmed = inside & diagnosis.eq("C")
    return ({int(y): int(n) for y, n in year[confirmed].value_counts().sort_index().items()},
            {"piura_no_confirmadas": int((inside & ~diagnosis.eq("C")).sum()),
             "otros_departamentos_o_fuera_del_periodo": int((~inside).sum())})


def discarded_records(panel, notifications, sala, excluded):
    """Original records per year against the cases in the panel; what is not in the panel is discarded."""
    in_panel = panel.groupby("anio").casos_Dengue.sum()
    years, rows = sorted(set(in_panel.index)), []
    for year in years:
        source = "sala" if year >= SALA_FIRST_YEAR else "notificaciones_csv"
        original = int(sala.get(year, 0)) if year >= SALA_FIRST_YEAR else int(notifications.get(year, 0))
        kept = int(in_panel.get(year, 0))
        rows.append({"anio": int(year), "fuente": source, "registros_originales": original,
                     "casos_en_el_panel": kept, "descartados": max(original - kept, 0),
                     "exceso_en_el_panel": max(kept - original, 0)})
    original = sum(r["registros_originales"] for r in rows)
    discarded = sum(r["descartados"] for r in rows)
    ratio = discarded / original if original else 0.0
    return {"por_anio": rows, "registros_originales": original, "descartados": discarded,
            "proporcion_descartada": round(ratio, 6), "maximo": DISCARD_MAX, "cumple": bool(ratio <= DISCARD_MAX),
            "excluidos_por_definicion": excluded,
            "nota": "Los registros no confirmados y de otros departamentos se excluyen por la definición de la V4; "
                    "no se cuentan como descartados."}


def build_report(panel_path=V4_RELEASE_INTEGRATED, notifications_path=BRONZE_EPI_CSV, sala_path=V4_RELEASE_SALA,
                 catalog_path=UBIGEO_CATALOG, history_path=V4_RELEASE_HISTORY, meteo_path=V4_PANEL_WEATHER,
                 socio_path=V4_SOCIO, climate=None):
    """Assemble the report; reading only. ``climate`` replaces the folders that ``climate_sources`` reads."""
    panel = prepare_panel(pd.read_csv(panel_path, dtype={"ubigeo": "string"}))
    coverage_path = Path(panel_path).with_suffix(".coverage.csv")
    coverage = pd.read_csv(coverage_path, dtype={"ubigeo": "string"}) if coverage_path.exists() else None
    districts = load_ubigeo_catalog(catalog_path).ubigeo.tolist()
    first_year, last_year = int(panel.anio.min()), int(panel.anio.max())
    notifications, excluded = read_confirmed_notifications(notifications_path, first_year, SALA_FIRST_YEAR - 1)
    sala_frame = pd.read_csv(sala_path, dtype={"ubigeo": "string"})
    history_frame = pd.read_csv(history_path, dtype={"ubigeo": "string"}) if Path(history_path).exists() else None
    sala = sala_frame[sala_frame.anio.between(SALA_FIRST_YEAR, last_year)].groupby("anio").casos_Dengue.sum().to_dict()
    measure = completeness(panel, districts)
    discards = discarded_records(panel, notifications, sala, excluded)
    duplicate_controls = epidemiological_duplicates(panel, history_frame, sala_frame)
    territorial = territorial_correspondence(
        panel, districts, pd.read_csv(meteo_path) if Path(meteo_path).is_file() else None,
        pd.read_csv(socio_path, dtype={"ubigeo": "string"}) if Path(socio_path).is_file() else None)
    nonconformities = []
    for control in duplicate_controls[1:]:   # the history adds up its repeated rows; the other sources stop
        if control["claves_repetidas"]:
            nonconformities.append({"criterio": "HU0001-3 claves repetidas en " + control["fuente"],
                                    "variables_afectadas": ["casos"], "valor": control["claves_repetidas"]})
    if not territorial["cumple"]:
        nonconformities.append({"criterio": "HU0003-2 correspondencia territorial", "variables_afectadas": ["ubigeo"],
                                "valor": {k: v for k, v in territorial.items() if isinstance(v, list) and v}})
    if not measure["cumple"]:
        affected = [v for v, item in measure["por_variable"].items() if item["nulos"]]
        nonconformities.append({"criterio": "HU0005-5 completitud >= 95 %", "variables_afectadas": affected,
                                "valor": measure["completitud"]})
    if not discards["cumple"]:
        nonconformities.append({"criterio": "HU0005-5 descartados <= 5 %", "variables_afectadas": ["casos"],
                                "valor": discards["proporcion_descartada"]})
    return {
        "criterio": "HU0005-4 y HU0005-5 (US v1.4)", "generado_utc": datetime.now(timezone.utc).isoformat(),
        "estado": "conforme" if not nonconformities else "no conforme", "no_conformidades": nonconformities,
        "entradas": {"panel": Path(panel_path).name, "cobertura": coverage_path.name if coverage is not None else None,
                     "notificaciones": Path(notifications_path).name, "sala": Path(sala_path).name},
        "columnas_obligatorias": MANDATORY, "completitud": measure,
        "cobertura_por_distrito": coverage_by_district(panel, history_frame, sala_frame, districts),
        "duplicados": duplicates(panel), "control_duplicados_fuente_epidemiologica": duplicate_controls,
        "correspondencia_territorial": territorial, "fuentes_climaticas": climate_sources(**(climate or {})),
        "valores_faltantes": measure["por_variable"],
        "observaciones_descartadas": discards, "transformaciones": list(TRANSFORMATIONS),
        "ceros_de_casos": int(panel.casos_Dengue.eq(0).sum()),
        "casos_antes_de_asignar_ceros": None if history_frame is None else cases_with_source_record(
            panel, history_frame, sala_frame),
        "nota_rezagos": "El silver integrado no tiene columnas derivadas: los nulos estructurales de los rezagos no "
                        "entran en la medida.",
    }


def percent(value):
    return f"{value * 100:.2f} %".replace(".", ",")


def to_markdown(report):
    """The report as Markdown, in Spanish."""
    c, d = report["completitud"], report["observaciones_descartadas"]
    lines = [f"# Calidad y completitud de los datos de la V4 ({report['criterio']})", "",
             f"Generado: {report['generado_utc']}. Estado: **{report['estado']}**.", "",
             "Solo lectura: el reporte no corrige datos. Entradas: " + ", ".join(
                 f"`{v}`" for v in report["entradas"].values() if v) + ".", ""]
    if report["no_conformidades"]:
        lines += ["## No conformidades", ""]
        lines += [f"- {n['criterio']}: valor {n['valor']}; variables afectadas: {', '.join(n['variables_afectadas'])}."
                  for n in report["no_conformidades"]] + [""]
    p = c["periodo"]
    lines += ["## Completitud (HU0005-5)", "",
              f"Periodo {p['desde']} a {p['hasta']}: {p['distritos']} distritos × {p['semanas']} semanas = "
              f"{c['filas_esperadas']} filas esperadas. Presentes {c['filas_presentes']}, ausentes {c['filas_ausentes']}, "
              f"completas {c['filas_completas']}. **Completitud {percent(c['completitud'])}** "
              f"(mínimo {percent(c['minimo'])}): {'cumple' if c['cumple'] else 'no cumple'}.", "",
              "| Criterio | Columna | Nulos | Completitud |", "|---|---|---|---|"]
    lines += [f"| {v['criterio']} | `{k}` | {v['nulos']} | {percent(v['completitud'])} |"
              for k, v in c["por_variable"].items()]
    lines += ["", report["nota_rezagos"], "", "## Observaciones descartadas", "",
              f"Registros originales {d['registros_originales']}, descartados {d['descartados']} "
              f"({percent(d['proporcion_descartada'])}; máximo {percent(d['maximo'])}): "
              f"{'cumple' if d['cumple'] else 'no cumple'}.", "",
              "| Año | Fuente | Originales | En el panel | Descartados | Exceso en el panel |", "|---|---|---|---|---|---|"]
    lines += [f"| {r['anio']} | {r['fuente']} | {r['registros_originales']} | {r['casos_en_el_panel']} | "
              f"{r['descartados']} | {r['exceso_en_el_panel']} |" for r in d["por_anio"]]
    e = d["excluidos_por_definicion"]
    lines += ["", f"Excluidos por la definición de la V4 (no son descartes): {e['piura_no_confirmadas']} notificaciones "
              f"no confirmadas de Piura y {e['otros_departamentos_o_fuera_del_periodo']} de otros departamentos o fuera "
              "del periodo.", "", "## Duplicados", "",
              f"Llave (ubigeo, año, semana): {report['duplicados']['llave_ubigeo_anio_semana']}; "
              f"llave (ubigeo, inicio de semana): {report['duplicados']['llave_ubigeo_semana_inicio']}.", "",
              "## Control de duplicados de la fuente epidemiológica (HU0001-3)", "",
              "| Fuente | Filas | Claves repetidas | Filas con llave repetida | Resultado | Regla aplicada |",
              "|---|---|---|---|---|---|"]
    lines += [f"| {c['fuente']} | {c['filas']} | {c['claves_repetidas']} | {c['filas_con_llave_repetida']} | "
              f"{c['resultado']} | {c['regla_aplicada']} |" for c in report["control_duplicados_fuente_epidemiologica"]]
    for c in report["control_duplicados_fuente_epidemiologica"]:
        if c["ejemplos"]:
            lines += ["", f"Ejemplos de claves repetidas en {c['fuente']}: " + "; ".join(
                f"{e['ubigeo']}/{e['anio']}/{e['semana']} ({e['filas']} filas)" for e in c["ejemplos"]) + "."]
    t = report["correspondencia_territorial"]
    lines += ["", "## Correspondencia territorial (HU0003-2)", "",
              f"{t['distritos_panel']} distritos en el panel y {t['distritos_catalogo']} en el catálogo de UBIGEO: "
              f"{'cumple' if t['cumple'] else 'no cumple'}.", "",
              f"- En el panel sin catálogo: {t['en_panel_sin_catalogo'] or 'ninguno'}.",
              f"- En el catálogo sin panel: {t['en_catalogo_sin_panel'] or 'ninguno'}.",
              f"- UBIGEO con formato inválido: {t['ubigeo_con_formato_invalido'] or 'ninguno'}."]
    if t["meteo_vs_socio"] is not None:
        m = t["meteo_vs_socio"]
        aliases = ", ".join(f"«{a}» → «{b}»" for a, b in t["alias_de_nombres_aplicados"].items())
        lines += [f"- Clima sin correspondencia en el censo, después de los alias de nombres ({aliases}): "
                  f"{m['solo_en_meteo'] or 'ninguno'}.",
                  f"- Censo sin correspondencia en el clima: {m['solo_en_socio'] or 'ninguno'}.",
                  f"- Correspondencia ambigua: {m['ambiguos'] or 'ninguna'}."]
    else:
        lines += ["- Clima frente a censo: no se evaluó (faltan los silver de clima o de sociodemografía)."]
    lines += ["", "## Fuentes climáticas: producto y fecha de extracción (HU0002-1)", "",
              "| Fuente | Producto | Fecha de extracción | Tipo de fecha | Capturas | Referencia |",
              "|---|---|---|---|---|---|"]
    lines += [f"| {s['fuente']} | {s['producto']} | {s['fecha_extraccion'] or '—'} | {s['tipo_de_fecha']} | "
              f"{s['capturas']} | {s['referencia']} |" for s in report["fuentes_climaticas"]]
    lines += ["", "## Cobertura por distrito", "",
              "Completitud de cada distrito y proporción de semanas con casos verificados.", "",
              "| UBIGEO | Semanas | Completas | Completitud | Casos verificados |", "|---|---|---|---|---|"]
    for ubigeo, item in report["cobertura_por_distrito"].items():
        verified = "—" if item["casos_verificados"] is None else percent(item["casos_verificados"])
        lines.append(f"| {ubigeo} | {item['semanas_presentes']} / {item['semanas_esperadas']} | "
                     f"{item['filas_completas']} | {percent(item['completitud'])} | {verified} |")
    before = report["casos_antes_de_asignar_ceros"]
    if before:
        lines += ["", "## Casos antes de asignar ceros", "",
                  f"De {before['filas']} semanas distritales, {before['con_registro_de_casos_en_la_fuente']} "
                  f"({percent(before['proporcion_con_registro'])}) tienen un conteo en la fuente y "
                  f"{before['cero_asignado_en_la_union']} recibieron cero en la unión. {before['nota']}"]
    lines += ["", f"Semanas con cero casos en el panel: {report['ceros_de_casos']} (el archivo de cobertura distingue "
              "los ceros verificados).", "", "## Transformaciones", ""]
    lines += [f"- **{t['paso']}** (`{t['modulo']}`): {t['descripcion']}" for t in report["transformaciones"]]
    return "\n".join(lines) + "\n"


def write_report(report, folder=BACKEND_EVIDENCE):
    """Write the JSON and the Markdown; never inside ``data/``."""
    folder = Path(folder).resolve()
    if folder == DATA.resolve() or DATA.resolve() in folder.parents:
        raise ValueError("El reporte de calidad nunca se escribe en data/")
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{REPORT_NAME}.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    (folder / f"{REPORT_NAME}.md").write_text(to_markdown(report), encoding="utf-8")
    return folder / f"{REPORT_NAME}.json", folder / f"{REPORT_NAME}.md"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--salida", type=Path, default=BACKEND_EVIDENCE, help="Carpeta de salida (nunca data/)")
    parser.add_argument("--sin-escribir", action="store_true", help="Solo imprime el resumen")
    args = parser.parse_args(argv)
    report = build_report()
    if not args.sin_escribir:
        for path in write_report(report, args.salida):
            print(path)
    print(json.dumps({"estado": report["estado"], "completitud": report["completitud"]["completitud"],
                      "descartados": report["observaciones_descartadas"]["proporcion_descartada"],
                      "no_conformidades": report["no_conformidades"]}, ensure_ascii=False))
    return 0 if report["estado"] == "conforme" else 2


if __name__ == "__main__":
    raise SystemExit(main())
