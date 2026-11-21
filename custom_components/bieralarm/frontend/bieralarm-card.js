/* bieralarm-card — Bieraktionen pro 20er-Kiste, Filter und Marken-Alarm, im Stil der dimplex-heatpump-card */
const BA_STORE = {
  "PENNY": "#c62828", "Lidl": "#0050aa", "MPREIS": "#6d4c41",
  "BILLA": "#f9a825", "BILLA PLUS": "#e65100", "INTERSPAR": "#c8102e", "Eigenes Flugblatt": "#546e7a"
};
const BA_ALL = "Alle";
// Logos are loaded from each store's own website; if one fails, the coloured text badge is shown.
const BA_LOGO = {
  "PENNY": "https://www.penny.at/tenant/logo.svg",
  "Lidl": "https://www.lidl.at/cdn/assets/logos/1.0.1/lidl-logo-shop-cdn.svg",
  "MPREIS": "https://www.mpreis.at/apple-icon-180x180.webp",
  "BILLA": "https://assets-eu-01.kc-usercontent.com/cc0b17b0-a734-010a-8710-f644b7ee1f24/ff0150f7-0745-4842-b1de-9fc2b4499ac5/favicon.png",
  "BILLA PLUS": "https://assets-eu-01.kc-usercontent.com/cc0b17b0-a734-010a-8710-f644b7ee1f24/ff0150f7-0745-4842-b1de-9fc2b4499ac5/favicon.png"
};

class BierAlarmCard extends HTMLElement {
  static getStubConfig() { return { title: "BierAlarm" }; }

  setConfig(cfg) {
    this._cfg = Object.assign({
      // Entity ids are found automatically (platform bieralarm); set them only to override.
      title: "BierAlarm", subtitle: "Bieraktionen pro 20er-Kiste",
      deals: null, best_crate: null, best_liter: null, filter: null, store_filter: null, radius: null, crate_limit: null,
      map: true,
      max_rows: 40,
      store_logos: true,   // false = only coloured text badges
      logos: {}            // override, e.g. { "PENNY": "/local/penny.png" }
    }, cfg || {});
    if (!this._sr) this._sr = this.attachShadow({ mode: "open" });
    this._built = false;
  }
  getCardSize() { return 14; }
  set hass(h) {
    this._hass = h;
    if (!this._ids) this._find();
    if (!this._built) this._build();
    this._render();
  }

  // Look the BierAlarm entities up by their translation key, so renamed ids still work.
  _find() {
    const reg = Object.values(this._hass.entities || {}).filter((e) => e.platform === "bieralarm");
    if (!reg.length) return;
    const by = (domain, key) => (reg.find((e) => e.entity_id.startsWith(domain + ".") && e.translation_key === key) || {}).entity_id || null;
    const C = this._cfg;
    C.deals = C.deals || by("sensor", "deals");
    C.best_crate = C.best_crate || by("sensor", "best_crate_price");
    C.best_liter = C.best_liter || by("sensor", "best_price");
    C.filter = C.filter || by("text", "filter");
    C.store_filter = C.store_filter || by("select", "store_filter");
    C.radius = C.radius || by("number", "radius");
    C.crate_limit = C.crate_limit || by("number", "crate_limit");
    this._ids = true;
  }
  _beerSwitches() {
    const reg = Object.values(this._hass.entities || {});
    return reg.filter((e) => e.platform === "bieralarm" && e.translation_key === "brand" && this._hass.states[e.entity_id])
      .map((e) => this._hass.states[e.entity_id]);
  }

