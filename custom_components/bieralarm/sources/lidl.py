"""Lidl Österreich: the 'Bieraktion' category embeds product data as JSON."""

from __future__ import annotations

from datetime import datetime
import html as html_lib
import json
import re
from zoneinfo import ZoneInfo

from ..const import STORE_LIDL
from ..models import Deal, looks_like_beer, parse_alcohol, parse_volume

URL = "https://www.lidl.at/c/bieraktion/s10067981"
BASE = "https://www.lidl.at"

_GRID = re.compile(r'data-grid-data="([^"]*)"')
_VIENNA = ZoneInfo("Europe/Vienna")


def parse(html: str, region: str = "1") -> list[Deal]:
    blocks = _GRID.findall(html)
    if not blocks and "lidl" not in html.lower():
        raise ValueError("Lidl: unexpected page, layout changed?")
    deals: dict[str, Deal] = {}
    for raw in blocks:
        try:
            data = json.loads(html_lib.unescape(raw))
        except ValueError:
            continue
        for item in data if isinstance(data, list) else [data]:
            deal = _to_deal(item, region)
            if deal:
                deals[deal.id] = deal
    return list(deals.values())


def _date(ts) -> str | None:
    if isinstance(ts, (int, float)) and ts > 0:
        return datetime.fromtimestamp(ts, tz=_VIENNA).date().isoformat()
    return None


def _to_deal(item: dict, region: str) -> Deal | None:
    if not isinstance(item, dict):
        return None
    regions = [str(r) for r in item.get("regions") or []]
    if regions and region not in regions:
        return None
    region_prices = (item.get("regionsPrices") or {}).get(region) or {}
    current = region_prices.get("currentPrice") or item.get("price") or {}
    price = current.get("price")
    if price is None:
        return None
    keyfacts = item.get("keyfacts") or {}
    category = keyfacts.get("wonCategoryPrimary") or ""
    brand = (item.get("brand") or {}).get("name")
    title = keyfacts.get("title") or item.get("title") or item.get("fullTitle") or "?"
    if "bier" not in category.lower() and not looks_like_beer(title, brand):
        return None
    packaging = (current.get("packaging") or {}).get("text")
    discount = current.get("discount") or {}
    lidl_plus = (region_prices.get("currentLidlPlusPrice") or {}).get("price") or {}
    condition = discount.get("discountText")
    if lidl_plus.get("price") is not None:
        plus = f"Lidl Plus: € {lidl_plus['price']:.2f}".replace(".", ",")
        condition = f"{condition} · {plus}" if condition else plus
    badges = (item.get("stockAvailability") or {}).get("badgeInfo") or {}
    badge_text = ", ".join(b.get("text", "") for b in badges.get("badges", []) if b.get("text"))
    path = item.get("canonicalUrl") or item.get("canonicalPath")
    return Deal(
        store=STORE_LIDL,
        name=title,
        brand=brand,
        price=float(price),
        regular_price=discount.get("deletedPrice") or current.get("oldPrice"),
        package=packaging,
        volume_l=parse_volume(packaging),
        valid_from=_date(item.get("storeStartDate")),
        valid_to=_date(item.get("storeEndDate")),
        condition=" · ".join(x for x in (condition, badge_text) if x) or None,
        image=item.get("image"),
        url=f"{BASE}{path}" if path and path.startswith("/") else (path or URL),
        alcohol=parse_alcohol(title, (item.get("image_V1") or {}).get("accessibility")),
    )
