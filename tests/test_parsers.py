"""Parser tests. Fixtures are saved copies of the real pages (KW 47/2026)."""

from pathlib import Path

import pytest

from bieralarm.models import Deal, looks_like_beer, matches_brand, parse_alcohol, parse_volume, typical_alcohol
import json

from bieralarm.sources import billa, leaflet, lidl, mpreis, nearby, pdf_layout, penny
from bieralarm.sources.nuxt import unflatten

FIXTURES = Path(__file__).parent / "fixtures"


def _fixture(name: str) -> str:
    path = FIXTURES / name
    if not path.exists():
        pytest.skip(f"fixture {name} missing")
    return path.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("text", "liters"),
    [
        ("Je 20x 0,5 l", 10.0),
        ("0,33 liter Flasche", 0.33),
        ("6 x 0,5l Dose", 3.0),
        ("500 ml", 0.5),
        ("1 Kiste = 20 Flaschen à 0,5 Liter", 10.0),
        ("Kiste 0,5 Liter", 0.5),
        ("Einweg", None),
        (None, None),
    ],
)
def test_parse_volume(text, liters):
    assert parse_volume(text) == liters


def test_beer_detection():
    assert looks_like_beer("Gösser Märzen 0,5 Liter")
    assert looks_like_beer("Helles", "Ottakringer")
    assert not looks_like_beer("Vöslauer Mineralwasser")
    assert not looks_like_beer("Almsenner Pinzgauer Bierkäse Halb Laib")
    assert not looks_like_beer("Saftiges Weizenmischbrot")


def test_deal_math_and_brand_match():
    deal = Deal(store="penny", name="Märzen", brand="Gösser", price=0.69, regular_price=1.38, volume_l=0.5)
    assert deal.price_per_liter == 1.38
    assert deal.price_per_crate == 13.8
    assert deal.discount_percent == 50
    can = Deal(store="penny", name="Helles", price=0.69, volume_l=0.33)
    assert can.price_per_crate == 20.91
    assert deal.title == "Gösser Märzen"
    assert matches_brand(deal, ["gösser"])
    assert not matches_brand(deal, ["Stiegl"])
    assert matches_brand(deal, ["Gosser Märzen"])
    urtyp = Deal(store="mpreis", name="Zipfer Urtyp Medium 0,5 Liter", brand="Zipfer")
    assert matches_brand(urtyp, ["Zipfer Urtyp"])
    assert not matches_brand(urtyp, ["Zipfer Märzen"])
    assert matches_brand(urtyp, ["zipfer"])


def test_unflatten_devalue():
    flat = [{"a": 1, "b": 2}, "x", ["Reactive", 3], {"c": 4}, [5, 1], 7]
    assert unflatten(flat) == {"a": "x", "b": {"c": [7, "x"]}}


def test_penny():
    deals = penny.parse(_fixture("penny_bier.html"))
    assert deals
    otta = next(d for d in deals if d.brand == "Ottakringer")
    assert otta.price == 0.69
    assert otta.regular_price == 1.09
    assert otta.volume_l == 0.33
    assert otta.valid_to == "2026-11-25"
    assert otta.price_per_liter == 2.09


def test_lidl_region():
    html = _fixture("lidl_bier.html")
    deals = lidl.parse(html, "1")
    assert deals
    kaiser = next(d for d in deals if d.brand == "KAISER")
    assert kaiser.price == 14.8
    assert kaiser.volume_l == 10.0
    assert kaiser.price_per_liter == 1.48
    assert "Lidl Plus" in (kaiser.condition or "")
    assert kaiser.valid_from == "2026-11-19"
    assert kaiser.valid_to == "2026-11-21"


def test_mpreis():
    deals = mpreis.parse(_fixture("mpreis_bier.html"))
    titles = [d.title for d in deals]
    assert not any("Frucade" in t for t in titles)  # lemonade listed under 'Bier'
    zipfer = next(d for d in deals if d.title == "Zipfer Märzen 20x 0,5 Liter")
    assert zipfer.price == 14.8
    assert zipfer.price_per_crate == 14.8
    egger = next(d for d in deals if d.brand == "Egger")
    assert egger.condition == "1+1 gratis"
    assert egger.price_per_crate == 11.5
    kaiser = next(d for d in deals if d.brand == "Kaiser")
    assert kaiser.package == "Kiste 20x 0,5 Liter"
    assert zipfer.url.endswith("/shop/p/zipfer-maerzen-20x-05-liter-800210")


def test_billa_finds_pdfs():
    found = billa.find_leaflets(_fixture("billa_flugblatt.html"), "Wien")
    assert found["billa"].endswith("BILLA_FB_KW_47_2026_Wien.pdf")
    assert found["billa_plus"].endswith("BILLA_PLUS_FB_KW_47_2026_Wien.pdf")


