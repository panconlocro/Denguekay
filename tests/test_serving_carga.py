"""Carga idempotente, ceros, calendario y procedencia; sin modelos simulados."""

from dataclasses import replace
import hashlib
import io
from contextlib import redirect_stderr
from pathlib import Path
import tempfile
import unittest

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from backend_soporte import datos_muestra, entorno_bd, leer_muestra, motor_temporal
from src.db.modelos import CargaDatos, Distrito, ObservacionSemanal
from src.db.sesion import crear_motor, transaccion
from src.processing.epi_sala import load_ubigeo_catalog
from src.serving.cargar_datos import (cargar_datos, main, persistir_carga,
                                     preparar_distritos, preparar_observaciones)
from src.utils.paths import DISTRITOS_COORDS, UBIGEO_CATALOG


class TestPreparacionCarga(unittest.TestCase):
    def setUp(self):
        self.gold, self.sala = leer_muestra()

    def test_muestra_real_y_etiquetas_preservadas(self):
        registros, corte = preparar_observaciones(self.gold, self.sala)
        self.assertEqual(len(registros), 12)
        self.assertEqual(sum(r["casos"] == 0 for r in registros), 8)
        self.assertEqual(str(corte), "2025-12-27")
        for registro, original in zip(registros, self.gold.itertuples()):
            self.assertEqual(registro["casos"], original.casos_Dengue)
            self.assertEqual(registro["brote"], original.brote)
            self.assertEqual(registro["umbral_brote_casos"], original.umbral_brote_casos)
            self.assertEqual(registro["procedencia"], "Sala Situacional MINSA 2025" if original.anio == 2025 else "Excel histórico MINSA")

    def test_fecha_mmwr_inconsistente_es_rechazada(self):
        self.gold.loc[0, "semana"] += 3
        with self.assertRaisesRegex(ValueError, "calendario MMWR"):
            preparar_observaciones(self.gold, self.sala)

    def test_no_introduce_semana_53_de_sala_en_observaciones(self):
        registros, _ = preparar_observaciones(self.gold, self.sala)
        self.assertTrue(all(r["semana"] <= 52 for r in registros if r["anio"] == 2025))

    def test_sala_diferente_o_ausente_es_rechazada(self):
        for sala in (self.sala.iloc[1:], self.sala.assign(casos_Dengue=self.sala.casos_Dengue + 1)):
            with self.subTest(filas=len(sala)), self.assertRaisesRegex(ValueError, "no coinciden"):
                preparar_observaciones(self.gold, sala)

    def test_sala_y_gold_duplicados_son_rechazados(self):
        with self.assertRaisesRegex(ValueError, "duplicadas"):
            preparar_observaciones(self.gold, pd.concat([self.sala, self.sala.iloc[:1]]))
        with self.assertRaisesRegex(ValueError, "únicas"):
            preparar_observaciones(pd.concat([self.gold, self.gold.iloc[:1]]), self.sala)

    def test_sin_observacion_se_conserva_null_con_motivo(self):
        indice = self.gold.index[self.gold.anio.eq(2017)][0]
        self.gold.loc[indice, "casos_Dengue"] = float("nan")
        registros, _ = preparar_observaciones(self.gold, self.sala)
        self.assertIsNone(registros[indice]["casos"])
        self.assertIsNotNone(registros[indice]["motivo"])

    def test_casos_invalidos_o_etiquetas_invalidas_son_rechazados(self):
        indice = self.gold.index[self.gold.anio.eq(2017)][0]
        for columna, valor in (("casos_Dengue", -1), ("casos_Dengue", 1.5),
                               ("casos_Dengue", float("inf")), ("brote", 2),
                               ("umbral_brote_casos", float("nan"))):
            datos = self.gold.copy()
            datos[columna] = datos[columna].astype(float)
            datos.loc[indice, columna] = valor
            with self.subTest(columna=columna, valor=valor), self.assertRaises(ValueError):
                preparar_observaciones(datos, self.sala)

    def test_distritos_con_centroides_y_sin_poligonos(self):
        catalogo = load_ubigeo_catalog(UBIGEO_CATALOG)
        coords = pd.read_csv(DISTRITOS_COORDS)
        originales = coords.copy(deep=True)
        registros = preparar_distritos(catalogo, coords)
        self.assertEqual(len(registros), 65)
        self.assertEqual({r["ubigeo"] for r in registros}, set(catalogo.ubigeo))
        self.assertTrue(all(r["geometria"] is None and r["motivo_geometria"] for r in registros))
        pd.testing.assert_frame_equal(originales, coords)

    def test_centroide_faltante_invalido_y_catalogo_duplicado(self):
        catalogo = load_ubigeo_catalog(UBIGEO_CATALOG)
        coords = pd.read_csv(DISTRITOS_COORDS)
        with self.assertRaisesRegex(ValueError, "mismos distritos"):
            preparar_distritos(catalogo, coords.iloc[1:])
        with self.assertRaisesRegex(ValueError, "Centroide inválido"):
            preparar_distritos(catalogo, coords.assign(lat=float("nan")))
        with self.assertRaisesRegex(ValueError, "únicos"):
            preparar_distritos(pd.concat([catalogo, catalogo.iloc[:1]]), coords)


