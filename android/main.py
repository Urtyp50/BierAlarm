"""BierAlarm for Android: beer offers of Austrian supermarkets, without Home Assistant."""

from __future__ import annotations

from datetime import date, datetime, timedelta
import logging
import threading

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.lang import Builder
from kivy.metrics import dp
from kivy.properties import BooleanProperty, ListProperty, StringProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.screenmanager import FadeTransition, Screen, ScreenManager
from kivy.uix.togglebutton import ToggleButton
from kivy.utils import platform

from fetcher import ALL_STORES, Fetcher, store_name
from bieralarm.const import BEERS, BILLA_REGIONS, LIDL_REGIONS

logging.getLogger("pypdf").setLevel(logging.ERROR)

STORE_COLORS = {
    "penny": "#c62828", "lidl": "#0050aa", "mpreis": "#6d4c41", "billa": "#f9a825",
    "billa_plus": "#e65100", "interspar": "#c8102e", "hofer": "#1d3c78",
}
AUTO_REFRESH = timedelta(hours=3)
ALL = "Alle Märkte"

KV = """
#:import hex kivy.utils.get_color_from_hex

<Label>:
    color: hex('#eceff1')

<DealRow>:
    orientation: 'horizontal'
    size_hint_y: None
    height: dp(84)
    padding: dp(10), dp(6)
    spacing: dp(10)
    canvas.before:
        Color:
            rgba: hex('#1e2327')
        RoundedRectangle:
            pos: self.x + dp(6), self.y + dp(3)
            size: self.width - dp(12), self.height - dp(6)
            radius: [dp(10)]
        Color:
            rgba: hex('#ff9800') if self.favorite else (0, 0, 0, 0)
        RoundedRectangle:
            pos: self.x + dp(6), self.y + dp(3)
            size: dp(5), self.height - dp(6)
            radius: [dp(3)]
    BoxLayout:
        orientation: 'vertical'
        size_hint_x: 0.64
        padding: dp(6), 0, 0, 0
        BoxLayout:
            size_hint_y: None
            height: dp(22)
            spacing: dp(6)
            Label:
                text: root.store
                bold: True
                font_size: '11sp'
                size_hint_x: None
                width: self.texture_size[0] + dp(12)
                canvas.before:
                    Color:
                        rgba: hex(root.store_color)
                    RoundedRectangle:
                        pos: self.pos
                        size: self.size
                        radius: [dp(4)]
            Label:
                text: 'ALARM' if root.favorite else ''
                bold: True
                font_size: '11sp'
                color: hex('#ff9800')
                text_size: self.size
                halign: 'left'
                valign: 'middle'
        Label:
            text: root.title
            bold: True
            font_size: '15sp'
            text_size: self.size
            halign: 'left'
            valign: 'middle'
            shorten: True
            shorten_from: 'right'
        Label:
            text: root.detail
            font_size: '12sp'
            color: hex('#90a4ae')
            text_size: self.size
            halign: 'left'
            valign: 'top'
            shorten: True
            shorten_from: 'right'
    BoxLayout:
        orientation: 'vertical'
        size_hint_x: 0.36
        Label:
            text: root.price
            bold: True
            font_size: '19sp'
            color: hex('#ffb74d')
            text_size: self.size
            halign: 'right'
            valign: 'bottom'
        Label:
            text: root.crate
            font_size: '12sp'
            text_size: self.size
            halign: 'right'
            valign: 'middle'
        Label:
            text: root.until
            font_size: '11sp'
            color: hex('#90a4ae')
            text_size: self.size
            halign: 'right'
            valign: 'top'

<Field@TextInput>:
    multiline: False
    size_hint_y: None
    height: dp(44)
    font_size: '15sp'
    padding: dp(10), dp(12)
    background_color: hex('#263238')
    foreground_color: hex('#eceff1')
    cursor_color: hex('#ffb74d')
    hint_text_color: hex('#78909c')

<Btn@Button>:
    size_hint_y: None
    height: dp(44)
    font_size: '15sp'
    bold: True
    background_normal: ''
    background_color: hex('#37474f')

<Heading@Label>:
    size_hint_y: None
    height: dp(30)
    font_size: '13sp'
    bold: True
    color: hex('#ffb74d')
    text_size: self.size
    halign: 'left'
    valign: 'bottom'

<DealsScreen>:
    BoxLayout:
        orientation: 'vertical'
        canvas.before:
            Color:
                rgba: hex('#121517')
            Rectangle:
                pos: self.pos
                size: self.size
        BoxLayout:
            size_hint_y: None
            height: dp(56)
            padding: dp(14), dp(6)
            spacing: dp(8)
            canvas.before:
                Color:
                    rgba: hex('#1b1f22')
                Rectangle:
                    pos: self.pos
                    size: self.size
            Label:
                text: 'BierAlarm'
                bold: True
                font_size: '21sp'
                color: hex('#ffb74d')
                text_size: self.size
                halign: 'left'
                valign: 'middle'
            Btn:
                text: 'Laden…' if app.busy else 'Aktualisieren'
                disabled: app.busy
                size_hint_x: None
                width: dp(132)
                on_release: app.refresh(force=True)
            Btn:
                text: 'Einstellungen'
                size_hint_x: None
                width: dp(124)
                on_release: app.show_settings()
        BoxLayout:
            size_hint_y: None
            height: dp(74)
            padding: dp(14), dp(6)
            orientation: 'vertical'
            Label:
                text: 'Billigste 20er-Kiste'
                font_size: '12sp'
                color: hex('#90a4ae')
            Label:
                text: app.best
                bold: True
                font_size: '20sp'
                color: hex('#ffb74d')
        BoxLayout:
            size_hint_y: None
            height: dp(52)
            padding: dp(10), dp(4)
            spacing: dp(8)
            Field:
                id: search
                hint_text: 'Suche, z. B. Urtyp'
                on_text: app.apply_filter()
            Spinner:
                id: store
                text: 'Alle Märkte'
                values: app.store_choices
                size_hint: None, None
                width: dp(140)
                height: dp(44)
                background_normal: ''
                background_color: hex('#37474f')
                on_text: app.apply_filter()
        Label:
            text: app.status
            size_hint_y: None
            height: dp(26) if app.status else 0
            font_size: '12sp'
            color: hex('#ef9a9a') if app.has_errors else hex('#90a4ae')
            text_size: self.width - dp(24), None
            halign: 'left'
        RecycleView:
            id: rv
            viewclass: 'DealRow'
            RecycleBoxLayout:
                default_size: None, dp(84)
                default_size_hint: 1, None
                size_hint_y: None
                height: self.minimum_height
                orientation: 'vertical'
                padding: 0, dp(4), 0, dp(12)

<SettingsScreen>:
    BoxLayout:
        orientation: 'vertical'
        canvas.before:
            Color:
                rgba: hex('#121517')
            Rectangle:
                pos: self.pos
                size: self.size
        BoxLayout:
            size_hint_y: None
            height: dp(56)
            padding: dp(14), dp(6)
            canvas.before:
                Color:
                    rgba: hex('#1b1f22')
                Rectangle:
                    pos: self.pos
                    size: self.size
            Label:
                text: 'Einstellungen'
                bold: True
                font_size: '21sp'
                color: hex('#ffb74d')
                text_size: self.size
                halign: 'left'
                valign: 'middle'
        ScrollView:
            BoxLayout:
                id: form
                orientation: 'vertical'
                size_hint_y: None
                height: self.minimum_height
                padding: dp(14)
                spacing: dp(8)
                Heading:
                    text: 'Märkte'
                GridLayout:
                    id: stores
                    cols: 2
                    spacing: dp(6)
                    size_hint_y: None
                    height: self.minimum_height
                Heading:
                    text: 'Region (BILLA, INTERSPAR)'
                Spinner:
                    id: region
                    values: app.regions
                    size_hint_y: None
                    height: dp(44)
                    background_normal: ''
                    background_color: hex('#37474f')
                Heading:
                    text: 'Lidl-Region'
                Spinner:
                    id: lidl_region
                    values: app.lidl_regions
                    size_hint_y: None
                    height: dp(44)
                    background_normal: ''
                    background_color: hex('#37474f')
                Heading:
                    text: 'Benachrichtigen bei (mit Beistrich getrennt)'
                Field:
                    id: favorites
                    hint_text: 'z. B. Zipfer Urtyp, Gösser Märzen'
                Label:
                    text: 'Nur die Marke (z. B. Zipfer) heißt alle Sorten. Bekannt: ' + app.known_beers
                    font_size: '11sp'
                    color: hex('#78909c')
                    size_hint_y: None
                    text_size: self.width, None
                    height: self.texture_size[1]
                Heading:
                    text: 'Alarm, wenn eine 20er-Kiste höchstens so viel kostet (€, 0 = aus)'
                Field:
                    id: max_crate
                    input_filter: 'float'
                Label:
                    text: 'INTERSPAR und HOFER laden ein PDF-Flugblatt (bis ca. 45 MB, einmal pro Woche). Am besten im WLAN zuerst öffnen.'
                    font_size: '11sp'
                    color: hex('#78909c')
                    size_hint_y: None
                    text_size: self.width, None
                    height: self.texture_size[1] + dp(8)
                Btn:
                    text: 'Speichern'
                    background_color: hex('#e65100')
                    on_release: app.save_settings()
                Btn:
                    text: 'Abbrechen'
                    on_release: app.show_deals()
"""


