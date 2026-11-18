"""District polygons for the risk map (HU0014-1): read, validate and simplify the versioned boundaries.

Source: ``data/reference/distritos_piura_limites.geojson`` (65 polygons of the Peru COD-AB, IGN, published by OCHA on
HDX under CC BY-IGO 3.0; see ``denguekay.data.ingestion.district_boundaries`` for the attribution). The file keeps the
full-resolution geometry for the rainfall mean of CHIRPS; the map only needs the outline, so the load keeps a
Douglas-Peucker simplification (0.0005 degrees, about 55 m) with 5 decimals (about 1 m), which cuts the payload from
about 2.4 MB to about 0.2 MB. Each district is simplified on its own, so shared borders can differ by up to the
tolerance; that is invisible at the zoom levels of the map and is not meant for measuring areas.

It reads the reference file only and writes nothing.
"""

import json
import math
from pathlib import Path

from denguekay.config.paths import DISTRICT_BOUNDARIES

TOLERANCE_DEGREES = 0.0005
DECIMALS = 5
GEOMETRY_TYPES = ("Polygon", "MultiPolygon")
LATITUDE_RANGE = (-6.5, -3.5)       # same bounds as the CHECK constraints of ``distrito``
LONGITUDE_RANGE = (-81.5, -79.0)


def simplify_ring(ring, tolerance=TOLERANCE_DEGREES):
    """Douglas-Peucker on a closed ring (first point = last point); the ends always stay."""
    points = [(float(x), float(y)) for x, y in ring]
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    pending = [(0, len(points) - 1)]
    while pending:
        start, end = pending.pop()
        (x1, y1), (x2, y2) = points[start], points[end]
        dx, dy = x2 - x1, y2 - y1
        length = math.hypot(dx, dy)
        farthest, index = -1.0, None
        for i in range(start + 1, end):
            x, y = points[i]
            distance = abs(dy * (x - x1) - dx * (y - y1)) / length if length else math.hypot(x - x1, y - y1)
            if distance > farthest:
                farthest, index = distance, i
        if index is not None and farthest > tolerance:
            keep[index] = True
            pending.extend([(start, index), (index, end)])
    return [point for point, kept in zip(points, keep) if kept]


def _ring(ring, ubigeo):
    if len(ring) < 4 or list(ring[0]) != list(ring[-1]):
        raise ValueError(f"Anillo no cerrado o con menos de 4 puntos en el distrito {ubigeo}")
    simplified = simplify_ring(ring)
    if len(simplified) < 4:   # a sliver the tolerance would collapse: keep the original outline
        simplified = [(float(x), float(y)) for x, y in ring]
    rounded = []
    for x, y in simplified:
        if not (math.isfinite(x) and math.isfinite(y) and LONGITUDE_RANGE[0] <= x <= LONGITUDE_RANGE[1]
                and LATITUDE_RANGE[0] <= y <= LATITUDE_RANGE[1]):
            raise ValueError(f"Coordenada fuera de Piura en el distrito {ubigeo}")
        point = [round(x, DECIMALS), round(y, DECIMALS)]
        if not rounded or rounded[-1] != point:
            rounded.append(point)
    if len(rounded) < 4 or rounded[0] != rounded[-1]:
        raise ValueError(f"El anillo del distrito {ubigeo} quedó inválido al simplificarlo")
    return rounded


def simplify_geometry(geometry, ubigeo):
    """A ``Polygon`` or ``MultiPolygon`` with its rings simplified; anything else is rejected."""
    kind = (geometry or {}).get("type")
    if kind not in GEOMETRY_TYPES:
        raise ValueError(f"El distrito {ubigeo} no tiene un Polygon o MultiPolygon: {kind!r}")
    coordinates = geometry["coordinates"]
    if kind == "Polygon":
        return {"type": kind, "coordinates": [_ring(ring, ubigeo) for ring in coordinates]}
    return {"type": kind, "coordinates": [[_ring(ring, ubigeo) for ring in polygon] for polygon in coordinates]}


def read_boundaries(path: Path = DISTRICT_BOUNDARIES):
    """{ubigeo: simplified geometry} of the versioned boundaries; ``ubigeo`` is a unique 6-digit string."""
    collection = json.loads(Path(path).read_text(encoding="utf-8"))
    geometries = {}
    for feature in collection["features"]:
        ubigeo = feature["properties"]["ubigeo"]
        if not isinstance(ubigeo, str) or len(ubigeo) != 6 or not ubigeo.isdigit():
            raise ValueError(f"UBIGEO inválido en los límites distritales: {ubigeo!r}")
        if ubigeo in geometries:
            raise ValueError(f"UBIGEO repetido en los límites distritales: {ubigeo}")
        geometries[ubigeo] = simplify_geometry(feature["geometry"], ubigeo)
    return geometries
