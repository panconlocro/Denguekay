"""Integración de candidatos para pronóstico semanal a 2 y 4 semanas.

Gold conserva una fila por semana objetivo. Las estadísticas aprendidas
(climatología, PCA, umbral de alerta) se ajustan después dentro de cada fold.
"""

import hashlib
import json
import os
import tempfile
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

from src.eda.carga import cargar_integrado
from src.modeling.clima import construir_clima_observado
from src.modeling.etiqueta_brote import ConfiguracionBroteEstacional, etiquetar_brote_estacional
from src.modeling.historia_calendario import construir_historia_calendario
from src.modeling.sociodemografia import (
    DIRECTAS, construir_sociodemografia, construir_sociodemografia_anual_cruda,
    referencia_2017,
)
from src.modeling.vecinos_jerarquia import construir_vecinos_jerarquia
from src.processing.socio_interpolacion import SOCIO_COLUMNS
from src.utils.paths import GOLD, SILVER_EPI_HISTORICO, SILVER_INTEGRADO, UBIGEO_CATALOG
from src.validation.contrato_pronostico import CLAVE, auditar_origen
from src.validation.expectations_integrado import (
    coverage_path, load_case_coverage, validate_complete, validate_geography,
)

HORIZONTES = (2, 4)
FECHA_SOCIO_2017 = "2019-01-01"  # barrera conservadora, no fecha verificada del Excel
BASE = ["provincia", "distrito", "distrito_key", *CLAVE, "semana_inicio", "casos_Dengue"]


def columnas_gold(horizonte: int, *, con_brote: bool = False) -> list[str]:
    """Contrato de columnas candidatas y metadatos para un horizonte."""
    if horizonte not in HORIZONTES:
        raise ValueError("El horizonte debe ser 2 o 4 semanas")
    columnas = [
        *BASE, "origen_inicio", "origen_cierre",
        f"casos_lag_{horizonte}", f"casos_lag_{horizonte + 1}",
        f"casos_media_4_h{horizonte}", f"casos_semanas_positivas_4_h{horizonte}",
        "semana_epi_seno", "semana_epi_coseno",
        f"vecinos_media_casos_knn5_h{horizonte}",
        f"vecinos_frac_con_casos_knn5_h{horizonte}",
        f"provincia_otros_casos_h{horizonte}",
        f"provincia_otros_frac_con_casos_h{horizonte}",
        f"region_otros_casos_h{horizonte}",
        f"region_otros_frac_con_casos_h{horizonte}",
        f"hum_rel_media_media5_h{horizonte}",
        f"precip_total_mm_media5_h{horizonte}",
        *(f"{c}_2017" for c in DIRECTAS), "log_poblacion_censo_2017",
        *(f"{c}_anual" for c in SOCIO_COLUMNS if c != "poblacion"),
        "log_poblacion_anual", "socio_2017_disponible_al_origen",
        "socio_fracciones_interpoladas_con_2025",
    ]
    if con_brote:
        columnas += ["umbral_brote_casos", "brote"]
    return columnas


def _anexar(base: pd.DataFrame, fragmento: pd.DataFrame) -> pd.DataFrame:
    """Cruza una familia sin cambiar grano, fecha, orden ni nombres existentes."""
    if fragmento.duplicated(CLAVE).any() or len(fragmento) != len(base):
        raise ValueError("Una familia tiene llaves duplicadas o perdió filas")
    fechas_origen = [c for c in ("origen_inicio", "origen_cierre") if c in base and c in fragmento]
    if fechas_origen:
        cotejo = base[CLAVE + fechas_origen].merge(
            fragmento[CLAVE + fechas_origen], on=CLAVE, validate="one_to_one",
            suffixes=("", "_familia"), sort=False)
        if len(cotejo) != len(base):
            raise ValueError("Las fechas de origen de la familia tienen llaves distintas")
        for columna in fechas_origen:
            if not pd.to_datetime(cotejo[columna]).equals(pd.to_datetime(cotejo[f"{columna}_familia"])):
                raise ValueError(f"La familia tiene {columna} distinto")
        fragmento = fragmento.drop(columns=fechas_origen)
    extras = set(fragmento) - set(CLAVE + ["semana_inicio"])
    if extras & set(base):
        raise ValueError(f"Columnas de features repetidas: {sorted(extras & set(base))}")
    salida = base.merge(fragmento, on=CLAVE, how="left", validate="one_to_one", sort=False,
                        suffixes=("", "_familia"))
    if len(salida) != len(base) or salida[CLAVE].ne(base[CLAVE]).any().any():
        raise ValueError("El cruce de features alteró filas o su orden")
    if not salida.semana_inicio.eq(salida.pop("semana_inicio_familia")).all():
        raise ValueError("La fecha de la familia difiere de la semana objetivo")
    return salida


