"""Ablación temporal de demografía fija y anual reconstruida."""

import numpy as np
import pandas as pd

from src.eda.temporal import asignar_temporada
from src.processing.socio_interpolacion import SOCIO_COLUMNS
from src.modeling.clima import ajustar_climatologia, construir_clima
from src.modeling.diagnostico import ridge_predecir
from src.modeling.historia_calendario import construir_historia_calendario
from src.modeling.sociodemografia import (
    DIRECTAS, ajustar_eje_urbano, construir_sociodemografia,
    construir_sociodemografia_anual, referencia_2017,
)
from src.validation.contrato_pronostico import CLAVE


def contrastar_sociodemografia(
    panel: pd.DataFrame,
    fecha_disponible: str | pd.Timestamp,
    horizontes: tuple[int, ...] = (2, 4),
    temporadas: tuple[int, ...] = (2022, 2023, 2024, 2025),
    semana_inicio_temporada: int = 35,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Compara demografía fija y anual contra historia y clima en folds temporales.

    Usa las mismas filas de entrenamiento y prueba en todas las variantes.
    La fecha de disponibilidad del corte 2017 debe documentarse en el análisis.
    Los valores anuales se reconstruyeron con fuentes disponibles hoy, por lo
    que el resultado anual no simula un pronóstico histórico en tiempo real.
    Devuelve métricas por fold y metadatos del PCA ajustado en cada fold.
    """
    referencia = referencia_2017(panel)
    resultados, pca_ajustes = [], []
    for h in horizontes:
        historia = construir_historia_calendario(panel, h)
        base = panel[CLAVE + ["semana_inicio", "casos_Dengue"]].merge(
            historia.drop(columns="semana_inicio"), on=CLAVE, validate="one_to_one")
        if len(base) != len(panel):
            raise ValueError("Historia cambió el número de filas")
        base["temporada"] = asignar_temporada(base.anio, base.semana, semana_inicio_temporada)
        base[f"log_casos_lag_{h}"] = np.log1p(base[f"casos_lag_{h}"])
        base[f"log_casos_media_4_h{h}"] = np.log1p(base[f"casos_media_4_h{h}"])
        historia_cols = [f"log_casos_lag_{h}", f"log_casos_media_4_h{h}",
                         "semana_epi_seno", "semana_epi_coseno"]
        clima_cols = [f"{v}_anomalia_media5_h{h}" for v in
                      ("hum_rel_media", "precip_total_mm")]
        poblacion = ["log_poblacion_censo_2017"]
        directas = [f"{v}_2017" for v in DIRECTAS]
        eje_cols = ["eje_urbano_2017"]
        poblacion_anual = ["log_poblacion_anual"]
        directas_anuales = [f"{v}_anual" for v in DIRECTAS]
        eje_anual = ["eje_urbano_anual"]
        todas_anuales = [f"{c}_anual" for c in SOCIO_COLUMNS if c != "poblacion"]
        variantes = {
            "historia_calendario": historia_cols,
            "mas_poblacion_2017": historia_cols + poblacion,
            "mas_tres_fracciones_2017": historia_cols + directas,
            "mas_eje_urbano_2017": historia_cols + eje_cols,
            "mas_poblacion_y_eje": historia_cols + poblacion + eje_cols,
            "mas_clima": historia_cols + clima_cols,
            "mas_clima_poblacion_y_eje": historia_cols + clima_cols + poblacion + eje_cols,
            "mas_poblacion_anual": historia_cols + poblacion_anual,
            "mas_tres_fracciones_anuales": historia_cols + directas_anuales,
            "mas_eje_urbano_anual": historia_cols + eje_anual,
            "mas_15_fracciones_anuales": historia_cols + todas_anuales,
            "mas_poblacion_y_eje_anual": historia_cols + poblacion_anual + eje_anual,
            "mas_clima_poblacion_y_eje_anual": historia_cols + clima_cols + poblacion_anual + eje_anual,
        }
        for temporada in temporadas:
            prueba_previa = base.loc[base.temporada.eq(temporada)]
            if prueba_previa.empty:
                raise ValueError(f"Temporada {temporada} fuera del panel")
            primera = prueba_previa.semana_inicio.min()
            origen = primera - pd.Timedelta(weeks=h)
            corte = origen + pd.Timedelta(days=6)
            if corte < pd.Timestamp(fecha_disponible):
                raise ValueError(f"Corte de prueba anterior a la disponibilidad censal: {corte}")
            distritos_train = set(base.loc[base.semana_inicio.le(origen), "ubigeo"].astype(str))
            eje = ajustar_eje_urbano(referencia, distritos_train)
            clima = construir_clima(panel, h, ajustar_climatologia(panel, corte))
            socio = construir_sociodemografia(
                panel, h, referencia, fecha_disponible, eje,
                enmascarar_antes_disponibilidad=False,
            )
            socio_anual = construir_sociodemografia_anual(panel, eje)
            datos = base.merge(clima.drop(columns="semana_inicio"), on=CLAVE, validate="one_to_one")
            datos = datos.merge(socio.drop(columns="semana_inicio"), on=CLAVE, validate="one_to_one")
            datos = datos.merge(socio_anual.drop(columns="semana_inicio"), on=CLAVE, validate="one_to_one")
            if len(datos) != len(panel):
                raise ValueError("Los cruces cambiaron el número de filas")
            todas = sorted({c for cols in variantes.values() for c in cols})
            datos = datos.loc[datos[todas + ["casos_Dengue"]].notna().all(axis=1)]
            train = datos.loc[datos.semana_inicio.le(origen)]
            test = datos.loc[datos.temporada.eq(temporada)]
            if train.empty or test.empty:
                raise ValueError(f"Sin filas suficientes para temporada {temporada}, h={h}")
            if test.origen_cierre.isna().any() or test.origen_cierre.lt(pd.Timestamp(fecha_disponible)).any():
                raise ValueError("La prueba incluye orígenes anteriores a la disponibilidad censal")
            real = test.casos_Dengue.to_numpy(float)
            predicciones = {"persistencia": test[f"casos_lag_{h}"].to_numpy(float)}
            predicciones.update({nombre: ridge_predecir(train, test, cols)
                                  for nombre, cols in variantes.items()})
            pca_ajustes.append({"horizonte": h, "temporada": temporada,
                                "corte_ajuste": str(corte.date()),
                                "distritos_ajuste": len(eje.distritos_ajuste),
                                "varianza_explicada_cp1": eje.varianza_explicada})
            for nombre, pred in predicciones.items():
                resultados.append({"horizonte": h, "temporada": temporada,
                                   "primera_semana_prueba": str(primera.date()),
                                   "corte_ajuste": str(corte.date()),
                                   "modelo": nombre, "n_entrenamiento": len(train),
                                   "n_prueba": len(test),
                                   "mae_casos": float(np.mean(np.abs(real - pred))),
                                   "mae_log1p": float(np.mean(np.abs(np.log1p(real) - np.log1p(pred))))})
    return pd.DataFrame(resultados), pd.DataFrame(pca_ajustes)
