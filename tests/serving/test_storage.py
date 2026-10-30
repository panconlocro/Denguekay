"""Storage port: SupabaseStorage over a simulated HTTP transport (never a real service) and the factory."""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import httpx

from denguekay.serving.artifacts import InvalidArtifact
from denguekay.serving.package import load_package
from denguekay.serving.storage import LocalStorage, StorageError, SupabaseStorage, storage_from_environment

URL = "https://proyecto-prueba.supabase.invalid"
KEY = "sb_secret_clave_de_prueba"


def sha(content):
    return hashlib.sha256(content).hexdigest()


class FakeStorageServer:
    """Minimal Supabase Storage: private objects, x-upsert, 400 with statusCode 404 for a missing one."""

    def __init__(self):
        self.objects = {}
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        path = request.url.path
        prefix = "/storage/v1/object/"
        if not path.startswith(prefix):
            return httpx.Response(404)
        name = path[len(prefix):]
        if request.method == "GET":
            if not name.startswith("authenticated/"):
                return httpx.Response(400, json={"statusCode": "400", "error": "público no permitido"})
            name = name[len("authenticated/"):]
            if name not in self.objects:
                return httpx.Response(400, json={"statusCode": "404", "error": "not_found", "message": "Object not found"})
            return httpx.Response(200, content=self.objects[name])
        if request.method == "HEAD":
            return httpx.Response(200 if name in self.objects else 400)
        if request.method == "POST":
            if name in self.objects and request.headers.get("x-upsert") != "true":
                return httpx.Response(400, json={"statusCode": "409", "error": "Duplicate"})
            self.objects[name] = request.content
            return httpx.Response(200, json={"Key": name})
        return httpx.Response(405)


class TestSupabaseStorage(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.server = FakeStorageServer()
        self.storage = SupabaseStorage(URL + "/", KEY, Path(self.folder.name) / "cache",
                                       transport=httpx.MockTransport(self.server))

    def tearDown(self):
        self.storage.close()
        self.folder.cleanup()

    def test_guardar_leer_y_existir_con_las_rutas_de_la_api(self):
        self.assertFalse(self.storage.exists("modelos/p1/manifest.json"))
        self.storage.save("modelos/p1/manifest.json", b'{"a": 1}')
        self.assertTrue(self.storage.exists("modelos/p1/manifest.json"))
        self.assertEqual(self.storage.read("modelos/p1/manifest.json"), b'{"a": 1}')
        head, post, head2, get = self.server.requests
        self.assertEqual((post.method, post.url.path), ("POST", "/storage/v1/object/modelos/p1/manifest.json"))
        self.assertEqual(post.headers["x-upsert"], "true")
        self.assertEqual(post.headers["content-type"], "application/json")
        self.assertEqual((head.method, head.url.path), ("HEAD", "/storage/v1/object/modelos/p1/manifest.json"))
        self.assertEqual(get.url.path, "/storage/v1/object/authenticated/modelos/p1/manifest.json")
        for request in self.server.requests:
            self.assertEqual(request.headers["apikey"], KEY)
            self.assertNotIn("authorization", request.headers)  # an sb_secret_ key is not a JWT

    def test_la_clave_heredada_jwt_va_tambien_como_bearer(self):
        server = FakeStorageServer()
        storage = SupabaseStorage(URL, "eyJhbGciOiJIUzI1NiJ9.prueba.firma", Path(self.folder.name) / "c2",
                                  transport=httpx.MockTransport(server))
        storage.exists("modelos/x.json")
        self.assertEqual(server.requests[0].headers["authorization"], "Bearer eyJhbGciOiJIUzI1NiJ9.prueba.firma")
        storage.close()

    def test_objeto_inexistente_y_errores_del_servicio(self):
        with self.assertRaises(FileNotFoundError):
            self.storage.read("modelos/no/existe.json")
        failing = SupabaseStorage(URL, KEY, Path(self.folder.name) / "c3",
                                  transport=httpx.MockTransport(lambda r: httpx.Response(403, json={"error": "x"})))
        for action in (lambda: failing.read("modelos/a.json"), lambda: failing.exists("modelos/a.json"),
                       lambda: failing.save("modelos/a.json", b"x")):
            with self.assertRaises(StorageError) as error:
                action()
            self.assertNotIn(KEY, str(error.exception))
        failing.close()

    def test_rutas_invalidas_y_configuracion_incompleta(self):
        for path in ("otro/a.json", "modelos/../a.json", "/modelos/a.json", "modelos"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.storage.read(path)
        with self.assertRaises(ValueError):
            SupabaseStorage("", KEY)
        with self.assertRaises(ValueError):
            SupabaseStorage(URL, " ")

    def test_cache_verificada_por_sha256(self):
        content = b"booster"
        self.server.objects["modelos/p1/b.json"] = content
        self.assertEqual(self.storage.read("modelos/p1/b.json", sha256=sha(content)), content)
        self.assertEqual(self.storage.read("modelos/p1/b.json", sha256=sha(content)), content)
        gets = [r for r in self.server.requests if r.method == "GET"]
        self.assertEqual(len(gets), 1)  # the second read comes from the cache
        cached = Path(self.folder.name) / "cache" / sha(content)
        cached.write_bytes(b"alterado")  # a corrupt cache entry is discarded and downloaded again
        self.assertEqual(self.storage.read("modelos/p1/b.json", sha256=sha(content)), content)
        self.assertEqual(cached.read_bytes(), content)
        self.server.objects["modelos/p1/c.json"] = b"otro"
        self.assertEqual(self.storage.read("modelos/p1/c.json", sha256=sha(b"esperado")), b"otro")
        self.assertFalse((Path(self.folder.name) / "cache" / sha(b"esperado")).exists())  # never cached

    def test_el_cargador_de_paquetes_rechaza_un_archivo_alterado_en_storage(self):
        file = b"contenido"
        manifest = {"version_manifiesto": 1, "version_minima_denguekay": "0", "codigo_paquete": "p1",
                    "archivos": {"b": {"ruta": "modelos/p1/b.json", "sha256": sha(file)}}}
        manifest_bytes = json.dumps(manifest).encode()
        self.server.objects["modelos/p1/manifest.json"] = manifest_bytes
        self.server.objects["modelos/p1/b.json"] = b"alterado"
        with self.assertRaises(InvalidArtifact):
            load_package(self.storage, "modelos/p1/manifest.json", sha(manifest_bytes))
        self.server.objects["modelos/p1/b.json"] = file
        package = load_package(self.storage, "modelos/p1/manifest.json", sha(manifest_bytes))
        self.assertEqual(package.files["b"], file)


class TestFabricaDeStorage(unittest.TestCase):
    def test_elige_el_adaptador(self):
        self.assertIsInstance(storage_from_environment("local"), LocalStorage)
        with tempfile.TemporaryDirectory() as folder:
            storage = storage_from_environment("supabase", {"SUPABASE_URL": URL, "SUPABASE_SECRET_KEY": KEY,
                                                            "STORAGE_CACHE_DIR": folder})
            self.assertIsInstance(storage, SupabaseStorage)
            self.assertEqual(storage.cache, Path(folder))
            storage.close()
        with self.assertRaises(ValueError):
            storage_from_environment("supabase", {})
        with self.assertRaises(ValueError):
            storage_from_environment("s3")


if __name__ == "__main__":
    unittest.main()
