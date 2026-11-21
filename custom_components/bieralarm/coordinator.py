"""Fetch all sources, analyse leaflets, and announce new deals."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime
import logging
from typing import Any

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    AI_STORES,
    BEERS,
    CONF_AI_TASK_ENTITY,
    CONF_BILLA_REGION,
    CONF_EXTRA_LEAFLETS,
    CONF_FAVORITE_BRANDS,
    CONF_LIDL_REGION,
    CONF_MAX_PRICE_PER_LITER,
    CONF_NOTIFY_ENTITY,
    CONF_RADIUS_KM,
    CONF_STORES,
    DEFAULT_BILLA_REGION,
    DEFAULT_LIDL_REGION,
    DEFAULT_STORES,
    DOMAIN,
    EVENT_NEW_DEAL,
    NEARBY_MAX_AGE,
    REQUEST_TIMEOUT,
    STORAGE_KEY,
    STORAGE_VERSION,
    STORE_HOFER,
    STORE_INTERSPAR,
    STORE_LIDL,
    STORE_MPREIS,
    STORE_NAMES,
    STORE_PENNY,
    UPDATE_INTERVAL,
    USER_AGENT,
)
from .models import Deal, matches_brand
from .sources import billa, hofer, interspar, leaflet, lidl, mpreis, nearby, pdf_layout, penny

_LOGGER = logging.getLogger(__name__)

STORE_CUSTOM = "custom"
_JOB_STORES = {"billa": AI_STORES}


@dataclass
class BierData:
    deals: list[Deal] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)
    updated: datetime | None = None
    matches: list[str] = field(default_factory=list)
    # store -> branches within the radius (None = no radius set or unknown)
    nearby: dict[str, list[dict]] | None = None
    out_of_range: list[str] = field(default_factory=list)
    home_address: str | None = None


class BierAlarmCoordinator(DataUpdateCoordinator[BierData]):
    """Coordinates fetching for one BierAlarm config entry."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )
        self._session = async_get_clientsession(hass)
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{STORAGE_KEY}.{entry.entry_id}"
        )
        self._cache: dict[str, Any] = {}

    # ---------------------------------------------------------------- options
    @property
    def opts(self) -> dict[str, Any]:
        return {**self.config_entry.data, **self.config_entry.options}

    @property
    def stores(self) -> list[str]:
        return list(self.opts.get(CONF_STORES, DEFAULT_STORES))

    @property
    def favorite_brands(self) -> list[str]:
        raw = self.opts.get(CONF_FAVORITE_BRANDS) or ""
        return [b.strip() for b in raw.split(",") if b.strip()]

    @property
    def brand_names(self) -> list[str]:
        """Beers that get a switch: the fixed list plus any typed favourite."""
        known = {b.lower() for b in BEERS}
        return BEERS + [b for b in self.favorite_brands if b.lower() not in known]

    def beer_image(self, beer: str) -> str | None:
        """Product photo of this beer from the latest deal that showed it."""
        return (self._cache.get("images") or {}).get(beer.lower())

    def _remember_images(self, deals: list[Deal]) -> None:
        """Keep one product photo per beer, also after the offer has ended."""
        images: dict[str, str] = self._cache.setdefault("images", {})
        for beer in self.brand_names:
            radler = "radler" in beer.lower()
            for deal in deals:
                if (
                    deal.image
                    and deal.image.startswith("http")
                    and ("radler" in deal.title.lower()) == radler
                    and matches_brand(deal, [beer])
                ):
                    images[beer.lower()] = deal.image
                    break

    def favorite_options(self, brand: str, on: bool) -> dict[str, Any]:
        """Options with `brand` added to or removed from the favourite brands."""
        brands = [b for b in self.favorite_brands if b.lower() != brand.lower()]
        if on:
            brands.append(brand)
        return {**self.config_entry.options, CONF_FAVORITE_BRANDS: ", ".join(brands)}

    async def async_rematch(self) -> None:
        """Favourite brands changed: re-evaluate alarms without fetching again."""
        if self.data is None:
            return
        self.data.matches = [d.id for d in self.data.deals if self.is_match(d)]
        await self._announce(self.data)
        await self._store.async_save(self._cache)
        self.async_update_listeners()

    @property
    def radius_km(self) -> float | None:
        value = self.opts.get(CONF_RADIUS_KM)
        return float(value) if value else None

    def stores_in_range(self, data: BierData) -> list[str]:
        """Configured stores, minus chains without a branch within the radius."""
        if data.nearby is None:
            return self.stores
        return [s for s in self.stores if s not in nearby.WIKIDATA or data.nearby.get(s)]

    def distance(self, store: str) -> float | None:
        """Distance to the nearest branch of a store, if known."""
        branches = (self.data.nearby or {}).get(store) if self.data else None
        return branches[0]["distance_km"] if branches else None

    @property
    def max_price_per_liter(self) -> float | None:
        value = self.opts.get(CONF_MAX_PRICE_PER_LITER)
        return float(value) if value else None

    # ----------------------------------------------------------------- update
    async def async_load_cache(self) -> None:
        self._cache = await self._store.async_load() or {}
        self._cache.setdefault("leaflets", {})
        self._cache.setdefault("notified", [])

    async def _async_update_data(self) -> BierData:
        data = BierData()
        if self.radius_km:
            try:
                data.nearby = await self._nearby()
            except Exception as err:  # noqa: BLE001 - without locations, show all stores
                _LOGGER.warning("BierAlarm: store locations failed: %s", err)
                data.errors["umkreis"] = f"Filialen im Umkreis nicht abrufbar: {err}"
                data.nearby = (self._cache.get("nearby") or {}).get("stores")
            data.home_address = await self._home_address()
        stores = self.stores_in_range(data)
        data.out_of_range = [s for s in self.stores if s not in stores]
        jobs: dict[str, Any] = {}
        if STORE_PENNY in stores:
            jobs[STORE_PENNY] = self._fetch_penny()
        if STORE_LIDL in stores:
            jobs[STORE_LIDL] = self._fetch_lidl()
        if STORE_MPREIS in stores:
            jobs[STORE_MPREIS] = self._fetch_mpreis()
        if any(s in stores for s in AI_STORES):
            jobs["billa"] = self._fetch_billa()
        if STORE_INTERSPAR in stores:
            jobs[STORE_INTERSPAR] = self._fetch_interspar()
        if STORE_HOFER in stores:
            jobs[STORE_HOFER] = self._fetch_hofer()
        if self._extra_leaflets():
            jobs[STORE_CUSTOM] = self._fetch_extra()

        results = await asyncio.gather(*jobs.values(), return_exceptions=True)
        for name, result in zip(jobs, results, strict=True):
            if isinstance(result, Exception):
                _LOGGER.warning("BierAlarm: %s failed: %s", name, result)
                data.errors[name] = str(result) or type(result).__name__
                # Keep showing what we had for this source until it works again.
                if self.data:
                    owned = _JOB_STORES.get(name, {name})
                    data.deals.extend(d for d in self.data.deals if d.store in owned)
            else:
                data.deals.extend(result)
        # BILLA and BILLA PLUS come from one job: drop the one that is out of range.
        data.deals = [d for d in data.deals if d.store not in data.out_of_range]

        if jobs and len(set(data.errors) & set(jobs)) == len(jobs) and self.data is None:
            raise UpdateFailed(f"Alle Quellen fehlgeschlagen: {data.errors}")

        today = _today()
        data.deals = [d for d in data.deals if not d.valid_to or d.valid_to >= today]
        data.deals.sort(key=lambda d: (d.price_per_liter is None, d.price_per_liter or 0, d.price or 0))
        data.updated = dt_util.utcnow()
        data.matches = [d.id for d in data.deals if self.is_match(d)]
        self._remember_images(data.deals)
        await self._announce(data)
        self._prune_cache()
        await self._store.async_save(self._cache)
        return data

    def is_favorite(self, deal: Deal) -> bool:
        """One of the beers switched on in 'Benachrichtigen bei'."""
        brands = self.favorite_brands
        return bool(brands) and matches_brand(deal, brands)

    def is_match(self, deal: Deal) -> bool:
        """Alarm when a favourite brand is on offer OR the liter price is low enough."""
        brands = self.favorite_brands
        limit = self.max_price_per_liter
        if brands and matches_brand(deal, brands):
            return True
        return bool(
            limit and deal.price_per_liter is not None and deal.price_per_liter <= limit
        )

    # ---------------------------------------------------------------- sources
    async def _home_address(self) -> str | None:
        """Address of the home location, looked up once and cached (shown in the card)."""
        lat, lon = self.hass.config.latitude, self.hass.config.longitude
        key = f"{lat:.5f},{lon:.5f}"
        cached = self._cache.get("home_address") or {}
        if cached.get("key") == key:
            return cached.get("text")
        try:
            async with self._session.get(
                nearby.REVERSE_URL,
                params=nearby.reverse_params(lat, lon),
                headers={"User-Agent": nearby.USER_AGENT},
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
            ) as resp:
                resp.raise_for_status()
                text = nearby.parse_address(await resp.json(content_type=None))
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            _LOGGER.debug("BierAlarm: address lookup failed: %s", err)
            return cached.get("text")  # try again next update
        self._cache["home_address"] = {"key": key, "text": text}
        return text

    async def _nearby(self) -> dict[str, list[dict]]:
        lat, lon, radius = self.hass.config.latitude, self.hass.config.longitude, self.radius_km
        key = f"v2,{lat:.5f},{lon:.5f},{radius},{','.join(sorted(self.stores))}"
        cached = self._cache.get("nearby") or {}
        if cached.get("key") == key and (
            dt_util.utcnow() - dt_util.parse_datetime(cached["fetched"]) < NEARBY_MAX_AGE
        ):
            return cached["stores"]
        query = nearby.build_query(lat, lon, radius, self.stores)
        timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT * 2)
        last_err: Exception | None = None
        for url in nearby.URLS:
            try:
                async with self._session.post(
                    url, data={"data": query}, headers={"User-Agent": nearby.USER_AGENT}, timeout=timeout
                ) as resp:
                    resp.raise_for_status()
                    result = nearby.parse(await resp.json(content_type=None), lat, lon, radius)
                break
            except (aiohttp.ClientError, TimeoutError) as err:
                last_err = err
        else:
            raise UpdateFailed(f"OpenStreetMap: {last_err}")
        self._cache["nearby"] = {"key": key, "fetched": dt_util.utcnow().isoformat(), "stores": result}
        return result

    async def _get(self, url: str, *, binary: bool = False) -> str | bytes:
        timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT * (8 if binary else 1))
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "de-AT,de;q=0.9",
        }
        async with self._session.get(url, headers=headers, timeout=timeout) as resp:
            if resp.status == 403:
                raise UpdateFailed(f"{url}: Zugriff verweigert (403)")
            resp.raise_for_status()
            return await resp.read() if binary else await resp.text()

    async def _fetch_penny(self) -> list[Deal]:
        return penny.parse(await self._get(penny.URL))

    async def _fetch_lidl(self) -> list[Deal]:
        region = str(self.opts.get(CONF_LIDL_REGION, DEFAULT_LIDL_REGION))
        return lidl.parse(await self._get(lidl.URL), region)

    async def _fetch_mpreis(self) -> list[Deal]:
        return mpreis.parse(await self._get(mpreis.URL))

    async def _fetch_billa(self) -> list[Deal]:
        region = self.opts.get(CONF_BILLA_REGION, DEFAULT_BILLA_REGION)
        found = billa.find_leaflets(await self._get(billa.URL), region)
        wanted = {s: u for s, u in found.items() if s in self.stores}
        if not wanted:
            raise UpdateFailed("BILLA: kein PDF-Flugblatt auf billa.at gefunden")
        deals: list[Deal] = []
        for store, url in wanted.items():
            deals.extend(await self._analyse_pdf(store, STORE_NAMES[store], url))
        return deals

    async def _fetch_interspar(self) -> list[Deal]:
        region = self.opts.get(CONF_BILLA_REGION, DEFAULT_BILLA_REGION)
        for flipbook in interspar.flipbook_urls(region, dt_util.now().date()):
            if flipbook in self._cache["leaflets"]:
                return await self._analyse_pdf(STORE_INTERSPAR, "INTERSPAR", flipbook)
            try:
                await self._get(flipbook)
            except aiohttp.ClientResponseError as err:
                if err.status == 404:
                    continue  # this week's leaflet is not online yet
                raise
            return await self._analyse_pdf(
                STORE_INTERSPAR, "INTERSPAR", flipbook, download=self._interspar_pdf
            )
        raise UpdateFailed("INTERSPAR: kein Flugblatt auf flugblatt.interspar.at gefunden")

    async def _interspar_pdf(self, flipbook: str) -> bytes:
        """POST GetPDF.ashx answers with a redirect to the PDF (a POST must not follow it)."""
        async with self._session.post(
            interspar.pdf_endpoint(flipbook),
            data={"pageNumbers": ""},
            headers={"User-Agent": USER_AGENT, "Referer": flipbook},
            allow_redirects=False,
            timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
        ) as resp:
            location = resp.headers.get("Location")
            if resp.status not in (301, 302, 303, 307) or not location:
                raise UpdateFailed(f"INTERSPAR: PDF-Download nicht verfügbar ({resp.status})")
        return await self._get(location, binary=True)

    async def _fetch_hofer(self) -> list[Deal]:
        """Next week's and this week's catalog; each is read once and kept in the cache."""
        deals: dict[str, Deal] = {}
        found = False
        for flipbook in hofer.flipbook_urls(dt_util.now().date()):
            cached = self._cache["leaflets"].get(flipbook)
            if cached is not None and cached.get("parser") == hofer.VERSION:
                found = True
                read = [Deal(**d) for d in cached["deals"]]
            else:
                try:
                    html = await self._get(flipbook)
                except aiohttp.ClientResponseError as err:
                    if err.status == 404:
                        continue  # not online yet
                    raise
                found = True
                read = await self._read_hofer(flipbook, html)
                self._cache["leaflets"][flipbook] = {
                    "fetched": dt_util.utcnow().isoformat(),
                    "parser": hofer.VERSION,
                    "deals": [_deal_fields(d) for d in read],
                }
            for deal in read:
                deals.setdefault(deal.id, deal)
        if not found:
            raise UpdateFailed("HOFER: kein Katalog auf katalog.hofer.at gefunden")
        return list(deals.values())

    async def _read_hofer(self, flipbook: str, html: str) -> list[Deal]:
        pages = hofer.beer_pages(json.loads(await self._get(f"{flipbook}spreads.json")))
        if not pages:
            return []  # no beer this week: the PDF (about 45 MB) is not downloaded
        pdf_url = hofer.find_pdf(html)
        if not pdf_url:
            raise UpdateFailed("HOFER: PDF-Link im Katalog nicht gefunden")
        pdf = await self._get(pdf_url, binary=True)
        year = dt_util.now().year
        return await self.hass.async_add_executor_job(hofer.parse, pdf, flipbook, year, pages)

    def _extra_leaflets(self) -> list[str]:
        raw = self.opts.get(CONF_EXTRA_LEAFLETS) or ""
        return [u.strip() for u in raw.replace("\n", ",").split(",") if u.strip().startswith("http")]

    async def _fetch_extra(self) -> list[Deal]:
        deals: list[Deal] = []
        for url in self._extra_leaflets():
            label = url.rsplit("/", 1)[-1][:40]
            deals.extend(await self._analyse_pdf(STORE_CUSTOM, label, url))
        return deals

    async def _analyse_pdf(
        self, store: str, store_name: str, url: str, download: Any = None
    ) -> list[Deal]:
        """Read a PDF leaflet: first from the page layout (no AI), the AI only as a fallback.

        The result is cached per PDF URL, so each leaflet is read once per week.
        """
        cached = self._cache["leaflets"].get(url)
        if cached is not None and cached.get("parser") in (pdf_layout.VERSION, "ai"):
            return [Deal(**d) for d in cached["deals"]]
        pdf = await download(url) if download else await self._get(url, binary=True)
        year = dt_util.now().year
        deals = await self.hass.async_add_executor_job(pdf_layout.parse, pdf, store, url, year)
        parser = pdf_layout.VERSION
        ai_entity = self.opts.get(CONF_AI_TASK_ENTITY)
        if not deals and ai_entity:
            text = await self.hass.async_add_executor_job(leaflet.extract_beer_text, pdf)
            if text:
                response = await self.hass.services.async_call(
                    "ai_task",
                    "generate_data",
                    {
                        "task_name": f"BierAlarm {store_name}",
                        "entity_id": ai_entity,
                        "instructions": leaflet.build_instructions(store_name, text, year),
                    },
                    blocking=True,
                    return_response=True,
                )
                deals = leaflet.parse_ai_answer((response or {}).get("data"), store, url)
                parser = "ai"
        self._cache["leaflets"][url] = {
            "fetched": dt_util.utcnow().isoformat(),
            "parser": parser,
            "deals": [_deal_fields(d) for d in deals],
        }
        return deals

    # ----------------------------------------------------------- notification
    async def _announce(self, data: BierData) -> None:
        notified: list[str] = self._cache["notified"]
        new = [d for d in data.deals if d.id in data.matches and d.id not in notified]
        if not new:
            return
        for deal in new:
            self.hass.bus.async_fire(EVENT_NEW_DEAL, deal.as_dict())
        notified.extend(d.id for d in new)

        lines = [_line(d, self.is_favorite(d)) for d in new[:10]]
        if len(new) > 10:
            lines.append(f"… und {len(new) - 10} weitere")
        message = "\n".join(lines)
        title = f"🍺 BierAlarm: {len(new)} neue Bieraktion{'en' if len(new) > 1 else ''}"
        notify_entity = self.opts.get(CONF_NOTIFY_ENTITY)
        try:
            if notify_entity:
                await self.hass.services.async_call(
                    "notify",
                    "send_message",
                    {"entity_id": notify_entity, "title": title, "message": message},
                    blocking=True,
                )
            else:
                await self.hass.services.async_call(
                    "persistent_notification",
                    "create",
                    {"title": title, "message": message, "notification_id": f"{DOMAIN}_new"},
                    blocking=True,
                )
        except Exception as err:  # noqa: BLE001 - a broken notifier must not break updates
            _LOGGER.warning("BierAlarm: Benachrichtigung fehlgeschlagen: %s", err)

    def _prune_cache(self) -> None:
        self._cache["notified"] = self._cache["notified"][-500:]
        leaflets = self._cache["leaflets"]
        for url in sorted(leaflets, key=lambda u: leaflets[u]["fetched"])[:-20]:
            leaflets.pop(url)

    async def async_clear_leaflet_cache(self) -> None:
        self._cache["leaflets"] = {}
        await self._store.async_save(self._cache)


def _today() -> str:
    return dt_util.now().date().isoformat()


def _deal_fields(deal: Deal) -> dict:
    data = deal.as_dict()
    for key in ("id", "title", "price_per_liter", "price_per_crate", "discount_percent", "alcohol_typical"):
        data.pop(key, None)
    data["alcohol"] = deal.alcohol
    return data


def _line(deal: Deal, favorite: bool = True) -> str:
    price = f"€ {deal.price:.2f}".replace(".", ",") if deal.price is not None else "?"
    per_l = (
        f" (20er-Kiste € {deal.price_per_crate:.2f})".replace(".", ",")
        if deal.price_per_crate
        else ""
    )
    store = STORE_NAMES.get(deal.store, deal.store)
    extra = f" – {deal.condition}" if deal.condition else ""
    alcohol = deal.as_dict()["alcohol"]
    alc = f" · {alcohol:.1f} % vol".replace(".", ",") if alcohol else ""
    why = "" if favorite else " (Preis-Alarm)"
    return f"• {store}: {deal.title} {deal.package or ''}{alc} {price}{per_l}{extra}{why}".replace("  ", " ")
