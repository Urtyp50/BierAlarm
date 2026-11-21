"""Constants for BierAlarm."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "bieralarm"

CONF_STORES = "stores"
CONF_LIDL_REGION = "lidl_region"
CONF_BILLA_REGION = "billa_region"
CONF_AI_TASK_ENTITY = "ai_task_entity"
CONF_FAVORITE_BRANDS = "favorite_brands"
CONF_MAX_PRICE_PER_LITER = "max_price_per_liter"
CONF_NOTIFY_ENTITY = "notify_entity"
CONF_EXTRA_LEAFLETS = "extra_leaflets"
CONF_RADIUS_KM = "radius_km"

STORE_PENNY = "penny"
STORE_LIDL = "lidl"
STORE_BILLA = "billa"
STORE_BILLA_PLUS = "billa_plus"
STORE_MPREIS = "mpreis"

STORE_NAMES = {
    STORE_PENNY: "PENNY",
    STORE_LIDL: "Lidl",
    STORE_MPREIS: "MPREIS",
    STORE_BILLA: "BILLA",
    STORE_BILLA_PLUS: "BILLA PLUS",
}

# Stores that need the AI Task entity because their leaflet only exists as PDF.
AI_STORES = {STORE_BILLA, STORE_BILLA_PLUS}

LIDL_REGIONS = {
    "1": "Ost – Lager Großebersdorf (Wien, NÖ, Bgld)",
    "2": "West – Lager Laakirchen (OÖ, Sbg, Tirol, Vbg)",
    "3": "Süd – Lager Wundschuh (Stmk, Kärnten)",
}

BILLA_REGIONS = [
    "Wien",
    "Niederösterreich",
    "Burgenland",
    "Oberösterreich",
    "Salzburg",
    "Steiermark",
    "Kärnten",
    "Tirol",
    "Vorarlberg",
]

DEFAULT_STORES = [STORE_PENNY, STORE_LIDL]
DEFAULT_LIDL_REGION = "1"
DEFAULT_BILLA_REGION = "Wien"

UPDATE_INTERVAL = timedelta(hours=6)
REQUEST_TIMEOUT = 30

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0 Safari/537.36 BierAlarm-HomeAssistant"
)

EVENT_NEW_DEAL = f"{DOMAIN}_new_deal"
SERVICE_REFRESH = "refresh"

PANEL_URL_PATH = "bieralarm"
PANEL_COMPONENT = "bieralarm-panel"
PANEL_STATIC_URL = "/bieralarm_static"

STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}.cache"

# Beers that get an on/off switch ("benachrichtigen bei ..."). The first word is the brand.
# A name matches a deal when every word appears in it, so "Zipfer" alone means all Zipfer.
# Favourites typed in the options that are not listed here get a switch too.
BEERS = [
    "Zipfer Märzen",
    "Zipfer Urtyp",
    "Zipfer Pils",
    "Gösser Märzen",
    "Gösser Gold",
    "Gösser Zwickl",
    "Gösser Naturradler",
    "Stiegl Goldbräu",
    "Stiegl Hell",
    "Ottakringer Helles",
    "Ottakringer Wiener Original",
    "Ottakringer Zwickl",
    "Puntigamer",
    "Kaiser Märzen",
    "Kaiser Fasstyp",
    "Kaiser Doppelmalz",
    "Schwechater Bier",
    "Schwechater Zwickl",
    "Egger Märzen",
    "Egger Zwickl",
    "Wieselburger Gold",
    "Wieselburger Stammbräu",
    "Freistädter Ratsherrn",
    "Murauer Märzen",
    "Hirter Privat Pils",
    "Hirter Märzen",
    "Trumer Pils",
    "Edelweiss",
    "Villacher Märzen",
    "Schladminger Märzen",
    "Fohrenburger Jubiläum",
    "Franziskaner",
    "Budweiser",
    "Heineken",
]

FILTER_ALL = "Alle"

# Store locations change rarely: ask OpenStreetMap once a week.
NEARBY_MAX_AGE = timedelta(days=7)