class TestPersistenciaCarga(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.carpeta_fixture = tempfile.TemporaryDirectory()
        cls.datos = datos_muestra(Path(cls.carpeta_fixture.name))

    @classmethod
    def tearDownClass(cls):
        cls.carpeta_fixture.cleanup()

    def setUp(self):
        self.carpeta = tempfile.TemporaryDirectory()
        self.motor = motor_temporal(Path(self.carpeta.name))

    def tearDown(self):
        self.motor.dispose()
        self.carpeta.cleanup()

    def test_dos_cargas_no_duplican_ni_cambian_fecha(self):
        with transaccion(self.motor) as sesion:
            primero = persistir_carga(sesion, self.datos)
        with transaccion(self.motor) as sesion:
            fecha = sesion.get(ObservacionSemanal, 1).fecha_actualizacion
            segundo = persistir_carga(sesion, self.datos)
            self.assertTrue(segundo["reutilizada"])
            self.assertEqual(primero["carga_id"], segundo["carga_id"])
            self.assertEqual(sesion.scalar(select(func.count()).select_from(Distrito)), 65)
            self.assertEqual(sesion.scalar(select(func.count()).select_from(ObservacionSemanal)), 12)
            self.assertEqual(sesion.scalar(select(func.count()).select_from(CargaDatos)), 1)
            self.assertEqual(sesion.get(ObservacionSemanal, 1).fecha_actualizacion, fecha)

    def test_gx_fallido_no_escribe(self):
        datos = replace(self.datos, validacion_gx={"exito": False})
        with self.assertRaisesRegex(ValueError, "GX"), transaccion(self.motor) as sesion:
            persistir_carga(sesion, datos)
        with transaccion(self.motor) as sesion:
            self.assertEqual(sesion.scalar(select(func.count()).select_from(CargaDatos)), 0)

    def test_lote_invalido_revierte_toda_la_carga(self):
        datos = replace(self.datos, observaciones=self.datos.observaciones + self.datos.observaciones[:1])
        with self.assertRaises(IntegrityError), transaccion(self.motor) as sesion:
            persistir_carga(sesion, datos)
        with transaccion(self.motor) as sesion:
            self.assertEqual(sesion.scalar(select(func.count()).select_from(CargaDatos)), 0)
            self.assertEqual(sesion.scalar(select(func.count()).select_from(Distrito)), 0)

    def test_extension_real_actualiza_corte_y_conserva_auditoria(self):
        gold, sala = leer_muestra()
        anterior = gold.loc[gold.anio.eq(2017)]
        registros, corte = preparar_observaciones(anterior, sala)
        hashes = {"seleccion_gold": hashlib.sha256(anterior.to_csv(index=False).encode()).hexdigest()}
        datos = replace(self.datos, observaciones=registros, fecha_corte_datos=corte, hashes=hashes)
        with transaccion(self.motor) as sesion:
            primera = persistir_carga(sesion, datos)
        with transaccion(self.motor) as sesion:
            segunda = persistir_carga(sesion, self.datos)
            self.assertNotEqual(primera["carga_id"], segunda["carga_id"])
            self.assertEqual(sesion.scalar(select(func.count()).select_from(CargaDatos)), 2)
            self.assertEqual(sesion.scalar(select(func.count()).select_from(ObservacionSemanal)), 12)
            self.assertEqual(sesion.get(ObservacionSemanal, 1).fecha_corte_datos, self.datos.fecha_corte_datos)
            self.assertEqual(sesion.get(ObservacionSemanal, 1).carga_id, segunda["carga_id"])

    def test_rechaza_base_sin_migraciones(self):
        motor = crear_motor("sqlite://")
        try:
            with self.assertRaisesRegex(ValueError, "alembic upgrade head"):
                cargar_datos(motor)
        finally:
            motor.dispose()

    def test_cli_sin_configuracion_error_controlado(self):
        salida = io.StringIO()
        with entorno_bd(""), redirect_stderr(salida):
            resultado = main([])
        self.assertEqual(resultado, 1)
        self.assertIn("Falta DATABASE_URL", salida.getvalue())


if __name__ == "__main__":
    unittest.main()
