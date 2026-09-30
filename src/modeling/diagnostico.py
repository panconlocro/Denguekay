"""Modelo lineal fijo de prueba para ablaciones; no es el modelo final."""

import numpy as np
import pandas as pd


def ridge_predecir(train: pd.DataFrame, test: pd.DataFrame,
                  columnas: list[str], penalizacion: float = 10.0) -> np.ndarray:
    """Predice conteos con ridge en log1p y escalamiento ajustado solo en train."""
    x = train[columnas].to_numpy(float)
    z = test[columnas].to_numpy(float)
    centro = x.mean(axis=0)
    escala = x.std(axis=0)
    escala[escala == 0] = 1
    x = np.column_stack([np.ones(len(x)), (x - centro) / escala])
    z = np.column_stack([np.ones(len(z)), (z - centro) / escala])
    y = np.log1p(train["casos_Dengue"].to_numpy(float))
    regularizador = np.eye(x.shape[1]) * penalizacion
    regularizador[0, 0] = 0
    coef = np.linalg.solve(x.T @ x + regularizador, x.T @ y)
    return np.expm1(np.maximum(0, z @ coef))
