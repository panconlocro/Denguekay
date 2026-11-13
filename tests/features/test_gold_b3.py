"""B3 en el gold persistido: sin fuga y, con los datos locales, igual a la v2 y al respaldo bit a bit."""

import json
import unittest

import numpy as np
import pandas as pd

from denguekay.config.paths import GOLD, GOLD_BACKUP, GOLD_MANIFEST, SILVER_EPI_HISTORICAL, SILVER_INTEGRATED
from denguekay.features import onset_features as fi
from denguekay.features.climate import D3_COLUMNS
from denguekay.features.gold import ONSET_COLUMNS, PERSISTED_NON_PREDICTORS, persisted_columns

NOMBRE = f"{SILVER_INTEGRATED.stem}_h2_gold.csv"
HAY_DATOS = (GOLD / NOMBRE).exists() and SILVER_INTEGRATED.exists() and SILVER_EPI_HISTORICAL.exists()
FECHAS = ["semana_inicio", "origen_inicio", "origen_cierre"]


def leer(ruta):
    return pd.read_csv(ruta, dtype={"ubigeo": "string"}, parse_dates=FECHAS, float_precision="round_trip")


def panel_y_origenes(casos=None):
    fechas = pd.date_range("2018-01-07", periods=30, freq="W-SUN")
    filas = [{"ubigeo": u, "anio": f.year, "semana": f.isocalendar().week, "semana_inicio": f,
              "casos_Dengue": int((i * (d + 2)) % 7)}
             for d, u in enumerate(("200101", "200102")) for i, f in enumerate(fechas)]
    panel = pd.DataFrame(filas)
    if casos is not None:
        panel = casos(panel)
    gold = panel[["ubigeo", "anio", "semana", "semana_inicio"]].copy()
    gold["origen_cierre"] = gold.semana_inicio - pd.Timedelta(weeks=2) + pd.Timedelta(days=6)
    gold.loc[gold.semana_inicio.lt(fechas[2]), "origen_cierre"] = pd.NaT
    historia = pd.DataFrame([{"ubigeo": u, "anio": y, "semana": 1, "casos_Dengue": 3}
                             for u in ("200101", "200102") for y in (2016, 2017)])
    return gold, panel, historia


class TestB3SinFuga(unittest.TestCase):
    def test_constantes_coinciden_con_el_registro_de_variantes(self):
        self.assertEqual(ONSET_COLUMNS, fi.COLUMNS["B3"])

    def test_filas_sin_origen_quedan_nulas_y_el_orden_no_cambia(self):
        gold, panel, historia = panel_y_origenes()
        salida = fi.with_onset_columns(gold, panel, historia)
        self.assertEqual(list(salida.index), list(gold.index))
        sin_origen = gold.origen_cierre.isna()
        self.assertEqual(int(sin_origen.sum()), 4)
        self.assertTrue(salida.loc[sin_origen, ONSET_COLUMNS].isna().all().all())
        self.assertTrue(salida.loc[~sin_origen, "propia_semanas_desde_ultimo_caso"].notna().all())

    def test_perturbar_semanas_posteriores_al_origen_no_cambia_b3(self):
        objetivo = pd.Timestamp("2018-05-06")
        origen = objetivo - pd.Timedelta(weeks=2)

        def perturbar(panel):
            panel = panel.copy()
            panel.loc[panel.semana_inicio.gt(origen), "casos_Dengue"] += 500
            return panel

        antes = fi.with_onset_columns(*panel_y_origenes())
        despues = fi.with_onset_columns(*panel_y_origenes(perturbar))
        fila = antes.semana_inicio.le(objetivo)
        pd.testing.assert_frame_equal(antes.loc[fila, ONSET_COLUMNS], despues.loc[fila, ONSET_COLUMNS])
        self.assertFalse(antes.loc[~fila, ONSET_COLUMNS].equals(despues.loc[~fila, ONSET_COLUMNS]))


@unittest.skipUnless(HAY_DATOS, "requiere gold, silver integrado y epi histórico locales")
class TestGoldReal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gold = leer(GOLD / NOMBRE)

    def test_esquema_y_filas(self):
        self.assertEqual(list(self.gold.columns), persisted_columns(2))
        self.assertEqual(self.gold.shape, (30485, 24))  # 20 of the v2 + the 4 d3 columns of the v3
        self.assertEqual(sorted(p.name for p in GOLD.glob("*_gold.csv")), [NOMBRE])

    def test_b3_identica_a_frozen_configs_origins(self):
        from denguekay.data.loading import load_integrated
        from denguekay.evaluation import variants as fh
        from denguekay.model import frozen_configs as cf

        panel = load_integrated(SILVER_INTEGRATED)
        regla = json.loads(GOLD_MANIFEST.read_text(encoding="utf-8"))["regla_brote"]
        origenes = cf.origins(panel, fh.inputs(panel, regla), regla, configuration=cf.CONFIG_2026_V1)
        cruce = origenes[["ubigeo", "semana_inicio", *ONSET_COLUMNS]].merge(
            self.gold, on=["ubigeo", "semana_inicio"], how="left", suffixes=("_v2", ""), validate="one_to_one")
        self.assertEqual(len(cruce), 30160)
        for c in ONSET_COLUMNS:
            with self.subTest(columna=c):
                np.testing.assert_array_equal(cruce[f"{c}_v2"].to_numpy(float), cruce[c].to_numpy(float))

    @unittest.skipUnless(GOLD_BACKUP.exists(), "requiere data/gold/respaldo_pre_b3/")
    def test_las_17_columnas_que_quedan_son_identicas_al_respaldo(self):
        respaldo = leer(GOLD_BACKUP / NOMBRE)
        columnas = [c for c in persisted_columns(2) if c not in ONSET_COLUMNS and c not in D3_COLUMNS]
        self.assertEqual(len(columnas), 17)
        self.assertTrue(set(PERSISTED_NON_PREDICTORS) <= set(columnas))
        pd.testing.assert_frame_equal(self.gold[columnas], respaldo[columnas], check_exact=True)


if __name__ == "__main__":
    unittest.main()