def construir_gold(
    panel: pd.DataFrame, horizonte: int, etiquetas: pd.DataFrame | None = None,
    *, minimo_casos_brote: int = 1,
) -> pd.DataFrame:
    """Integra candidatos sin ajustar estadísticas con datos de prueba.

    Mantiene las filas iniciales con rezagos NaN esperados. La población y las
    fracciones anuales del silver son una reconstrucción retrospectiva que
    incorpora el extremo de 2025; su uso debe evaluarse por separado.
    """
    if horizonte not in HORIZONTES:
        raise ValueError("El horizonte debe ser 2 o 4 semanas")
    faltan = set(BASE) - set(panel)
    if faltan:
        raise ValueError(f"Faltan columnas del integrado: {sorted(faltan)}")
    auditar_origen(panel, horizonte)
    referencia = referencia_2017(panel)
    salida = panel[BASE].sort_values(["ubigeo", "semana_inicio"]).reset_index(drop=True).copy()
    salida["semana_inicio"] = pd.to_datetime(salida["semana_inicio"])
    familias = (
        construir_historia_calendario(panel, horizonte),
        construir_vecinos_jerarquia(panel, horizonte),
        construir_clima_observado(panel, horizonte),
        construir_sociodemografia(
            panel, horizonte, referencia, FECHA_SOCIO_2017,
            enmascarar_antes_disponibilidad=False,
        ),
        construir_sociodemografia_anual_cruda(panel),
    )
    for familia in familias:
        salida = _anexar(salida, familia)
    salida["socio_2017_disponible_al_origen"] = salida.origen_cierre.ge(pd.Timestamp(FECHA_SOCIO_2017))
    salida["socio_fracciones_interpoladas_con_2025"] = salida.anio.between(2018, 2024)
    if etiquetas is not None:
        if set(etiquetas) != set(CLAVE + ["umbral_brote_casos", "brote"]):
            raise ValueError("Las etiquetas de brote tienen un esquema inesperado")
        if etiquetas.duplicated(CLAVE).any() or len(etiquetas) != len(panel):
            raise ValueError("Las etiquetas de brote alteran el grano del panel")
        salida = salida.merge(etiquetas, on=CLAVE, how="left", validate="one_to_one", sort=False)
    validar_gold(salida, panel, horizonte, con_brote=etiquetas is not None,
                 minimo_casos_brote=minimo_casos_brote)
    return salida