  _o(id) { return id && this._hass ? this._hass.states[id] : null; }
  _s(id) { const o = this._o(id); return o ? o.state : null; }
  _v(id) { const o = this._o(id); if (!o) return null; const n = parseFloat(o.state); return isNaN(n) ? null : n; }
  _more(id) {
    const e = new Event("hass-more-info", { bubbles: true, composed: true }); e.detail = { entityId: id }; this.dispatchEvent(e);
  }
  _fmt(v, d) { return v === null || v === undefined ? "–" : Number(v).toLocaleString("de-AT", { minimumFractionDigits: d, maximumFractionDigits: d }); }
  _eur(v) { return v === null || v === undefined ? "–" : "€ " + this._fmt(v, 2); }
  _date(s) { if (!s) return null; const p = s.split("-"); return p.length === 3 ? p[2] + "." + p[1] + "." : s; }
  _esc(s) { return String(s === null || s === undefined ? "" : s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]); }
  _pct(v, lo, hi) { return v === null || hi <= lo ? 0 : Math.max(4, Math.min(100, ((v - lo) / (hi - lo)) * 100)); }

  _build() {
    this._sr.innerHTML = `
<style>
  :host { display:block; }
  ha-card { overflow:hidden; padding:0; }
  .hdr { display:flex; align-items:center; gap:12px; padding:16px 16px 12px; }
  .ic { width:44px; height:44px; border-radius:50%; display:flex; align-items:center; justify-content:center; flex:0 0 auto;
        transition:background .3s ease, color .3s ease; cursor:pointer; }
  .ic ha-icon { --mdc-icon-size:26px; }
  .ic.run ha-icon { animation:pulse 2.4s ease-in-out infinite; }
  @keyframes pulse { 0%,100% { opacity:1; } 50% { opacity:.55; } }
  .ttl { flex:1; min-width:0; }
  .nmh { font-size:1.05rem; font-weight:600; color:var(--primary-text-color); line-height:1.25; }
  .sb { font-size:.78rem; color:var(--secondary-text-color); }
  .pill { display:flex; align-items:center; gap:6px; padding:5px 10px; border-radius:14px; font-size:.78rem; font-weight:600; white-space:nowrap; }
  .dot { width:8px; height:8px; border-radius:50%; background:currentColor; }
  .ok { color:#2e7d32; background:rgba(46,125,50,.14); }
  .warn { color:#ef6c00; background:rgba(239,108,0,.16); }
  .err { color:#c62828; background:rgba(198,40,40,.16); }
  .beer { color:#e65100; background:rgba(230,81,0,.15); }
  .idle { color:var(--secondary-text-color); background:var(--divider-color); }
  .sec { padding:12px 16px; border-top:1px solid var(--divider-color); }
  .lbl { display:flex; align-items:baseline; gap:8px; font-size:.72rem; letter-spacing:.06em; text-transform:uppercase;
         color:var(--secondary-text-color); margin-bottom:9px; }
  .lbl span { margin-left:auto; letter-spacing:0; text-transform:none; font-variant-numeric:tabular-nums; }
  .big { display:flex; align-items:center; gap:6px; }
  .end { flex:1; min-width:0; text-align:center; cursor:pointer; }
  .end em { display:block; font-style:normal; font-size:.72rem; color:var(--secondary-text-color); }
  .end b { display:block; font-size:1.25rem; font-weight:600; font-variant-numeric:tabular-nums; line-height:1.3; color:var(--primary-text-color);
           white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .end.k b { color:#e65100; }
  .end small { display:block; font-size:.72rem; color:var(--secondary-text-color); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .search { display:flex; align-items:center; gap:8px; border:1px solid var(--divider-color); border-radius:12px;
            background:var(--secondary-background-color); padding:0 10px; margin-bottom:8px; }
  .search ha-icon { --mdc-icon-size:18px; color:var(--secondary-text-color); }
  .search input { flex:1; min-width:0; border:0; outline:0; background:transparent; font:inherit; font-size:.9rem;
                  color:var(--primary-text-color); padding:9px 0; }
  .search button { border:0; background:transparent; color:var(--secondary-text-color); cursor:pointer; padding:4px; display:flex; }
  .modes { display:grid; grid-template-columns:repeat(auto-fit,minmax(72px,1fr)); gap:6px; }
  .mode { border:1px solid var(--divider-color); border-radius:12px; background:var(--secondary-background-color);
          padding:7px 4px 6px; cursor:pointer; display:flex; flex-direction:column; align-items:center; gap:3px;
          font:inherit; font-size:.74rem; color:var(--secondary-text-color); transition:all .25s ease; }
  .mode ha-icon { --mdc-icon-size:18px; }
  .mode.on { color:#e65100; border-color:#e65100; background:rgba(230,81,0,.12); font-weight:600; }
  .mode { position:relative; }
  .mode img.prod { width:36px; height:36px; object-fit:contain; border-radius:8px; background:#fff; padding:2px; box-sizing:border-box; }
  .mode.pic ha-icon { position:absolute; top:4px; right:5px; --mdc-icon-size:14px; }
  .mode i { font-style:normal; font-size:.66rem; opacity:.8; }
  .rows { display:flex; flex-direction:column; gap:6px; }
  .row { border-radius:12px; padding:9px 10px; background:var(--secondary-background-color); cursor:pointer; }
  .row.hit { box-shadow:inset 0 0 0 1px rgba(230,81,0,.55); }
  .rtop { display:flex; align-items:center; gap:8px; }
  .logo { flex:0 0 auto; width:34px; height:34px; border-radius:9px; overflow:hidden; background:#fff;
          box-shadow:0 0 0 1px var(--divider-color); display:flex; align-items:center; justify-content:center; }
  .logo img { width:100%; height:100%; object-fit:contain; display:block; }
  .logo.fail { display:none; }
  .logo.fail + .st { display:inline-block; }
  .st.alt { display:none; }
  .st { flex:0 0 auto; font-size:.66rem; font-weight:700; letter-spacing:.03em; padding:3px 7px; border-radius:8px; color:#fff; }
  .nm { flex:1; min-width:0; }
  .nm b { display:block; font-size:.88rem; font-weight:600; color:var(--primary-text-color); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .nm em { display:block; font-style:normal; font-size:.72rem; color:var(--secondary-text-color); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .pr { text-align:right; flex:0 0 auto; }
  .pr b { display:block; font-size:1rem; font-weight:600; font-variant-numeric:tabular-nums; color:var(--primary-text-color); }
  .row.hit .pr b { color:#e65100; }
  .pr em { display:block; font-style:normal; font-size:.7rem; color:var(--secondary-text-color); font-variant-numeric:tabular-nums; }
  .bell { --mdc-icon-size:18px; color:#e65100; flex:0 0 auto; }
  .track { position:relative; height:5px; border-radius:3px; background:var(--divider-color); margin-top:7px; }
  .track > i { display:block; height:100%; border-radius:3px; transition:width .4s ease, background .3s ease; }
  .empty { font-size:.85rem; color:var(--secondary-text-color); text-align:center; padding:10px 0; }
  .more { font-size:.75rem; color:var(--secondary-text-color); text-align:center; padding-top:6px; }
  .tiles { display:grid; grid-template-columns:repeat(auto-fit,minmax(120px,1fr)); gap:8px; }
  .tile { border-radius:12px; padding:10px; background:var(--secondary-background-color); }
  .tile em { display:block; font-style:normal; font-size:.72rem; color:var(--secondary-text-color); }
  .tile b { display:block; font-size:.9rem; font-weight:600; color:var(--primary-text-color); font-variant-numeric:tabular-nums; margin-top:2px; }
  .tile small { display:block; font-size:.7rem; color:var(--secondary-text-color); margin-top:2px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .tile.bad { box-shadow:inset 0 0 0 1px rgba(198,40,40,.5); }
  .tile.bad b { color:#c62828; }
  .tile.att { box-shadow:inset 0 0 0 1px rgba(239,108,0,.5); }
  .tile.att b { color:#ef6c00; }
  .hide { display:none; }
  .map { position:relative; height:220px; border-radius:12px; overflow:hidden; background:var(--secondary-background-color);
         box-shadow:inset 0 0 0 1px var(--divider-color); }
  .mtiles img { position:absolute; max-width:none; user-select:none; pointer-events:none; }
  .mtiles.dark img { filter:invert(1) hue-rotate(180deg) brightness(.85) contrast(.9); }
  .mtiles img { filter:saturate(.75); }
  .mcirc { position:absolute; inset:0; width:100%; height:100%; pointer-events:none; }
  .mpins > div { position:absolute; transform:translate(-50%,-50%); }
  .pin { width:24px; height:24px; border-radius:7px; overflow:hidden; background:#fff; cursor:default;
         box-shadow:0 1px 4px rgba(0,0,0,.35), 0 0 0 2px #fff; display:flex; align-items:center; justify-content:center; }
  .pin.near { width:30px; height:30px; border-radius:8px; z-index:2; }
  .pin img { width:100%; height:100%; object-fit:contain; }
  .pin span { font-size:.55rem; font-weight:700; color:#fff; }
  .home { width:30px; height:30px; border-radius:50%; background:#e65100; color:#fff; z-index:3;
          box-shadow:0 1px 4px rgba(0,0,0,.35), 0 0 0 3px #fff; display:flex; align-items:center; justify-content:center; }
  .home ha-icon { --mdc-icon-size:18px; }
  .mattr { position:absolute; right:0; bottom:0; font-size:.6rem; padding:1px 5px; background:rgba(255,255,255,.75); color:#333;
           border-top-left-radius:6px; }
  .moff { position:absolute; inset:0; display:none; align-items:center; justify-content:center; font-size:.82rem;
          color:var(--secondary-text-color); text-align:center; padding:0 16px; }
  .map.off .moff { display:flex; }
  .map.off .mattr, .map.off .mcirc, .map.off .mtiles, .map.off .mpins { display:none; }
  .urow { display:flex; align-items:center; gap:10px; margin-top:10px; }
  .uic { --mdc-icon-size:22px; color:#e65100; flex:0 0 auto; }
  .addr { flex:1; min-width:0; }
  .addr em { display:block; font-style:normal; font-size:.72rem; color:var(--secondary-text-color); }
  .addr b { display:block; font-size:.88rem; font-weight:600; color:var(--primary-text-color); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .step { display:flex; align-items:center; gap:2px; border:1px solid var(--divider-color); border-radius:12px;
          background:var(--secondary-background-color); padding:2px; flex:0 0 auto; }
  .step button { width:32px; height:32px; border:0; border-radius:10px; background:transparent; cursor:pointer;
                 color:var(--primary-text-color); display:flex; align-items:center; justify-content:center; }
  .step button:hover { background:rgba(230,81,0,.12); color:#e65100; }
  .step button:disabled { opacity:.35; cursor:default; background:transparent; }
  .step ha-icon { --mdc-icon-size:18px; }
  .step b { min-width:54px; text-align:center; font-size:.9rem; font-weight:600; font-variant-numeric:tabular-nums; color:var(--primary-text-color); }
  .step b.pend { color:#e65100; }
  .urow.lim { margin:0 0 10px; padding-bottom:10px; border-bottom:1px dashed var(--divider-color); }
  .lbl.tog { cursor:pointer; user-select:none; }
  .lbl.tog ha-icon { --mdc-icon-size:18px; transition:transform .25s ease; margin-left:2px; }
  .lbl.tog.open ha-icon { transform:rotate(180deg); }
  .toggle { display:flex; align-items:center; justify-content:center; gap:4px; width:100%; margin-top:8px; padding:7px;
            border:1px dashed var(--divider-color); border-radius:12px; background:transparent; cursor:pointer;
            font:inherit; font-size:.76rem; color:var(--secondary-text-color); }
  .toggle:hover { color:#e65100; border-color:#e65100; }
  .none { font-size:.82rem; color:var(--secondary-text-color); padding:2px 0 4px; }
  .grp { display:flex; align-items:flex-start; gap:10px; padding:4px 0; }
  .grp + .grp { border-top:1px dashed var(--divider-color); padding-top:8px; margin-top:4px; }
  .gn { flex:0 0 92px; font-size:.82rem; font-weight:600; color:var(--primary-text-color); padding-top:9px;
        white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .gn.on { color:#e65100; }
  .grp .modes { flex:1; grid-template-columns:repeat(auto-fill,minmax(84px,1fr)); }
</style>
<ha-card>
  <div class="hdr">
    <div class="ic idle" id="ic"><ha-icon id="ici" icon="mdi:beer"></ha-icon></div>
    <div class="ttl"><div class="nmh" id="hn"></div><div class="sb" id="hs"></div></div>
    <div class="pill idle" id="pill"><span class="dot"></span><span id="pt"></span></div>
  </div>
  <div class="sec">
    <div class="big">
      <div class="end k" id="eK"><em>Billigste 20er-Kiste</em><b id="vK">–</b><small id="sK"></small></div>
      <div class="end" id="eL"><em>Literpreis</em><b id="vL">–</b><small id="sL"></small></div>
      <div class="end" id="eM"><em>Märkte</em><b id="vM">–</b><small id="sM"></small></div>
    </div>
  </div>
  <div class="sec" id="secU">
    <div class="lbl">Umkreis<span id="lU"></span></div>
    <div class="map" id="map">
      <div class="mtiles" id="mt"></div>
      <svg class="mcirc" id="mc"><circle id="mcc" fill="rgba(230,81,0,.08)" stroke="#e65100" stroke-width="1.5" stroke-dasharray="5 4"></circle></svg>
      <div class="mpins" id="mp"></div>
      <div class="mattr">© OpenStreetMap-Mitwirkende</div>
      <div class="moff" id="moff">Umkreis aus – alle Märkte werden gezeigt</div>
    </div>
    <div class="urow">
      <ha-icon class="uic" icon="mdi:home-map-marker"></ha-icon>
      <div class="addr"><em>Startpunkt</em><b id="addr">–</b></div>
      <div class="step">
        <button id="rm" title="Umkreis verkleinern"><ha-icon icon="mdi:minus"></ha-icon></button>
        <b id="rv">–</b>
        <button id="rp" title="Umkreis vergrößern"><ha-icon icon="mdi:plus"></ha-icon></button>
      </div>
    </div>
  </div>
  <div class="sec">
    <div class="lbl">Filter</div>
    <div class="search">
      <ha-icon icon="mdi:magnify"></ha-icon>
      <input id="q" type="search" placeholder="Suchen, z. B. Urtyp" autocomplete="off">
      <button id="qx" title="Suche löschen"><ha-icon icon="mdi:close"></ha-icon></button>
    </div>
    <div class="modes" id="stores"></div>
  </div>
  <div class="sec">
    <div class="lbl">Aktionen<span id="lA"></span></div>
    <div class="rows" id="rows"></div>
    <div class="more" id="more"></div>
  </div>
  <div class="sec">
    <div class="lbl tog" id="tB">Benachrichtigen bei<span id="lB"></span><ha-icon id="cB" icon="mdi:chevron-down"></ha-icon></div>
    <div class="urow lim">
      <ha-icon class="uic" icon="mdi:bell-ring-outline"></ha-icon>
      <div class="addr"><em>Preis-Alarm für jedes Bier</em><b id="ltx">–</b></div>
      <div class="step">
        <button id="lm" title="Grenze senken"><ha-icon icon="mdi:minus"></ha-icon></button>
        <b id="lv">–</b>
        <button id="lp" title="Grenze erhöhen"><ha-icon icon="mdi:plus"></ha-icon></button>
      </div>
    </div>
    <div id="brands"></div>
    <button class="toggle" id="bB"></button>
  </div>
  <div class="sec hide" id="secD">
    <div class="lbl">Diagnose</div>
    <div class="tiles" id="tDi"></div>
  </div>
</ha-card>`;

    const $ = (id) => this._sr.getElementById(id);
    const C = this._cfg;
    this._el = { ic: $("ic"), ici: $("ici"), hn: $("hn"), hs: $("hs"), pill: $("pill"), pt: $("pt"),
      vK: $("vK"), sK: $("sK"), vL: $("vL"), sL: $("sL"), vM: $("vM"), sM: $("sM"),
      q: $("q"), qx: $("qx"), stores: $("stores"), lA: $("lA"), rows: $("rows"), more: $("more"),
      lB: $("lB"), brands: $("brands"), tB: $("tB"), bB: $("bB"),
      map: $("map"), mt: $("mt"), mc: $("mc"), mcc: $("mcc"), mp: $("mp"), lU: $("lU"), addr: $("addr"),
      rv: $("rv"), rm: $("rm"), rp: $("rp"), lv: $("lv"), lm: $("lm"), lp: $("lp"), ltx: $("ltx"), secD: $("secD"), tDi: $("tDi") };
    $("ic").addEventListener("click", () => this._more(C.deals));
    try { this._open = localStorage.getItem("bieralarm-card-open") === "1"; } catch (e) { this._open = false; }
    const flip = () => {
      this._open = !this._open;
      try { localStorage.setItem("bieralarm-card-open", this._open ? "1" : "0"); } catch (e) { /* private mode */ }
      this._render();
    };
    $("tB").addEventListener("click", flip);
    // −/+ buttons: change locally at once, send to Home Assistant after a short pause
    const stepper = (key, lo, hi) => (d) => {
      const ent = this._cfg[key];
      const cur = this._pend[key] !== undefined ? this._pend[key] : (this._v(ent) || 0);
      this._pend[key] = Math.round(Math.max(lo, Math.min(hi, cur + d)) * 100) / 100;
      this._render();
      clearTimeout(this._pendT[key]);
      this._pendT[key] = setTimeout(() => {
        this._hass.callService("number", "set_value", { entity_id: ent, value: this._pend[key] })
          .finally(() => { delete this._pend[key]; this._mapSig = null; this._render(); });
      }, 1200);
    };
    this._pend = {}; this._pendT = {};
    const rStep = stepper("radius", 0, 100), lStep = stepper("crate_limit", 0, 50);
    $("rm").addEventListener("click", () => rStep(-1));
    $("rp").addEventListener("click", () => rStep(1));
    $("lm").addEventListener("click", () => lStep(-0.5));
    $("lp").addEventListener("click", () => lStep(0.5));
    if (window.ResizeObserver) {
      this._ro = new ResizeObserver(() => { this._mapSig = null; this._render(); });
      this._ro.observe($("map"));
    }
    $("bB").addEventListener("click", flip);
    $("eK").addEventListener("click", () => this._more(C.best_crate));
    $("eL").addEventListener("click", () => this._more(C.best_liter));
    $("eM").addEventListener("click", () => this._more(C.deals));

    const q = this._el.q;
    q.addEventListener("input", () => {
      this._typing = q.value;
      this._render();
      clearTimeout(this._qT);
      this._qT = setTimeout(() => this._setFilter(q.value), 700);
    });
    q.addEventListener("keydown", (e) => { if (e.key === "Enter") { clearTimeout(this._qT); this._setFilter(q.value); } });
    this._el.qx.addEventListener("click", () => { q.value = ""; this._typing = ""; clearTimeout(this._qT); this._setFilter(""); this._render(); });
    this._built = true;
  }

  _renderRadius(a) {
    const E = this._el, C = this._cfg;
    const no = this._o(C.radius);
    const pend = this._pend.radius !== undefined;
    const r = pend ? this._pend.radius : (no ? this._v(C.radius) || 0 : a.radius_km || 0);
    E.rv.textContent = r ? r + " km" : "aus";
    E.rv.classList.toggle("pend", pend);
    E.rm.disabled = !no || r <= 0;
    E.rp.disabled = !no || r >= 100;
    E.addr.textContent = a.start_address || (this._hass.config && this._hass.config.location_name) || "Zuhause";
    E.lU.textContent = pend ? "wird geändert …" : (a.branches ? a.branches.length + " Filialen" : "");
    this._renderMap(pend ? 0 : (a.radius_km || 0), a.branches || []);
  }

  _renderMap(radius, branches) {
    const E = this._el, C = this._cfg, cfg = this._hass.config || {};
    const lat = cfg.latitude, lon = cfg.longitude;
    const show = C.map && radius > 0 && typeof lat === "number";
    E.map.classList.toggle("off", !show);
    E.map.parentElement.querySelector(".moff").textContent =
      this._pend.radius !== undefined ? "Umkreis wird geändert …" : "Umkreis aus – alle Märkte werden gezeigt";
    if (!C.map) { E.map.style.display = "none"; return; }
    if (!show) return;
    const w = E.map.clientWidth || 400, h = E.map.clientHeight || 200;
    const dark = !!(this._hass.themes && this._hass.themes.darkMode);
    const cos = Math.cos(lat * Math.PI / 180);
    // continuous zoom: the radius circle fills ~84 % of the shorter side; tiles are scaled to fit
    const zf = Math.log2((156543.03 * cos * Math.min(w, h) * 0.42) / (radius * 1000));
    const z = Math.max(8, Math.min(16, Math.ceil(zf)));
    const k = Math.min(1, Math.pow(2, zf - z));   // 0.5 … 1
    const T = 256 * k;                             // on-screen tile size
    const sig = [w, h, z, k.toFixed(4), lat, lon, dark, radius, branches.map((b) => b.lat + "," + b.lon).join(";")].join("|");
    if (this._mapSig === sig) return;
    this._mapSig = sig;
    const n = 256 * Math.pow(2, z);
    const px = (la, lo) => {
      const sn = Math.sin(la * Math.PI / 180);
      return [(lo + 180) / 360 * n * k, (0.5 - Math.log((1 + sn) / (1 - sn)) / (4 * Math.PI)) * n * k];
    };
    const [cx, cy] = px(lat, lon);
    const left = cx - w / 2, top = cy - h / 2;
    let tiles = "";
    const max = Math.pow(2, z);
    for (let tx = Math.floor(left / T); tx <= Math.floor((left + w) / T); tx++) {
      for (let ty = Math.floor(top / T); ty <= Math.floor((top + h) / T); ty++) {
        if (ty < 0 || ty >= max) continue;
        const x = ((tx % max) + max) % max;
        tiles += `<img alt="" referrerpolicy="origin" src="https://tile.openstreetmap.org/${z}/${x}/${ty}.png" style="left:${(tx * T - left).toFixed(1)}px;top:${(ty * T - top).toFixed(1)}px;width:${T.toFixed(2)}px;height:${T.toFixed(2)}px">`;
      }
    }
    E.mt.innerHTML = tiles;
    E.mt.classList.toggle("dark", dark);
    const mpp = 156543.03 * cos / Math.pow(2, z) / k;
    E.mcc.setAttribute("cx", w / 2); E.mcc.setAttribute("cy", h / 2); E.mcc.setAttribute("r", (radius * 1000) / mpp);
    const nearest = {};
    branches.forEach((b) => { if (!nearest[b.store] || b.distance_km < nearest[b.store].distance_km) nearest[b.store] = b; });
    const pins = branches.slice().sort((a, b) => (nearest[a.store] === a) - (nearest[b.store] === b)).map((b) => {
      const [bx, by] = px(b.lat, b.lon);
      const x = bx - left, y = by - top;
      if (x < -20 || y < -20 || x > w + 20 || y > h + 20) return "";
      const logo = C.store_logos ? (C.logos[b.store] || BA_LOGO[b.store]) : null;
      const col = BA_STORE[b.store] || "#546e7a";
      const tip = [b.store, b.address, this._fmt(b.distance_km, 1) + " km"].filter(Boolean).join(" · ");
      const inner = logo ? `<img alt="" src="${this._esc(logo)}" referrerpolicy="no-referrer">` : `<span>${this._esc(b.store.slice(0, 2))}</span>`;
      return `<div class="pin${nearest[b.store] === b ? " near" : ""}" style="left:${x}px;top:${y}px;background:${logo ? "#fff" : col}" title="${this._esc(tip)}">${inner}</div>`;
    }).join("");
    E.mp.innerHTML = pins + `<div class="home" style="left:${w / 2}px;top:${h / 2}px" title="Startpunkt"><ha-icon icon="mdi:home"></ha-icon></div>`;
    E.mp.querySelectorAll(".pin img").forEach((img) => img.addEventListener("error", () => {
      const pin = img.parentElement; pin.style.background = "#546e7a"; img.remove();
    }));
  }

  _setFilter(v) {
    const C = this._cfg;
    if (!this._o(C.filter)) return;
    this._hass.callService("text", "set_value", { entity_id: C.filter, value: v.trim() }).finally(() => { this._typing = null; });
  }

  _query() {
    if (this._typing !== null && this._typing !== undefined) return this._typing.trim().toLowerCase();
    const s = this._s(this._cfg.filter);
    return !s || s === "unknown" || s === "unavailable" ? "" : s.trim().toLowerCase();
  }

  _alc(d) {
    if (d.alcohol === null || d.alcohol === undefined) return null;
    if (!d.alcohol) return "alkoholfrei";
    return (d.alcohol_typical ? "ca. " : "") + this._fmt(d.alcohol, 1) + " % vol";
  }

  _chips(el, items) {
    // Rebuild only when the set of chips changes, so clicks are not lost while rendering.
    const sig = items.map((i) => i.id + "|" + i.label + "|" + (i.sub || "") + "|" + (i.pic || "")).join(";");
    if (el._sig !== sig) {
      el._sig = sig;
      el.innerHTML = items.map((it, i) =>
        `<button class="mode${it.pic ? " pic" : ""}" data-i="${i}">${it.pic ? `<img class="prod" src="${this._esc(it.pic)}" alt="" loading="lazy" referrerpolicy="no-referrer">` : ""}<ha-icon icon="${it.icon}"></ha-icon>${this._esc(it.label)}${it.sub ? `<i>${this._esc(it.sub)}</i>` : ""}</button>`).join("");
      Array.from(el.children).forEach((b) => b.addEventListener("click", () => el._items[parseInt(b.dataset.i, 10)].click()));
      el.querySelectorAll("img.prod").forEach((img) => img.addEventListener("error", () => { img.parentElement.classList.remove("pic"); img.remove(); }));
    }
    el._items = items;
    Array.from(el.children).forEach((b, i) => { b.classList.toggle("on", !!items[i].on); b.disabled = !!items[i].disabled; });
  }

  _render() {
    if (!this._hass || !this._built) return;
    const E = this._el, C = this._cfg;
    if (!this._ids) { E.hn.textContent = C.title; E.hs.textContent = "BierAlarm-Integration nicht gefunden"; return; }
    const so = this._o(C.deals);
    const a = so ? so.attributes : {};
    const deals = (a.deals || []).filter((d) => d.price_per_crate !== null && d.price_per_crate !== undefined);
    const errors = a.errors || {};
    const nearby = a.nearby || {};
    const away = a.out_of_range || [];
    const radius = a.radius_km;

    E.hn.textContent = C.title;
    const upd = so ? new Date(so.last_updated) : null;
    E.hs.textContent = C.subtitle + (radius ? " · Umkreis " + this._fmt(radius, 0) + " km" : "")
      + (upd ? " · " + upd.toLocaleTimeString("de-AT", { hour: "2-digit", minute: "2-digit" }) : "");

    // header pill
    const hits = deals.filter((d) => d.match).length;
    const nErr = Object.keys(errors).length;
    let txt, cls;
    if (!so || so.state === "unavailable") { txt = "Keine Daten"; cls = "idle"; }
    else if (hits) { txt = hits + (hits === 1 ? " Alarm" : " Alarme"); cls = "beer"; }
    else if (nErr) { txt = nErr + (nErr === 1 ? " Quelle gestört" : " Quellen gestört"); cls = "warn"; }
    else { txt = "Keine Alarme"; cls = "ok"; }
    E.pt.textContent = txt;
    E.pill.className = "pill " + cls;
    E.ic.className = "ic " + (hits ? "beer run" : nErr ? "warn" : "ok");
    E.ici.setAttribute("icon", hits ? "mdi:beer" : "mdi:beer-outline");

    // best prices
    const bc = this._o(C.best_crate), bl = this._o(C.best_liter);
    E.vK.textContent = this._eur(this._v(C.best_crate));
    E.sK.textContent = bc && bc.attributes.store ? bc.attributes.store + " · " + (bc.attributes.title || "") : "";
    const lv = this._v(C.best_liter);
    E.vL.textContent = lv === null ? "–" : this._fmt(lv, 2) + " €/l";
    E.sL.textContent = bl && bl.attributes.package ? bl.attributes.package : "";
    const shops = [...new Set(deals.map((d) => d.store))];
    E.vM.textContent = shops.length ? String(shops.length) : "–";
    E.sM.textContent = so ? so.state + " Aktionen" + (away.length ? " · " + away.join(", ") + " zu weit" : "") : "";

    this._renderRadius(a);

    // filters
    const q = this._query();
    if (this._sr.activeElement !== E.q) E.q.value = this._typing !== null && this._typing !== undefined ? this._typing : (this._s(C.filter) || "").replace(/^(unknown|unavailable)$/, "");
    E.qx.style.visibility = q ? "visible" : "hidden";
    const sel = this._o(C.store_filter);
    const store = sel ? sel.state : BA_ALL;
    const opts = sel && sel.attributes.options ? sel.attributes.options : [BA_ALL];
    this._chips(E.stores, opts.map((o) => {
      const near = nearby[o];
      return {
        id: o, label: o, icon: o === BA_ALL ? "mdi:store-search" : "mdi:store",
        sub: near ? this._fmt(near.distance_km, 1) + " km" : (away.includes(o) ? "zu weit" : ""),
        on: o === store, disabled: !sel,
        click: () => this._hass.callService("select", "select_option", { entity_id: C.store_filter, option: o })
      };
    }));

    // deal rows
    const shown = deals.filter((d) =>
      (store === BA_ALL || !store || store === "unknown" || d.store === store) &&
      (!q || [d.store, d.brand, d.title, d.package, d.condition].join(" ").toLowerCase().includes(q)));
    E.lA.textContent = shown.length === deals.length ? deals.length + " gesamt" : shown.length + " von " + deals.length;
    const lo = deals.length ? Math.min(...deals.map((d) => d.price_per_crate)) : 0;
    const hi = deals.length ? Math.max(...deals.map((d) => d.price_per_crate)) : 1;
    const rows = shown.slice(0, C.max_rows);
    // Rebuild the rows only when they change: re-creating them on every update makes the logos blink.
    const rsig = JSON.stringify([rows, q, store, lo, hi, C.store_logos]);
    if (E.rows._sig === rsig) {
      // nothing changed
    } else if (!rows.length) {
      E.rows._sig = rsig;
      E.rows.innerHTML = `<div class="empty">${deals.length ? "Gerade keine Aktion" + (q ? " für „" + this._esc(q) + "“" : "") + (store && store !== BA_ALL ? " bei " + this._esc(store) : "") + "." : "Noch keine Aktionen geladen."}</div>`;
    } else {
      E.rows._sig = rsig;
      E.rows.innerHTML = rows.map((d) => {
        const col = BA_STORE[d.store] || "#546e7a";
        const pct = this._pct(d.price_per_crate, lo - (hi - lo) * 0.15, hi);
        const fav = d.favorite !== undefined ? d.favorite : d.match;
        const bar = fav ? "#e65100" : pct < 45 ? "#2e7d32" : pct < 75 ? "#ef6c00" : "#8a8a8a";
        const logo = C.store_logos ? (C.logos[d.store] || BA_LOGO[d.store]) : null;
        const meta = [logo ? d.store : null, d.package && !String(d.title).includes(d.package) ? d.package : null,
          this._alc(d), d.condition, d.distance_km !== null && d.distance_km !== undefined ? this._fmt(d.distance_km, 1) + " km" : null]
          .filter(Boolean).join(" · ");
        const until = this._date(d.valid_to);
        return `<div class="row${fav ? " hit" : ""}">
          <div class="rtop">
            ${logo ? `<span class="logo" title="${this._esc(d.store)}"><img src="${this._esc(logo)}" alt="${this._esc(d.store)}" loading="lazy" referrerpolicy="no-referrer"></span>` : ""}
            <span class="st${logo ? " alt" : ""}" style="background:${col}">${this._esc(d.store)}</span>
            <div class="nm"><b>${this._esc(d.title)}</b><em>${this._esc(meta || " ")}</em></div>
            ${fav ? '<ha-icon class="bell" icon="mdi:bell-ring"></ha-icon>' : ""}
            <div class="pr"><b>${this._eur(d.price_per_crate)}</b><em>${this._eur(d.price)}${until ? " · bis " + until : ""}</em></div>
          </div>
          <div class="track"><i style="width:${pct}%;background:${bar}"></i></div>
        </div>`;
      }).join("");
      Array.from(E.rows.children).forEach((r) => r.addEventListener("click", () => this._more(C.deals)));
      E.rows.querySelectorAll(".logo img").forEach((img) => {
        const fail = () => img.parentElement.classList.add("fail");
        if (img.complete && !img.naturalWidth) fail(); else img.addEventListener("error", fail);
      });
    }
    E.more.textContent = shown.length > rows.length ? "… und " + (shown.length - rows.length) + " weitere in der Seitenleiste BierAlarm" : "";

    // price alarm threshold
    const ln = this._o(C.crate_limit);
    const lp = this._pend.crate_limit !== undefined;
    const lim = lp ? this._pend.crate_limit : (ln ? this._v(C.crate_limit) || 0 : 0);
    E.lv.textContent = lim ? this._eur(lim) : "aus";
    E.lv.classList.toggle("pend", lp);
    E.lm.disabled = !ln || lim <= 0;
    E.lp.disabled = !ln || lim >= 50;
    E.ltx.textContent = lim ? "🔔 wenn die 20er-Kiste höchstens " + this._eur(lim) + " kostet" : "aus – nur die gewählten Sorten";

    // beer switches, grouped by brand
    const beers = this._beerSwitches();
    const on = beers.filter((b) => b.state === "on").length;
    E.lB.textContent = on ? on + (on === 1 ? " Sorte" : " Sorten") : "nichts gewählt";
    // Collapsed: only the active types. Open: every type, grouped by brand.
    const groups = [];
    beers.filter((b) => this._open || b.state === "on").forEach((b) => {
      const brand = b.attributes.brand || (b.attributes.beer || "").split(" ")[0] || "?";
      let g = groups.find((x) => x.brand === brand);
      if (!g) { g = { brand, items: [] }; groups.push(g); }
      g.items.push(b);
    });
    E.tB.classList.toggle("open", !!this._open);
    E.bB.textContent = this._open ? "Nur aktive zeigen" : "Alle " + beers.length + " Sorten zeigen";
    E.bB.classList.toggle("hide", !beers.length);
    const gsig = groups.map((g) => g.brand + ":" + g.items.map((b) => b.entity_id).join(",")).join(";");
    if (E.brands._sig !== gsig) {
      E.brands._sig = gsig;
      E.brands.innerHTML = !groups.length ? '<div class="none">Noch keine Sorte aktiv. Aufklappen und Sorten wählen.</div>' : groups.map((g, i) => `<div class="grp"><div class="gn" data-g="${i}">${this._esc(g.brand)}</div><div class="modes" data-g="${i}"></div></div>`).join("");
    }
    groups.forEach((g, i) => {
      const box = E.brands.querySelector(`.modes[data-g="${i}"]`);
      const name = E.brands.querySelector(`.gn[data-g="${i}"]`);
      if (name) name.classList.toggle("on", g.items.some((b) => b.state === "on"));
      if (!box) return;
      this._chips(box, g.items.map((b) => ({
        id: b.entity_id, label: b.attributes.sort || b.attributes.beer || b.attributes.friendly_name,
        icon: b.state === "on" ? "mdi:bell-ring" : "mdi:bell-outline",
        pic: b.attributes.entity_picture || "",
        sub: b.attributes.deals ? b.attributes.deals + " in Aktion" : "",
        on: b.state === "on", disabled: b.state === "unavailable",
        click: () => this._hass.callService("switch", "toggle", { entity_id: b.entity_id })
      })));
      Array.from(box.children).forEach((btn, j) => {
        const ic = btn.querySelector("ha-icon");
        if (ic && g.items[j]) ic.setAttribute("icon", g.items[j].state === "on" ? "mdi:bell-ring" : "mdi:bell-outline");
      });
    });

    // diagnosis only when something is wrong
    const diag = Object.entries(errors).map(([k, v]) => [k, v, "bad"]);
    E.secD.classList.toggle("hide", !diag.length);
    E.tDi.innerHTML = diag.map((t) => `<div class="tile ${t[2]}"><em>${this._esc(t[0])}</em><b>Fehler</b><small title="${this._esc(t[1])}">${this._esc(t[1])}</small></div>`).join("");
  }
}

customElements.define("bieralarm-card", BierAlarmCard);
window.customCards = window.customCards || [];
window.customCards.push({
  type: "bieralarm-card",
  name: "BierAlarm Card",
  description: "Bieraktionen pro 20er-Kiste mit Filter und Marken-Alarm"
});
