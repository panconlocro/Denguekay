"""Caché acotada de DTO, con TTL y revisión de publicaciones en la BD."""

from collections import OrderedDict
from copy import deepcopy
from threading import Lock
from time import monotonic


class CacheLecturas:
    def __init__(self, ttl=10, capacidad=128):
        self.ttl, self.capacidad = ttl, capacidad
        self.entradas = OrderedDict()
        self.cerrojo = Lock()

    def obtener(self, clave):
        with self.cerrojo:
            entrada = self.entradas.get(clave)
            if entrada is None:
                return None
            instante, valor = entrada
            if monotonic() - instante >= self.ttl:
                del self.entradas[clave]
                return None
            self.entradas.move_to_end(clave)
            return deepcopy(valor)

    def guardar(self, clave, valor):
        with self.cerrojo:
            self.entradas[clave] = (monotonic(), deepcopy(valor))
            self.entradas.move_to_end(clave)
            while len(self.entradas) > self.capacidad:
                self.entradas.popitem(last=False)

    def limpiar(self):
        with self.cerrojo:
            self.entradas.clear()
