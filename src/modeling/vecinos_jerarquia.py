"""Contexto espacial y jerárquico disponible al origen del pronóstico."""

import numpy as np
import pandas as pd

from src.eda.espacial import distancias_km, pesos_inverso_distancia, pesos_knn
from src.validation.contrato_pronostico import CLAVE, auditar_origen


def catalogo_geografico(panel: pd.DataFrame) -> pd.DataFrame:
    """Extrae una geografía única y estable por UBIGEO del panel integrado."""
    requeridas = {"ubigeo", "provincia", "lat", "lon"}
    faltan = requeridas - set(panel)
    if faltan:
        raise ValueError(f"Faltan columnas geográficas: {sorted(faltan)}")
    geo = panel[list(requeridas)].copy()
    if geo.isna().any().any():
        raise ValueError("Hay identificadores, provincias o coordenadas faltantes")
    geo["ubigeo"] = geo["ubigeo"].astype("string")
    if not geo.ubigeo.str.fullmatch(r"\d{6}").all():
        raise ValueError("UBIGEO debe tener seis dígitos")
    geo["lat"] = pd.to_numeric(geo["lat"], errors="raise")
    geo["lon"] = pd.to_numeric(geo["lon"], errors="raise")
    if (not np.isfinite(geo[["lat", "lon"]].to_numpy()).all()
            or not geo.lat.between(-90, 90).all()
            or not geo.lon.between(-180, 180).all()):
        raise ValueError("Coordenadas no finitas o fuera de rango")
    if (geo.groupby("ubigeo")[["provincia", "lat", "lon"]].nunique() > 1).any().any():
        raise ValueError("Un UBIGEO tiene geografía inconsistente entre semanas")
    geo = geo.drop_duplicates("ubigeo").sort_values("ubigeo").reset_index(drop=True)
    if geo.duplicated(["lat", "lon"]).any():
        raise ValueError("Hay centroides idénticos; los pesos por distancia serían ambiguos")
    if geo.groupby("provincia").size().lt(2).any():
        raise ValueError("Cada provincia necesita otro distrito para agregados sin sí mismo")
    return geo[["ubigeo", "provincia", "lat", "lon"]]


