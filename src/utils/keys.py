import re
import unicodedata
import pandas as pd


def normalizar(s):
    """Quita tildes y uniformiza mayúsculas. Úsalo en cualquier columna 'distrito'
    antes de mergear datasets de fuentes distintas."""
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s).strip().upper()


def separar_camel(s):
    """GADM devuelve nombres tipo 'CuraMori'; esto los separa en 'Cura Mori'."""
    return re.sub(r"(?<=[a-záéíóú])(?=[A-ZÁÉÍÓÚ])", " ", s)


def semana_epi(inicio):
    """inicio = domingo de inicio de una semana (dom-sáb).
    Devuelve (año_epi, semana_epi), consistente con el criterio de
    'al menos 4 días del año nuevo definen la SE 1'."""
    miercoles = inicio + pd.Timedelta(days=3)
    anio = miercoles.year
    jan1 = pd.Timestamp(anio, 1, 1)
    dias_desde_dom = (jan1.weekday() + 1) % 7
    inicio_semana_jan1 = jan1 - pd.Timedelta(days=dias_desde_dom)
    dias_en_anio = 7 - dias_desde_dom
    se1 = inicio_semana_jan1 if dias_en_anio >= 4 else inicio_semana_jan1 + pd.Timedelta(days=7)
    return anio, (inicio - se1).days // 7 + 1