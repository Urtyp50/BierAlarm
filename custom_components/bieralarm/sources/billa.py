"""BILLA / BILLA PLUS: the leaflet page links the current week's PDFs."""

from __future__ import annotations

import re

from ..const import STORE_BILLA, STORE_BILLA_PLUS

URL = "https://www.billa.at/flugblatt"

_PDF = re.compile(r'https:(?://|\\u002F\\u002F)[^"\s<>]+?\.pdf', re.I)


def find_leaflets(html: str, region: str = "Wien") -> dict[str, str]:
    """Return {store: pdf_url} for BILLA and BILLA PLUS main leaflets."""
    urls = {u.replace("\\u002F", "/") for u in _PDF.findall(html)}
    result: dict[str, str] = {}
    for store, marker in ((STORE_BILLA_PLUS, "BILLA_PLUS_FB_"), (STORE_BILLA, "BILLA_FB_")):
        candidates = [
            u
            for u in urls
            if marker in u.rsplit("/", 1)[-1].upper()
            and "BEILAGE" not in u.upper()
            and (store == STORE_BILLA_PLUS or "BILLA_PLUS" not in u.upper())
        ]
        if not candidates:
            continue
        regional = [u for u in candidates if _norm(region) in _norm(u)]
        result[store] = sorted(regional or candidates)[0]
    return result


def _norm(text: str) -> str:
    return (
        text.lower()
        .replace("ä", "ae")
        .replace("ö", "oe")
        .replace("ü", "ue")
        .replace(" ", "")
    )
