"""Database fixtures may reuse empty schema bytes, but never a test's mutable state."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from sqlalchemy import delete, func, inspect, select

from backend_support import migrar, motor_temporal
from denguekay.db.models import SystemParameter
from denguekay.db.session import transaction


class TestSQLiteFixtureIsolation(unittest.TestCase):
    def test_copies_are_independent_and_reopening_keeps_only_their_own_changes(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            folders = [root / name for name in ("first", "second", "third")]
            for folder in folders:
                folder.mkdir()
            engines = []
            try:
                first, second = [motor_temporal(folder) for folder in folders[:2]]
                engines.extend((first, second))
                with transaction(first) as session:
                    seed_count = session.scalar(select(func.count()).select_from(SystemParameter))
                    self.assertGreater(seed_count, 0)
                    session.execute(delete(SystemParameter))
                with transaction(second) as session:
                    self.assertEqual(session.scalar(select(func.count()).select_from(SystemParameter)), seed_count)
                first.dispose()
                reopened = motor_temporal(folders[0])
                engines.append(reopened)
                with transaction(reopened) as session:
                    self.assertEqual(session.scalar(select(func.count()).select_from(SystemParameter)), 0)
                migrar(reopened, "base")
                self.assertFalse(inspect(reopened).has_table("parametro_sistema"))
                self.assertTrue(inspect(second).has_table("parametro_sistema"))
                third = motor_temporal(folders[2])
                engines.append(third)
                with transaction(third) as session:
                    self.assertEqual(session.scalar(select(func.count()).select_from(SystemParameter)), seed_count)
            finally:
                for engine in engines:
                    engine.dispose()
