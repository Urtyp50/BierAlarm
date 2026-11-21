"""HOFER: the weekly catalog on katalog.hofer.at (a Publitas flip book) with a public PDF download.

- flipbook_kw{week}_{yy}_0/            the viewer page, it links the PDF
- flipbook_kw{week}_{yy}_0/spreads.json  the text of every page (used to skip catalogs without beer)

HOFER tiles: a small brand line ('GÖSSER') above the product name ('MÄRZEN'),
package lines below, and the big price at the bottom right of the tile
('per Dose', '0,74'). Each price belongs to the nearest product name above it
in the same column, so every product on the page is considered, not only beer.
"""

from __future__ import annotations

from datetime import date, timedelta
import io
import re

from ..models import Deal, looks_like_beer, parse_alcohol, parse_volume
from .pdf_layout import VERSION as LAYOUT_VERSION, _Frag, _fragments

VERSION = f"hofer-2/{LAYOUT_VERSION}"
BASE = "https://katalog.hofer.at"

_PDF = re.compile(r'https://view\.publitas\.com/[^"\'\s<>]+?/pdfs/[^"\'\s<>]+?\.pdf[^"\'\s<>]*')
_BADGES = {"TIEFPREIS", "AKTION", "GRATIS", "UVP", "PFAND", "FREI", "NEU", "STATT", "NUR"}
_PRICE = re.compile(r"^\d{1,3},\d{2}$")
_CAPS = re.compile(r"^[A-ZÄÖÜ0-9][A-ZÄÖÜ0-9 &./'+-]*$")
_HEADER = re.compile(
    r"(?:(AB)\s+)?[A-Z]{2}\.\s*(\d{1,2})\.(\d{1,2})\.(?:\s*(UND|BIS)\s*[A-Z]{2}\.\s*(\d{1,2})\.(\d{1,2})\.)?"
)
_SINGLE_REGULAR = re.compile(r"VERKAUF\s*€\s*(\d+,\d{2})", re.I)
_COUNT = re.compile(r"(\d{1,2})\s*x\s*\d", re.I)
_MULTI = re.compile(r"^\d{1,2}\s?\+\s?\d{1,2}$")
_PERCENT = re.compile(r"^-\s?\d{1,2}\s?%$")
_EACH = re.compile(r"^bei\s+\d+\s+\w+\s+je$", re.I)

PRICE_SIZE = 25.0
NAME_SIZE = (9.0, 10.5)
BRAND_SIZE = (5.5, 6.5)
PACKAGE_SIZE = (7.0, 8.5)
MAX_ABOVE = 360  # the product photo sits between name and price
COLUMN = (-15, 170)  # price.x - name.x


def flipbook_urls(today: date) -> list[str]:
    """Next week's catalog (online from the weekend) and this week's."""
    urls = []
    for day in (today + timedelta(days=7), today):
        iso = day.isocalendar()
        urls.append(f"{BASE}/flipbook_kw{iso.week}_{iso.year % 100}_0/")
    return urls


def find_pdf(html: str) -> str | None:
    match = _PDF.search(html)
    return match.group(0).replace("&amp;", "&") if match else None


def beer_pages(spreads: list) -> list[int]:
    """0-based PDF page numbers whose text mentions beer."""
    pages = []
    for spread in spreads or []:
        for page in spread.get("pages", []):
            text = page.get("text") or ""
            if re.search(r"bier|märzen|pils|radler|lager|zwickl|weizen|gösser|zipfer|stiegl|ottakringer|egger|puntigamer|kaiser|wieselburger|schwechater|hirter|trumer|heineken", text, re.I):
                pages.append(int(page.get("number", 0)) - 1)
    return sorted({p for p in pages if p >= 0})


def parse(pdf_bytes: bytes, url: str, year: int, pages: list[int] | None = None) -> list[Deal]:
    from pypdf import PdfReader  # noqa: PLC0415 - heavy import, only when needed

    reader = PdfReader(io.BytesIO(pdf_bytes))
    wanted = pages if pages is not None else range(len(reader.pages))
    deals: dict[str, Deal] = {}
    for index in wanted:
        if 0 <= index < len(reader.pages):
            for deal in _page_deals(_fragments(reader.pages[index]), url, year):
                old = deals.get(deal.id)
                if old is None or _detail(deal) > _detail(old):  # the cover repeats offers in short
                    deals[deal.id] = deal
    return list(deals.values())


def _detail(deal: Deal) -> int:
    return len(deal.package or "") + len(deal.condition or "") + (10 if deal.regular_price else 0)


def _within(size: float, bounds: tuple[float, float]) -> bool:
    return bounds[0] <= size <= bounds[1]


def _products(frags: list[_Frag]) -> list[dict]:
    """Every product name: optional brand line + one or more name lines in capitals."""
    lines = [
        f for f in frags
        if _within(f.size, NAME_SIZE) and _CAPS.match(f.text) and len(f.text) > 2 and f.text not in _BADGES
    ]
    brands = [f for f in frags if _within(f.size, BRAND_SIZE) and _CAPS.match(f.text)]
    used: set[int] = set()
    products = []
    for line in sorted(lines, key=lambda f: -f.y):
        if id(line) in used:
            continue
        block = [line]
        used.add(id(line))
        for other in sorted(lines, key=lambda f: -f.y):  # 'NATURGOLD' + 'ALKOHOLFREI'
            if id(other) not in used and abs(other.x - line.x) <= 3 and 0 < block[-1].y - other.y <= 12:
                block.append(other)
                used.add(id(other))
        brand = next(
            (b for b in brands if abs(b.x - line.x) <= 3 and 0 < b.y - line.y <= 13), None
        )
        products.append({"brand": brand, "lines": block, "x": line.x, "y": block[-1].y})
    return products


