"""PENNY Österreich: the beer category page lists only current offers."""

from __future__ import annotations

from ..const import STORE_PENNY
from ..models import Deal, parse_volume
from .nuxt import extract_nuxt_data, find_product_lists

URL = "https://www.penny.at/kategorie/bier-und-radler-13026"
PRODUCT_URL = "https://www.penny.at/produkte/{slug}"


def parse(html: str) -> list[Deal]:
    payload = extract_nuxt_data(html)
    if payload is None:
        raise ValueError("PENNY: no __NUXT_DATA__ found, page layout changed?")
    deals: dict[str, Deal] = {}
    for products in find_product_lists(payload):
        for product in products:
            deal = _to_deal(product)
            if deal:
                deals[deal.id] = deal
    return list(deals.values())


def _cents(value) -> float | None:
    return round(value / 100, 2) if isinstance(value, (int, float)) else None


def _to_deal(p: dict) -> Deal | None:
    price = p.get("price") or {}
    promo = price.get("regular") or {}
    standard = price.get("standard") or {}
    value = _cents(promo.get("value"))
    if value is None:
        return None
    brand = (p.get("brand") or {}).get("name")
    amount = p.get("amount")
    unit = p.get("volumeLabelShort") or ""
    unit_label = "Liter" if unit.lower() in ("l", "liter") else unit
    shown_amount = str(amount).replace(".", ",") if amount else ""
    package = " ".join(
        x for x in (f"{shown_amount} {unit_label}".strip(), p.get("packageLabel")) if x
    ) or None
    images = p.get("images") or []
    return Deal(
        store=STORE_PENNY,
        name=p.get("name") or "?",
        brand=brand,
        price=value,
        regular_price=_cents(standard.get("value")),
        package=package,
        volume_l=parse_volume(f"{amount} {unit}") if amount else None,
        valid_from=price.get("validityStart"),
        valid_to=price.get("validityEnd"),
        condition=promo.get("promotionText"),
        image=images[0] if images else None,
        url=PRODUCT_URL.format(slug=p["slug"]) if p.get("slug") else URL,
    )
