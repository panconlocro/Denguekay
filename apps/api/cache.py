"""Bounded DTO cache, with TTL and the revision of publications in the database."""

from collections import OrderedDict
from copy import deepcopy
from threading import Lock
from time import monotonic


class ReadCache:
    def __init__(self, ttl=10, capacity=128):
        self.ttl, self.capacity = ttl, capacity
        self.entries = OrderedDict()
        self.lock = Lock()

    def get(self, key):
        with self.lock:
            entry = self.entries.get(key)
            if entry is None:
                return None
            instant, value = entry
            if monotonic() - instant >= self.ttl:
                del self.entries[key]
                return None
            self.entries.move_to_end(key)
            return deepcopy(value)

    def save(self, key, value):
        with self.lock:
            self.entries[key] = (monotonic(), deepcopy(value))
            self.entries.move_to_end(key)
            while len(self.entries) > self.capacity:
                self.entries.popitem(last=False)

    def clear(self):
        with self.lock:
            self.entries.clear()
