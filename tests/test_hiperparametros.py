"""Pruebas de la optimización de hiperparámetros (fase 3 del encargo de FE sobre E3·S4_s2)."""

import json
import math
import unittest

import numpy as np
import pandas as pd

from denguekay.model import horizon_strategies as eh
from src.modeling import hiperparametros as hp
from denguekay.model import probabilistic_output as sp
from denguekay.config.paths import GOLD_MANIFEST, SILVER_EPI_HISTORICAL, SILVER_INTEGRATED

HAY_DATOS = SILVER_INTEGRATED.exists() and GOLD_MANIFEST.exists() and SILVER_EPI_HISTORICAL.exists()


def _evaluacion(celdas=((2, 3, 4), ("temporada_2022", "temporada_2023"))):
    rng = np.random.default_rng(0)
    filas = []
    for h in celdas[0]:
        for b in celdas[1]:
            y = rng.integers(0, 2, 50)
            p = np.clip(rng.random(50), 0.01, 0.99)
            filas.append(pd.DataFrame({"horizonte": h, "bloque": b, "brote": y, "probabilidad_calibrada": p}))
    return {"datos": pd.concat(filas, ignore_index=True)}


class TestObjetivo(unittest.TestCase):
    def test_logloss(self):
        self.assertAlmostEqual(hp.logloss([1, 0], [0.8, 0.2]), -math.log(0.8))

    def test_media_de_las_seis_celdas(self):
        ev = _evaluacion()
        valor, celdas = hp.objetivo(ev)
        self.assertEqual(len(celdas), 6)
        esperado = np.mean([hp.logloss(g.brote, g.probabilidad_calibrada)
                            for _, g in ev["datos"].groupby(["horizonte", "bloque"])])
        self.assertAlmostEqual(valor, esperado)

    def test_celda_faltante_no_es_finita(self):
        valor, _ = hp.objetivo(_evaluacion(((2, 3), ("temporada_2022", "temporada_2023"))))
        self.assertTrue(math.isnan(valor))


class TestEspacioYEstudio(unittest.TestCase):
    def test_limites_y_base_encolada(self):
        import optuna

        optuna.logging.set_verbosity(optuna.logging.ERROR)
        st = optuna.create_study(sampler=optuna.samplers.TPESampler(seed=hp.SEMILLA_TPE))
        st.enqueue_trial(hp.TRIAL_0, user_attrs={"es_base": True})
        st.optimize(lambda t: sum(float(v) for v in hp.sugerir(t).values()), n_trials=30)
        self.assertEqual(st.trials[0].params, hp.TRIAL_0)
        self.assertEqual({k: v for k, v in hp.TRIAL_0.items() if k != "reg_alpha"},
                         {k: v for k, v in hp.BASE.items() if k != "reg_alpha"})
        self.assertTrue(st.trials[0].user_attrs["es_base"])
        for t in st.trials[1:]:
            for nombre, (_, lo, hi, _) in hp.ESPACIO.items():
                self.assertTrue(lo <= t.params[nombre] <= hi, nombre)
        self.assertEqual(hp.ESPACIO["max_delta_step"][1:3], (0.3, 2.0))

    def test_fallidos_quedan_registrados(self):
        import optuna

        optuna.logging.set_verbosity(optuna.logging.ERROR)
        st = optuna.create_study()

        def funcion(t):
            x = t.suggest_int("x", 0, 2)
            if x == 1:
                raise RuntimeError("falla")
            return float("nan") if x == 2 else 1.0
        for x in (0, 1, 2):
            st.enqueue_trial({"x": x})
        st.optimize(funcion, n_trials=3, catch=(Exception,))
        estados = hp.tabla_trials(st).estado.tolist()
        self.assertEqual(estados, ["COMPLETE", "FAIL", "FAIL"])


