"""Carga OE2 con filas reales: provincia, distrito, calendario, observaciones e ingesta."""

from dataclasses import replace
from datetime import date
from pathlib import Path
import tempfile
import unittest

from sqlalchemy import func, select

from backend_soporte import datos_muestra, leer_muestra, motor_temporal
from src.db.modelos import (Distrito, Ejecucion, ObservacionSemanal, ParametroSistema, Provincia,
                            SemanaEpidemiologica)
from src.db.sesion import transaccion
from src.serving import cargar_datos as carga
from src.serving.configuracion import configuracion_servicio


class TestCargaOE2(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = tempfile.TemporaryDirectory()
        cls.datos = datos_muestra(Path(cls.fixture.name), configuracion_servicio().seleccion_experimental)

    @classmethod
    def tearDownClass(cls):
        cls.fixture.cleanup()

    def setUp(self):
        self.carpeta = tempfile.TemporaryDirectory()
        self.motor = motor_temporal(Path(self.carpeta.name))

    def tearDown(self):
        self.motor.dispose()
        self.carpeta.cleanup()

    def cargar(self, datos=None):
        with transaccion(self.motor) as s:
            return carga.persistir_carga(s, datos or self.datos)

    def contar(self, s, modelo):
        return s.scalar(select(func.count()).select_from(modelo))

    def test_carga_completa_y_trazable(self):
        r = self.cargar()
        self.assertFalse(r["reutilizada"])
        self.assertEqual((r["provincias"], r["distritos"], r["observaciones"]), (8, 65, 75))
        self.assertEqual(r["id_semana_corte"], 202552)
        with transaccion(self.motor) as s:
            self.assertEqual(self.contar(s, Provincia), 8)
            piura = s.get(Distrito, "200101")
            self.assertEqual((piura.ubigeo_provincia, piura.poblacion_censo_2017), ("2001", 158495))
            self.assertIsInstance(piura.ubigeo, str)
            self.assertEqual(s.get(Provincia, "2001").nombre, "Piura")
            o2017 = s.get(ObservacionSemanal, ("200101", 201720))
            o2025 = s.get(ObservacionSemanal, ("200101", 202552))
            self.assertEqual((o2017.fuente_casos, o2025.fuente_casos), ("excel_historico", "sala_situacional"))
            self.assertEqual(o2025.estado_cobertura, "verificado")
            self.assertIsNotNone(o2025.temp_media_c)
            self.assertLessEqual(o2025.temp_min_c, o2025.temp_media_c)
            ejecucion = s.get(Ejecucion, r["id_ejecucion"])
            self.assertEqual((ejecucion.tipo, ejecucion.estado, ejecucion.id_semana_corte), ("ingesta", "exitosa", 202552))
            self.assertEqual(ejecucion.detalle["hashes_entrada"], self.datos.hashes)
            self.assertTrue(ejecucion.detalle["validacion_gx"]["exito"])
            self.assertEqual(o2025.id_ejecucion, ejecucion.id_ejecucion)
            seleccion = s.get(ParametroSistema, "seleccion_experimental").valor
            self.assertEqual(seleccion["4"]["clasificacion"], "clf-h4-v1")

    def test_ceros_se_conservan_y_casos_de_gold_coinciden(self):
        self.cargar()
        silver = leer_muestra()["silver"]
        with transaccion(self.motor) as s:
            casos = {(o.ubigeo, o.id_semana): o.casos_dengue for o in s.scalars(select(ObservacionSemanal))}
        for fila in silver.itertuples():
            self.assertEqual(casos[fila.ubigeo, fila.anio * 100 + fila.semana], fila.casos_Dengue)
        self.assertIn(0, casos.values())

    def test_calendario_mmwr_incluye_semana_53_y_temporada(self):
        semanas = {s["id_semana"]: s for s in self.datos.semanas}
        s53 = semanas[202553]
        self.assertEqual((s53["fecha_inicio"], s53["fecha_fin"]), (date(2025, 12, 28), date(2026, 1, 3)))
        self.assertEqual(semanas[202601]["fecha_inicio"], date(2026, 1, 4))
        self.assertEqual((semanas[202534]["temporada"], semanas[202535]["temporada"]), (2025, 2026))
        self.assertTrue(all(s["fecha_fin"].toordinal() - s["fecha_inicio"].toordinal() == 6 for s in self.datos.semanas))

    def test_idempotente_y_actualizacion_sin_duplicados(self):
        primera = self.cargar()
        segunda = self.cargar()
        self.assertTrue(segunda["reutilizada"])
        self.assertEqual(primera["id_ejecucion"], segunda["id_ejecucion"])
        distritos = [{**d, "nombre": d["nombre"].upper()} for d in self.datos.distritos]
        tercera = self.cargar(replace(self.datos, distritos=distritos, hashes={**self.datos.hashes, "otra": "x"}))
        self.assertNotEqual(tercera["id_ejecucion"], primera["id_ejecucion"])
        with transaccion(self.motor) as s:
            self.assertEqual(self.contar(s, ObservacionSemanal), 75)
            self.assertEqual(self.contar(s, Distrito), 65)
            self.assertEqual(s.get(Distrito, "200101").nombre, "PIURA")
            self.assertEqual(self.contar(s, Ejecucion), 2)

    def test_semilla_experimental_no_pisa_un_valor_existente(self):
        self.cargar()
        with transaccion(self.motor) as s:
            s.get(ParametroSistema, "seleccion_experimental").valor = {"2": {"clasificacion": "x", "regresion": "y"}}
        self.cargar(replace(self.datos, hashes={**self.datos.hashes, "otra": "x"}))
        with transaccion(self.motor) as s:
            self.assertEqual(s.get(ParametroSistema, "seleccion_experimental").valor["2"]["clasificacion"], "x")

    def test_rechaza_gx_fallido(self):
        with self.assertRaisesRegex(ValueError, "GX"):
            self.cargar(replace(self.datos, validacion_gx={"exito": False}))

    def test_fuentes_inconsistentes_se_rechazan(self):
        muestra = leer_muestra()
        ubigeo_corto = muestra["silver"].copy()
        ubigeo_corto.loc[ubigeo_corto.index[0], "ubigeo"] = "20010"
        casos = [
            ("sala", muestra["sala"].assign(casos_Dengue=muestra["sala"].casos_Dengue + 1), "Sala"),
            ("gold", muestra["gold"].iloc[1:], "etiqueta"),
            ("gold", muestra["gold"].assign(casos_Dengue=muestra["gold"].casos_Dengue + 1), "silver y gold"),
            ("silver", muestra["silver"].assign(semana=muestra["silver"].semana + 1), "MMWR"),
            ("cobertura", muestra["cobertura"].iloc[1:], "cobertura"),
            ("silver", ubigeo_corto, "seis dígitos"),
        ]
        for clave, valor, mensaje in casos:
            entradas = {**muestra, clave: valor}
            with self.subTest(clave=clave, mensaje=mensaje), self.assertRaisesRegex(ValueError, mensaje):
                carga.preparar_observaciones(entradas["silver"], entradas["cobertura"], entradas["gold"], entradas["sala"])

    def test_exige_esquema_y_registra_fallos(self):
        from sqlalchemy.engine import URL
        from src.db.sesion import crear_motor
        vacio = crear_motor(URL.create("sqlite", database=str(Path(self.carpeta.name) / "vacia.db")))
        try:
            with self.assertRaisesRegex(ValueError, "alembic upgrade head"):
                carga.cargar_datos(vacio)
        finally:
            vacio.dispose()
        carga.registrar_fallo(self.motor, "ingesta", ValueError("fuente ilegible"), {"huella": "h"})
        with transaccion(self.motor) as s:
            fallida = s.scalar(select(Ejecucion).where(Ejecucion.estado == "fallida"))
            self.assertEqual(fallida.tipo, "ingesta")
            self.assertIn("fuente ilegible", fallida.mensaje_error)

    def test_semanas_cubren_objetivos_futuros(self):
        self.cargar()
        with transaccion(self.motor) as s:
            ultima = s.scalar(select(func.max(SemanaEpidemiologica.id_semana)))
        self.assertGreaterEqual(ultima, 202605)


if __name__ == "__main__":
    unittest.main()