def matriz_vecindad(
    catalogo: pd.DataFrame, k: int = 5, metodo: str = "knn",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Devuelve pesos sin diagonal y distancias, ambos indexados por UBIGEO.

    ``knn`` reutiliza los k vecinos uniformes del EDA. ``knn_inversa`` usa
    esos mismos k vecinos con peso inverso a la distancia. ``inversa`` usa
    todos los demás distritos con peso inverso; en ese caso ``k`` se ignora.
    """
    geo = catalogo.sort_values("ubigeo").reset_index(drop=True)
    if geo.empty or geo.ubigeo.duplicated().any():
        raise ValueError("El catálogo está vacío o duplica UBIGEO")
    if metodo not in ("knn", "knn_inversa", "inversa"):
        raise ValueError("Método de vecindad desconocido")
    if metodo in ("knn", "knn_inversa") and (not isinstance(k, int) or not 1 <= k < len(geo)):
        raise ValueError("k debe estar entre 1 y el número de distritos menos 1")
    dist = distancias_km(geo.lat.to_numpy(), geo.lon.to_numpy())
    if (dist[np.triu_indices(len(geo), 1)] <= 0).any():
        raise ValueError("Hay centroides coincidentes")
    if metodo == "knn":
        pesos = pesos_knn(dist, k)
    elif metodo == "knn_inversa":
        mascara = pesos_knn(dist, k) > 0
        pesos = pesos_inverso_distancia(dist) * mascara
        pesos = pesos / pesos.sum(axis=1, keepdims=True)
    else:
        pesos = pesos_inverso_distancia(dist)
    if not np.isfinite(pesos).all() or not np.allclose(pesos.sum(axis=1), 1):
        raise ValueError("Pesos espaciales no finitos o sin normalizar")
    if not np.allclose(np.diag(pesos), 0):
        raise ValueError("La matriz espacial incluye al distrito objetivo")
    ids = pd.Index(geo.ubigeo, name="ubigeo")
    return (pd.DataFrame(pesos, index=ids, columns=ids),
            pd.DataFrame(dist, index=ids, columns=ids))


def construir_vecinos_jerarquia(
    panel: pd.DataFrame, horizonte: int, k: int = 5, metodo: str = "knn",
) -> pd.DataFrame:
    """Calcula vecinos, provincia y región usando solo casos de ``t-h``.

    Cada salida mantiene una fila por distrito y semana objetivo; sus fechas
    de origen permiten auditar la disponibilidad. Los agregados provincial y
    regional excluyen al propio distrito. ``frac_con_casos`` significa casos
    estrictamente positivos, sin adoptar la definición de brote D1 del EDA.
    Se exige un panel completo en todas las fechas para evitar promedios
    espaciales calculados silenciosamente con distritos ausentes.
    """
    if horizonte not in (2, 4):
        raise ValueError("El proyecto contempla horizontes de 2 o 4 semanas")
    if "casos_Dengue" not in panel:
        raise ValueError("Falta casos_Dengue")
    audit = auditar_origen(panel, horizonte)
    geo = catalogo_geografico(panel)
    pesos, _ = matriz_vecindad(geo, k=k, metodo=metodo)
    fuente = audit.merge(panel[CLAVE + ["casos_Dengue"]], on=CLAVE,
                         how="left", validate="one_to_one", sort=False)
    if len(fuente) != len(panel):
        raise ValueError("El cruce con casos cambió el número de filas")
    casos = pd.to_numeric(fuente.casos_Dengue, errors="raise")
    if casos.isna().any() or not np.isfinite(casos.to_numpy(dtype=float)).all() or (casos < 0).any():
        raise ValueError("casos_Dengue debe ser numérico, finito y no negativo")

    ids = pesos.index
    ancho = fuente.assign(casos_Dengue=casos).pivot(
        index="semana_inicio", columns="ubigeo", values="casos_Dengue"
    ).reindex(columns=ids)
    if ancho.isna().any().any() or len(ancho) * len(ids) != len(panel):
        raise ValueError("Faltan distrito-semanas para construir el contexto espacial")
    y = ancho.to_numpy(dtype=float)
    activos = (y > 0).astype(float)
    provincias = geo.set_index("ubigeo").loc[ids, "provincia"].to_numpy()
    misma_provincia = (provincias[:, None] == provincias[None, :]).astype(float)
    np.fill_diagonal(misma_provincia, 0)
    otros_region = np.ones_like(misma_provincia) - np.eye(len(ids))
    conteo_provincia = misma_provincia.sum(axis=1)

    etiqueta = (f"knn{k}" if metodo == "knn" else
                f"knn{k}_inversa" if metodo == "knn_inversa" else "inversa")
    valores = {
        f"vecinos_media_casos_{etiqueta}_h{horizonte}": y @ pesos.to_numpy().T,
        f"vecinos_frac_con_casos_{etiqueta}_h{horizonte}": activos @ pesos.to_numpy().T,
        f"provincia_otros_casos_h{horizonte}": y @ misma_provincia.T,
        f"provincia_otros_frac_con_casos_h{horizonte}":
            (activos @ misma_provincia.T) / conteo_provincia[None, :],
        f"region_otros_casos_h{horizonte}": y @ otros_region.T,
        f"region_otros_frac_con_casos_h{horizonte}":
            (activos @ otros_region.T) / (len(ids) - 1),
    }
    salida = audit.copy()
    filas = ancho.index.get_indexer(audit.semana_inicio)
    columnas = ids.get_indexer(audit.ubigeo.astype("string"))
    if (filas < 0).any() or (columnas < 0).any():
        raise ValueError("Un distrito o una semana no se pudo alinear")
    for nombre, matriz in valores.items():
        # La fila objetivo t toma el agregado que existía en t-h.
        rezagado = pd.DataFrame(matriz, index=ancho.index, columns=ids).shift(horizonte).to_numpy()
        salida[nombre] = rezagado[filas, columnas]
    return salida
