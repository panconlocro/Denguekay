"""Which district-weeks have a case record in the effective source, and which source that is.

The V4 counts confirmed cases. Before ``SALA_FIRST_YEAR`` the effective source is the confirmed notifications of the
open-data CSV (its weekly silver, ``epi_piura_semanal.csv``, holds one row per district-week with a notification);
from that year it is the Sala Situacional, which publishes an explicit weekly point (zeros included) per district.

A district-week without a record in its source keeps the count 0 that the merge assigns (the team's decision and
HU0004-1), but it is not a verified zero: its coverage state is ``sin_registro``. Only the label changes, never the count.
"""

import pandas as pd

from denguekay.data.processing.epi_sala import KEY, SALA_FIRST_YEAR

SOURCE_BEFORE_SALA = "datos_abiertos_confirmados"
SOURCE_SALA = "sala_situacional"
VERIFIED = "verificado"
NO_RECORD = "sin_registro"


def case_source(year: int) -> str:
    """Effective source of the confirmed counts of an epidemiological year."""
    return SOURCE_SALA if int(year) >= SALA_FIRST_YEAR else SOURCE_BEFORE_SALA


def _keys(frame: pd.DataFrame) -> pd.DataFrame:
    return frame[KEY].assign(ubigeo=frame.ubigeo.astype("string").str.zfill(6)).drop_duplicates()


def has_source_record(frame: pd.DataFrame, history: pd.DataFrame, sala: pd.DataFrame) -> pd.Series:
    """Boolean per row of ``frame``: its key (ubigeo, anio, semana) has a record in the effective source.

    ``history`` is the weekly silver of the confirmed CSV (used before ``SALA_FIRST_YEAR``) and ``sala`` the Sala silver
    (used from that year). Absence from either source is absence of record; no count enters the decision."""
    source = pd.concat([_keys(history[history.anio.lt(SALA_FIRST_YEAR)]), _keys(sala[sala.anio.ge(SALA_FIRST_YEAR)])])
    probe = frame[KEY].assign(ubigeo=frame.ubigeo.astype("string").str.zfill(6))
    present = probe.merge(source.drop_duplicates().assign(_ok=True), on=KEY, how="left")["_ok"].eq(True)
    return pd.Series(present.to_numpy(), index=frame.index)


def coverage_state(has_record: bool) -> str:
    return VERIFIED if has_record else NO_RECORD


def case_labels(frame: pd.DataFrame, history: pd.DataFrame, sala: pd.DataFrame) -> pd.DataFrame:
    """``fuente_casos`` and ``estado_cobertura`` of each row of ``frame``; the case counts are not read or changed."""
    record = has_source_record(frame, history, sala)
    return pd.DataFrame({"fuente_casos": frame.anio.map(case_source),
                         "estado_cobertura": record.map(coverage_state)}, index=frame.index)