def validar_gold(
    gold: pd.DataFrame, silver: pd.DataFrame, horizonte: int, *,
    con_brote: bool = False, minimo_casos_brote: int = 1,
) -> dict[str, int]:
    """Comprueba llaves, etiqueta, origen, nulos de arranque y finitud."""
    if horizonte not in HORIZONTES:
        raise ValueError("Horizonte inválido")
    if len(gold) != len(silver) or gold.duplicated(CLAVE).any() or silver.duplicated(CLAVE).any():
        raise ValueError("Gold debe conservar las llaves únicas y el número de filas de silver")
    esperadas = set(columnas_gold(horizonte, con_brote=con_brote))
    if set(gold) != esperadas:
        raise ValueError(f"Esquema gold inesperado: faltan {sorted(esperadas - set(gold))}; sobran {sorted(set(gold) - esperadas)}")
    if gold.columns.duplicated().any() or any(c.endswith(("_x", "_y", "_familia")) for c in gold):
        raise ValueError("Gold contiene columnas duplicadas o sufijos de merge")
    base = silver[CLAVE + ["semana_inicio", "casos_Dengue"]].copy()
    base["semana_inicio"] = pd.to_datetime(base.semana_inicio)
    cruce = gold[CLAVE + ["semana_inicio", "casos_Dengue"]].merge(
        base, on=CLAVE, validate="one_to_one", suffixes=("", "_silver"))
    if len(cruce) != len(silver) or not cruce.semana_inicio.eq(cruce.semana_inicio_silver).all() or not cruce.casos_Dengue.eq(cruce.casos_Dengue_silver).all():
        raise ValueError("Gold cambió las semanas objetivo o las etiquetas de silver")
    audit = auditar_origen(gold, horizonte)
    origen = gold[CLAVE + ["origen_inicio", "origen_cierre"]].merge(
        audit[CLAVE + ["origen_inicio", "origen_cierre"]], on=CLAVE,
        suffixes=("", "_esperado"), validate="one_to_one")
    for campo in ("origen_inicio", "origen_cierre"):
        actual = pd.to_datetime(origen[campo])
        esperado = pd.to_datetime(origen[f"{campo}_esperado"])
        if not actual.equals(esperado):
            raise ValueError(f"Gold tiene {campo} fuera del horizonte")
    if not gold.socio_2017_disponible_al_origen.eq(
        pd.to_datetime(gold.origen_cierre).ge(pd.Timestamp(FECHA_SOCIO_2017))).all():
        raise ValueError("La marca de disponibilidad censal no coincide con el origen")
    if not gold.socio_fracciones_interpoladas_con_2025.eq(gold.anio.between(2018, 2024)).all():
        raise ValueError("La marca de fracciones interpoladas no coincide con el año")
    if con_brote:
        if not gold.brote.isin([0, 1]).all() or not pd.to_numeric(gold.umbral_brote_casos, errors="coerce").ge(0).all():
            raise ValueError("La etiqueta o el umbral de brote son inválidos")
        esperado = (gold.casos_Dengue.gt(gold.umbral_brote_casos)
                    & gold.casos_Dengue.ge(minimo_casos_brote)).astype("int8")
        if not gold.brote.eq(esperado).all():
            raise ValueError("La etiqueta de brote no coincide con sus casos y umbral")
    orden = gold.sort_values(["ubigeo", "semana_inicio"])
    posicion = orden.groupby("ubigeo", sort=False).cumcount()
    arranque = {
        f"casos_lag_{horizonte}": horizonte,
        f"casos_lag_{horizonte + 1}": horizonte + 1,
        f"casos_media_4_h{horizonte}": horizonte + 3,
        f"casos_semanas_positivas_4_h{horizonte}": horizonte + 3,
    }
    arranque.update({c: horizonte for c in gold if c.startswith(("vecinos_", "provincia_otros_", "region_otros_"))})
    arranque.update({c: horizonte + 4 for c in gold if c.endswith(f"_media5_h{horizonte}")})
    for columna, inicio in arranque.items():
        if columna not in orden or not orden[columna].isna().eq(posicion.lt(inicio)).all():
            raise ValueError(f"Nulos o cobertura temporal inesperados en {columna}")
    siempre = [c for c in gold if c not in set(CLAVE + ["semana_inicio", "origen_inicio", "origen_cierre", *arranque])
              and pd.api.types.is_numeric_dtype(gold[c])]
    if gold[siempre].isna().any().any():
        raise ValueError("Hay nulos no esperados en columnas completas de gold")
    numericas = gold.select_dtypes(include="number")
    if not np.isfinite(numericas.to_numpy(float)[~numericas.isna().to_numpy()]).all():
        raise ValueError("Gold contiene valores numéricos no finitos")
    return {"filas": len(gold), "distritos": int(gold.ubigeo.nunique()),
            "semanas_por_distrito": int(gold.groupby("ubigeo").size().min()),
            "filas_con_ventanas_completas": int(posicion.ge(horizonte + 4).sum()),
            "filas_sin_ventanas_completas": int(posicion.lt(horizonte + 4).sum())}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def generar_gold(
    input_path: Path = SILVER_INTEGRADO, output_dir: Path = GOLD,
    catalog_path: Path = UBIGEO_CATALOG,
    *, brote: ConfiguracionBroteEstacional | None = None,
    historia_path: Path = SILVER_EPI_HISTORICO,
) -> dict[int, dict[str, object]]:
    """Valida silver, genera ambos horizontes y escribe CSV/linaje reproducibles."""
    input_path, output_dir = Path(input_path), Path(output_dir)
    panel = cargar_integrado(input_path)
    cobertura = load_case_coverage(coverage_path(input_path))
    if cobertura is None:
        raise ValueError("Falta el archivo de cobertura epidemiológica del integrado")
    validate_complete(panel, cobertura)
    validate_geography(panel, catalog_path)
    etiquetas = None
    if brote is not None:
        historia_path = Path(historia_path)
        historia = pd.read_csv(historia_path, dtype={"ubigeo": "string"})
        primero = int(panel.anio.min())
        historia = historia.loc[historia.anio.between(primero - brote.anios_previos, primero - 1)]
        etiquetas = etiquetar_brote_estacional(
            panel, historia, multiplicador=brote.multiplicador,
            anios_previos=brote.anios_previos, minimo_casos=brote.minimo_casos,
        )
    salidas = {h: construir_gold(panel, h, etiquetas,
                                minimo_casos_brote=brote.minimo_casos if brote else 1)
               for h in HORIZONTES}
    resumen = {h: validar_gold(salidas[h], panel, h, con_brote=brote is not None,
                              minimo_casos_brote=brote.minimo_casos if brote else 1) for h in HORIZONTES}
    output_dir.mkdir(parents=True, exist_ok=True)
    temporales: list[tuple[Path, Path]] = []
    try:
        for h in HORIZONTES:
            destino = output_dir / f"{input_path.stem}_h{h}_gold.csv"
            with tempfile.NamedTemporaryFile(dir=output_dir, suffix=".csv.tmp", delete=False) as temp:
                temporal = Path(temp.name)
            temporales.append((temporal, destino))
            salidas[h].to_csv(temporal, index=False, date_format="%Y-%m-%d", float_format="%.17g")
            persistido = pd.read_csv(
                temporal, dtype={"ubigeo": "string"},
                parse_dates=["semana_inicio", "origen_inicio", "origen_cierre"],
            )
            validar_gold(persistido, panel, h, con_brote=brote is not None,
                         minimo_casos_brote=brote.minimo_casos if brote else 1)
            resumen[h]["archivo"] = destino.name
            resumen[h]["sha256"] = _sha256(temporal)
            resumen[h]["columnas"] = len(salidas[h].columns)
        manifiesto = {
            "fuente": input_path.name,
            "sha256_fuente": _sha256(input_path),
            "sha256_cobertura": _sha256(coverage_path(input_path)),
            "catalogo_geografico": Path(catalog_path).name,
            "sha256_catalogo_geografico": _sha256(Path(catalog_path)),
            "grano": CLAVE,
            "etiqueta": "casos_Dengue (conteo observado)" if brote is None else "brote (semana elevada; 0/1)",
            "columnas_no_predictoras": [
                "casos_Dengue", "brote", "umbral_brote_casos", "ubigeo", "anio", "semana",
                "provincia", "distrito", "distrito_key", "semana_inicio",
                "origen_inicio", "origen_cierre", "socio_2017_disponible_al_origen",
                "socio_fracciones_interpoladas_con_2025",
            ] if brote is not None else [
                "casos_Dengue", "ubigeo", "anio", "semana", "provincia", "distrito", "distrito_key",
                "semana_inicio", "origen_inicio", "origen_cierre",
                "socio_2017_disponible_al_origen", "socio_fracciones_interpoladas_con_2025",
            ],
            "regla_brote": None if brote is None else {
                "metodo": "misma semana epidemiológica de años previos; media + multiplicador * DE muestral; desigualdad estricta",
                **asdict(brote), "fuente_historia": historia_path.name,
                "sha256_fuente_historia": _sha256(historia_path),
                "ausencia_historica": "sin registro tratado como cero, no cero notificado",
                "semana_53": "se suma a semana 52 para la referencia",
            },
            "fecha_disponibilidad_socio_2017_supuesta": FECHA_SOCIO_2017,
            "limitaciones": [
                "Fracciones 2018-2024 interpoladas con 2025: reconstrucción retrospectiva.",
                "Población anual proyectada: fecha/version de publicación no comprobada.",
                "Casos y clima semanal suponen disponibilidad al cierre de su semana; latencia no verificada.",
                "No incluye anomalías climáticas ni PCA globales: ajustar por fold de entrenamiento.",
                "No hay partición train/test final; brote y umbral son etiquetas/metadatos, no predictores.",
            ],
            "horizontes": {str(h): resumen[h] for h in HORIZONTES},
        }
        if etiquetas is not None:
            manifiesto["positivos_brote_por_anio"] = {
                str(y): int(n) for y, n in etiquetas.groupby("anio").brote.sum().items()
            }
        destino_manifest = output_dir / "manifest_fase6.json"
        with tempfile.NamedTemporaryFile(dir=output_dir, suffix=".json.tmp", delete=False) as temp:
            temporal_manifest = Path(temp.name)
        temporales.append((temporal_manifest, destino_manifest))
        temporal_manifest.write_text(json.dumps(manifiesto, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        for temporal, destino in temporales:
            os.replace(temporal, destino)
    finally:
        for temporal, _ in temporales:
            temporal.unlink(missing_ok=True)
    return resumen