def _page_deals(frags: list[_Frag], url: str, year: int) -> list[Deal]:
    prices = [f for f in frags if f.size >= PRICE_SIZE and _PRICE.match(f.text)]
    if not prices:
        return []
    products = _products(frags)
    valid_from, valid_to = _validity(frags, year)
    owner: dict[int, dict] = {}
    for price in prices:
        candidates = [
            p for p in products
            if 20 < p["y"] - price.y <= MAX_ABOVE and COLUMN[0] <= price.x - p["x"] <= COLUMN[1]
        ]
        if candidates:  # the closest column to the left, then the closest above
            owner[id(price)] = max(candidates, key=lambda p: (round(p["x"] / 20), -(p["y"] - price.y)))
    deals = []
    for product in products:
        name = _name(product)
        if not looks_like_beer(name):
            continue
        mine = [p for p in prices if owner.get(id(p)) is product]
        if not mine:
            continue
        price = max(mine, key=lambda p: p.y)  # the first price below the name
        package = [
            f for f in frags
            if _within(f.size, PACKAGE_SIZE) and abs(f.x - product["x"]) <= 3
            and 0 < product["y"] - f.y <= 45
        ]
        lines = [f.text for f in sorted(package, key=lambda f: -f.y)]
        alcohol = parse_alcohol(*lines)
        # 'zzgl. Pfand € 0,25' and '5,2% Vol.' are not part of the package
        package_text = " ".join(t for t in lines if not re.match(r"zzgl|.*%\s*Vol", t, re.I)) or None
        deal = _build(name, price, package_text, frags, prices, url, valid_from, valid_to)
        if deal:
            deal.alcohol = alcohol
            deals.append(deal)
    return deals


def _name(product: dict) -> str:
    parts = ([product["brand"].text] if product["brand"] else []) + [f.text for f in product["lines"]]
    text = " ".join(parts)
    return " ".join(w if any(c.isdigit() for c in w) else w.capitalize() for w in text.split()).replace(
        "/n", "/N"
    )


def _near(f: _Frag, price: _Frag, prices: list[_Frag]) -> bool:
    """Text belongs to this price tile: above it and closer to it than to any other price."""
    dy, dx = f.y - price.y, f.x - price.x
    if not (0 < dy <= 95 and -135 <= dx <= 70):
        return False
    return all(
        not (0 < f.y - p.y <= 95) or _dist(f, p) >= _dist(f, price) for p in prices if p is not price
    )


def _dist(f: _Frag, price: _Frag) -> float:
    """Tile texts sit left of / above their price; text right of a price belongs to the next tile."""
    dx = f.x - price.x
    return (abs(dx) if dx <= 0 else 2 * dx) + (f.y - price.y)


def _build(name, price, package_text, frags, prices, url, valid_from, valid_to) -> Deal | None:  # noqa: ANN001
    value = float(price.text.replace(",", "."))
    near = [f for f in frags if f is not price and _near(f, price, prices)]
    unit = next((f.text[4:].lower() for f in near if f.text.lower().startswith("per ")), "")
    regular = None
    conditions = []
    for f in sorted(near, key=lambda f: -f.y):
        text = f.text
        if m := _SINGLE_REGULAR.search(text):
            regular = float(m.group(1).replace(",", "."))
        elif _PRICE.match(text) and 7 <= f.size <= 12:  # 'per Dose 1,59' or '1,19 UVP'
            regular = regular or float(text.replace(",", "."))
        elif _MULTI.match(text) or _PERCENT.match(text):
            conditions.insert(0, text.replace(" ", ""))
        elif _EACH.match(text):
            conditions.append(text.capitalize())
            unit = unit or "flasche"  # 'bei 12 Flaschen je': the price is per bottle
    volume = parse_volume(package_text)
    count = _COUNT.search(package_text or "")
    if count and unit in ("dose", "flasche", "stück"):
        volume = parse_volume(re.sub(r"\d{1,2}\s*x\s*", "", package_text, flags=re.I))
    if count and regular and regular < value and unit in ("kiste", "packung", "träger"):
        regular = round(regular * int(count.group(1)), 2)  # single bottle price -> crate
    return Deal(
        store="hofer",
        name=name,
        price=value,
        regular_price=regular if regular and regular > value else None,
        package=f"{package_text} (per {unit.capitalize()})" if unit and package_text else package_text,
        volume_l=volume,
        condition=" ".join(conditions) or None,
        valid_from=valid_from,
        valid_to=valid_to,
        url=url,
        source="pdf",
    )


def _validity(frags: list[_Frag], year: int) -> tuple[str | None, str | None]:
    """Page header like 'MO. 23.11. BIS DO. 26.11.', 'FR. 20.11. UND SA. 21.11.' or 'AB FR. 20.11.'."""
    header = " ".join(f.text for f in frags if f.size >= 18 and f.y > 760 and "X.X" not in f.text)
    match = _HEADER.search(header)
    if not match:
        return None, None
    _ab, d1, m1, _join, d2, m2 = match.groups()
    try:
        start = date(year, int(m1), int(d1))
        end = date(year + (1 if int(m2) < int(m1) else 0), int(m2), int(d2)) if d2 else None
    except ValueError:
        return None, None
    return start.isoformat(), end.isoformat() if end else None
