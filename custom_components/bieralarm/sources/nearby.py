"""Which supermarket branches are near home? Uses OpenStreetMap (Overpass API).

Only a bounding box around a rounded home position is sent to OpenStreetMap; the
exact distances are computed locally.
"""

from __future__ import annotations

from math import asin, cos, radians, sin, sqrt

from ..const import STORE_BILLA, STORE_BILLA_PLUS, STORE_LIDL, STORE_MPREIS, STORE_PENNY

URL = "https://overpass-api.de/api/interpreter"

# OpenStreetMap brand:wikidata ids of the chains BierAlarm reads.
WIKIDATA = {
    STORE_PENNY: "Q284688",
    STORE_LIDL: "Q151954",
    STORE_MPREIS: "Q873491",
    STORE_BILLA: "Q537781",
    STORE_BILLA_PLUS: "Q115431077",
}
_KM_PER_DEG_LAT = 111.32
_MARGIN_KM = 2.0  # rounding the home position moves it by up to ~0.8 km


def build_query(lat: float, lon: float, radius_km: float, stores: list[str]) -> str:
    ids = "|".join(WIKIDATA[s] for s in stores if s in WIKIDATA)
    lat_r, lon_r = round(lat, 2), round(lon, 2)
    dlat = (radius_km + _MARGIN_KM) / _KM_PER_DEG_LAT
    dlon = (radius_km + _MARGIN_KM) / (_KM_PER_DEG_LAT * max(cos(radians(lat_r)), 0.1))
    bbox = f"{lat_r - dlat:.4f},{lon_r - dlon:.4f},{lat_r + dlat:.4f},{lon_r + dlon:.4f}"
    return f'[out:json][timeout:30];nwr["shop"]["brand:wikidata"~"^({ids})$"]({bbox});out center tags;'


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    lat1, lon1, lat2, lon2 = map(radians, (lat1, lon1, lat2, lon2))
    a = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371.0 * asin(sqrt(a))


def parse(data: dict, lat: float, lon: float, radius_km: float) -> dict[str, list[dict]]:
    """Branches within the radius per store, nearest first."""
    by_id = {v: k for k, v in WIKIDATA.items()}
    found: dict[str, list[dict]] = {}
    for el in data.get("elements", []):
        tags = el.get("tags") or {}
        store = by_id.get(tags.get("brand:wikidata"))
        point = el if "lat" in el else el.get("center") or {}
        if not store or "lat" not in point:
            continue
        km = distance_km(lat, lon, point["lat"], point["lon"])
        if km > radius_km:
            continue
        street = " ".join(x for x in (tags.get("addr:street"), tags.get("addr:housenumber")) if x)
        city = tags.get("addr:city") or tags.get("addr:place") or ""
        found.setdefault(store, []).append(
            {
                "name": tags.get("name") or tags.get("brand") or store,
                "address": ", ".join(x for x in (street, city) if x),
                "distance_km": round(km, 1),
            }
        )
    for branches in found.values():
        branches.sort(key=lambda b: b["distance_km"])
    return found