class DealRow(BoxLayout):
    store = StringProperty("")
    store_color = StringProperty("#546e7a")
    title = StringProperty("")
    detail = StringProperty("")
    price = StringProperty("")
    crate = StringProperty("")
    until = StringProperty("")
    favorite = BooleanProperty(False)


class DealsScreen(Screen):
    pass


class SettingsScreen(Screen):
    pass


def euro(value: float | None) -> str:
    return "" if value is None else f"€ {value:.2f}".replace(".", ",")


def short_date(iso: str | None) -> str:
    if not iso:
        return ""
    try:
        return datetime.strptime(iso, "%Y-%m-%d").strftime("bis %d.%m.")
    except ValueError:
        return ""


class BierAlarmApp(App):
    title = "BierAlarm"
    busy = BooleanProperty(False)
    has_errors = BooleanProperty(False)
    status = StringProperty("")
    best = StringProperty("–")
    store_choices = ListProperty([ALL])
    regions = ListProperty(BILLA_REGIONS)
    lidl_regions = ListProperty(list(LIDL_REGIONS.values()))
    known_beers = StringProperty(", ".join(BEERS[:12]) + " …")

    def build(self):
        Window.clearcolor = (0.07, 0.08, 0.09, 1)
        Builder.load_string(KV)
        self.fetcher = Fetcher(self.user_data_dir)
        self.deals = []
        self.sm = ScreenManager(transition=FadeTransition(duration=0.12))
        self.deals_screen = DealsScreen(name="deals")
        self.settings_screen = SettingsScreen(name="settings")
        self.sm.add_widget(self.deals_screen)
        self.sm.add_widget(self.settings_screen)
        return self.sm

    def on_start(self):
        self._ask_notification_permission()
        self.deals = self.fetcher.cached_deals()
        self._show(self.deals, {})
        self.refresh()

    def on_resume(self):
        self.refresh()

    # ----------------------------------------------------------------- refresh
    def refresh(self, force: bool = False) -> None:
        if self.busy:
            return
        updated = self.fetcher.cache.get("updated")
        if not force and updated and datetime.now() - datetime.fromisoformat(updated) < AUTO_REFRESH:
            return
        self.busy = True
        self.status = "Flugblätter werden geladen …"
        self.has_errors = False
        threading.Thread(target=self._refresh_worker, daemon=True).start()

    def _refresh_worker(self) -> None:
        try:
            deals, errors, new = self.fetcher.refresh()
        except Exception as err:  # noqa: BLE001
            Clock.schedule_once(lambda _dt: self._failed(err))
            return
        Clock.schedule_once(lambda _dt: self._done(deals, errors, new))

    def _failed(self, err: Exception) -> None:
        self.busy = False
        self.has_errors = True
        self.status = f"Fehler: {err}"

    def _done(self, deals, errors, new) -> None:  # noqa: ANN001
        self.busy = False
        self.deals = deals
        self._show(deals, errors)
        if new:
            self._notify(new)

    def _show(self, deals, errors) -> None:  # noqa: ANN001
        stores = sorted({store_name(d.store) for d in deals})
        self.store_choices = [ALL, *stores]
        crates = [d for d in deals if d.price_per_crate]
        if crates:
            top = min(crates, key=lambda d: d.price_per_crate)
            self.best = f"{euro(top.price_per_crate)}  ·  {store_name(top.store)} {top.title}"
        else:
            self.best = "–"
        updated = self.fetcher.cache.get("updated")
        when = datetime.fromisoformat(updated).strftime("%d.%m. %H:%M") if updated else "noch nie"
        if errors:
            self.has_errors = True
            self.status = "Nicht erreichbar: " + ", ".join(
                "BILLA" if k == "billa" else store_name(k) for k in errors
            ) + f"  ·  Stand {when}"
        else:
            self.has_errors = False
            self.status = f"{len(deals)} Aktionen  ·  Stand {when}" if deals else ""
        self.apply_filter()

    def apply_filter(self) -> None:
        ids = self.deals_screen.ids
        query = ids.search.text.strip().lower()
        store = ids.store.text
        rows = []
        for d in self.deals:
            if store != ALL and store_name(d.store) != store:
                continue
            if query and query not in f"{d.title} {d.package or ''} {store_name(d.store)}".lower():
                continue
            alcohol = d.as_dict().get("alcohol")
            detail = " · ".join(
                x for x in (
                    d.package,
                    d.condition,
                    "alkoholfrei" if alcohol == 0 else (f"{alcohol:.1f} % vol".replace(".", ",") if alcohol else None),
                ) if x
            )
            regular = f"  statt {euro(d.regular_price)}" if d.regular_price else ""
            rows.append({
                "store": store_name(d.store),
                "store_color": STORE_COLORS.get(d.store, "#546e7a"),
                "title": d.title,
                "detail": detail,
                "price": euro(d.price),
                "crate": f"Kiste {euro(d.price_per_crate)}" if d.price_per_crate else regular.strip(),
                "until": short_date(d.valid_to),
                "favorite": self.fetcher.is_favorite(d),
            })
        ids.rv.data = rows

    # ---------------------------------------------------------- notifications
    def _ask_notification_permission(self) -> None:
        if platform != "android":
            return
        try:
            from android.permissions import Permission, request_permissions  # noqa: PLC0415

            request_permissions([Permission.POST_NOTIFICATIONS])
        except Exception:  # noqa: BLE001 - older Android: no runtime permission needed
            pass

    def _notify(self, deals) -> None:  # noqa: ANN001
        lines = [
            f"{store_name(d.store)}: {d.title} {euro(d.price)}"
            + (f" (Kiste {euro(d.price_per_crate)})" if d.price_per_crate else "")
            for d in deals[:5]
        ]
        title = "Bier in Aktion" if len(deals) == 1 else f"{len(deals)} Bieraktionen"
        try:
            from plyer import notification  # noqa: PLC0415

            notification.notify(title=title, message="\n".join(lines), app_name="BierAlarm", timeout=10)
        except Exception:  # noqa: BLE001 - desktop without notifications
            self.status = f"{title}: " + "; ".join(lines)

    # --------------------------------------------------------------- settings
    def show_settings(self) -> None:
        s = self.fetcher.settings
        ids = self.settings_screen.ids
        ids.stores.clear_widgets()
        for store in ALL_STORES:
            button = ToggleButton(
                text=store_name(store), state="down" if store in s["stores"] else "normal",
                size_hint_y=None, height=dp(44), background_normal="", background_down="",
            )
            button.store = store
            button.bind(state=self._color_toggle)
            self._color_toggle(button, button.state)
            ids.stores.add_widget(button)
        ids.region.text = s.get("region") or "Wien"
        ids.lidl_region.text = LIDL_REGIONS.get(str(s.get("lidl_region", "1")), LIDL_REGIONS["1"])
        ids.favorites.text = s.get("favorites", "")
        ids.max_crate.text = str(s.get("max_crate_price") or 0).replace(".", ",") if s.get("max_crate_price") else ""
        self.sm.current = "settings"

    @staticmethod
    def _color_toggle(button, state) -> None:  # noqa: ANN001
        button.background_color = (0.9, 0.32, 0, 1) if state == "down" else (0.22, 0.28, 0.31, 1)

    def save_settings(self) -> None:
        ids = self.settings_screen.ids
        s = self.fetcher.settings
        old = (sorted(s["stores"]), s.get("region"), s.get("lidl_region"))
        s["stores"] = [b.store for b in ids.stores.children if b.state == "down"]
        s["region"] = ids.region.text
        s["lidl_region"] = next((k for k, v in LIDL_REGIONS.items() if v == ids.lidl_region.text), "1")
        s["favorites"] = ids.favorites.text.strip()
        try:
            s["max_crate_price"] = float((ids.max_crate.text or "0").replace(",", "."))
        except ValueError:
            s["max_crate_price"] = 0
        self.fetcher.save_settings()
        self.show_deals()
        changed = old != (sorted(s["stores"]), s.get("region"), s.get("lidl_region"))
        if changed:
            self.refresh(force=True)
        else:
            self.apply_filter()

    def show_deals(self) -> None:
        self.sm.current = "deals"


if __name__ == "__main__":
    BierAlarmApp().run()
