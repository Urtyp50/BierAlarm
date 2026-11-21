"""Data model and helpers for beer deals (no Home Assistant imports)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import re
import unicodedata

CRATE_LITERS = 10.0  # 20 Flaschen à 0,5 l

BEER_WORDS = (
    "bier",
    "märzen",
    "maerzen",
    "pils",
    "lager",
    "helles",
    "zwickl",
    "weizen",
    "radler",
    "bockbier",
    "stout",
    "goldbräu",
    "gösser",
    "ottakringer",
    "stiegl",
    "zipfer",
    "puntigamer",
    "kaiser",
    "schwechater",
    "egger",
    "murauer",
    "hirter",
    "trumer",
    "edelweiss",
    "budweiser",
    "heineken",
    "corona",
    "freistädter",
    "wieselburger",
    "schladminger",
    "mohren",
    "fohrenburger",
    "villacher",
    "reininghaus",
)


@dataclass
class Deal:
    """One beer offer."""

    store: str
    name: str
    brand: str | None = None
    price: float | None = None
    regular_price: float | None = None
    package: str | None = None
    volume_l: float | None = None
    valid_from: str | None = None
    valid_to: str | None = None
    condition: str | None = None
    image: str | None = None
    url: str | None = None
    source: str = "web"
    alcohol: float | None = None  # % vol, when the shop states it
    extra: dict = field(default_factory=dict)

    @property
    def id(self) -> str:
        """Stable id so the same offer is not announced twice."""
        key = "|".join(
            str(x)
            for x in (
                self.store,
                (self.brand or "").lower(),
                self.name.lower(),
                self.price,
                self.valid_from,
                self.valid_to,
            )
        )
        return hashlib.sha1(key.encode()).hexdigest()[:16]

    @property
    def price_per_liter(self) -> float | None:
        if self.price is None or not self.volume_l:
            return None
        return round(self.price / self.volume_l, 2)

    @property
    def price_per_crate(self) -> float | None:
        """Comparison price for a 20er-Kiste à 0,5 l (10 liters)."""
        if self.price is None or not self.volume_l:
            return None
        return round(self.price / self.volume_l * CRATE_LITERS, 2)

    @property
    def discount_percent(self) -> int | None:
        if not self.price or not self.regular_price or self.regular_price <= self.price:
            return None
        return round((1 - self.price / self.regular_price) * 100)

    @property
    def title(self) -> str:
        if self.brand and self.brand.lower() not in self.name.lower():
            return f"{self.brand} {self.name}"
        return self.name

    def as_dict(self) -> dict:
        data = asdict(self)
        data.pop("extra", None)
        data.update(
            id=self.id,
            title=self.title,
            price_per_liter=self.price_per_liter,
            price_per_crate=self.price_per_crate,
            discount_percent=self.discount_percent,
        )
        typical = None if self.alcohol is not None else typical_alcohol(self)
        data["alcohol"] = self.alcohol if self.alcohol is not None else typical
        data["alcohol_typical"] = typical is not None
        return data


_NUM = r"(\d+(?:[.,]\d+)?)"


def _f(value: str) -> float:
    return float(value.replace(",", "."))


def parse_volume(text: str | None) -> float | None:
    """Total liters from texts like 'Je 20x 0,5 l', '0,33 Liter', '6 x 0,5l', '500 ml'."""
    if not text:
        return None
    t = text.lower().replace("\xa0", " ")
    multi = re.search(_NUM + r"\s*[x×]\s*" + _NUM + r"\s*(ml|cl|l(?:iter)?)\b", t)
    if multi:
        count, size, unit = _f(multi.group(1)), _f(multi.group(2)), multi.group(3)
        return round(count * _to_liter(size, unit), 3)
    single = re.search(_NUM + r"\s*(ml|cl|l(?:iter)?)\b", t)
    if single:
        liters = _to_liter(_f(single.group(1)), single.group(2))
        crate = re.search(r"kiste\s*=\s*(\d+)", t)
        if crate and int(crate.group(1)) > 0:
            liters *= int(crate.group(1))
        return round(liters, 3)
    return None


def _to_liter(value: float, unit: str) -> float:
    if unit == "ml":
        return value / 1000
    if unit == "cl":
        return value / 100
    return value


def looks_like_beer(*texts: str | None) -> bool:
    blob = " ".join(t for t in texts if t).lower()
    if "alkoholfrei" in blob and "bier" not in blob:
        return False
    if re.search(r"brot|mehl|backofen|waschmittel|chips|gebäck|semmel|käse|senf|essig|wurst|gulasch", blob):
        return False
    return any(re.search(rf"\b{re.escape(w)}", blob) for w in BEER_WORDS)


def _norm(text: str) -> str:
    """Lowercase without accents, so 'Gösser' == 'Gosser' and 'Weißbier' == 'Weissbier'."""
    text = unicodedata.normalize("NFKD", text.lower().replace("ß", "ss"))
    return "".join(c for c in text if not unicodedata.combining(c))


def matches_brand(deal: Deal, brands: list[str]) -> bool:
    """True when every word of one favourite ('Zipfer Urtyp') appears in the deal."""
    hay = _norm(f"{deal.brand or ''} {deal.name}")
    return any(
        words and all(w in hay for w in words) for words in (_norm(b).split() for b in brands)
    )


_ALC = re.compile(r"(\d{1,2}(?:[.,]\d{1,2})?)\s*%\s*(?:vol|alk)", re.I)


def parse_alcohol(*texts: str | None) -> float | None:
    """'4,5 % Alkoholgehalt', '5,2% vol.' -> 4.5 / 5.2; 'alkoholfrei' -> 0."""
    blob = " ".join(t for t in texts if t)
    found = _ALC.search(blob)
    if found:
        value = _f(found.group(1))
        return value if 0 <= value <= 15 else None
    if re.search(r"alkoholfrei|\b0[,.]0\s*%", blob, re.I):
        return 0.0
    return None


# Typical values from brewery or retailer listings, used when the shop gives none.
TYPICAL_ALCOHOL = {
    "Zipfer Märzen": 5.0,
    "Zipfer Urtyp": 5.4,
    "Gösser Märzen": 5.2,
    "Gösser Gold": 5.3,
    "Gösser Zwickl": 5.2,
    "Gösser Naturradler": 2.0,
    "Stiegl Goldbräu": 5.0,
    "Ottakringer Helles": 5.2,
    "Ottakringer Wiener Original": 5.3,
    "Ottakringer Zwickl": 5.2,
    "Puntigamer": 5.1,
    "Kaiser Märzen": 5.0,
    "Kaiser Fasstyp": 5.0,
    "Kaiser Doppelmalz": 4.7,
    "Schwechater Bier": 5.0,
    "Wieselburger Gold": 5.0,
    "Egger Märzen": 5.0,
    "Hirter Privat Pils": 5.2,
    "Trumer Pils": 4.9,
    "Heineken": 5.0,
}


def typical_alcohol(deal: Deal) -> float | None:
    """Most specific table entry whose words all appear in the deal (radler only for radler)."""
    hay = _norm(f"{deal.brand or ''} {deal.name}")
    if "alkoholfrei" in hay:
        return 0.0
    best: tuple[int, float] | None = None
    for beer, value in TYPICAL_ALCOHOL.items():
        words = _norm(beer).split()
        if ("radler" in hay) != any("radler" in w for w in words):
            continue
        if all(w in hay for w in words) and (best is None or len(words) > best[0]):
            best = (len(words), value)
    return best[1] if best else None
