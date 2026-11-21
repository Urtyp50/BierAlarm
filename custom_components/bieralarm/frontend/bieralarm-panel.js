// BierAlarm sidebar panel. Plain web component, no build step.

const esc = (v) =>
  String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const euro = (v) => (v == null ? "–" : `€ ${Number(v).toFixed(2).replace(".", ",")}`);
const day = (iso) => {
  if (!iso) return "";
  const d = new Date(`${iso}T12:00:00`);
  return isNaN(d) ? esc(iso) : d.toLocaleDateString("de-AT", { weekday: "short", day: "2-digit", month: "2-digit" });
};
const safeUrl = (u) => (typeof u === "string" && /^https:\/\//.test(u) ? u : null);

const SORTS = {
  liter: { label: "Preis pro 20er-Kiste", fn: (a, b) => (a.price_per_liter ?? 1e9) - (b.price_per_liter ?? 1e9) },
  price: { label: "Preis", fn: (a, b) => (a.price ?? 1e9) - (b.price ?? 1e9) },
  discount: { label: "Rabatt", fn: (a, b) => (b.discount_percent ?? -1) - (a.discount_percent ?? -1) },
  until: { label: "Endet bald", fn: (a, b) => String(a.valid_to ?? "9").localeCompare(String(b.valid_to ?? "9")) },
};

class BierAlarmPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._data = null;
    this._error = null;
    this._loading = false;
    this._state = { store: "all", q: "", onlyMatches: false, sort: "liter" };
    try {
      Object.assign(this._state, JSON.parse(localStorage.getItem("bieralarm-panel") || "{}"));
    } catch (e) {
      /* ignore */
    }
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first) this._load();
    const menu = this.shadowRoot.querySelector("ha-menu-button");
    if (menu) menu.hass = hass;
  }

  set narrow(narrow) {
    this._narrow = narrow;
    const menu = this.shadowRoot.querySelector("ha-menu-button");
    if (menu) menu.narrow = narrow;
  }

  set panel(panel) {
    this._panel = panel;
  }

  connectedCallback() {
    this._render();
    this._timer = setInterval(() => this._load(true), 5 * 60 * 1000);
  }

  disconnectedCallback() {
    clearInterval(this._timer);
  }

  async _load(silent = false) {
    if (!this._hass) return;
    if (!silent) {
      this._loading = true;
      this._render();
    }
    try {
      this._data = await this._hass.callWS({ type: "bieralarm/deals" });
      this._error = null;
    } catch (err) {
      this._error = err?.message || String(err);
    }
    this._loading = false;
    this._render();
  }

  async _refresh() {
    this._loading = true;
    this._render();
    try {
      await this._hass.callService("bieralarm", "refresh", {});
    } catch (err) {
      this._error = err?.message || String(err);
    }
    await this._load();
  }

  _set(patch) {
    Object.assign(this._state, patch);
    try {
      localStorage.setItem("bieralarm-panel", JSON.stringify(this._state));
    } catch (e) {
      /* ignore */
    }
    this._render();
  }

  _filtered() {
    const { store, q, onlyMatches, sort } = this._state;
    const needle = q.trim().toLowerCase();
    return (this._data?.deals || [])
      .filter((d) => store === "all" || d.store === store)
      .filter((d) => !onlyMatches || d.match)
      .filter((d) => !needle || `${d.title} ${d.package ?? ""} ${d.brand ?? ""}`.toLowerCase().includes(needle))
      .sort(SORTS[sort]?.fn || SORTS.liter.fn);
  }

  _card(d) {
    const names = this._data.store_names || {};
    const url = safeUrl(d.url);
    const img = safeUrl(d.image);
    const valid =
      d.valid_from || d.valid_to ? `${d.valid_from ? day(d.valid_from) : ""} – ${d.valid_to ? day(d.valid_to) : ""}` : "";
    return `
      <article class="card ${d.match ? "match" : ""}">
        <div class="img">${img ? `<img loading="lazy" src="${esc(img)}" alt="">` : `<span class="noimg">🍺</span>`}</div>
        <div class="body">
          <div class="top">
            <span class="store s-${esc(d.store)}">${esc(names[d.store] || d.store)}</span>
            ${(d.favorite !== undefined ? d.favorite : d.match) ? `<span class="alarm" title="Gewählte Sorte">🔔 Alarm</span>` : ""}
            ${d.source === "ai" ? `<span class="ai" title="Von der KI aus dem PDF-Flugblatt gelesen">KI</span>` : ""}
          </div>
          <h3>${esc(d.title)}</h3>
          <div class="pkg">${esc(d.package || "")}</div>
          <div class="crate" title="Umgerechnet auf 20 × 0,5 l (10 Liter)">
            <span class="label">20er-Kiste</span>
            <span class="now">${d.price_per_crate != null ? euro(d.price_per_crate) : "–"}</span>
            ${d.discount_percent ? `<span class="pct">-${d.discount_percent}%</span>` : ""}
          </div>
          <div class="pl">
            Aktion: <b>${euro(d.price)}</b>${d.regular_price ? ` <span class="was">${euro(d.regular_price)}</span>` : ""}
            ${d.price_per_liter != null ? ` · ${euro(d.price_per_liter)}/l` : ""}
          </div>
          ${d.condition ? `<div class="cond">${esc(d.condition)}</div>` : ""}
          <div class="foot">
            <span>${valid}</span>
            ${url ? `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">Ansehen ↗</a>` : ""}
          </div>
        </div>
      </article>`;
  }

  _render() {
    const root = this.shadowRoot;
    const focused = root.activeElement?.id;
    const caret = root.activeElement?.selectionStart;
    const data = this._data;
    const deals = data ? this._filtered() : [];
    const storesPresent = data ? [...new Set(data.deals.map((d) => d.store))] : [];
    const names = data?.store_names || {};
    const errors = Object.entries(data?.errors || {});
    const best = deals.find((d) => d.price_per_liter != null);
    const updated = data?.updated
      ? new Date(data.updated).toLocaleString("de-AT", { dateStyle: "short", timeStyle: "short" })
      : "–";

    root.innerHTML = `
      <style>${STYLE}</style>
      <div class="toolbar">
        <ha-menu-button></ha-menu-button>
        <div class="title">🍺 BierAlarm</div>
        <button class="refresh" ${this._loading ? "disabled" : ""} title="Jetzt aktualisieren">
          ${this._loading ? "Lädt…" : "↻ Aktualisieren"}
        </button>
      </div>
      <main>
        ${this._error ? `<div class="banner err">Fehler: ${esc(this._error)}</div>` : ""}
        ${
          data && !data.configured
            ? `<div class="banner">BierAlarm ist noch nicht eingerichtet. Einstellungen → Geräte & Dienste → Integration hinzufügen → BierAlarm.</div>`
            : ""
        }
        ${errors
          .map(([k, v]) => `<div class="banner warn"><b>${esc(names[k] || k)}:</b> ${esc(v)}</div>`)
          .join("")}
        ${
          data?.configured
            ? `
          <section class="stats">
            <div><span class="n">${data.deals.length}</span><span>Bieraktionen</span></div>
            <div><span class="n">${data.deals.filter((d) => d.match).length}</span><span>Alarm-Treffer</span></div>
            <div><span class="n">${best ? euro(best.price_per_crate) : "–"}</span><span>billigste 20er-Kiste</span></div>
            <div><span class="n small">${esc(updated)}</span><span>zuletzt geprüft</span></div>
          </section>
          <section class="filters">
            <div class="chips">
              <button data-store="all" class="${this._state.store === "all" ? "on" : ""}">Alle</button>
              ${storesPresent
                .map(
                  (s) =>
                    `<button data-store="${esc(s)}" class="${this._state.store === s ? "on" : ""}">${esc(names[s] || s)}</button>`,
                )
                .join("")}
            </div>
            <input id="q" type="search" placeholder="Marke oder Sorte suchen…" value="${esc(this._state.q)}">
            <select id="sort">
              ${Object.entries(SORTS)
                .map(([k, v]) => `<option value="${k}" ${this._state.sort === k ? "selected" : ""}>${v.label}</option>`)
                .join("")}
            </select>
            <label class="toggle"><input id="only" type="checkbox" ${this._state.onlyMatches ? "checked" : ""}> nur Alarm-Treffer</label>
          </section>
          <div class="hint">
            Alarm bei: ${esc(data.favorite_brands || "keinen Lieblingsmarken")}${
              data.max_price_per_liter
                ? ` oder unter ${euro(data.max_price_per_liter * 10)} pro 20er-Kiste (${euro(data.max_price_per_liter)}/l)`
                : ""
            } · Kistenpreis = umgerechnet auf 20 × 0,5 l, ohne Pfand · ändern unter Einstellungen → Geräte & Dienste → BierAlarm → Konfigurieren
          </div>
          <section class="grid">
            ${deals.length ? deals.map((d) => this._card(d)).join("") : `<div class="empty">Keine passenden Bieraktionen gefunden.</div>`}
          </section>
          <footer>Daten von penny.at, lidl.at, mpreis.at und billa.at. Angaben ohne Gewähr. Preise teils exkl. Pfand.</footer>`
            : !data && !this._error
              ? `<div class="empty">Lädt…</div>`
              : ""
        }
      </main>`;

    const menu = root.querySelector("ha-menu-button");
    if (menu) {
      menu.hass = this._hass;
      menu.narrow = this._narrow;
    }
    root.querySelector(".refresh")?.addEventListener("click", () => this._refresh());
    root.querySelectorAll("[data-store]").forEach((b) =>
      b.addEventListener("click", () => this._set({ store: b.dataset.store })),
    );
    root.querySelector("#q")?.addEventListener("input", (e) => this._set({ q: e.target.value }));
    root.querySelector("#sort")?.addEventListener("change", (e) => this._set({ sort: e.target.value }));
    root.querySelector("#only")?.addEventListener("change", (e) => this._set({ onlyMatches: e.target.checked }));

    if (focused) {
      const el = root.getElementById(focused);
      if (el) {
        el.focus();
        if (caret != null && el.setSelectionRange) el.setSelectionRange(caret, caret);
      }
    }
  }
}

const STYLE = `
  :host { display:block; min-height:100vh; background:var(--primary-background-color); color:var(--primary-text-color);
    font-family:var(--paper-font-body1_-_font-family, Roboto, system-ui, sans-serif); }
  .toolbar { display:flex; align-items:center; gap:8px; height:var(--header-height,56px); padding:0 12px;
    background:var(--app-header-background-color, var(--primary-color)); color:var(--app-header-text-color, #fff);
    position:sticky; top:0; z-index:2; }
  .title { font-size:20px; flex:1; }
  .refresh { background:transparent; color:inherit; border:1px solid currentColor; border-radius:18px; padding:6px 14px;
    font:inherit; cursor:pointer; }
  .refresh:disabled { opacity:.6; cursor:default; }
  main { max-width:1200px; margin:0 auto; padding:16px; }
  .banner { padding:10px 14px; border-radius:8px; margin-bottom:10px; background:var(--card-background-color);
    border-left:4px solid var(--primary-color); }
  .banner.warn { border-color:var(--warning-color,#ffa600); }
  .banner.err { border-color:var(--error-color,#db4437); }
  .stats { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:12px; margin-bottom:16px; }
  .stats div { background:var(--card-background-color); border-radius:12px; padding:14px; display:flex; flex-direction:column; gap:4px;
    box-shadow:var(--ha-card-box-shadow,none); border:1px solid var(--divider-color); }
  .stats .n { font-size:26px; font-weight:600; }
  .stats .n.small { font-size:16px; }
  .stats span:last-child { color:var(--secondary-text-color); font-size:13px; }
  .filters { display:flex; flex-wrap:wrap; gap:10px; align-items:center; margin-bottom:8px; }
  .chips { display:flex; flex-wrap:wrap; gap:6px; }
  .chips button { border:1px solid var(--divider-color); background:var(--card-background-color); color:var(--primary-text-color);
    border-radius:16px; padding:6px 12px; cursor:pointer; font:inherit; font-size:14px; }
  .chips button.on { background:var(--primary-color); color:var(--text-primary-color,#fff); border-color:var(--primary-color); }
  input[type=search], select { font:inherit; font-size:14px; padding:7px 10px; border-radius:8px; border:1px solid var(--divider-color);
    background:var(--card-background-color); color:var(--primary-text-color); }
  input[type=search] { flex:1; min-width:160px; }
  .toggle { display:flex; gap:6px; align-items:center; font-size:14px; }
  .hint { color:var(--secondary-text-color); font-size:12px; margin:4px 0 14px; }
  .grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(250px,1fr)); gap:14px; }
  .card { display:flex; flex-direction:column; background:var(--card-background-color); border-radius:12px; overflow:hidden;
    border:1px solid var(--divider-color); box-shadow:var(--ha-card-box-shadow,none); }
  .card.match { border:2px solid var(--warning-color,#ffa600); }
  .img { height:130px; display:flex; align-items:center; justify-content:center; background:#fff; }
  .img img { max-height:120px; max-width:90%; object-fit:contain; }
  .noimg { font-size:56px; }
  .body { padding:12px 14px; display:flex; flex-direction:column; gap:4px; flex:1; }
  .top { display:flex; gap:6px; flex-wrap:wrap; }
  .store, .alarm, .ai { font-size:11px; font-weight:600; padding:2px 8px; border-radius:10px; text-transform:uppercase; letter-spacing:.3px; }
  .store { background:var(--secondary-background-color); }
  .s-penny { background:#cd1414; color:#fff; } .s-lidl { background:#0050aa; color:#fff; }
  .s-billa, .s-billa_plus { background:#fed500; color:#222; }
  .s-mpreis { background:#e2001a; color:#fff; }
  .alarm { background:var(--warning-color,#ffa600); color:#222; }
  .ai { background:var(--secondary-background-color); color:var(--secondary-text-color); }
  h3 { margin:4px 0 0; font-size:16px; line-height:1.25; }
  .pkg { color:var(--secondary-text-color); font-size:13px; }
  .crate { display:flex; align-items:baseline; gap:8px; margin-top:4px; flex-wrap:wrap; }
  .crate .label { font-size:12px; color:var(--secondary-text-color); text-transform:uppercase; letter-spacing:.3px; }
  .now { font-size:22px; font-weight:700; color:var(--primary-color); }
  .was { text-decoration:line-through; color:var(--secondary-text-color); font-size:12px; }
  .pct { background:var(--error-color,#db4437); color:#fff; font-size:12px; font-weight:600; padding:1px 6px; border-radius:6px; }
  .pl { font-size:13px; }
  .cond { font-size:12px; color:var(--secondary-text-color); }
  .foot { margin-top:auto; padding-top:8px; display:flex; justify-content:space-between; font-size:12px; color:var(--secondary-text-color); }
  .foot a { color:var(--primary-color); text-decoration:none; }
  .empty { padding:40px; text-align:center; color:var(--secondary-text-color); grid-column:1/-1; }
  footer { margin:24px 0 8px; font-size:12px; color:var(--secondary-text-color); text-align:center; }
  @media (max-width:600px) { main { padding:12px 16px; } .grid { grid-template-columns:1fr; } }
`;

customElements.define("bieralarm-panel", BierAlarmPanel);
