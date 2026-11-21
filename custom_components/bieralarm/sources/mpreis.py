"""MPREIS: the 'Bier in Aktion' page embeds its products in window.__INITIAL_STATE__."""

from __future__ import annotations

import json
import re

from ..const import STORE_MPREIS
from ..models import Deal, parse_alcohol, parse_volume

URL = "https://www.mpreis.at/m/bier-in-aktion"
PRODUCT_URL = "https://www.mpreis.at/shop/p/{slug}"

_STATE = re.compile(r'window\.__INITIAL_STATE__\s*=\s*("(?:[^"\\]|\\.)*")', re.S)
# The category 'Bier' on mpreis.at also holds a few soft drinks from breweries.
_NOT_BEER = ("frucade", "limonade", "kracherl", "eistee", "cola", "mineral", "saft")


def parse(html: str) -> list[Deal]:
    match = _STATE.search(html)
    if not match:
        raise ValueError("MPREIS: no __INITIAL_STATE__ found, page layout changed?")
    state = json.loads(json.loads(match.group(1)))
    products = ((state.get("shop") or {}).get("_product")) or {}
    deals: dict[str, Deal] = {}
    for product in products.values():
        deal = _to_deal(product)
        if deal:
            deals[deal.id] = deal
    return list(deals.values())


def _to_deal(p: dict) -> Deal | None:
    if not isinstance(p, dict):
        return None
    name = (p.get("name") or "").strip()
    brand = (p.get("brand") or "").strip() or None
    if any(w in f"{brand or ''} {name}".lower() for w in _NOT_BEER):
        return None
    labels = [str(c).lower() for c in p.get("categoryLabels") or []]
    if labels and not any("bier" in c or "radler" in c for c in labels):
        return None
    price = p.get("price") or {}
    original = price.get("originalPriceObject") or {}
    effective = original.get("effective", price.get("discountAmount"))
    if effective is None:
        return None
    regular = original.get("original", price.get("amount"))
    promo = price.get("promotionType") or original.get("promotionType")
    volume = parse_volume(p.get("packagingUnit")) or parse_volume(name)
    slug = p.get("slug")
    return Deal(
        store=STORE_MPREIS,
        name=name or "Bier",
        brand=brand,
        price=float(effective),
        regular_price=float(regular) if regular else None,
        package=_package(name, volume),
        volume_l=volume,
        condition=promo or None,
        image=p.get("media"),
        url=PRODUCT_URL.format(slug=slug) if slug else URL,
        alcohol=parse_alcohol(name),
    )


def _package(name: str, volume: float | None) -> str | None:
    """'Märzen 12x 0,33 Liter' -> '12x 0,33 Liter'; 'Kiste 0,5 Liter' (10 l) -> 'Kiste 20x 0,5 Liter'."""
    match = re.search(r"((?:kiste|tray)\s+)?(\d+\s*x\s*)?\d+(?:,\d+)?\s*(?:liter|l)\b.*", name, re.I)
    if not match:
        return None
    package = match.group(0).strip()
    single = parse_volume(package)
    if volume and single and not match.group(2) and volume > single * 1.5:
        count = round(volume / single)
        package = re.sub(r"(\d+(?:,\d+)?\s*(?:liter|l)\b)", rf"{count}x \1", package, count=1, flags=re.I)
    return package
