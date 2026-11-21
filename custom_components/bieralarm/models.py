"""Data model and helpers for beer deals (no Home Assistant imports)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import re

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
            discount_percent=self.discount_percent,
        )
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
        crate = re.search(r"kiste\s*=?\s*(\d+)", t)
        if crate:
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
    return any(re.search(rf"\b{re.escape(w)}", blob) for w in BEER_WORDS)


def matches_brand(deal: Deal, brands: list[str]) -> bool:
    hay = f"{deal.brand or ''} {deal.name}".lower()
    return any(b and b.lower() in hay for b in brands)
