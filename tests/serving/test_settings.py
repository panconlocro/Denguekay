"""config.yaml gives the defaults and the environment replaces them (CORS_ORIGINS, SERVIR_NO_VALIDADAS, STORAGE_BACKEND)."""

import tempfile
import unittest
from pathlib import Path

import yaml

from denguekay.config.paths import CONFIG
from denguekay.serving.settings import parse_origins, service_settings


class TestConfiguracionPorEntorno(unittest.TestCase):
    def test_valores_por_defecto_de_config_yaml(self):
        cfg = service_settings(CONFIG, environ={})
        self.assertEqual(cfg.cors_origenes, ["http://localhost:5173"])
        self.assertIs(cfg.servir_no_validadas, True)
        self.assertEqual(cfg.almacenamiento, "local")

    def test_el_entorno_reemplaza_a_config_yaml(self):
        cfg = service_settings(CONFIG, environ={
            "CORS_ORIGINS": " https://denguekay.vercel.app, http://localhost:5173 ,https://denguekay.vercel.app",
            "SERVIR_NO_VALIDADAS": "False", "STORAGE_BACKEND": "Supabase"})
        self.assertEqual(cfg.cors_origenes, ["https://denguekay.vercel.app", "http://localhost:5173"])
        self.assertIs(cfg.servir_no_validadas, False)
        self.assertEqual(cfg.almacenamiento, "supabase")
        self.assertEqual(service_settings(CONFIG, environ={"CORS_ORIGINS": " ", "STORAGE_BACKEND": ""}).almacenamiento,
                         "local")

    def test_valores_invalidos_del_entorno(self):
        for variable, value in (("CORS_ORIGINS", "*"), ("CORS_ORIGINS", "https://a.app/"),
                                ("CORS_ORIGINS", "denguekay.app"), ("CORS_ORIGINS", "https://a.app/ruta"),
                                ("SERVIR_NO_VALIDADAS", "quizas"), ("STORAGE_BACKEND", "s3")):
            with self.subTest(variable=variable, value=value), self.assertRaises(ValueError):
                service_settings(CONFIG, environ={variable: value})

    def test_cors_en_config_yaml_debe_ser_una_lista_valida(self):
        with self.assertRaises(ValueError):
            parse_origins(5)
        with self.assertRaises(ValueError):
            parse_origins([])
        base = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))["serving"]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "config.yaml"
            path.write_text(yaml.safe_dump({"serving": {**base, "almacenamiento": "ftp"}}), encoding="utf-8")
            with self.assertRaises(ValueError):
                service_settings(path, environ={})

    def test_la_huella_de_publicacion_no_depende_del_despliegue(self):
        local = service_settings(CONFIG, environ={})
        deployed = service_settings(CONFIG, environ={"CORS_ORIGINS": "https://denguekay.vercel.app",
                                                     "STORAGE_BACKEND": "supabase"})
        self.assertEqual(local.publication_options(), deployed.publication_options())


if __name__ == "__main__":
    unittest.main()
