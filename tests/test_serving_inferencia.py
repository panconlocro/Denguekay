"""Inferencia desde la BD: vector igual a gold, probabilidad igual al pipeline, UPSERT y alertas.

Condición de la decisión (c) de la Fase 0: el vector reconstruido desde la BD
debe coincidir con gold (tolerancia 1e-9) y la probabilidad resultante con la
del pipeline actual (vectores de construir_filas_futuras sobre gold).
"""

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

import numpy as np
import pandas as pd
from sqlalchemy import delete, func, select

from backend_soporte import datos_muestra, leer_csv, migrar, motor_temporal, url_pg_pruebas
from serving_soporte import preparar_muestra
from src.db.modelos import (Alerta, Distrito, Ejecucion, ObservacionSemanal, ParametroSistema,
                            Prediccion, SemanaEpidemiologica, VersionModelo)
from src.db.sesion import crear_motor, transaccion
from src.modeling.inferencia_futura import construir_filas_futuras
from src.serving import parametros
from src.serving.almacenamiento import AlmacenamientoLocal
from src.serving.artefactos import ArtefactoInvalido, predecir_con_version
from src.serving.cargar_datos import persistir_carga
from src.serving.inferencia import (InferenciaNoDisponible, actualizar_alertas, importar_oos, inferir,
                                    seleccionar_versiones, vectores_desde_bd)
from src.serving.modelos import guardar_versiones

UBIGEOS = ["200101", "200201", "200502"]
TOLERANCIA = 1e-9


class EntornoInferencia:
    """BD migrada con la carga de fixtures (tramo contiguo 2025) y versiones entrenadas."""

    @classmethod
    def crear_motor(cls, carpeta):
        return motor_temporal(carpeta)

    @classmethod
    def setUpClass(cls):
        cls.carpeta = tempfile.TemporaryDirectory()
        ruta = Path(cls.carpeta.name)
        cls.cfg, cls.protocolo, cls.preparadas = preparar_muestra()
        datos = datos_muestra(ruta, cls.cfg.seleccion_experimental)
        # Solo el tramo contiguo 2025 S30-S52: la historia de la fixture tiene un hueco 2017-2025.
        cls.datos = replace(datos, observaciones=[o for o in datos.observaciones if o["id_semana"] >= 202530])
        cls.motor = cls.crear_motor(ruta)
        cls.almacenamiento = AlmacenamientoLocal(ruta / "storage")
        with transaccion(cls.motor) as s:
            persistir_carga(s, cls.datos)
            cls.versiones = {k: v.id_version for k, v in guardar_versiones(
                s, cls.preparadas, "run-prueba", parametros.criterios_aceptacion(s), cls.almacenamiento).items()}

    @classmethod
    def tearDownClass(cls):
        cls.motor.dispose()
        cls.carpeta.cleanup()

    def tearDown(self):
        with transaccion(self.motor) as s:
            s.execute(delete(Alerta))
            s.execute(delete(Prediccion))
            s.execute(delete(Ejecucion).where(Ejecucion.tipo == "inferencia"))
            s.execute(VersionModelo.__table__.update().values(estado="candidata", cumple_umbrales=False))

    def inferir(self, h=2, corte=None, servir=True):
        with transaccion(self.motor) as s:
            return inferir(s, h, corte, almacenamiento=self.almacenamiento, servir_no_validadas=servir)

    def predicciones(self, h=2, corte=202552):
        with transaccion(self.motor) as s:
            return {p.ubigeo: (p.estado, p.probabilidad_brote, p.nivel_riesgo, p.motivo_no_disponible, p.id_ejecucion)
                    for p in s.scalars(select(Prediccion).where(Prediccion.horizonte == h,
                                                                Prediccion.id_semana_corte == corte))}

    def test_inferencia_upsert_y_experimental(self):
        r = self.inferir(2)
        self.assertEqual((r["id_semana_corte"], r["id_semana_objetivo"]), (202552, 202601))
        self.assertTrue(r["experimental"])
        self.assertEqual(r["seleccion"], "experimental")
        self.assertEqual((r["predicciones"], r["disponibles"]), (65, 3))
        primera = self.predicciones()
        self.assertEqual({u for u, p in primera.items() if p[0] == "disponible"}, set(UBIGEOS))
        sin_datos = next(p for u, p in primera.items() if u not in UBIGEOS)
        self.assertEqual((sin_datos[0], sin_datos[1], sin_datos[2]), ("no_disponible", None, None))
        self.assertTrue(sin_datos[3])
        r2 = self.inferir(2)
        segunda = self.predicciones()
        self.assertEqual(len(segunda), 65)  # UPSERT: misma clave, sin duplicados
        self.assertTrue(all(p[4] == r2["id_ejecucion"] for p in segunda.values()))
        self.assertEqual({u: p[1] for u, p in primera.items()}, {u: p[1] for u, p in segunda.items()})
        with transaccion(self.motor) as s:
            e = s.get(Ejecucion, r2["id_ejecucion"])
            self.assertEqual((e.tipo, e.estado, e.id_semana_corte), ("inferencia", "exitosa", 202552))
            self.assertTrue(e.detalle["experimental"])
            self.assertEqual(e.detalle["versiones"]["clasificacion"], "clf-h2-v1")


