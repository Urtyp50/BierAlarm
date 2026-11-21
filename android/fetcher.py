"""Fetch all stores without Home Assistant (plain urllib), for the Android app.

Uses the same readers as the integration (copied into the package 'bieralarm'
by sync_core.py). PDF leaflets are read once and kept in a JSON cache file.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import date, datetime
import json
import os
import ssl
import urllib.error
import urllib.parse
import urllib.request

from bieralarm.const import (
    STORE_BILLA,
    STORE_BILLA_PLUS,
    STORE_HOFER,
    STORE_INTERSPAR,
    STORE_LIDL,
    STORE_MPREIS,
    STORE_NAMES,
    STORE_PENNY,
    USER_AGENT,
)
from bieralarm.models import Deal, matches_brand
from bieralarm.sources import billa, hofer, interspar, lidl, mpreis, pdf_layout, penny

TIMEOUT = 30
try:  # Android's Python has no system CA store: use certifi's
    import certifi

    _SSL = ssl.create_default_context(cafile=certifi.where())
except ImportError:  # pragma: no cover
    _SSL = ssl.create_default_context()
ALL_STORES = [STORE_PENNY, STORE_LIDL, STORE_MPREIS, STORE_BILLA, STORE_BILLA_PLUS, STORE_INTERSPAR, STORE_HOFER]

DEFAULT_SETTINGS = {
    "stores": [STORE_PENNY, STORE_LIDL, STORE_BILLA, STORE_BILLA_PLUS, STORE_INTERSPAR, STORE_HOFER],
    "lidl_region": "1",
    "region": "Wien",
    "favorites": "",
    "max_crate_price": 0,
}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):  # noqa: ANN002, ANN003
        return None


def _request(url: str, data: bytes | None = None, referer: str | None = None) -> urllib.request.Request:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "de-AT,de;q=0.9",
    }
    if referer:
        headers["Referer"] = referer
    return urllib.request.Request(url, data=data, headers=headers)


def get(url: str, *, binary: bool = False) -> str | bytes:
    with urllib.request.urlopen(_request(url), timeout=TIMEOUT * (8 if binary else 1), context=_SSL) as resp:
        body = resp.read()
    return body if binary else body.decode("utf-8", errors="replace")


class Fetcher:
    def __init__(self, data_dir: str) -> None:
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)
        self.cache_path = os.path.join(data_dir, "cache.json")
        self.settings_path = os.path.join(data_dir, "settings.json")
        self.cache = self._load(self.cache_path, {"leaflets": {}, "notified": [], "deals": [], "updated": None})
        self.settings = {**DEFAULT_SETTINGS, **self._load(self.settings_path, {})}

    # ------------------------------------------------------------------ storage
    @staticmethod
    def _load(path: str, default: dict) -> dict:
        try:
            with open(path, encoding="utf-8") as f:
                return {**default, **json.load(f)}
        except (OSError, ValueError):
            return dict(default)

    def _save(self, path: str, data: dict) -> None:
        tmp = f"{path}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, path)

    def save_settings(self) -> None:
        self._save(self.settings_path, self.settings)

    # ------------------------------------------------------------------- alarm
    @property
    def favorites(self) -> list[str]:
        return [b.strip() for b in (self.settings.get("favorites") or "").split(",") if b.strip()]

    def is_favorite(self, deal: Deal) -> bool:
        return bool(self.favorites) and matches_brand(deal, self.favorites)

    def is_match(self, deal: Deal) -> bool:
        limit = float(self.settings.get("max_crate_price") or 0)
        if self.is_favorite(deal):
            return True
        return bool(limit and deal.price_per_crate is not None and deal.price_per_crate <= limit)

    def cached_deals(self) -> list[Deal]:
        return [Deal(**d) for d in self.cache.get("deals", [])]

    # ------------------------------------------------------------------- fetch
    def refresh(self) -> tuple[list[Deal], dict[str, str], list[Deal]]:
        """Return (deals, errors per store, new alarm deals)."""
        stores = [s for s in self.settings.get("stores", []) if s in ALL_STORES]
        jobs = {}
        if STORE_PENNY in stores:
            jobs[STORE_PENNY] = lambda: penny.parse(get(penny.URL))
        if STORE_LIDL in stores:
            jobs[STORE_LIDL] = lambda: lidl.parse(get(lidl.URL), str(self.settings.get("lidl_region", "1")))
        if STORE_MPREIS in stores:
            jobs[STORE_MPREIS] = lambda: mpreis.parse(get(mpreis.URL))
        if STORE_BILLA in stores or STORE_BILLA_PLUS in stores:
            jobs["billa"] = lambda: self._billa(stores)
        if STORE_INTERSPAR in stores:
            jobs[STORE_INTERSPAR] = self._interspar
        if STORE_HOFER in stores:
            jobs[STORE_HOFER] = self._hofer

        old = {d.id: d for d in self.cached_deals()}
        deals: dict[str, Deal] = {}
        errors: dict[str, str] = {}
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {name: pool.submit(job) for name, job in jobs.items()}
            for name, future in futures.items():
                try:
                    for deal in future.result():
                        deals[deal.id] = deal
                except Exception as err:  # noqa: BLE001 - one store failing must not stop the others
                    errors[name] = _describe(err)
                    owned = {STORE_BILLA, STORE_BILLA_PLUS} if name == "billa" else {name}
                    deals.update({i: d for i, d in old.items() if d.store in owned})
        today = date.today().isoformat()
        result = [d for d in deals.values() if d.store in stores and (not d.valid_to or d.valid_to >= today)]
        result.sort(key=lambda d: (d.price_per_crate is None, d.price_per_crate or 0, d.price or 0))

        notified = set(self.cache.get("notified", []))
        new = [d for d in result if self.is_match(d) and d.id not in notified]
        self.cache["notified"] = sorted(notified | {d.id for d in new})[-500:]
        self.cache["deals"] = [_fields(d) for d in result]
        self.cache["updated"] = datetime.now().isoformat(timespec="minutes")
        self._prune()
        self._save(self.cache_path, self.cache)
        return result, errors, new

    def _pdf(self, key: str, store: str, download) -> list[Deal]:  # noqa: ANN001
        cached = self.cache["leaflets"].get(key)
        if cached and cached.get("parser") == pdf_layout.VERSION:
            return [Deal(**d) for d in cached["deals"]]
        deals = pdf_layout.parse(download(), store, key, date.today().year)
        self.cache["leaflets"][key] = {"fetched": date.today().isoformat(), "parser": pdf_layout.VERSION,
                                       "deals": [_fields(d) for d in deals]}
        return deals

    def _billa(self, stores: list[str]) -> list[Deal]:
        found = billa.find_leaflets(get(billa.URL), self.settings.get("region", "Wien"))
        deals: list[Deal] = []
        for store, url in found.items():
            if store in stores:
                deals.extend(self._pdf(url, store, lambda url=url: get(url, binary=True)))
        if not found:
            raise RuntimeError("kein PDF-Flugblatt auf billa.at gefunden")
        return deals

    def _interspar(self) -> list[Deal]:
        for flipbook in interspar.flipbook_urls(self.settings.get("region", "Wien"), date.today()):
            if flipbook not in self.cache["leaflets"]:
                try:
                    get(flipbook)
                except urllib.error.HTTPError as err:
                    if err.code == 404:
                        continue
                    raise
            return self._pdf(flipbook, STORE_INTERSPAR, lambda flipbook=flipbook: _interspar_pdf(flipbook))
        raise RuntimeError("kein Flugblatt auf flugblatt.interspar.at gefunden")

    def _hofer(self) -> list[Deal]:
        deals: dict[str, Deal] = {}
        found = False
        for flipbook in hofer.flipbook_urls(date.today()):
            cached = self.cache["leaflets"].get(flipbook)
            if cached and cached.get("parser") == hofer.VERSION:
                found = True
                read = [Deal(**d) for d in cached["deals"]]
            else:
                try:
                    html = get(flipbook)
                except urllib.error.HTTPError as err:
                    if err.code == 404:
                        continue
                    raise
                found = True
                read = []
                pages = hofer.beer_pages(json.loads(get(f"{flipbook}spreads.json")))
                pdf_url = hofer.find_pdf(html)
                if pages and pdf_url:  # the PDF (about 45 MB) only when there is beer in it
                    read = hofer.parse(get(pdf_url, binary=True), flipbook, date.today().year, pages)
                self.cache["leaflets"][flipbook] = {"fetched": date.today().isoformat(), "parser": hofer.VERSION,
                                                    "deals": [_fields(d) for d in read]}
            for deal in read:
                deals.setdefault(deal.id, deal)
        if not found:
            raise RuntimeError("kein Katalog auf katalog.hofer.at gefunden")
        return list(deals.values())

    def _prune(self) -> None:
        """Forget leaflets after 3 weeks."""
        cutoff = date.fromordinal(date.today().toordinal() - 21).isoformat()
        self.cache["leaflets"] = {k: v for k, v in self.cache["leaflets"].items() if v.get("fetched", "") >= cutoff}


def _interspar_pdf(flipbook: str) -> bytes:
    """POST GetPDF.ashx answers with a redirect to the PDF file."""
    opener = urllib.request.build_opener(_NoRedirect, urllib.request.HTTPSHandler(context=_SSL))
    data = urllib.parse.urlencode({"pageNumbers": ""}).encode()
    try:
        opener.open(_request(interspar.pdf_endpoint(flipbook), data=data, referer=flipbook), timeout=TIMEOUT)
    except urllib.error.HTTPError as err:
        location = err.headers.get("Location")
        if err.code in (301, 302, 303, 307) and location:
            return get(location, binary=True)
        raise
    raise RuntimeError("PDF-Download nicht verfügbar")


def _fields(deal: Deal) -> dict:
    return {k: v for k, v in asdict(deal).items()}


def _describe(err: Exception) -> str:
    if isinstance(err, urllib.error.HTTPError):
        return f"HTTP {err.code}"
    if isinstance(err, urllib.error.URLError):
        return f"keine Verbindung ({err.reason})"
    return str(err) or type(err).__name__


def store_name(store: str) -> str:
    return STORE_NAMES.get(store, store)
