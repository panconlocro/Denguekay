"""Result of the repeated-key control of the epidemiological sources (HU0001-3).

The control never changes the data: it describes which keys repeat and which documented rule the pipeline applies,
so that the quality report can record it. The rules themselves live where the data is built
(``processing/epi_cases.py`` adds up the repeated rows of the weekly counts; ``processing/epi_sala.py`` stops on a
repeated Sala key).
"""

import pandas as pd

KEY = ("ubigeo", "anio", "semana")
SAMPLE = 10


def duplicate_key_report(frame: pd.DataFrame, *, source: str, rule: str, key=KEY, sample: int = SAMPLE) -> dict:
    """Repeated keys of ``frame`` and the rule applied to them.

    ``claves_repetidas`` counts the distinct keys that appear in more than one row and ``filas_con_llave_repetida``
    the rows that carry them; ``ejemplos`` lists up to ``sample`` of those keys with their number of rows.
    ``resultado`` is ``sin duplicados`` or ``con duplicados``."""
    key = list(key)
    absent = [column for column in key if column not in frame]
    if absent:
        raise ValueError(f"{source}: faltan las columnas de la llave {absent}")
    repeated = frame.duplicated(key, keep=False)
    counts = frame.loc[repeated].groupby(key, sort=True).size()
    examples = [{**dict(zip(key, (str(v) if isinstance(v, str) else int(v) for v in index))), "filas": int(n)}
                for index, n in ((i if isinstance(i, tuple) else (i,), n) for i, n in counts.head(sample).items())]
    return {"fuente": source, "llave": key, "filas": int(len(frame)), "claves_repetidas": int(len(counts)),
            "filas_con_llave_repetida": int(repeated.sum()), "ejemplos": examples, "regla_aplicada": rule,
            "resultado": "con duplicados" if len(counts) else "sin duplicados"}
