"""Integration test inside a real Home Assistant core (pytest-homeassistant-custom-component)."""

from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.setup import async_setup_component

from custom_components.bieralarm.const import DOMAIN
from custom_components.bieralarm.sources import lidl, penny

FIXTURES = Path(__file__).parents[1] / "fixtures"

OPTIONS = {
    "stores": ["penny", "lidl"],
    "lidl_region": "1",
    "billa_region": "Wien",
    "favorite_brands": "Ottakringer",
    "max_price_per_liter": 1.5,
}


@pytest.fixture(autouse=True)
def _custom(enable_custom_integrations):
    yield


@pytest.fixture
def mock_pages(aioclient_mock):
    aioclient_mock.get(penny.URL, text=(FIXTURES / "penny_bier.html").read_text(encoding="utf-8"))
    aioclient_mock.get(lidl.URL, text=(FIXTURES / "lidl_bier.html").read_text(encoding="utf-8"))
    return aioclient_mock


async def test_config_flow_billa_without_ai(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] is FlowResultType.FORM
    with patch("custom_components.bieralarm.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {**OPTIONS, "stores": ["billa"]}
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_billa_pdf_read_without_ai(hass: HomeAssistant, aioclient_mock) -> None:
    from custom_components.bieralarm.sources import billa

    page = (FIXTURES / "billa_flugblatt.html").read_text(encoding="utf-8")
    aioclient_mock.get(billa.URL, text=page)
    pdfs = billa.find_leaflets(page, "Wien")
    aioclient_mock.get(pdfs["billa"], content=(FIXTURES / "billa_kw47_bier.pdf").read_bytes())
    aioclient_mock.get(pdfs["billa_plus"], content=(FIXTURES / "billa_plus_kw47_bier.pdf").read_bytes())
    options = {**OPTIONS, "stores": ["billa", "billa_plus"], "favorite_brands": "Gösser Märzen"}
    entry = MockConfigEntry(domain=DOMAIN, title="BierAlarm", data={}, options=options)
    entry.add_to_hass(hass)
    with patch("custom_components.bieralarm.coordinator._today", return_value="2026-11-20"):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    data = entry.runtime_data.data
    assert not data.errors
    crate = next(d for d in data.deals if d.store == "billa" and d.price == 13.8)
    assert crate.title == "Gösser Märzen" and crate.price_per_crate == 13.8
    assert crate.valid_to == "2026-11-25"
    assert {d.store for d in data.deals} == {"billa", "billa_plus"}
    assert crate.id in data.matches
    calls = aioclient_mock.call_count
    await entry.runtime_data.async_refresh()  # the PDFs are cached per URL
    assert aioclient_mock.call_count == calls + 1  # only the leaflet overview page


async def test_interspar_pdf_download(hass: HomeAssistant, aioclient_mock) -> None:
    from custom_components.bieralarm.sources import interspar

    flipbooks = interspar.flipbook_urls("Oberösterreich", date(2026, 11, 20))
    pdf_url = "https://cdn.ipaper.io/x/Download.pdf?token=t"
    aioclient_mock.get(flipbooks[0], text="<html></html>")
    aioclient_mock.post(interspar.pdf_endpoint(flipbooks[0]), status=302, headers={"Location": pdf_url})
    aioclient_mock.get(pdf_url, content=(FIXTURES / "interspar_kw47_bier.pdf").read_bytes())
    options = {**OPTIONS, "stores": ["interspar"], "billa_region": "Oberösterreich", "favorite_brands": "Zipfer Urtyp"}
    entry = MockConfigEntry(domain=DOMAIN, title="BierAlarm", data={}, options=options)
    entry.add_to_hass(hass)
    with patch.object(interspar, "flipbook_urls", return_value=flipbooks):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        data = entry.runtime_data.data
        assert not data.errors
        urtyp = next(d for d in data.deals if d.title == "Zipfer Urtyp")
        assert (urtyp.store, urtyp.price, urtyp.url) == ("interspar", 14.3, flipbooks[0])
        assert urtyp.id in data.matches
        calls = aioclient_mock.call_count
        await entry.runtime_data.async_refresh()  # cached per flip book, nothing downloaded again
        assert aioclient_mock.call_count == calls


async def test_hofer_catalog(hass: HomeAssistant, aioclient_mock) -> None:
    from custom_components.bieralarm.sources import hofer

    next_week, this_week = hofer.flipbook_urls(date(2026, 11, 21))
    pdf_url = "https://view.publitas.com/1/2/pdfs/abc.pdf?x=1"
    aioclient_mock.get(next_week, text=f'<a href="{pdf_url}">PDF</a>')
    aioclient_mock.get(f"{next_week}spreads.json", text=(FIXTURES / "hofer_spreads.json").read_text(encoding="utf-8"))
    aioclient_mock.get(pdf_url, content=(FIXTURES / "hofer_kw48_bier.pdf").read_bytes())
    aioclient_mock.get(this_week, text="<html>no beer</html>")
    aioclient_mock.get(f"{this_week}spreads.json", text='[{"pages": [{"number": 1, "text": "KARTOFFELN"}]}]')
    options = {**OPTIONS, "stores": ["hofer"], "favorite_brands": "Gösser Märzen"}
    entry = MockConfigEntry(domain=DOMAIN, title="BierAlarm", data={}, options=options)
    entry.add_to_hass(hass)
    with patch.object(hofer, "flipbook_urls", return_value=[next_week, this_week]):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        data = entry.runtime_data.data
        assert not data.errors
        crate = next(d for d in data.deals if d.price == 13.8)
        assert (crate.store, crate.title, crate.url) == ("hofer", "Gösser Märzen", next_week)
        assert crate.id in data.matches
        calls = aioclient_mock.call_count
        await entry.runtime_data.async_refresh()  # both catalogs are cached
        assert aioclient_mock.call_count == calls


@pytest.fixture(autouse=True)
def _fixture_week():
    # Fixtures are from KW 47/2026 and expired deals are dropped, so pin "today".
    with patch("custom_components.bieralarm.coordinator._today", return_value="2026-11-20"):
        yield


async def test_setup_sensors_panel_ws_and_alarm(hass: HomeAssistant, mock_pages, hass_ws_client) -> None:
    assert await async_setup_component(hass, "persistent_notification", {})
    events = []
    hass.bus.async_listen("bieralarm_new_deal", events.append)

    entry = MockConfigEntry(domain=DOMAIN, title="BierAlarm", data={}, options=OPTIONS)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    count = hass.states.get("sensor.bieralarm_beer_deals")
    assert count is not None, [s.entity_id for s in hass.states.async_all("sensor")]
    assert int(count.state) > 3
    best = hass.states.get("sensor.bieralarm_best_price_per_liter")
    assert float(best.state) > 0
    crate = hass.states.get("sensor.bieralarm_best_price_per_20_crate")
    assert crate is not None
    assert float(crate.state) == round(float(best.state) * 10, 2)

    # Ottakringer is a favourite brand -> at least one alarm event
    assert any("Ottakringer" in e.data["title"] for e in events)
    assert "bieralarm" in hass.data.get("frontend_panels", {})
    from homeassistant.components.frontend import DATA_EXTRA_MODULE_URL

    assert any("bieralarm-card.js" in u for u in hass.data[DATA_EXTRA_MODULE_URL].urls)

    client = await hass_ws_client(hass)
    await client.send_json({"id": 1, "type": "bieralarm/deals"})
    msg = await client.receive_json()
    assert msg["success"]
    assert msg["result"]["configured"]
    assert any(d["match"] for d in msg["result"]["deals"])

    # Second refresh must not announce the same deals again
    before = len(events)
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert len(events) == before

    assert await hass.config_entries.async_unload(entry.entry_id)
    assert "bieralarm" not in hass.data.get("frontend_panels", {})


async def test_brand_switches_and_filters(hass: HomeAssistant, mock_pages) -> None:
    assert await async_setup_component(hass, "persistent_notification", {})
    events = []
    hass.bus.async_listen("bieralarm_new_deal", events.append)
    entry = MockConfigEntry(domain=DOMAIN, title="BierAlarm", data={}, options=OPTIONS)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = entry.runtime_data
    calls = len(mock_pages.mock_calls)

    switches = {s.entity_id: s for s in hass.states.async_all("switch")}
    assert hass.states.get("switch.bieralarm_alarm_ottakringer").state == "on", list(switches)
    assert hass.states.get("switch.bieralarm_alarm_gosser_marzen").state == "off"
    assert hass.states.get("switch.bieralarm_alarm_zipfer_urtyp").attributes["sort"] == "Urtyp"
    # product photo from the current PENNY offer, kept for the switch
    assert hass.states.get("switch.bieralarm_alarm_gosser_marzen").attributes["entity_picture"].startswith("https://")
    assert "entity_picture" not in hass.states.get("switch.bieralarm_alarm_trumer_pils").attributes

    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": "switch.bieralarm_alarm_gosser_marzen"}, blocking=True
    )
    await hass.async_block_till_done()
    assert entry.options["favorite_brands"] == "Ottakringer, Gösser Märzen"
    assert entry.runtime_data is coordinator  # no reload ...
    assert len(mock_pages.mock_calls) == calls  # ... and no new download
    assert hass.states.get("switch.bieralarm_alarm_gosser_marzen").state == "on"

    # Ottakringer was typed in the options: switching it off removes its switch (reload).
    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": "switch.bieralarm_alarm_ottakringer"}, blocking=True
    )
    await hass.async_block_till_done()
    assert entry.options["favorite_brands"] == "Gösser Märzen"
    assert hass.states.get("switch.bieralarm_alarm_ottakringer") is None
    assert any("Gösser" in e.data["title"] for e in events)

    await hass.services.async_call(
        "text", "set_value", {"entity_id": "text.bieralarm_filter", "value": " Urtyp "}, blocking=True
    )
    assert hass.states.get("text.bieralarm_filter").state == "Urtyp"
    select = hass.states.get("select.bieralarm_store_filter")
    assert select.attributes["options"] == ["Alle", "PENNY", "Lidl"]
    deals = hass.states.get("sensor.bieralarm_beer_deals").attributes["deals"]
    crates = [d["price_per_crate"] for d in deals if d["price_per_crate"] is not None]
    assert crates == sorted(crates)
    # bell only for chosen beers: Gösser Märzen is on, the rest are no favourites
    favs = {d["title"] for d in deals if d["favorite"]}
    assert favs and all("Gösser" in t for t in favs)


