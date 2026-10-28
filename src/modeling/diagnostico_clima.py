"""Ablación temporal pequeña para medir si el clima mejora un pronóstico.

El ajuste lineal regularizado es un diagnóstico fijo, no el XGBoost final.
"""

import numpy as np
import pandas as pd

from src.eda.temporal import asignar_temporada
from src.modeling.clima import CLIMA_PRINCIPAL, ajustar_climatologia, construir_clima
from src.modeling.diagnostico import ridge_predecir
from src.modeling.historia_calendario import construir_historia_calendario
from src.validation.contrato_pronostico import CLAVE


def contrastar_clima(
    panel: pd.DataFrame, horizontes: tuple[int, ...] = (2, 4),
    temporadas: tuple[int, ...] = (2022, 2023, 2024, 2025),
    semana_inicio_temporada: int = 35,
    variables_clima: tuple[str, ...] = CLIMA_PRINCIPAL,
) -> pd.DataFrame:
    """Compara persistencia y ridge base/con clima en cortes por temporada.

    Cada modelo se entrena una sola vez antes del primer origen del bloque de
    prueba. La climatología se ajusta con clima cerrado a ese mismo origen.
    Las filas futuras del bloque usan solo el clima ya observado en su propio
    origen móvil; no se reajustan modelo ni climatología dentro del bloque.
    """
    if panel.duplicated(CLAVE).any():
        raise ValueError("Llaves duplicadas en el panel")
    if panel["casos_Dengue"].isna().any():
        raise ValueError("casos_Dengue contiene faltantes")
    resultados = []
    for h in horizontes:
        historia = construir_historia_calendario(panel, h)
        base = panel[CLAVE + ["semana_inicio", "casos_Dengue"]].merge(
            historia.drop(columns="semana_inicio"), on=CLAVE, validate="one_to_one")
        if len(base) != len(panel):
            raise ValueError("Historia cambió el número de filas")
        base["temporada"] = asignar_temporada(base.anio, base.semana, semana_inicio_temporada)
        base[f"log_casos_lag_{h}"] = np.log1p(base[f"casos_lag_{h}"])
        base[f"log_casos_media_4_h{h}"] = np.log1p(base[f"casos_media_4_h{h}"])
        columnas_base = [f"log_casos_lag_{h}", f"log_casos_media_4_h{h}",
                         "semana_epi_seno", "semana_epi_coseno"]
        columnas_clima = [f"{v}_anomalia_media5_h{h}" for v in variables_clima]
        for t in temporadas:
            prueba_previa = base.loc[base.temporada.eq(t)]
            if prueba_previa.empty:
                raise ValueError(f"Temporada {t} fuera del panel")
            primera = prueba_previa.semana_inicio.min()
            origen = primera - pd.Timedelta(weeks=h)
            corte = origen + pd.Timedelta(days=6)
            clima = construir_clima(panel, h, ajustar_climatologia(panel, corte, variables_clima))
            datos = base.merge(clima.drop(columns="semana_inicio"), on=CLAVE,
                               validate="one_to_one")
            if len(datos) != len(panel):
                raise ValueError("Clima cambió el número de filas")
            columnas = columnas_base + columnas_clima
            datos = datos.loc[datos[columnas + ["casos_Dengue"]].notna().all(axis=1)]
            train = datos.loc[datos.semana_inicio.le(origen)]
            test = datos.loc[datos.temporada.eq(t)]
            if train.empty or test.empty:
                raise ValueError(f"Sin filas suficientes en temporada {t}, h={h}")
            real = test.casos_Dengue.to_numpy(float)
            predicciones = {
                "persistencia": test[f"casos_lag_{h}"].to_numpy(float),
                "historia_calendario": ridge_predecir(train, test, columnas_base),
                "historia_calendario_clima": ridge_predecir(train, test, columnas),
            }
            for modelo, pred in predicciones.items():
                resultados.append({"horizonte": h, "temporada": t,
                                   "primera_semana_prueba": str(primera.date()),
                                   "corte_ajuste": str(corte.date()),
                                   "modelo": modelo, "n_entrenamiento": len(train),
                                   "n_prueba": len(test),
                                   "mae_casos": float(np.mean(np.abs(real - pred))),
                                   "mae_log1p": float(np.mean(np.abs(np.log1p(real) - np.log1p(pred))))})
    return pd.DataFrame(resultados)
