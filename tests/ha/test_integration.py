"""Integration test inside a real Home Assistant core (pytest-homeassistant-custom-component)."""

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


async def test_config_flow_requires_ai_for_billa(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**OPTIONS, "stores": ["billa"]}
    )
    assert result["errors"] == {"ai_task_entity": "ai_required"}


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
    assert hass.states.get("switch.bieralarm_alarm_gosser").state == "off"

    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": "switch.bieralarm_alarm_gosser"}, blocking=True
    )
    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": "switch.bieralarm_alarm_ottakringer"}, blocking=True
    )
    await hass.async_block_till_done()
    assert entry.options["favorite_brands"] == "Gösser"
    assert entry.runtime_data is coordinator  # no reload ...
    assert len(mock_pages.mock_calls) == calls  # ... and no new download
    assert hass.states.get("switch.bieralarm_alarm_gosser").state == "on"
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


async def test_radius_skips_far_stores(hass: HomeAssistant, mock_pages) -> None:
    from custom_components.bieralarm.sources import nearby

    hass.config.latitude, hass.config.longitude = 48.2085, 16.3731
    mock_pages.post(nearby.URL, text=(FIXTURES / "osm_wien.json").read_text(encoding="utf-8"))
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
    assert attrs["deals"][0]["distance_km"] == 1.3

    # Second refresh uses the cached locations
    def posts():
        return sum(1 for c in mock_pages.mock_calls if c[0].lower() == "post")

    assert posts() == 1
    await entry.runtime_data.async_refresh()
    assert posts() == 1