def test_ai_answer_parsing():
    answer = """```json
    {"deals": [{"brand": "Gösser", "name": "Märzen", "package": "0,5 Liter Dose",
      "price": "0,69", "regular_price": 1.39, "condition": "bei 12 Dosen je"},
      {"brand": "", "name": "", "price": 1}]}
    ```"""
    deals = leaflet.parse_ai_answer(answer, "billa", "https://example.invalid/x.pdf")
    assert len(deals) == 1
    assert deals[0].price == 0.69
    assert deals[0].price_per_liter == 1.38
    assert deals[0].source == "ai"


WIEN = (48.2085, 16.3731)  # Stephansplatz, only used with the saved fixture


def test_nearby_radius():
    data = json.loads(_fixture("osm_wien.json"))
    data["elements"].append(
        {"type": "way", "id": 1, "center": {"lat": 48.2090, "lon": 16.3740},
         "tags": {"brand:wikidata": "Q873491", "name": "MPREIS Test"}}
    )
    found = nearby.parse(data, *WIEN, 2.0)
    assert set(found) == {"penny", "billa_plus", "mpreis"}  # Lidl is 3 km away, Spar not read
    assert found["penny"][0]["distance_km"] == 1.3
    assert found["penny"][0]["distance_km"] <= found["penny"][1]["distance_km"]
    assert set(nearby.parse(data, *WIEN, 5.0)) >= {"lidl"}


def test_nearby_query_rounds_location():
    query = nearby.build_query(48.208512, 16.373123, 7, ["penny", "lidl", "custom"])
    assert "Q284688|Q151954" in query
    assert "48.2085" not in query and "16.3731" not in query


def test_reverse_address():
    answer = {"address": {"road": "Stadtplatz", "house_number": "27", "postcode": "4400", "town": "Steyr"}}
    assert nearby.parse_address(answer) == "Stadtplatz 27, 4400 Steyr"
    assert nearby.parse_address({"display_name": "Irgendwo"}) == "Irgendwo"
    assert nearby.reverse_params(48.0381234, 14.4199876)["lat"] == "48.03812"


def test_alcohol():
    assert parse_alcohol("Sechserpack Dosen helles Bier mit 4,5 % Alkoholgehalt.") == 4.5
    assert parse_alcohol("Zipfer Bier 0,0% alkoholfrei") == 0.0
    assert parse_alcohol("Gösser Märzen 0,5 Liter") is None
    assert typical_alcohol(Deal(store="penny", name="Urtyp", brand="Zipfer")) == 5.4
    assert typical_alcohol(Deal(store="penny", name="Naturradler", brand="Gösser")) == 2.0
    assert typical_alcohol(Deal(store="penny", name="Märzen Radler", brand="Gösser")) is None
    assert typical_alcohol(Deal(store="penny", name="Bockbier", brand="Unbekannt")) is None
    lidl_hell = next(d for d in lidl.parse(_fixture("lidl_bier.html"), "1") if d.alcohol)
    assert lidl_hell.alcohol == 4.5
    info = lidl_hell.as_dict()
    assert info["alcohol"] == 4.5 and info["alcohol_typical"] is False
    zipfer = next(d for d in mpreis.parse(_fixture("mpreis_bier.html")) if d.title == "Zipfer Märzen 20x 0,5 Liter")
    assert zipfer.as_dict()["alcohol"] == 5.0 and zipfer.as_dict()["alcohol_typical"] is True


def test_billa_pdf_layout():
    path = FIXTURES / "billa_kw47_bier.pdf"
    if not path.exists():
        pytest.skip("fixture missing")
    deals = {(d.title, d.price): d for d in pdf_layout.parse(path.read_bytes(), "billa", "x", 2026)}
    assert len(deals) == 8
    assert deals[("Wieselburger Gold", 14.8)].volume_l == 10.0
    assert "nördlichen Burgenland" in deals[("Wieselburger Gold", 14.8)].condition
    otta = deals[("Ottakringer Helles", 0.69)]
    assert (otta.regular_price, otta.volume_l, otta.condition) == (1.39, 0.5, "6+6 Bei 12 dosen je")
    assert deals[("Stiegl Goldbräu", 0.86)].condition.startswith("8+4")
    assert all(d.valid_from == "2026-11-19" and d.valid_to == "2026-11-25" for d in deals.values())
    plus = {d.title for d in pdf_layout.parse((FIXTURES / "billa_plus_kw47_bier.pdf").read_bytes(), "billa_plus", "x", 2026)}
    assert {"Pilsner Urquell", "Heineken Lager od. 0.0 %"} <= plus
    assert not any("Riese" in t or "brot" in t for t in plus)
