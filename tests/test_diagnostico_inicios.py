"""Pruebas del diagnóstico de inicios (fase 1 del encargo de FE sobre E3·S4_s2)."""

import json
import unittest

import numpy as np
import pandas as pd

from src.modeling import diagnostico_inicios as di
from src.utils.paths import GOLD_MANIFEST, SILVER_EPI_HISTORICO, SILVER_INTEGRADO

HAY_DATOS = SILVER_INTEGRADO.exists() and GOLD_MANIFEST.exists() and SILVER_EPI_HISTORICO.exists()


def _resumen(medias: dict, ic: dict) -> pd.DataFrame:
    filas = []
    for (tipo, periodo), m in medias.items():
        lo, hi = ic.get((tipo, periodo), (m - 1, m + 1))
        filas.append({"familia": "f", "variable": "v", "ventana": "origen_2_4", "tipo_control": tipo,
                      "periodo_resumen": periodo, "inicios": 10, "media": m, "media_inicio": np.nan,
                      "media_control": np.nan, "ic95_inferior": lo, "ic95_superior": hi})
    return pd.DataFrame(filas)


class TestConsistencia(unittest.TestCase):
    CELDAS = [(t, p) for t in ("semana", "distrito") for p in ("2017", "2018_2021", "2017_2021")]

    def test_observada(self):
        r = _resumen({c: 1.0 for c in self.CELDAS},
                     {("semana", "2017_2021"): (0.2, 1.5), ("distrito", "2017_2021"): (0.1, 1.2)})
        self.assertEqual(di.consistencia(r).veredicto.iloc[0], "observada")

    def test_solo_2017(self):
        medias = {c: 1.0 for c in self.CELDAS} | {("semana", "2018_2021"): -0.5}
        ic = {("semana", "2017"): (0.5, 2), ("distrito", "2017"): (0.3, 2)}
        self.assertEqual(di.consistencia(_resumen(medias, ic)).veredicto.iloc[0], "hipotesis_solo_2017")

    def test_mismo_signo_sin_ic_que_excluya_cero(self):
        r = _resumen({c: 1.0 for c in self.CELDAS}, {})
        self.assertEqual(di.consistencia(r).veredicto.iloc[0], "no_observada")

    def test_celda_faltante(self):
        medias = {c: 1.0 for c in self.CELDAS} | {("distrito", "2017"): np.nan}
        self.assertEqual(di.consistencia(_resumen(medias, {})).veredicto.iloc[0], "no_evaluable")


class TestPerfiles(unittest.TestCase):
    def test_diferencia_contra_media_de_controles(self):
        semanas = pd.date_range("2018-01-07", periods=10, freq="7D")
        estado = pd.DataFrame([(u, s, v) for u, base in (("000001", 0), ("000002", 100)) for s, v in
                               zip(semanas, base + np.arange(10))], columns=["ubigeo", "semana_inicio", "x"])
        inicios = pd.DataFrame({"id_inicio": [0], "ubigeo": ["000001"], "inicio": [semanas[5]],
                                "periodo": ["2018_2021"], "temporada": [2018]})
        pares = pd.DataFrame({"id_inicio": [0, 0], "tipo": ["semana", "semana"], "tipo_efectivo": ["semana"] * 2,
                              "ubigeo_control": ["000002", "000002"], "semana_control": [semanas[6], semanas[8]]})
        t = di.perfiles(estado, inicios, pares, ["x"], rezagos=(1, 2))
        # inicio en k=1 vale 4; controles valen 100+5 y 100+7 → media 106.
        fila = t[t.k.eq(1)].iloc[0]
        self.assertEqual(fila.valor_inicio, 4)
        self.assertEqual(fila.valor_control, 106)
        self.assertEqual(fila.diferencia, -102)
        self.assertEqual(fila.n_controles, 2)


