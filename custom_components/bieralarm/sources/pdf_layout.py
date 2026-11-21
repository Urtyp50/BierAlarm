"""Read beer offers from a BILLA / BILLA PLUS PDF leaflet without AI.

Each offer is a tile: the big price ('1380' = € 13,80) sits at the bottom left,
name and package text above it on the right, conditions ('6+6', 'BEI 12 DOSEN JE',
'1 DOSE € 1.39') around it. The text comes with page positions, so every small
text is given to the nearest big price below it.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date
import io
import re

from ..models import Deal, looks_like_beer, parse_volume

VERSION = "layout-1"  # bump when the reader changes, so cached leaflets are read again
PRICE_MIN_SIZE = 25.0  # font size of the big tile prices
TEXT_MAX_SIZE = 10.0
MAX_ABOVE = 190  # how far (pt) the name may sit above its price

_PRICE = re.compile(r"^\d{2,4}$")
_REGULAR = re.compile(r"(?:1\s*(?:DOSE|FL\.?|FLASCHE|STK\.?|PKG\.?|KISTE|TRÄGER)\s*€|statt)\s*(\d+[.,]\d{2})", re.I)
_DEAL_WORDS = re.compile(r"^(?:BEI|AB|JE|AKTION|STATT|NUR)\b", re.I)
_BADGE = re.compile(r"^[A-ZÄÖÜ ]{3,}$")  # 'KURZE ZEIT', 'NUR' ...
_PERCENT = re.compile(r"^-\s?\d{1,2}\s?%$")
_MULTI = re.compile(r"^\d{1,2}\s?\+\s?\d{1,2}$")
_FOOTNOTE = re.compile(r"(\d)\)$")
_FOOTNOTE_TEXT = re.compile(r"^(\d)\)\s*(.+)$")
_DATES = re.compile(
    r"(\d{1,2})\.\s?(\d{1,2})\.?\s*BIS\s*(?:[A-ZÄÖÜa-zäöü]{2,10}\.?,?\s*)?(\d{1,2})\.\s?(\d{1,2})\.", re.I
)


@dataclass
class _Frag:
    x: float
    y: float
    size: float
    text: str


def _fragments(page) -> list[_Frag]:
    frags: list[_Frag] = []

    def visit(text, cm, tm, font, size):  # noqa: ANN001 - pypdf callback
        text = (text or "").replace(" ", " ").replace("\xa0", " ").strip()
        if not text:
            return
        x = cm[4] + tm[4] * cm[0]
        y = cm[5] + tm[5] * cm[3]
        scale = abs(tm[3] or tm[0] or 1) * abs(cm[3] or cm[0] or 1)
        frags.append(_Frag(x, y, (size or 0) * scale, text))

    page.extract_text(visitor_text=visit)
    return frags


def _validity(texts: list[str], year: int) -> tuple[str | None, str | None]:
    found = Counter(m.groups() for t in texts for m in _DATES.finditer(t))
    if not found:
        return None, None
    d1, m1, d2, m2 = (int(v) for v in found.most_common(1)[0][0])
    try:
        start = date(year, m1, d1)
        end = date(year + 1 if m2 < m1 else year, m2, d2)
    except ValueError:
        return None, None
    return start.isoformat(), end.isoformat()


def parse(pdf_bytes: bytes, store: str, url: str, year: int) -> list[Deal]:
    from pypdf import PdfReader  # noqa: PLC0415 - heavy import, only when needed

    reader = PdfReader(io.BytesIO(pdf_bytes))
    pages = [_fragments(p) for p in reader.pages]
    valid_from, valid_to = _validity([f.text for frags in pages for f in frags], year)
    deals: dict[str, Deal] = {}
    for frags in pages:
        for deal in _page_deals(frags, store, url):
            deal.valid_from, deal.valid_to = valid_from, valid_to
            deals[deal.id] = deal
    return list(deals.values())


def _page_deals(frags: list[_Frag], store: str, url: str) -> list[Deal]:
    """Start from each beer name, then find its price below and its conditions."""
    prices = [f for f in frags if f.size >= PRICE_MIN_SIZE and _PRICE.match(f.text)]
    if not prices:
        return []
    notes = {m.group(1): m.group(2) for f in frags if (m := _FOOTNOTE_TEXT.match(f.text))}
    small = [f for f in frags if 3 <= f.size <= TEXT_MAX_SIZE]
    names = [f for f in small if not _is_deal_text(f.text) and not _REGULAR.search(f.text)]
    deals: list[Deal] = []
    used: set[int] = set()
    for seed in names:
        if id(seed) in used or not looks_like_beer(seed.text):
            continue
        block = _name_block(seed, names)
        used.update(id(f) for f in block)
        top, bottom = max(f.y for f in block), min(f.y for f in block)
        left = min(f.x for f in block)
        price = _closest_price(prices, left, bottom)
        if price is None:
            continue
        package: list[_Frag] = []
        column = list(block)
        for f in sorted(names, key=lambda f: -f.y):  # top to bottom, each line must join the column
            if (
                f.size < seed.size - 0.3 and price.y - 3 <= f.y < bottom and bottom - f.y <= 45
                and any(abs(f.y - c.y) <= 20 and _aligned(f, c) for c in column)
            ):
                package.append(f)
                column.append(f)
        deal_texts = [
            f for f in small + [f for f in frags if f.size > TEXT_MAX_SIZE and f.size < PRICE_MIN_SIZE]
            if (_is_deal_text(f.text) or _REGULAR.search(f.text))
            and 0 < f.y - price.y <= 150 and -15 <= f.x - price.x <= 45
        ]
        deal = _build(price, block, package, deal_texts, notes, store, url)
        if deal:
            deals.append(deal)
    return deals


def _name_block(seed: _Frag, names: list[_Frag]) -> list[_Frag]:
    """Lines of the same size right above / below each other ('Otta-', 'kringer', 'Helles')."""
    block = [seed]
    grown = True
    while grown:
        grown = False
        for f in names:
            if f in block or abs(f.size - seed.size) > 0.3:
                continue
            if any(abs(f.y - b.y) <= seed.size * 1.6 and _aligned(f, b) for b in block):
                block.append(f)
                grown = True
    return block


def _aligned(a: _Frag, b: _Frag) -> bool:
    """Same text column: left, right or centre aligned (width estimated from the text length)."""
    wa, wb = len(a.text) * a.size * 0.5, len(b.text) * b.size * 0.5
    return (
        abs(a.x - b.x) <= 8
        or abs((a.x + wa) - (b.x + wb)) <= 12
        or abs((a.x + wa / 2) - (b.x + wb / 2)) <= 8
    )


def _closest_price(prices: list[_Frag], x: float, y: float) -> _Frag | None:
    best = None
    for p in prices:
        dy, dx = y - p.y, abs(x - p.x)
        if -5 <= dy <= MAX_ABOVE and dx <= 130:
            cost = dy + 2 * dx
            if best is None or cost < best[0]:
                best = (cost, p)
    return best[1] if best else None


def _build(price, block, package, deal_texts, notes, store, url) -> Deal | None:  # noqa: ANN001
    footnote = None
    name_parts = []
    for f in sorted(block, key=lambda f: -f.y):
        text = f.text
        if m := _FOOTNOTE.search(text):
            footnote = notes.get(m.group(1))
            text = text[: m.start()].strip()
        name_parts.append(text)
    name = _join(name_parts)
    if not looks_like_beer(name):
        return None
    package_text = " ".join(f.text for f in sorted(package, key=lambda f: -f.y)) or None
    regular = None
    conditions = []
    for f in sorted(deal_texts, key=lambda f: -f.y):
        if m := _REGULAR.search(f.text):
            regular = float(m.group(1).replace(",", "."))
        else:
            conditions.append(f.text)
    value = int(price.text) / 100
    volume = parse_volume(package_text)
    if volume and volume < 2 and value > 5 and "kiste" in (package_text or "").lower():
        volume = parse_volume(re.sub(r"\(.*?\)", "", package_text))
    condition = " ".join(_order(conditions)) or None
    if footnote:
        condition = f"{condition} · {footnote}" if condition else footnote
    return Deal(
        store=store,
        name=name,
        price=round(value, 2),
        regular_price=regular if regular and regular > value else None,
        package=package_text,
        volume_l=volume,
        condition=condition,
        url=url,
        source="pdf",
    )


def _is_deal_text(text: str) -> bool:
    return bool(_DEAL_WORDS.match(text) or _MULTI.match(text) or _PERCENT.match(text) or _BADGE.match(text))


def _order(conditions: list[str]) -> list[str]:
    """'6+6' / '-39 %' first, then 'BEI 12 DOSEN JE'."""
    head = [c for c in conditions if _MULTI.match(c) or _PERCENT.match(c)]
    rest = [c for c in conditions if c not in head and _DEAL_WORDS.match(c) and c.upper() not in ("AKTION", "NUR")]
    return [c.replace(" ", "") if _MULTI.match(c) else c for c in head] + [c.capitalize() for c in rest]


def _join(parts: list[str]) -> str:
    """'Otta-' + 'kringer' -> 'Ottakringer'; everything else with spaces."""
    out = ""
    for part in parts:
        if out.endswith("-") and part[:1].islower():
            out = out[:-1] + part
        else:
            out = f"{out} {part}".strip()
    return re.sub(r"\s+", " ", out)