async def test_radius_skips_far_stores(hass: HomeAssistant, mock_pages) -> None:
    from custom_components.bieralarm.sources import nearby

    hass.config.latitude, hass.config.longitude = 48.2085, 16.3731
    mock_pages.post(nearby.URL, text=(FIXTURES / "osm_wien.json").read_text(encoding="utf-8"))
    mock_pages.get(
        nearby.REVERSE_URL,
        json={"address": {"road": "Stephansplatz", "house_number": "1", "postcode": "1010", "city": "Wien"}},
    )
    entry = MockConfigEntry(
        domain=DOMAIN, title="BierAlarm", data={}, options={**OPTIONS, "radius_km": 2}
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    data = entry.runtime_data.data
    assert data.out_of_range == ["lidl"]
    assert {d.store for d in data.deals} == {"penny"}
    assert not any(str(c[1]) == lidl.URL for c in mock_pages.mock_calls)
    attrs = hass.states.get("sensor.bieralarm_beer_deals").attributes
    assert attrs["nearby"]["PENNY"]["distance_km"] == 1.3
    assert attrs["start_address"] == "Stephansplatz 1, 1010 Wien"
    assert {b["store"] for b in attrs["branches"]} == {"PENNY", "BILLA PLUS"}
    assert all("lat" in b and "lon" in b for b in attrs["branches"])
    radius = hass.states.get("number.bieralarm_radius")
    assert float(radius.state) == 2
    assert radius.attributes["start_address"] == "Stephansplatz 1, 1010 Wien"
    assert attrs["deals"][0]["distance_km"] == 1.3

    # Second refresh uses the cached locations
    def posts():
        return sum(1 for c in mock_pages.mock_calls if c[0].lower() == "post")

    assert posts() == 1
    ua = next(c[3] for c in mock_pages.mock_calls if c[0].lower() == "post")["User-Agent"]
    assert "Mozilla" not in ua  # OpenStreetMap answers 406 to browser-like agents
    await entry.runtime_data.async_refresh()
    assert posts() == 1


async def test_radius_number_updates_options(hass: HomeAssistant, mock_pages) -> None:
    entry = MockConfigEntry(domain=DOMAIN, title="BierAlarm", data={}, options=OPTIONS)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert float(hass.states.get("number.bieralarm_radius").state) == 0
    await hass.services.async_call(
        "number", "set_value", {"entity_id": "number.bieralarm_radius", "value": 0}, blocking=True
    )
    await hass.async_block_till_done()
    assert entry.options["radius_km"] == 0


async def test_crate_limit_rematches_without_reload(hass: HomeAssistant, mock_pages) -> None:
    entry = MockConfigEntry(domain=DOMAIN, title="BierAlarm", data={}, options={**OPTIONS, "favorite_brands": ""})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = entry.runtime_data
    assert float(hass.states.get("number.bieralarm_alarm_below_crate_price").state) == 15
    before = hass.states.get("sensor.bieralarm_beer_deals").attributes["matches"]
    await hass.services.async_call(
        "number", "set_value",
        {"entity_id": "number.bieralarm_alarm_below_crate_price", "value": 0}, blocking=True,
    )
    await hass.async_block_till_done()
    assert entry.options["max_price_per_liter"] == 0
    assert entry.runtime_data is coordinator
    assert before > 0
    assert hass.states.get("sensor.bieralarm_beer_deals").attributes["matches"] == 0