@unittest.skipUnless(HAY_DATOS, "requiere silver integrado, manifiesto y etiquetas")
class TestConDatos(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from src.eda.carga import cargar_integrado
        from src.modeling import fe_hiperparametros as fh

        cls.panel = cargar_integrado(SILVER_INTEGRADO)
        regla = json.loads(GOLD_MANIFEST.read_text(encoding="utf-8"))["regla_brote"]
        cls.serie = fh.insumos(cls.panel, regla)["serie"]
        cls.corte = di.corte_diseno(cls.serie)
        cls.estado = di.estado_semanal(cls.panel, cls.serie, cls.corte)
        cls.inicios = di.inicios_limpios(cls.serie)

    def _alterar(self, desde: pd.Timestamp):
        panel, serie = self.panel.copy(), self.serie.copy()
        fp = pd.to_datetime(panel.semana_inicio) >= desde
        fs = serie.semana_inicio >= desde
        panel.loc[fp, "casos_Dengue"] = panel.loc[fp, "casos_Dengue"] * 3 + 7
        for c in di.CLIMA:
            panel.loc[fp, c] = panel.loc[fp, c] + 5
        serie.loc[fs, "casos_Dengue"] = serie.loc[fs, "casos_Dengue"] * 3 + 7
        serie.loc[fs, "brote"] = 1 - serie.loc[fs, "brote"]
        return panel, serie

    def test_corte_y_conteo_de_inicios(self):
        self.assertEqual(self.corte, pd.Timestamp("2021-08-28"))
        diseno = self.inicios[self.inicios.verificable & self.inicios.temporada.isin(di.TEMPORADAS_DISENO)]
        self.assertEqual(len(diseno), 71)
        self.assertEqual(int(self.inicios.temporada.isin([2022, 2023]).sum()), 95)

    def test_no_fuga_despues_del_corte(self):
        """Alterar casos, brote y clima desde 2021-09-05 no cambia ningún estado anterior."""
        desde = pd.Timestamp("2021-09-05")
        panel, serie = self._alterar(desde)
        otro = di.estado_semanal(panel, serie, self.corte)
        sel = self.estado.semana_inicio < desde
        columnas = [c for c in self.estado if c not in ("ubigeo", "semana_inicio")]
        pd.testing.assert_frame_equal(self.estado.loc[sel, columnas].reset_index(drop=True),
                                      otro.loc[sel, columnas].reset_index(drop=True))
        self.assertFalse(np.allclose(self.estado.loc[~sel, "propia_log_casos"], otro.loc[~sel, "propia_log_casos"]))

    def test_estado_de_w_solo_usa_semanas_hasta_w(self):
        """Antes del corte, salvo núcleo y anomalías (ajustados al corte), el estado de w no ve w+1."""
        desde = pd.Timestamp("2019-06-02")
        panel, serie = self._alterar(desde)
        otro = di.estado_semanal(panel, serie, self.corte)
        sel = self.estado.semana_inicio < desde
        columnas = [c for c in self.estado if c not in ("ubigeo", "semana_inicio")
                    and not c.startswith("nucleo_") and not c.endswith("_anomalia")]
        pd.testing.assert_frame_equal(self.estado.loc[sel, columnas].reset_index(drop=True),
                                      otro.loc[sel, columnas].reset_index(drop=True))

    def test_controles(self):
        elegibles = di.semanas_elegibles(self.serie)
        self.assertTrue(elegibles.temporada.isin(di.TEMPORADAS_DISENO).all())
        s = self.serie.sort_values(["ubigeo", "semana_inicio"])
        previo = s.groupby("ubigeo").brote.transform(lambda x: x.rolling(9, min_periods=1).max())
        claves = set(zip(s.ubigeo[previo.eq(0)], s.semana_inicio[previo.eq(0)]))
        self.assertTrue(all((u, w) in claves for u, w in zip(elegibles.ubigeo, elegibles.semana_inicio)))
        diseno = self.inicios[self.inicios.verificable & self.inicios.temporada.isin(di.TEMPORADAS_DISENO)]
        tercil = di.terciles(self.serie, self.corte)
        pares = di.controles(diseno, elegibles, tercil)
        info = pares.merge(diseno[["id_inicio", "ubigeo", "temporada", "semana_clima"]], on="id_inicio").merge(
            elegibles.rename(columns={"ubigeo": "ubigeo_control", "semana_inicio": "semana_control",
                                      "temporada": "temporada_control", "semana_clima": "semana_clima_control"}),
            on=["ubigeo_control", "semana_control"])
        self.assertTrue(info.semana_clima.eq(info.semana_clima_control).all())
        dist = info[info.tipo_efectivo.eq("distrito")]
        self.assertTrue(dist.ubigeo.eq(dist.ubigeo_control).all())
        self.assertTrue(dist.temporada.ne(dist.temporada_control).all())
        ter = info[info.tipo_efectivo.eq("tercil")]
        self.assertTrue(ter.ubigeo.map(tercil).eq(ter.ubigeo_control.map(tercil)).all())
        self.assertEqual(set(pares.groupby("tipo").id_inicio.nunique()), {len(diseno)})

    def test_controles_con_respaldo_por_tercil(self):
        diseno = self.inicios[self.inicios.verificable & self.inicios.temporada.isin(di.TEMPORADAS_DISENO)]
        pares = di.controles(diseno, di.semanas_elegibles(self.serie), di.terciles(self.serie, self.corte),
                             minimo_distrito=99)
        dist = pares[pares.tipo.eq("distrito")]
        self.assertTrue(dist.tipo_efectivo.eq("tercil").all())
        self.assertEqual(dist.id_inicio.nunique(), len(diseno))


if __name__ == "__main__":
    unittest.main()
