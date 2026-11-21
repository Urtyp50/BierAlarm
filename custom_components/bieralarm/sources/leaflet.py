"""Turn a PDF leaflet into beer deals with the help of an AI Task entity.

Step 1 (no AI): extract the text layer of each PDF page and keep only pages
that mention beer. Step 2: ask the AI to turn that messy text into JSON.
"""

from __future__ import annotations

from io import BytesIO
import json
import re

from ..models import Deal, looks_like_beer, parse_volume

MAX_CHARS = 24000

INSTRUCTIONS = """Du bekommst den Rohtext aus einem österreichischen Supermarkt-Flugblatt ({store}).
Der Text ist durcheinander: Spalten sind vermischt, Preise stehen oft ohne Komma
(z. B. "069" heißt 0,69 €, "1380" heißt 13,80 €). Finde ALLE Angebote für Bier
und Radler (auch Kisten, Dosen, Träger). Ignoriere alles andere.

Antworte NUR mit JSON, ohne Erklärung, in genau diesem Format:
{{"deals": [{{"brand": "Gösser", "name": "Märzen", "package": "0,5 Liter Dose",
"price": 0.69, "regular_price": 1.39, "condition": "bei 12 Dosen je",
"valid_from": "2026-11-19", "valid_to": "2026-11-25"}}]}}

Regeln:
- price ist der Aktionspreis pro Einheit (Dose/Flasche/Kiste) in Euro als Zahl.
- regular_price ist der Normalpreis, falls angegeben, sonst null.
- package beschreibt Menge und Gebinde, z. B. "1 Kiste = 20 Flaschen à 0,5 Liter".
- condition: Bedingung wie "ab 6 Dosen", "6+6 gratis", "nur Fr & Sa", sonst null.
- Daten als YYYY-MM-DD, falls erkennbar (Jahr {year}), sonst null.
- Erfinde nichts. Wenn kein Bier vorkommt: {{"deals": []}}

Flugblatt-Text:
{text}
"""


def extract_beer_text(pdf_bytes: bytes) -> str:
    """Text of the pages that mention beer, page by page (CPU bound: run in executor)."""
    from pypdf import PdfReader  # noqa: PLC0415 - heavy import, only when needed

    reader = PdfReader(BytesIO(pdf_bytes))
    parts: list[str] = []
    for number, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception:  # noqa: BLE001 - one broken page should not stop the rest
            continue
        flat = re.sub(r"\s*\n\s*", " | ", text)
        if looks_like_beer(flat):
            parts.append(f"--- Seite {number} ---\n{flat}")
    return "\n".join(parts)[:MAX_CHARS]


def build_instructions(store_name: str, text: str, year: int) -> str:
    return INSTRUCTIONS.format(store=store_name, text=text, year=year)


def parse_ai_answer(answer, store: str, url: str) -> list[Deal]:
    """Accept the AI answer as dict or (fenced) JSON text and build Deals."""
    data = answer
    if isinstance(answer, str):
        cleaned = re.sub(r"^```(?:json)?|```$", "", answer.strip(), flags=re.M).strip()
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start == -1 or end == -1:
            raise ValueError("AI answer contains no JSON object")
        data = json.loads(cleaned[start : end + 1])
    items = data.get("deals", []) if isinstance(data, dict) else data
    deals: list[Deal] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        price = _num(item.get("price"))
        name = str(item.get("name") or "").strip()
        brand = str(item.get("brand") or "").strip() or None
        if price is None or not (name or brand):
            continue
        package = item.get("package") or None
        deals.append(
            Deal(
                store=store,
                name=name or brand or "Bier",
                brand=brand,
                price=price,
                regular_price=_num(item.get("regular_price")),
                package=package,
                volume_l=parse_volume(package),
                valid_from=item.get("valid_from") or None,
                valid_to=item.get("valid_to") or None,
                condition=item.get("condition") or None,
                url=url,
                source="ai",
            )
        )
    return deals


def _num(value) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    match = re.search(r"\d+(?:[.,]\d+)?", str(value))
    return float(match.group(0).replace(",", ".")) if match else None
