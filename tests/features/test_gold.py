"""Integridad, causalidad y escritura reproducible de la fase 6."""

import hashlib
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from denguekay.features.gold import build_gold, generate_gold, persisted_columns, validate_gold
from denguekay.features.outbreak_label import SeasonalOutbreakConfig
from denguekay.data.processing.socio_interpolation import SOCIO_COLUMNS
from denguekay.data.validation.integrated_expectations import WEATHER_COLUMNS, coverage_path


def panel_ejemplo() -> pd.DataFrame:
    fechas = pd.date_range("2017-12-03", periods=12, freq="W-SUN")
    filas = []
    for d in range(6):
        for i, fecha in enumerate(fechas):
            iso = (fecha + pd.Timedelta(days=3)).isocalendar()
            fila = {
                "provincia": "PIURA" if d < 3 else "SULLANA",
                "distrito": f"DISTRITO {d}", "distrito_key": f"DISTRITO_{d}",
                "ubigeo": f"20010{d + 1}", "anio": iso.year, "semana": iso.week,
                "semana_inicio": fecha, "lat": -5.0 - d * 0.1,
                "lon": -80.0 - d * 0.1, "casos_Dengue": i + d,
                "poblacion": 1000 + 100 * d + (100 if iso.year == 2018 else 0),
            }
            for j, c in enumerate(SOCIO_COLUMNS[1:]):
                fila[c] = 0.1 + d * 0.01 + j * 0.001 + (0.02 if iso.year == 2018 else 0)
            for j, c in enumerate(WEATHER_COLUMNS):
                fila[c] = float(20 + d + i + j)
            filas.append(fila)
    return pd.DataFrame(filas)