class TestConteoDelEstudio(unittest.TestCase):
    def test_termina_con_n_trials_ejecutados_y_reanuda(self):
        """El trial 0 encolado cuenta solo al ejecutarse; reanudar completa hasta ``n_trials``."""
        import tempfile
        from pathlib import Path
        from unittest import mock

        import optuna

        valores = iter([0.3, float("nan"), *np.linspace(0.2, 0.1, 20)])

        def falso(*_args, **_kwargs):
            return {"objetivo": next(valores)}

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp, \
                mock.patch.object(hp, "evaluar_configuracion", return_value=None), \
                mock.patch.object(hp, "resumen_trial", side_effect=falso):
            storage = f"sqlite:///{(Path(tmp) / 'estudio.db').as_posix()}"
            st = hp.estudio(None, None, None, None, storage, nombre="prueba", n_trials=5)
            hechos = [t for t in st.trials if t.state in (optuna.trial.TrialState.COMPLETE, optuna.trial.TrialState.FAIL)]
            self.assertEqual(len(st.trials), 5)
            self.assertEqual(len(hechos), 5)
            self.assertTrue(st.trials[0].user_attrs["es_base"])
            self.assertEqual(st.trials[1].state, optuna.trial.TrialState.FAIL)
            st = hp.estudio(None, None, None, None, storage, nombre="prueba", n_trials=7)
            self.assertEqual(len(st.trials), 7)
            st = hp.estudio(None, None, None, None, storage, nombre="prueba", n_trials=7)
            self.assertEqual(len(st.trials), 7)

    def test_huella_top_cambia_solo_con_la_seleccion(self):
        from types import SimpleNamespace as N

        a = [N(number=1, params={"x": 1.0}), N(number=2, params={"x": 2.0})]
        self.assertEqual(hp.huella_top(a), hp.huella_top([N(number=1, params={"x": 1.0}), N(number=2, params={"x": 2.0})]))
        self.assertNotEqual(hp.huella_top(a), hp.huella_top([a[0], N(number=3, params={"x": 3.0})]))


class TestAdopcion(unittest.TestCase):
    @staticmethod
    def _v(*veredictos):
        return pd.DataFrame({"candidata": "x", "horizonte": [2, 3, 4], "veredicto": list(veredictos)})

    def test_regla(self):
        simple = {**hp.BASE, "n_estimators": 100, "max_depth": 3}
        compleja = {**hp.BASE, "n_estimators": 800, "max_depth": 6}
        self.assertEqual(hp.adoptar(self._v("gana", "empate", "empate"), compleja)["adoptada"], "candidata")
        self.assertEqual(hp.adoptar(self._v(*["empate"] * 3), simple)["adoptada"], "candidata")
        self.assertEqual(hp.adoptar(self._v(*["empate"] * 3), hp.BASE)["adoptada"], "candidata")
        self.assertEqual(hp.adoptar(self._v(*["empate"] * 3), compleja)["adoptada"], "base")
        self.assertEqual(hp.adoptar(self._v("gana", "pierde", "empate"), simple)["adoptada"], "base")


@unittest.skipUnless(HAY_DATOS, "requiere silver integrado, historia, manifiesto y gold")
class TestConDatos(unittest.TestCase):
    def test_base_explicita_reproduce_los_parametros_por_defecto(self):
        """BASE (con max_delta_step = 0,7, reg_alpha = gamma = 0 explícitos) da lo mismo que los fijos heredados."""
        from denguekay.data.loading import load_integrated
        from src.modeling import fe_hiperparametros as fh
        from src.modeling import features_inicio as fi

        panel = load_integrated(SILVER_INTEGRATED)
        regla = json.loads(GOLD_MANIFEST.read_text(encoding="utf-8"))["regla_brote"]
        ins = fh.insumos(panel, regla)
        historia = pd.read_csv(SILVER_EPI_HISTORICAL, dtype={"ubigeo": "string"})
        vi = fi.VariablesInicio(panel, ins["serie"], historia, regla)
        origenes = vi.origenes(eh.origin_table(ins["matrices"][2]), ["B3"], pd.Timestamp("2021-08-28"))
        columnas = [*eh.GENERIC, *fi.COLUMNAS["B3"]]
        defecto = sp.predict_e3(ins["matrices"], 17, "S4_s2", columns=columnas, origins=origenes)
        explicita = hp.evaluar_configuracion(ins["matrices"], ins["serie"], origenes, columnas, hp.BASE)["predicciones"]
        np.testing.assert_array_equal(defecto.casos_predichos, explicita.casos_predichos)
        np.testing.assert_array_equal(defecto.probabilidad_brote, explicita.probabilidad_brote)


if __name__ == "__main__":
    unittest.main()
