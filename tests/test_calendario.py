"""Regresión del desfase ISO/MMWR en la frontera de 2025 y años siguientes."""

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from src.eda.calidad import semana_epi_mmwr as calendario_eda
from src.eda.carga import cargar_integrado
from src.processing.agregacion_semanal import AGG_DIARIO_A_SEMANAL, agregar_a_semanal
from src.utils.calendario import semana_epi_mmwr
from src.validation.expectations_integrado import prepare_dataset
from tests.test_update_dataset_module import model_row


class CalendarioTests(unittest.TestCase):
    def test_fronteras_de_anio_y_recurrencia_conservan_indice(self):
        fechas = pd.Series(pd.to_datetime([
            "2025-12-21", "2025-12-28", "2026-01-04", "2026-01-11",
            "2031-12-28", "2032-01-04", "2036-12-28", "2037-01-04",
        ]), index=[8, 6, 4, 2, 9, 7, 5, 3])
        esperado = [(2025, 52), (2025, 53), (2026, 1), (2026, 2),
                    (2031, 53), (2032, 1), (2036, 53), (2037, 1)]
        resultado = semana_epi_mmwr(fechas)
        self.assertEqual(list(resultado.itertuples(index=False, name=None)), esperado)
        pd.testing.assert_index_equal(resultado.index, fechas.index)
        self.assertIs(calendario_eda, semana_epi_mmwr)

    def test_todo_2026_tiene_numeracion_consecutiva_correcta(self):
        fechas = pd.Series(pd.date_range("2026-01-04", periods=52, freq="W-SUN"))
        resultado = semana_epi_mmwr(fechas)
        self.assertTrue(resultado.anio_epi.eq(2026).all())
        self.assertEqual(resultado.semana_epi.tolist(), list(range(1, 53)))

    def test_agregacion_climatica_conserva_semana_53_y_descarta_parcial(self):
        diario = pd.DataFrame({"time": pd.date_range("2025-12-21", periods=23),
                               "id_distrito": 1})
        for columna in set(AGG_DIARIO_A_SEMANAL) - {"time"}:
            diario[columna] = 1.0
        copia = diario.copy(deep=True)
        distritos = pd.DataFrame([{"id_distrito": 1, "provincia": "Paita",
                                   "distrito": "Amotape", "lat": -4.83, "lon": -81.0}])
        resultado = agregar_a_semanal(diario, distritos)
        self.assertEqual(list(resultado[["anio", "semana"]].itertuples(index=False, name=None)),
                         [(2025, 52), (2025, 53), (2026, 1)])
        self.assertEqual(resultado.semana_inicio.dt.strftime("%Y-%m-%d").tolist(),
                         ["2025-12-21", "2025-12-28", "2026-01-04"])
        self.assertEqual(resultado.precip_total_mm.tolist(), [7.0, 7.0, 7.0])
        pd.testing.assert_frame_equal(diario, copia)

    def test_integrado_y_carga_aceptan_calendario_oficial_sin_mutar(self):
        segunda = model_row(1)
        segunda.update(anio=2026, semana_inicio="2026-01-04")
        original = pd.DataFrame([model_row(53), segunda])
        copia = original.copy(deep=True)
        resultado = prepare_dataset(original)
        self.assertEqual(resultado.semana.tolist(), [53, 1])
        pd.testing.assert_frame_equal(original, copia)
        with tempfile.TemporaryDirectory() as carpeta:
            archivo = Path(carpeta) / "integrado.csv"
            original.to_csv(archivo, index=False)
            antes = archivo.read_bytes()
            self.assertEqual(cargar_integrado(archivo).semana.tolist(), [53, 1])
            self.assertEqual(archivo.read_bytes(), antes)

    def test_integrado_y_carga_rechazan_convencion_antigua(self):
        for fila in [model_row(53), {**model_row(1), "anio": 2026,
                                    "semana_inicio": "2026-01-04"}]:
            with self.subTest(fecha=fila["semana_inicio"]):
                fecha = pd.Timestamp(fila["semana_inicio"])
                iso = (fecha + pd.Timedelta(days=3)).isocalendar()
                fila.update(anio=iso.year, semana=iso.week)
                incorrecto = pd.DataFrame([fila])
                with self.assertRaisesRegex(ValueError, "MMWR"):
                    prepare_dataset(incorrecto)
                with tempfile.TemporaryDirectory() as carpeta:
                    archivo = Path(carpeta) / "integrado.csv"
                    incorrecto.to_csv(archivo, index=False)
                    with self.assertRaisesRegex(ValueError, "MMWR"):
                        cargar_integrado(archivo)


if __name__ == "__main__":
    unittest.main()
