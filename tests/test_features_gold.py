"""Integridad, causalidad y escritura reproducible de la fase 6."""

import hashlib
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from src.modeling.features import construir_gold, generar_gold, validar_gold
from src.modeling.etiqueta_brote import ConfiguracionBroteEstacional
from src.processing.socio_interpolacion import SOCIO_COLUMNS
from src.validation.expectations_integrado import WEATHER_COLUMNS, coverage_path


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
                gold = construir_gold(self.panel, h)
                resumen = validar_gold(gold, self.panel, h)
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
                antes = construir_gold(self.panel, h)
                cambiado = self.panel.copy()
                objetivo = pd.Timestamp("2018-01-28")
                origen = objetivo - pd.Timedelta(weeks=h)
                mascara = cambiado.ubigeo.eq("200101") & cambiado.semana_inicio.gt(origen)
                cambiado.loc[mascara, "casos_Dengue"] += 500
                cambiado.loc[mascara, "hum_rel_media"] += 500
                despues = construir_gold(cambiado, h)
                fila = antes.ubigeo.eq("200101") & antes.semana_inicio.eq(objetivo)
                cols = [c for c in antes if c not in ("casos_Dengue",)]
                pd.testing.assert_frame_equal(antes.loc[fila, cols], despues.loc[fila, cols])

    def test_gold_invalido_se_rechaza(self):
        gold = construir_gold(self.panel, 4)
        repetido = pd.concat([gold, gold.iloc[[0]]], ignore_index=True)
        with self.assertRaisesRegex(ValueError, "llaves únicas"):
            validar_gold(repetido, self.panel, 4)
        etiqueta = gold.copy()
        etiqueta.loc[0, "casos_Dengue"] += 1
        with self.assertRaisesRegex(ValueError, "etiquetas"):
            validar_gold(etiqueta, self.panel, 4)
        sin_clima = gold.drop(columns="hum_rel_media_media5_h4")
        with self.assertRaisesRegex(ValueError, "Esquema gold"):
            validar_gold(sin_clima, self.panel, 4)
        # La validación estructural comprueba cobertura; la causalidad de
        # valores se prueba mutando la fuente y reconstruyendo el panel.
        nulo = gold.copy()
        nulo.loc[8, "casos_lag_4"] = np.nan
        with self.assertRaisesRegex(ValueError, "Nulos"):
            validar_gold(nulo, self.panel, 4)

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
            primer = generar_gold(fuente, salida, catalogo)
            hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in salida.iterdir()}
            segundo = generar_gold(fuente, salida, catalogo)
            self.assertEqual(primer, segundo)
            self.assertEqual(hashes, {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                      for p in salida.iterdir()})
            self.assertEqual(len(hashes), 3)
            self.assertEqual(pd.read_csv(salida / "integrado_h4_gold.csv", dtype={"ubigeo": "string"}).ubigeo.nunique(), 6)
            historia = raiz / "historia.csv"
            pd.DataFrame([
                {"ubigeo": f"20010{d + 1}", "anio": y, "semana": 1, "casos_Dengue": 0}
                for d in range(6) for y in range(2012, 2017)
            ]).to_csv(historia, index=False)
            etiquetado = raiz / "gold_etiquetado"
            generar_gold(fuente, etiquetado, catalogo,
                         brote=ConfiguracionBroteEstacional(2.0, minimo_casos=2),
                         historia_path=historia)
            etiquetas_por_h = {}
            for h in (2, 4):
                g = pd.read_csv(etiquetado / f"integrado_h{h}_gold.csv",
                                dtype={"ubigeo": "string"},
                                parse_dates=["semana_inicio", "origen_inicio", "origen_cierre"])
                validar_gold(g, self.panel, h, con_brote=True, minimo_casos_brote=2)
                etiquetas_por_h[h] = g[["ubigeo", "anio", "semana", "umbral_brote_casos", "brote"]]
                self.assertTrue(g.brote.isin([0, 1]).all())
                self.assertEqual(g.loc[g.ubigeo.eq("200101") & g.anio.eq(2017), "brote"].sum(), 2)
                roto = g.copy()
                indice = roto.index[roto.brote.eq(1)][0]
                roto.loc[indice, "brote"] = 0
                with self.assertRaisesRegex(ValueError, "no coincide"):
                    validar_gold(roto, self.panel, h, con_brote=True, minimo_casos_brote=2)
            pd.testing.assert_frame_equal(etiquetas_por_h[2], etiquetas_por_h[4])
            catalogo_incorrecto = pd.read_csv(catalogo, dtype={"ubigeo": "string"})
            catalogo_incorrecto.loc[0, "distrito"] = "OTRO DISTRITO"
            catalogo_incorrecto.to_csv(catalogo, index=False)
            with self.assertRaisesRegex(ValueError, "does not match"):
                generar_gold(fuente, raiz / "geografia_invalida", catalogo)
            self.assertFalse((raiz / "geografia_invalida").exists())
            self.panel[["provincia", "distrito", "ubigeo"]].drop_duplicates().to_csv(catalogo, index=False)
            malo = self.panel.copy()
            malo.loc[0, "hum_rel_media"] = np.nan
            malo.to_csv(fuente, index=False)
            with self.assertRaisesRegex(ValueError, "incomplete|Non-numeric"):
                generar_gold(fuente, raiz / "fallido", catalogo)
            self.assertFalse((raiz / "fallido").exists())


if __name__ == "__main__":
    unittest.main()