class TestInferenciaSQLite(EntornoInferencia, unittest.TestCase):

    def test_vector_reconstruido_desde_bd_igual_a_gold(self):
        for h in (2, 4):
            columnas = list(self.preparadas[h, "clasificacion"].datos["variables"])
            gold = leer_csv(f"gold_temporal_h{h}_muestra.csv").set_index(["ubigeo", "semana_inicio"])
            for corte in (202533, 202540, 202552 - h):
                with self.subTest(h=h, corte=corte), transaccion(self.motor) as s:
                    filas, motivos = vectores_desde_bd(s, h, corte, columnas)
                    self.assertEqual(sorted(filas.ubigeo), UBIGEOS)
                    esperado = gold.loc[list(zip(filas.ubigeo, filas.semana_inicio)), columnas].to_numpy(float)
                    np.testing.assert_allclose(filas[columnas].to_numpy(float), esperado, rtol=0, atol=TOLERANCIA)

    def test_probabilidad_igual_al_pipeline_actual(self):
        """El pipeline anterior evaluaba vectores de construir_filas_futuras sobre gold."""
        referencia = leer_csv("referencia_2017_muestra.csv")
        for h in (2, 4):
            panel = leer_csv(f"gold_temporal_h{h}_muestra.csv")
            with transaccion(self.motor) as s:
                clf = s.get(VersionModelo, self.versiones[h, "clasificacion"])
                reg = s.get(VersionModelo, self.versiones[h, "regresion"])
                columnas = sorted(set(clf.variables) | set(reg.variables))
                for corte in (202540, 202552 - h):
                    fecha = pd.Timestamp(s.get(SemanaEpidemiologica, corte).fecha_fin)
                    actual, _ = construir_filas_futuras(panel, h, columnas=columnas, fecha_corte=fecha, referencia=referencia)
                    desde_bd, _ = vectores_desde_bd(s, h, corte, columnas)
                    actual, desde_bd = actual.sort_values("ubigeo"), desde_bd.sort_values("ubigeo")
                    for version in (clf, reg):
                        with self.subTest(h=h, corte=corte, tarea=version.tarea):
                            np.testing.assert_array_equal(
                                predecir_con_version(version, desde_bd, self.almacenamiento),
                                predecir_con_version(version, actual, self.almacenamiento))
        # La probabilidad guardada es la del modelo redondeada a numeric(5,4).
        self.inferir(4, 202548)
        with transaccion(self.motor) as s:
            clf = s.get(VersionModelo, self.versiones[4, "clasificacion"])
            filas, _ = vectores_desde_bd(s, 4, 202548, sorted(set(clf.variables)))
            esperadas = dict(zip(filas.ubigeo, predecir_con_version(clf, filas, self.almacenamiento)))
        guardadas = self.predicciones(4, 202548)
        for ubigeo, p in esperadas.items():
            self.assertAlmostEqual(guardadas[ubigeo][1], round(float(p), 4), places=9)

    def test_sin_version_utilizable_queda_no_disponible(self):
        r = self.inferir(2, servir=False)
        self.assertFalse(r["experimental"])
        self.assertEqual(r["disponibles"], 0)
        estados = {p[0] for p in self.predicciones().values()}
        motivos = {p[3] for p in self.predicciones().values()}
        self.assertEqual(estados, {"no_disponible"})
        self.assertIn("umbrales", motivos.pop())

    def test_version_activa_tiene_prioridad(self):
        with transaccion(self.motor) as s:
            for clave in ((2, "clasificacion"), (2, "regresion")):
                v = s.get(VersionModelo, self.versiones[clave])
                v.cumple_umbrales, v.estado = True, "activa"
        r = self.inferir(2)
        self.assertFalse(r["experimental"])
        self.assertEqual(r["seleccion"], "activa")
        with transaccion(self.motor) as s:
            versiones, motivo = seleccionar_versiones(s, 2, False)
            self.assertIsNone(motivo)
            self.assertEqual(versiones["clasificacion"].estado, "activa")

    def test_errores_de_solicitud(self):
        for h, corte, mensaje in ((3, None, "h=3"), (2, 202601, "No hay observaciones"), (2, 209901, "calendario")):
            with self.subTest(h=h, corte=corte), self.assertRaisesRegex(InferenciaNoDisponible, mensaje):
                self.inferir(h, corte)
        with self.assertRaises(ValueError):
            self.inferir(5)

    def test_artefacto_alterado_se_rechaza(self):
        ruta = Path(self.carpeta.name) / "storage" / "modelos" / "clf-h2-v1.json"
        original = ruta.read_bytes()
        try:
            ruta.write_bytes(original + b" ")
            with self.assertRaisesRegex(ArtefactoInvalido, "SHA-256"):
                self.inferir(2)
            ruta.unlink()
            with self.assertRaisesRegex(ArtefactoInvalido, "No se encontró"):
                self.inferir(2)
        finally:
            ruta.write_bytes(original)

    def test_alertas_cambio_y_retiro(self):
        with transaccion(self.motor) as s:
            ejecucion = Ejecucion(tipo="inferencia", estado="exitosa")
            s.add(ejecucion)
            s.flush()

            def predecir(corte, probabilidad, nivel):
                base = {"ubigeo": "200101", "id_semana_corte": corte, "id_semana_objetivo": corte + 2,
                        "horizonte": 2, "id_ejecucion": ejecucion.id_ejecucion}
                existente = s.scalar(select(Prediccion).where(Prediccion.id_semana_corte == corte,
                                                              Prediccion.ubigeo == "200101", Prediccion.horizonte == 2))
                if existente is None:
                    existente = Prediccion(**base, estado="disponible")
                    s.add(existente)
                existente.probabilidad_brote, existente.nivel_riesgo = probabilidad, nivel
                s.flush()
                return actualizar_alertas(s, 2, corte)

            def alertas():
                return [(a.prediccion.id_semana_corte, a.nivel, a.estado, a.cambio)
                        for a in s.scalars(select(Alerta).order_by(Alerta.id_alerta))]

            predecir(202540, 0.6, "alto")
            self.assertEqual(alertas(), [(202540, "alto", "activa", "nueva")])
            predecir(202541, 0.8, "muy_alto")
            self.assertEqual(alertas()[-1], (202541, "muy_alto", "activa", "sube_nivel"))
            self.assertEqual(alertas()[0][2], "retirada")
            predecir(202542, 0.8, "muy_alto")
            self.assertEqual(alertas()[-1][3], "se_mantiene")
            predecir(202543, 0.55, "alto")
            self.assertEqual(alertas()[-1][3], "baja_nivel")
            predecir(202544, 0.3, "medio")
            self.assertEqual(sum(a[2] == "activa" for a in alertas()), 0)
            retirada = s.scalar(select(Alerta).where(Alerta.estado == "retirada").order_by(Alerta.id_alerta.desc()))
            self.assertIsNotNone(retirada.fecha_retiro)
            self.assertIn("202544", retirada.motivo)
            predecir(202544, 0.9, "muy_alto")  # recálculo del mismo corte
            self.assertEqual(alertas()[-1], (202544, "muy_alto", "activa", "nueva"))
            predecir(202544, 0.1, "bajo")
            self.assertEqual(alertas()[-1][2], "retirada")

    def test_importa_oos_como_cortes_pasados(self):
        with transaccion(self.motor) as s:
            versiones = {k: s.get(VersionModelo, v) for k, v in self.versiones.items()}
            resumen = importar_oos(s, self.protocolo, (2, 4), self.cfg, versiones)
            self.assertTrue(resumen)
            total = s.scalar(select(func.count()).select_from(Prediccion))
            esperado = len(self.protocolo.predicciones.loc[
                self.protocolo.predicciones.variante.eq(self.cfg.variantes["clasificacion"])])
            self.assertEqual(total, esperado)
            p = s.scalar(select(Prediccion).limit(1))
            self.assertIsNone(p.id_version_clasificador)
            self.assertEqual(p.estado, "disponible")
            e = s.get(Ejecucion, p.id_ejecucion)
            self.assertEqual(e.detalle["origen"], "oos_protocolo")
            self.assertIn(e.detalle["bloque"], {r["bloque"] for r in resumen})
            self.assertTrue(e.detalle["experimental"])
            self.assertEqual(s.scalar(select(func.count()).select_from(Alerta)), 0)
            # Reimportar no duplica (UPSERT por la clave del documento).
            importar_oos(s, self.protocolo, (2, 4), self.cfg, versiones)
            self.assertEqual(s.scalar(select(func.count()).select_from(Prediccion)), total)

    def test_seleccion_experimental_incompleta(self):
        with transaccion(self.motor) as s:
            s.get(ParametroSistema, "seleccion_experimental").valor = {"2": {"clasificacion": "clf-h2-v1"}}
        try:
            r = self.inferir(2)
            self.assertEqual(r["disponibles"], 0)
            self.assertIn("h=2", r["motivo"])
        finally:
            with transaccion(self.motor) as s:
                s.get(ParametroSistema, "seleccion_experimental").valor = {
                    str(h): v for h, v in self.cfg.seleccion_experimental.items()}


@unittest.skipUnless(url_pg_pruebas(), "Sin DENGUEKAY_PG_PRUEBAS_URL: se omite la inferencia en PostgreSQL")
class TestInferenciaPostgreSQL(EntornoInferencia, unittest.TestCase):
    @classmethod
    def crear_motor(cls, carpeta):
        motor = crear_motor(url_pg_pruebas())
        migrar(motor, "base")
        migrar(motor)
        return motor

    @classmethod
    def tearDownClass(cls):
        migrar(cls.motor, "base")
        super().tearDownClass()


if __name__ == "__main__":
    unittest.main()