class GoldTests(unittest.TestCase):
    def setUp(self):
        self.panel = panel_ejemplo()

    def test_grano_horizontes_nulos_y_valores(self):
        for h in (2, 4):
            with self.subTest(h=h):
                gold = build_gold(self.panel, h)
                resumen = validate_gold(gold, self.panel, h)
                self.assertEqual(resumen["filas"], len(self.panel))
                self.assertEqual(resumen["filas_sin_ventanas_completas"], 6 * (h + 4))
                self.assertFalse(gold.duplicated(["ubigeo", "anio", "semana"]).any())
                self.assertFalse(any(c.endswith(("_x", "_y")) for c in gold))
                self.assertFalse(any("anomalia" in c or "eje_urbano" in c for c in gold))
                a = gold.loc[gold.ubigeo.eq("200101")].reset_index(drop=True)
                i = 8
                self.assertEqual(a.loc[i, f"casos_lag_{h}"], i - h)
                self.assertEqual(a.loc[i, f"hum_rel_media_media5_h{h}"],
                                 np.mean(np.arange(20 + WEATHER_COLUMNS.index("hum_rel_media") + i - h - 4,
                                                   20 + WEATHER_COLUMNS.index("hum_rel_media") + i - h + 1)))
                self.assertEqual(a.loc[i, "origen_inicio"], a.loc[i - h, "semana_inicio"])
                self.assertAlmostEqual(a.loc[i, "log_poblacion_anual"], np.log(1100))
                self.assertAlmostEqual(a.loc[i, "fraccion_rural_anual"], 0.12)
                self.assertAlmostEqual(a.loc[i, "fraccion_rural_2017"], 0.1)

    def test_casos_y_clima_posteriores_al_origen_no_alteran_features(self):
        for h in (2, 4):
            with self.subTest(h=h):
                antes = build_gold(self.panel, h)
                cambiado = self.panel.copy()
                objetivo = pd.Timestamp("2018-01-28")
                origen = objetivo - pd.Timedelta(weeks=h)
                mascara = cambiado.ubigeo.eq("200101") & cambiado.semana_inicio.gt(origen)
                cambiado.loc[mascara, "casos_Dengue"] += 500
                cambiado.loc[mascara, "hum_rel_media"] += 500
                despues = build_gold(cambiado, h)
                fila = antes.ubigeo.eq("200101") & antes.semana_inicio.eq(objetivo)
                cols = [c for c in antes if c not in ("casos_Dengue",)]
                pd.testing.assert_frame_equal(antes.loc[fila, cols], despues.loc[fila, cols])

    def test_gold_invalido_se_rechaza(self):
        gold = build_gold(self.panel, 4)
        repetido = pd.concat([gold, gold.iloc[[0]]], ignore_index=True)
        with self.assertRaisesRegex(ValueError, "llaves únicas"):
            validate_gold(repetido, self.panel, 4)
        etiqueta = gold.copy()
        etiqueta.loc[0, "casos_Dengue"] += 1
        with self.assertRaisesRegex(ValueError, "etiquetas"):
            validate_gold(etiqueta, self.panel, 4)
        sin_clima = gold.drop(columns="hum_rel_media_media5_h4")
        with self.assertRaisesRegex(ValueError, "Esquema gold"):
            validate_gold(sin_clima, self.panel, 4)
        # La validación estructural comprueba cobertura; la causalidad de
        # valores se prueba mutando la fuente y reconstruyendo el panel.
        nulo = gold.copy()
        nulo.loc[8, "casos_lag_4"] = np.nan
        with self.assertRaisesRegex(ValueError, "Nulos"):
            validate_gold(nulo, self.panel, 4)

    def test_escritura_repetida_identica_y_fallo_sin_salida(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            fuente = raiz / "integrado.csv"
            salida = raiz / "gold"
            catalogo = raiz / "catalogo.csv"
            self.panel[["provincia", "distrito", "ubigeo"]].drop_duplicates().to_csv(catalogo, index=False)
            self.panel.to_csv(fuente, index=False)
            cobertura = self.panel[["ubigeo", "anio", "semana", "casos_Dengue"]].copy()
            cobertura["source"] = "verified"
            cobertura.to_csv(coverage_path(fuente), index=False)
            historia = raiz / "historia.csv"
            pd.DataFrame([
                {"ubigeo": f"20010{d + 1}", "anio": y, "semana": 1, "casos_Dengue": 0}
                for d in range(6) for y in range(2012, 2017)
            ]).to_csv(historia, index=False)
            era5 = raiz / "era5_land.csv"  # weekly ERA5-Land silver from 2017-06 (13 weeks before the first origin)
            semanas = pd.date_range("2017-06-04", "2018-03-04", freq="W-SUN")
            distritos = self.panel[["distrito", "lat", "lon"]].drop_duplicates()
            pd.DataFrame([{"distrito": r.distrito, "lat": r.lat, "lon": r.lon, "semana_inicio": w,
                           "temp_media": 24.0 + k * 0.1 + i * 0.01}
                          for k, r in enumerate(distritos.itertuples()) for i, w in enumerate(semanas)]).to_csv(era5, index=False)
            regla = {"outbreak": SeasonalOutbreakConfig(2.0, minimo_casos=2), "history_path": historia,
                     "era5_land_path": era5}
            primer = generate_gold(fuente, salida, catalogo, **regla)
            hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in salida.iterdir()}
            segundo = generate_gold(fuente, salida, catalogo, **regla)
            self.assertEqual(primer, segundo)
            self.assertEqual(hashes, {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                      for p in salida.iterdir()})
            self.assertEqual(sorted(hashes), ["integrado_h2_gold.csv", "manifest_fase6.json"])
            g = pd.read_csv(salida / "integrado_h2_gold.csv", dtype={"ubigeo": "string"},
                            parse_dates=["semana_inicio", "origen_inicio", "origen_cierre"])
            self.assertEqual(list(g.columns), persisted_columns(2))
            self.assertEqual(len(g.columns), 24)  # 20 of the v2 + the 4 d3 columns of the v3
            with_origin = g.origen_cierre.notna()
            self.assertFalse(g.loc[with_origin, ["temp_media_s0", "temp_media_media_s9_12"]].isna().any().any())
            self.assertTrue(g.loc[~with_origin, "temp_media_s0"].isna().all())  # no origin, no d3
            self.assertEqual(g.ubigeo.nunique(), 6)
            comprobar = {"with_outbreak": True, "min_outbreak_cases": 2, "persisted": True}
            validate_gold(g, self.panel, 2, **comprobar)
            self.assertTrue(g.brote.isin([0, 1]).all())
            self.assertEqual(g.loc[g.ubigeo.eq("200101") & g.anio.eq(2017), "brote"].sum(), 2)
            roto = g.copy()
            indice = roto.index[roto.brote.eq(1)][0]
            roto.loc[indice, "brote"] = 0
            with self.assertRaisesRegex(ValueError, "no coincide"):
                validate_gold(roto, self.panel, 2, **comprobar)
            sin_arranque = g.copy()
            sin_arranque.loc[g.index[g.origen_cierre.notna()][0], "propia_semanas_desde_ultimo_caso"] = np.nan
            with self.assertRaisesRegex(ValueError, "Nulos"):
                validate_gold(sin_arranque, self.panel, 2, **comprobar)
            with self.assertRaisesRegex(ValueError, "Esquema gold"):
                validate_gold(g.drop(columns="propia_pendiente_4"), self.panel, 2, **comprobar)
            catalogo_incorrecto = pd.read_csv(catalogo, dtype={"ubigeo": "string"})
            catalogo_incorrecto.loc[0, "distrito"] = "OTRO DISTRITO"
            catalogo_incorrecto.to_csv(catalogo, index=False)
            with self.assertRaisesRegex(ValueError, "does not match"):
                generate_gold(fuente, raiz / "geografia_invalida", catalogo, **regla)
            self.assertFalse((raiz / "geografia_invalida").exists())
            self.panel[["provincia", "distrito", "ubigeo"]].drop_duplicates().to_csv(catalogo, index=False)
            malo = self.panel.copy()
            malo.loc[0, "hum_rel_media"] = np.nan
            malo.to_csv(fuente, index=False)
            with self.assertRaisesRegex(ValueError, "incomplete|Non-numeric"):
                generate_gold(fuente, raiz / "fallido", catalogo, **regla)
            self.assertFalse((raiz / "fallido").exists())


if __name__ == "__main__":
    unittest.main()
