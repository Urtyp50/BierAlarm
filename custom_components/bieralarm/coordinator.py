"""Fetch all sources, analyse leaflets, and announce new deals."""

from __future__ import annotations

import asyncio
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
    CONF_AI_TASK_ENTITY,
    CONF_BILLA_REGION,
    CONF_EXTRA_LEAFLETS,
    CONF_FAVORITE_BRANDS,
    CONF_LIDL_REGION,
    CONF_MAX_PRICE_PER_LITER,
    CONF_NOTIFY_ENTITY,
    CONF_STORES,
    DEFAULT_BILLA_REGION,
    DEFAULT_LIDL_REGION,
    DEFAULT_STORES,
    DOMAIN,
    EVENT_NEW_DEAL,
    REQUEST_TIMEOUT,
    STORAGE_KEY,
    STORAGE_VERSION,
    STORE_LIDL,
    STORE_NAMES,
    STORE_PENNY,
    UPDATE_INTERVAL,
    USER_AGENT,
)
from .models import Deal, matches_brand
from .sources import billa, leaflet, lidl, penny

_LOGGER = logging.getLogger(__name__)

STORE_CUSTOM = "custom"
_JOB_STORES = {"billa": AI_STORES}


@dataclass
class BierData:
    deals: list[Deal] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)
    updated: datetime | None = None
    matches: list[str] = field(default_factory=list)


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
        jobs: dict[str, Any] = {}
        if STORE_PENNY in self.stores:
            jobs[STORE_PENNY] = self._fetch_penny()
        if STORE_LIDL in self.stores:
            jobs[STORE_LIDL] = self._fetch_lidl()
        if any(s in self.stores for s in AI_STORES):
            jobs["billa"] = self._fetch_billa()
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

        if jobs and len(data.errors) == len(jobs) and self.data is None:
            raise UpdateFailed(f"Alle Quellen fehlgeschlagen: {data.errors}")

        today = _today()
        data.deals = [d for d in data.deals if not d.valid_to or d.valid_to >= today]
        data.deals.sort(key=lambda d: (d.price_per_liter is None, d.price_per_liter or 0, d.price or 0))
        data.updated = dt_util.utcnow()
        data.matches = [d.id for d in data.deals if self.is_match(d)]
        await self._announce(data)
        self._prune_cache()
        await self._store.async_save(self._cache)
        return data

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
    async def _get(self, url: str, *, binary: bool = False) -> str | bytes:
        timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT * (4 if binary else 1))
        headers = {"User-Agent": USER_AGENT, "Accept-Language": "de-AT,de;q=0.9"}
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

    def _extra_leaflets(self) -> list[str]:
        raw = self.opts.get(CONF_EXTRA_LEAFLETS) or ""
        return [u.strip() for u in raw.replace("\n", ",").split(",") if u.strip().startswith("http")]

    async def _fetch_extra(self) -> list[Deal]:
        deals: list[Deal] = []
        for url in self._extra_leaflets():
            label = url.rsplit("/", 1)[-1][:40]
            deals.extend(await self._analyse_pdf(STORE_CUSTOM, label, url))
        return deals

    async def _analyse_pdf(self, store: str, store_name: str, url: str) -> list[Deal]:
        """AI analysis is cached per PDF URL, so each leaflet costs one AI call."""
        cached = self._cache["leaflets"].get(url)
        if cached is not None:
            return [Deal(**d) for d in cached["deals"]]
        ai_entity = self.opts.get(CONF_AI_TASK_ENTITY)
        if not ai_entity:
            raise UpdateFailed(
                f"{store_name}: Für PDF-Flugblätter bitte eine KI-Aufgabe (AI Task) in den Optionen wählen"
            )
        pdf = await self._get(url, binary=True)
        text = await self.hass.async_add_executor_job(leaflet.extract_beer_text, pdf)
        if not text:
            deals: list[Deal] = []
        else:
            response = await self.hass.services.async_call(
                "ai_task",
                "generate_data",
                {
                    "task_name": f"BierAlarm {store_name}",
                    "entity_id": ai_entity,
                    "instructions": leaflet.build_instructions(
                        store_name, text, dt_util.now().year
                    ),
                },
                blocking=True,
                return_response=True,
            )
            answer = (response or {}).get("data")
            deals = leaflet.parse_ai_answer(answer, store, url)
        self._cache["leaflets"][url] = {
            "fetched": dt_util.utcnow().isoformat(),
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

        lines = [_line(d) for d in new[:10]]
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
    for key in ("id", "title", "price_per_liter", "discount_percent"):
        data.pop(key, None)
    return data


def _line(deal: Deal) -> str:
    price = f"€ {deal.price:.2f}".replace(".", ",") if deal.price is not None else "?"
    per_l = (
        f" ({deal.price_per_liter:.2f} €/l)".replace(".", ",")
        if deal.price_per_liter
        else ""
    )
    store = STORE_NAMES.get(deal.store, deal.store)
    extra = f" – {deal.condition}" if deal.condition else ""
    return f"• {store}: {deal.title} {deal.package or ''} {price}{per_l}{extra}".replace("  ", " ")
