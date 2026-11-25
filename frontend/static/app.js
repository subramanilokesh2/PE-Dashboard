/* ZINNOV | PE Intelligence Command Center: single-page front end (vanilla JS, no CDN, no build step). */
(function () {
  "use strict";

  const MODULES = [
    { id: "overview", num: "01", label: "Executive Overview" },
    { id: "accounts", num: "02", label: "PE Account Intelligence" },
    { id: "portfolio", num: "03", label: "Portfolio Intelligence" },
    { id: "signals", num: "04", label: "Market Signals" },
    { id: "industry", num: "05", label: "Industry Intelligence" },
    { id: "stakeholders", num: "06", label: "Stakeholder Intelligence" },
    { id: "opportunities", num: "07", label: "Opportunity Intelligence" },
    { id: "outreach", num: "08", label: "Outreach Intelligence" },
  ];
  const MONTH_LABELS = { "2026-04": "Apr 2026", "2026-05": "May 2026", "2026-06": "Jun 2026", "2026-07": "Jul 2026",
    "2026-08": "Aug 2026", "2026-09": "Sep 2026", "2026-10": "Oct 2026", "2026-11": "Nov 2026" };
  const PUB_MONTHS = ["2026-04", "2026-05", "2026-06", "2026-07", "2026-08", "2026-09", "2026-10"];
  const CAPABILITY_BY_CATEGORY = {
    "Mergers and Acquisitions": "Commercial and technology due diligence, integration planning",
    "Center Setup and Expansion": "Global capability centre design, location and operating model",
    "Layoff": "Cost optimisation and operating model review",
    "Fundraise and Investments": "PE value creation and growth advisory",
    "Mass Hiring": "Engineering capacity and talent model",
    "Executive Movement": "Operating model review with the incoming leader",
    "New Product Development and Product Launch": "Digital product engineering and AI enablement",
    "Deals and Partnerships": "Technology partnership and transformation support",
    "Financial and Market Activity": "Market monitoring and advisory positioning",
  };
  const CHALLENGE_BY_CATEGORY = {
    "Mergers and Acquisitions": "Integrating acquired technology and delivery teams while protecting the deal thesis.",
    "Center Setup and Expansion": "Building or scaling offshore or captive capacity quickly and at the right cost.",
    "Layoff": "Reducing cost without losing delivery capability or product momentum.",
    "Fundraise and Investments": "Converting new capital into measurable operating and technology improvement.",
    "Mass Hiring": "Sourcing, onboarding and managing a large engineering intake.",
    "Executive Movement": "Setting priorities and reviewing the operating model under new leadership.",
    "New Product Development and Product Launch": "Shipping new products with the engineering and AI capacity available.",
    "Deals and Partnerships": "Delivering on a new partnership without disrupting the existing technology roadmap.",
    "Financial and Market Activity": "Responding to market movements with a clear commercial and operating position.",
  };
  const DEFAULTS = { month: "2026-11", firm: "", industry: "", region: "" };
  const S = Object.assign({}, DEFAULTS, safeLoad());
  let META = null;
  let renderSeq = 0;

  function safeLoad() {
    try { return JSON.parse(localStorage.getItem("zpe.filters") || "{}"); } catch (e) { return {}; }
  }
  function persist() {
    try { localStorage.setItem("zpe.filters", JSON.stringify({ month: S.month, firm: S.firm, industry: S.industry, region: S.region })); } catch (e) { /* storage may be unavailable */ }
  }

  /* ---------- helpers ---------- */
  const $ = (sel, root) => (root || document).querySelector(sel);
  const esc = (v) => String(v === null || v === undefined ? "" : v).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const num = (v) => (v === null || v === undefined || v === "" || Number.isNaN(Number(v))) ? "—" : Number(v).toLocaleString("en-US", { maximumFractionDigits: 0 });
  const dec = (v, d) => (v === null || v === undefined || Number.isNaN(Number(v))) ? "Not reported" : Number(v).toLocaleString("en-US", { maximumFractionDigits: d === undefined ? 1 : d });
  const dateStr = (v) => (v ? String(v).slice(0, 10) : "—");
  const monthLabel = (m) => MONTH_LABELS[m] || m || "—";
  const pct = (a, b) => (b ? Math.round((100 * a) / b) + "%" : "—");

  function gp(extra) {
    const p = new URLSearchParams();
    if (S.month) p.set("month", S.month);
    if (S.firm) p.set("firm", S.firm);
    if (S.industry) p.set("industry", S.industry);
    if (S.region) p.set("region", S.region);
    Object.keys(extra || {}).forEach((k) => { if (extra[k] !== undefined && extra[k] !== null && extra[k] !== "") p.set(k, extra[k]); });
    return p.toString();
  }
  async function api(path, extra) {
    const qs = gp(extra);
    const r = await fetch(path + (qs ? "?" + qs : ""), { headers: { Accept: "application/json" } });
    if (!r.ok) throw new Error("Request failed (" + r.status + ") for " + path);
    return r.json();
  }
  function pill(p) { return p ? '<span class="pill p-' + esc(p) + '">' + esc(p) + "</span>" : '<span class="muted">—</span>'; }
  function statusPill(s) {
    if (!s) return '<span class="muted">—</span>';
    const cls = s === "Confirmed" ? "s-ok" : /Left|Changed/.test(s) ? "s-warn" : "s-none";
    return '<span class="pill ' + cls + '">' + esc(s) + "</span>";
  }

  function kpis(items) {
    return '<div class="kpis">' + items.map((k, i) =>
      '<div class="kpi" style="animation-delay:' + i * 40 + 'ms" ' + (k.go ? 'role="button" tabindex="0" data-go="' + esc(k.go) + '" title="Open module"' : "") + ">" +
      '<div class="v">' + esc(k.v) + '</div><div class="l">' + esc(k.l) + '</div>' + (k.d ? '<div class="d">' + esc(k.d) + "</div>" : "") + "</div>").join("") + "</div>";
  }

  function bars(items, o) {
    o = o || {};
    if (!items || !items.length) return '<div class="empty">No records for the current filters.</div>';
    const max = Math.max.apply(null, items.map((i) => Number(i[o.value]) || 0)) || 1;
    return '<div class="bars">' + items.map((it) => {
      const v = Number(it[o.value]) || 0;
      const attr = o.click ? ' clickable" data-click="' + esc(o.click) + '" data-val="' + esc(it[o.key || "name"]) : "";
      return '<div class="row' + attr + '"><div class="lbl" title="' + esc(it[o.label]) + '">' + esc(it[o.label]) +
        '</div><div class="track"><div class="fill" data-w="' + ((v / max) * 100).toFixed(1) + '"></div></div><div class="num">' +
        (o.fmt ? o.fmt(v) : num(v)) + "</div></div>";
    }).join("") + "</div>";
  }
  function bindClicks(root) {
    root.querySelectorAll(".row[data-click]").forEach((row) => {
      row.addEventListener("click", () => {
        const go = row.dataset.click, val = row.dataset.val;
        if (go === "industry") setFilter("industry", val);
        else if (go === "firm") setFilter("firm", val);
        else if (go === "account") openAccount(val);
      });
    });
  }
  function animateBars(root) {
    requestAnimationFrame(() => root.querySelectorAll(".fill[data-w]").forEach((el) => { el.style.width = el.dataset.w + "%"; }));
  }
  function lineChart(points, key, labelKey) {
    if (!points || !points.length) return '<div class="empty">No trend data.</div>';
    const W = 520, H = 190, padL = 40, padB = 26, padT = 12, padR = 14;
    const max = Math.max.apply(null, points.map((p) => p[key])) || 1;
    const xs = (i) => padL + (i * (W - padL - padR)) / Math.max(1, points.length - 1);
    const ys = (v) => padT + (H - padT - padB) * (1 - v / max);
    const path = points.map((p, i) => (i ? "L" : "M") + xs(i).toFixed(1) + " " + ys(p[key]).toFixed(1)).join(" ");
    const grid = [0, 0.5, 1].map((t) => '<line x1="' + padL + '" x2="' + (W - padR) + '" y1="' + ys(max * t) + '" y2="' + ys(max * t) + '" stroke="#EEF3F8"/><text x="4" y="' + (ys(max * t) + 3) + '">' + num(Math.round(max * t)) + "</text>").join("");
    const xlabels = points.map((p, i) => '<text x="' + xs(i) + '" y="' + (H - 8) + '" text-anchor="middle">' + esc(p[labelKey || "label"]) + "</text>").join("");
    const dots = points.map((p, i) => '<circle class="dot" cx="' + xs(i) + '" cy="' + ys(p[key]) + '" r="3.2"><title>' + esc(p[labelKey || "label"]) + ": " + num(p[key]) + "</title></circle>").join("");
    return '<div class="chart"><svg viewBox="0 0 ' + W + " " + H + '" role="img" aria-label="Trend chart">' + grid +
      '<path class="line" d="' + path + '"/>' + dots + xlabels + "</svg></div>";
  }

  function scatterChart(points) {
    if (!points || !points.length) return '<div class="empty">No companies with both revenue and IT spend for this snapshot.</div>';
    const W = 520, H = 260, pl = 46, pb = 30, pt = 10, pr = 10;
    const lx = (v) => Math.log10(v + 1), xs = points.map((p) => lx(p.revenue)), ys = points.map((p) => lx(p.it_spend));
    const x0 = Math.min.apply(null, xs), x1 = Math.max.apply(null, xs), y0 = Math.min.apply(null, ys), y1 = Math.max.apply(null, ys);
    const sx = (v) => pl + ((v - x0) / (x1 - x0 || 1)) * (W - pl - pr);
    const sy = (v) => pt + (H - pt - pb) * (1 - (v - y0) / (y1 - y0 || 1));
    const dots = points.map((p, i) => '<circle cx="' + sx(xs[i]).toFixed(1) + '" cy="' + sy(ys[i]).toFixed(1) + '" r="3" fill="#145DA0" fill-opacity=".55"><title>' +
      esc(p.name) + " | Revenue $" + dec(p.revenue) + "m | IT spend $" + dec(p.it_spend) + "m</title></circle>").join("");
    const axes = '<line x1="' + pl + '" y1="' + (H - pb) + '" x2="' + (W - pr) + '" y2="' + (H - pb) + '" stroke="#B4CFEA"/><line x1="' + pl + '" y1="' + pt + '" x2="' + pl + '" y2="' + (H - pb) + '" stroke="#B4CFEA"/>' +
      '<text x="' + (W / 2 - 60) + '" y="' + (H - 6) + '">Revenue, USD m (log scale)</text><text x="4" y="' + (pt + 10) + '">IT spend (log)</text>';
    return '<div class="chart"><svg viewBox="0 0 ' + W + " " + H + '" role="img" aria-label="Revenue against IT spend">' + axes + dots + "</svg></div>" +
      '<div class="note">Showing ' + num(points.length) + " companies with both values reported. Missing values are excluded, not treated as zero.</div>";
  }

  function openDrawer(title, sub, body) {
    $("#drawerBody").innerHTML = '<h2>' + esc(title) + '</h2><div class="sub">' + esc(sub || "") + "</div>" + body;
    $("#drawer").classList.add("open"); $("#drawer").setAttribute("aria-hidden", "false");
    $("#backdrop").hidden = false;
    $("#drawerBody").scrollTop = 0; $("#drawer").scrollTop = 0;
  }
  function closeDrawer() {
    $("#drawer").classList.remove("open"); $("#drawer").setAttribute("aria-hidden", "true"); $("#backdrop").hidden = true;
  }
  function kv(rows) {
    return '<div class="kv">' + rows.map((r) => "<div>" + esc(r[0]) + "</div><div>" + (r[2] ? r[1] : esc(r[1] === null || r[1] === undefined || r[1] === "" ? "Not recorded" : r[1])) + "</div>").join("") + "</div>";
  }

  /* ---------- reusable data table ---------- */
  function DataTable(root, cfg) {
    const st = { page: 1, size: cfg.size || 25, sort: cfg.defaultSort || "", dir: cfg.defaultDir || "", q: "", filters: {}, seq: 0 };
    const rowKey = cfg.rowKey || "id";
    (cfg.filters || []).forEach((f) => { st.filters[f.name] = ""; });
    const tools = (cfg.filters || []).map((f) => '<label class="muted" style="font-size:11px">' + esc(f.label) + ' <select class="select" data-filter="' + esc(f.name) + '"><option value="">All</option>' +
      f.options.map((o) => '<option value="' + esc(o.value) + '">' + esc(o.label) + "</option>").join("") + "</select></label>").join(" ");
    root.innerHTML = '<div class="tbl-wrap"><div class="tbl-tools"><div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">' +
      '<input class="input" type="search" placeholder="' + esc(cfg.placeholder || "Search") + '" aria-label="Search table" style="min-width:240px"> ' + tools +
      '</div><div><a class="btn ghost small" data-export href="#" download>Export CSV</a></div></div>' +
      '<div class="tbl-scroll"><table><thead><tr>' + cfg.columns.map((c) => '<th class="' + (c.num ? "num " : "") + '" data-key="' + esc(c.sort || "") + '"' +
      (c.sort ? "" : ' style="cursor:default"') + ">" + esc(c.label) + "</th>").join("") + '</tr></thead><tbody></tbody></table></div>' +
      '<div class="pager"><span data-info></span><button class="btn ghost small" data-prev type="button">Prev</button><span data-pg></span><button class="btn ghost small" data-next type="button">Next</button></div></div>';
    const tbody = root.querySelector("tbody");
    const input = root.querySelector("input[type=search]");
    let debounce;
    input.addEventListener("input", () => { clearTimeout(debounce); debounce = setTimeout(() => { st.q = input.value.trim(); st.page = 1; load(); }, 280); });
    root.querySelectorAll("select[data-filter]").forEach((sel) => sel.addEventListener("change", () => { st.filters[sel.dataset.filter] = sel.value; st.page = 1; load(); }));
    root.querySelectorAll("th[data-key]").forEach((th) => th.addEventListener("click", () => {
      const k = th.dataset.key; if (!k) return;
      if (st.sort === k) st.dir = st.dir === "desc" ? "asc" : "desc"; else { st.sort = k; st.dir = "asc"; }
      st.page = 1; load();
    }));
    root.querySelector("[data-prev]").addEventListener("click", () => { if (st.page > 1) { st.page--; load(); } });
    root.querySelector("[data-next]").addEventListener("click", () => { st.page++; load(); });
    function params(extra) {
      const p = Object.assign({ page: st.page, size: st.size, q: st.q, sort: st.sort, dir: st.dir }, st.filters, extra || {});
      return p;
    }
    function exportHref() {
      const p = new URLSearchParams(gp(Object.assign({ q: st.q, sort: st.sort, dir: st.dir, format: "csv" }, st.filters)));
      return cfg.endpoint + "?" + p.toString();
    }
    async function load() {
      const seq = ++st.seq;
      tbody.innerHTML = '<tr><td colspan="' + cfg.columns.length + '"><div class="skeleton"></div><div class="skeleton" style="width:70%"></div></td></tr>';
      try {
        const data = await api(cfg.endpoint, params());
        if (seq !== st.seq) return;
        const rows = data.rows || [];
        tbody.innerHTML = rows.length ? rows.map((r) => '<tr class="' + (cfg.onRow ? "clickable" : "") + '" data-id="' + esc(r[rowKey] !== undefined ? r[rowKey] : "") + '">' +
          cfg.columns.map((c) => '<td class="' + (c.num ? "num " : "") + (c.wrap ? "" : "") + '">' + (c.fmt ? c.fmt(r[c.key], r) : esc(r[c.key] === null || r[c.key] === undefined ? "—" : r[c.key])) + "</td>").join("") + "</tr>").join("")
          : '<tr><td class="empty" colspan="' + cfg.columns.length + '">No records match the current filters.</td></tr>';
        if (cfg.onRow) tbody.querySelectorAll("tr[data-id]").forEach((tr) => tr.addEventListener("click", () => cfg.onRow(tr.dataset.id, rows.find((x) => String(x[rowKey]) === tr.dataset.id) || {})));
        root.querySelector("[data-info]").textContent = num(data.total) + " records";
        root.querySelector("[data-pg]").textContent = "Page " + data.page + " of " + data.pages;
        root.querySelector("[data-prev]").disabled = data.page <= 1;
        root.querySelector("[data-next]").disabled = data.page >= data.pages;
        root.querySelector("[data-export]").setAttribute("href", exportHref());
        root.querySelectorAll("th[data-key]").forEach((th) => {
          const active = th.dataset.key === st.sort;
          th.classList.toggle("sorted", active);
          th.classList.toggle("desc", active && st.dir === "desc");
        });
      } catch (err) {
        if (seq === st.seq) tbody.innerHTML = '<tr><td colspan="' + cfg.columns.length + '"><div class="error">' + esc(err.message) + "</div></td></tr>";
      }
    }
    load();
    return { reload: load };
  }

  /* ---------- filters ---------- */
  function setFilter(name, value) {
    S[name] = value || "";
    persist(); syncFilterControls(); renderCurrent();
    if (name === "industry" && location.hash !== "#/industry") location.hash = "#/industry";
    if (name === "firm" && location.hash !== "#/accounts") location.hash = "#/accounts";
  }
  function fillSelect(sel, items, value, allLabel) {
    sel.innerHTML = '<option value="">' + esc(allLabel) + "</option>" + items.map((i) => '<option value="' + esc(i.value) + '">' + esc(i.label) + "</option>").join("");
    sel.value = value || "";
  }
  function syncFilterControls() {
    fillSelect($("#fMonth"), META.months.map((m) => ({ value: m.value, label: m.label })), S.month, "All months");
    $("#fMonth").value = S.month || "2026-11";
    $("#fFirm").value = S.firm || ""; $("#fIndustry").value = S.industry || ""; $("#fRegion").value = S.region || "";
    const n = [S.firm, S.industry, S.region].filter(Boolean).length;
    $("#filterCount").textContent = n ? n + " active filter" + (n > 1 ? "s" : "") : "No filters applied";
  }
  function bindFilters() {
    $("#fMonth").addEventListener("change", (e) => { S.month = e.target.value || "2026-11"; persist(); syncFilterControls(); renderCurrent(); });
    $("#fFirm").addEventListener("change", (e) => { S.firm = e.target.value; persist(); syncFilterControls(); renderCurrent(); });
    $("#fIndustry").addEventListener("change", (e) => { S.industry = e.target.value; persist(); syncFilterControls(); renderCurrent(); });
    $("#fRegion").addEventListener("change", (e) => { S.region = e.target.value; persist(); syncFilterControls(); renderCurrent(); });
    $("#resetBtn").addEventListener("click", () => { Object.assign(S, DEFAULTS); persist(); syncFilterControls(); renderCurrent(); });
  }

  /* ---------- navigation ---------- */
  function buildNav() {
    const nav = $("#nav");
    nav.innerHTML = MODULES.map((m) => '<button class="nav-item" type="button" data-route="' + m.id + '" aria-label="' + esc(m.num + " " + m.label) + '"><span class="nav-num">' + m.num + '</span><span class="lbl-long nav-label">' + esc(m.label) + "</span></button>").join("");
    nav.querySelectorAll("[data-route]").forEach((b) => b.addEventListener("click", () => { location.hash = "#/" + b.dataset.route; }));
    $("#collapseBtn").addEventListener("click", () => { $("#sidebar").classList.toggle("collapsed"); });
  }
  function currentRoute() {
    const r = (location.hash || "#/overview").replace(/^#\//, "");
    return MODULES.some((m) => m.id === r) ? r : "overview";
  }
  function renderCurrent() {
    const route = currentRoute();
    document.querySelectorAll(".nav-item").forEach((b) => b.classList.toggle("active", b.dataset.route === route));
    const view = $("#view");
    const seq = ++renderSeq;
    view.classList.remove("view"); void view.offsetWidth; view.classList.add("view");
    view.innerHTML = '<div class="skeleton" style="height:22px;width:40%;margin:14px 0"></div><div class="skeleton"></div><div class="skeleton" style="width:80%"></div>';
    RENDER[route]().then((html) => { if (seq !== renderSeq) return; view.innerHTML = html.html; if (html.after) html.after(view); })
      .catch((err) => { if (seq === renderSeq) view.innerHTML = '<div class="error">' + esc(err.message) + "</div>"; });
  }

  /* ---------- module 01 executive overview ---------- */
  async function renderOverview() {
    const d = await api("/api/overview");
    const k = d.kpis;
    const cards = [
      { v: num(k.targeted_firms), l: "Targeted PE firms", d: d.kpi_definitions.targeted_firms, go: "accounts" },
      { v: num(k.matched_accounts), l: "Matched PE accounts", d: d.kpi_definitions.matched_accounts, go: "accounts" },
      { v: num(k.portfolio_companies), l: "Unique portfolio companies", d: d.kpi_definitions.portfolio_companies, go: "portfolio" },
      { v: num(k.detailed_profiles), l: "Detailed portfolio profiles", d: d.kpi_definitions.detailed_profiles, go: "portfolio" },
      { v: num(k.unique_market_signals), l: "Unique market signals", d: d.kpi_definitions.unique_market_signals, go: "signals" },
      { v: num(k.industries_covered), l: "Industries covered", d: d.kpi_definitions.industries_covered, go: "industry" },
      { v: num(k.verified_stakeholders), l: "Verified stakeholders", d: d.kpi_definitions.verified_stakeholders, go: "stakeholders" },
      { v: num(k.high_priority_opportunities), l: "High-priority hypotheses", d: d.kpi_definitions.high_priority_opportunities, go: "opportunities" },
      { v: num(k.companies_with_it_spend), l: "Companies with IT spend", d: d.kpi_definitions.companies_with_it_spend, go: "portfolio" },
      { v: num(k.companies_with_revenue), l: "Companies with revenue", d: d.kpi_definitions.companies_with_revenue, go: "portfolio" },
    ];
    const narrative = d.narrative.map((s, i) => '<details ' + (i < 2 ? "open" : "") + "><summary>" + esc(s.title) + "</summary>" +
      s.paragraphs.map((p) => "<p>" + esc(p) + "</p>").join("") + "</details>").join("");
    const html = '<h1 class="page-title">Executive Overview</h1>' +
      '<p class="page-sub">Eight months of PE intelligence for ' + esc(monthLabel(d.month)) + " snapshot. Snapshot counts follow the reporting month; news counts cover publication dates from April to October 2026.</p>" +
      kpis(cards) +
      '<section class="narr"><h2>Executive summary</h2>' + narrative + "</section>" +
      '<div class="grid-2"><div class="card"><h3>Portfolio coverage progression</h3>' + lineChart(d.trend, "portfolio_companies") +
      '<div class="legend"><span class="lg-High">Portfolio companies by snapshot</span></div></div>' +
      '<div class="card"><h3>Captured market signals by publication month</h3>' + bars(d.signal_trend.map((s) => ({ label: s.label, value: s.signals })), { label: "label", value: "value" }) +
      '<div class="note">Publication month from each news row. The 30 Apr workbook has no signal sheets.</div></div></div>' +
      '<div class="grid-2"><div class="card"><h3>Opportunity priority distribution</h3>' + bars(d.priority_distribution, { label: "priority", value: "n" }) +
      '<div class="note">Hypotheses for human validation. Priority bands: Critical 85-100, High 70-84, Medium 50-69, Low below 50.</div></div>' +
      '<div class="card"><h3>Industry concentration (top 10)</h3>' + bars(d.industry_concentration, { label: "name", value: "companies", click: "industry", key: "name" }) +
      '<div class="note">Click an industry to filter Industry Intelligence.</div></div></div>' +
      '<div class="grid-2"><div class="card"><h3>PE account ranking by portfolio coverage</h3>' + bars(d.firm_ranking, { label: "name", value: "companies", click: "firm", key: "id" }) +
      '<div class="note">Click a firm to open its account profile.</div></div>' +
      '<div class="card"><h3>Data coverage and caveats</h3><div class="note" id="caveats">Loading caveats…</div></div></div>';
    return { html, after(root) {
      animateBars(root); bindClicks(root);
      root.querySelectorAll("[data-go]").forEach((el) => el.addEventListener("click", () => { location.hash = "#/" + el.dataset.go; }));
      root.querySelectorAll(".kpi[data-go]").forEach((el) => el.addEventListener("keydown", (e) => { if (e.key === "Enter") location.hash = "#/" + el.dataset.go; }));
      api("/api/data-notes").then((n) => { const c = root.querySelector("#caveats"); if (c) c.innerHTML = '<ul style="padding-left:16px;margin:4px 0">' + n.caveats.map((x) => "<li>" + esc(x) + "</li>").join("") + "</ul>"; });
    } };
  }

  /* ---------- module 02 accounts ---------- */
  async function renderAccounts() {
    const list = await api("/api/accounts", { size: 200, sort: "portfolio_companies", dir: "desc" });
    const rows = list.rows;
    const funnel = [
      { label: "Targeted firms", value: rows.length },
      { label: "With portfolio companies this snapshot", value: rows.filter((r) => r.portfolio_companies > 0).length },
      { label: "With matched profiles", value: rows.filter((r) => r.matched_profiles > 0).length },
      { label: "With PE-level news", value: rows.filter((r) => r.pe_signals > 0).length },
      { label: "With stakeholders on file", value: rows.filter((r) => r.stakeholders > 0).length },
      { label: "With opportunity hypotheses", value: rows.filter((r) => r.opportunities > 0).length },
    ];
    const html = '<h1 class="page-title">PE Account Intelligence</h1>' +
      '<p class="page-sub">Account-level view of the 44 targeted PE firms for ' + esc(monthLabel(S.month)) + ". Click a row to open the firm profile. Historical associations are snapshot records, not verified current ownership.</p>" +
      '<div class="grid-2"><div class="card"><h3>Account coverage funnel</h3>' + bars(funnel, { label: "label", value: "value" }) + "</div>" +
      '<div class="card"><h3>Top accounts by portfolio coverage</h3>' + bars(rows.slice(0, 10).map((r) => ({ name: r.firm, value: r.portfolio_companies, id: r.id })), { label: "name", value: "value", click: "account", key: "id" }) +
      '<div class="note">Click a firm to open its profile.</div></div></div>' +
      '<div class="card" style="margin-bottom:14px"><h3>Top accounts by captured PE-level signal activity</h3>' + bars(rows.slice().sort((a, b) => b.pe_signals - a.pe_signals).slice(0, 8).map((r) => ({ name: r.firm, value: r.pe_signals })), { label: "name", value: "value" }) + "</div>" +
      '<div id="accTable"></div>';
    return { html, after(root) {
      animateBars(root); bindClicks(root);
      DataTable(root.querySelector("#accTable"), {
        endpoint: "/api/accounts", placeholder: "Search PE firm", defaultSort: "portfolio_companies", defaultDir: "desc",
        onRow: (id) => openAccount(id),
        columns: [
          { key: "firm", label: "PE firm", sort: "firm" },
          { key: "account_status", label: "Account status", sort: "account_status" },
          { key: "portfolio_companies", label: "Portfolio companies", sort: "portfolio_companies", num: true },
          { key: "matched_profiles", label: "Matched profiles", sort: "matched_profiles", num: true },
          { key: "pe_signals", label: "PE-level signals", sort: "pe_signals", num: true },
          { key: "stakeholders", label: "Stakeholders", sort: "stakeholders", num: true },
          { key: "opportunities", label: "Opportunities", sort: "opportunities", num: true },
          { key: "high_priority", label: "Critical/High", sort: "high_priority", num: true },
          { key: "latest_period_label", label: "Latest period", sort: "latest_period" },
        ],
      });
    } };
  }
  async function openAccount(id) {
    const d = await api("/api/accounts/" + id);
    const f = d.firm;
    const body = '<h4>Account summary</h4>' + kv([
      ["Requested name", f.requested_name || f.canonical_name], ["Matched name", f.draup_name || "Not matched"],
      ["Portfolio companies", num(d.companies.length) + " shown of this snapshot"],
      ["Revenue (latest year)", f.in_account_list ? dec(d.financials.revenue_usd_mm) + " USD m across " + num(d.financials.companies_with_revenue) + " companies" : "n/a"],
      ["IT spend (latest year)", dec(d.financials.it_spend_usd_mm) + " USD m across " + num(d.financials.companies_with_it_spend) + " companies"],
      ["Portfolio news count", num(d.portfolio_signal_count)],
    ]) +
      '<h4>Historical account coverage</h4><table><thead><tr><th>Snapshot</th><th>Status</th><th class="num">Portfolio companies</th></tr></thead><tbody>' +
      d.history.map((h) => "<tr><td>" + esc(h.label) + "</td><td>" + esc(h.status || "—") + '</td><td class="num">' + num(h.portfolio_count) + "</td></tr>").join("") + "</tbody></table>" +
      '<h4>Industry exposure</h4>' + bars(d.industries.map((x) => ({ name: x.name, value: x.n })), { label: "name", value: "value" }) +
      '<h4>Geographic exposure</h4>' + bars(d.regions.map((x) => ({ name: x.name, value: x.n })), { label: "name", value: "value" }) +
      '<h4>Associated portfolio companies (first 300)</h4><table><thead><tr><th>Company</th><th>Industry</th><th>Status</th></tr></thead><tbody>' +
      d.companies.map((c) => "<tr><td>" + esc(c.name) + "</td><td>" + esc(c.industry || "—") + "</td><td>" + (c.has_profile ? "Profiled" : "Not profiled") + "</td></tr>").join("") + "</tbody></table>" +
      '<h4>Recent PE-level signals</h4>' + (d.pe_signals.length ? '<ul style="padding-left:18px">' + d.pe_signals.map((s) => "<li><a href=\"" + esc(s.url || "#") + '" target="_blank" rel="noopener noreferrer">' + esc(s.title) + "</a> <span class=\"muted\">" + esc(dateStr(s.publication_date)) + " · " + esc(s.category) + "</span></li>").join("") + "</ul>" : '<div class="muted">No PE-level news recorded.</div>') +
      '<h4>Stakeholders</h4>' + (d.stakeholders.length ? '<ul style="padding-left:18px">' + d.stakeholders.map((s) => "<li>" + esc(s.name) + " — " + esc(s.designation || "") + " " + statusPill(s.verification_status) + "</li>").join("") + "</ul>" : '<div class="muted">No stakeholders recorded.</div>') +
      '<h4>Top potential opportunities (hypotheses)</h4>' + (d.top_opportunities.length ? '<ul style="padding-left:18px">' + d.top_opportunities.map((o) => "<li>" + pill(o.priority) + " " + esc(o.capability) + " — " + esc(o.company || "Firm-level") + " (" + dec(o.score, 0) + ")</li>").join("") + "</ul>" : '<div class="muted">None.</div>') +
      '<div class="callout">Opportunities are hypotheses for human validation. Historical associations are not verified current ownership.</div>';
    openDrawer(f.canonical_name, "Snapshot: " + d.month_label, body);
  }

  /* ---------- module 03 portfolio ---------- */
  async function renderPortfolio() {
    const s = await api("/api/portfolio/summary");
    const k = s.kpis;
    const html = '<h1 class="page-title">Portfolio Intelligence</h1>' +
      '<p class="page-sub">Portfolio companies linked to the targeted firms in the ' + esc(monthLabel(s.month)) + ' snapshot. Missing financials are shown as "Not reported", never as zero. Revenue and IT spend are source-reported USD millions.</p>' +
      kpis([
        { v: num(k.unique_companies), l: "Unique portfolio companies", d: "Distinct companies in this snapshot", go: "" },
        { v: num(k.matched_links), l: "Matched links", d: "Links with a platform status", go: "" },
        { v: num(k.unmatched_links), l: "Unmatched links", d: "Links with no platform status", go: "" },
        { v: num(k.detailed_profiles), l: "Detailed profiles", d: "Companies with a dashboard profile in this month", go: "" },
        { v: num(k.with_signals), l: "Companies with signals", d: "Any publication month", go: "signals" },
        { v: num(k.with_revenue), l: "Companies with revenue", d: "Reported revenue this month", go: "" },
        { v: num(k.with_it_spend), l: "Companies with IT spend", d: "Reported IT spend this month", go: "" },
      ]) +
      '<div class="grid-2"><div class="card"><h3>Industry distribution (top 12)</h3>' + bars(s.industry, { label: "name", value: "n", click: "industry", key: "name" }) + '<div class="note">Click an industry to filter Industry Intelligence.</div></div>' +
      '<div class="card"><h3>Geographic distribution</h3>' + bars(s.region, { label: "name", value: "n" }) + "</div></div>" +
      '<div class="grid-2"><div class="card"><h3>Portfolio coverage by PE firm (top 15)</h3>' + bars(s.firm_coverage, { label: "name", value: "n" }) + "</div>" +
      '<div class="card"><h3>Revenue versus IT spend</h3>' + scatterChart(s.revenue_it_scatter) + "</div></div>" +
      '<div class="card" style="margin-bottom:14px"><h3>Eight-month portfolio progression</h3>' + lineChart(s.trend, "companies") + "</div>" +
      '<div id="portTable"></div>';
    return { html, after(root) {
      animateBars(root); bindClicks(root);
      DataTable(root.querySelector("#portTable"), {
        endpoint: "/api/portfolio", placeholder: "Search company or domain", defaultSort: "company", defaultDir: "asc", onRow: (id) => openCompany(id),
        columns: [
          { key: "company", label: "Company", sort: "company" },
          { key: "pe_firms", label: "PE firm(s)", fmt: (v) => esc(v || "—") },
          { key: "industry", label: "Industry", sort: "industry" },
          { key: "headquarters", label: "Headquarters" },
          { key: "revenue_usd_mm", label: "Revenue USD m", sort: "revenue_usd_mm", num: true, fmt: (v) => dec(v) },
          { key: "it_spend_usd_mm", label: "IT spend USD m", sort: "it_spend_usd_mm", num: true, fmt: (v) => dec(v) },
          { key: "match_status", label: "Profile" },
          { key: "signal_count", label: "Signals", sort: "signal_count", num: true },
          { key: "opportunity_priority", label: "Top priority", sort: "opportunity_priority", fmt: (v) => pill(v) },
        ],
      });
    } };
  }
  async function openCompany(id) {
    const d = await api("/api/portfolio/" + id);
    const c = d.company;
    const body = '<h4>Company overview</h4>' + kv([
      ["Industry", c.primary_vertical], ["Sub-industry", c.sub_vertical], ["Headquarters", c.hq_location], ["Country", c.hq_country],
      ["Region", c.hq_region], ["Company type", c.company_type], ["Founded", c.founded_year], ["Domain", c.domain],
      ["Latest revenue", d.latest_revenue_usd_mm === null ? "Not reported" : dec(d.latest_revenue_usd_mm) + " USD m (FY" + d.latest_revenue_year + ")"],
      ["Latest IT spend", d.latest_it_spend_usd_mm === null ? "Not reported" : dec(d.latest_it_spend_usd_mm) + " USD m (FY" + d.latest_it_spend_year + ")"],
      ["IT spend % of revenue", d.it_spend_pct_of_revenue === null ? "Not calculable" : d.it_spend_pct_of_revenue + "%"],
    ]) +
      '<h4>Historical PE associations</h4><table><thead><tr><th>Snapshot</th><th>PE firm</th><th>Platform status</th></tr></thead><tbody>' +
      d.associations.slice(0, 40).map((a) => "<tr><td>" + esc(monthLabel(a.month)) + "</td><td>" + esc(a.pe_firm) + "</td><td>" + esc(a.platform_status || "—") + "</td></tr>").join("") + "</tbody></table>" +
      '<h4>Captured market signals</h4>' + (d.signals.length ? '<ul style="padding-left:18px">' + d.signals.map((s) => "<li>" + (s.url ? '<a href="' + esc(s.url) + '" target="_blank" rel="noopener noreferrer">' + esc(s.title) + "</a>" : esc(s.title)) + " <span class=\"muted\">" + esc(dateStr(s.publication_date)) + " · " + esc(s.category) + "</span></li>").join("") + "</ul>" : '<div class="muted">No portfolio-level news captured.</div>') +
      '<h4>Potential consulting hypotheses</h4>' + (d.opportunities.length ? '<ul style="padding-left:18px">' + d.opportunities.map((o) => "<li>" + pill(o.priority) + " " + esc(o.capability) + " (" + dec(o.score, 0) + ") · " + esc(o.pe_firm) + "</li>").join("") + "</ul>" : '<div class="muted">None.</div>') +
      '<div class="callout">Hypotheses require validation with the company. Scores are not win probabilities.</div>';
    openDrawer(c.display_name, [c.primary_vertical, c.hq_country].filter(Boolean).join(" · "), body);
  }

  /* ---------- module 04 market signals ---------- */
  async function renderSignals() {
    const sum = await api("/api/signals/summary");
    const k = sum.kpis;
    const catOptions = META.categories.map((c) => ({ value: c, label: c }));
    const monthOptions = PUB_MONTHS.map((m) => ({ value: m, label: MONTH_LABELS[m] }));
    const html = '<h1 class="page-title">Market Signals</h1>' +
      '<p class="page-sub">Captured news, de-duplicated across workbooks. Dates shown are publication dates from each row. The "observed in" column records which reporting workbooks contained the item. ' +
      'Firm and industry filters apply to portfolio-level news. Industry and region filters exclude PE-level news.</p>' +
      kpis([
        { v: num(k.unique_signals), l: "Unique market signals", d: "Publication months Apr-Oct 2026" },
        { v: num(k.pe_firm_signals), l: "PE firm signals", d: "Headline news about the PE firm" },
        { v: num(k.portfolio_signals), l: "Portfolio company signals", d: "News about portfolio companies" },
        { v: num(k.companies_with_signals), l: "Companies with signals", d: "Distinct companies with at least one item" },
      ]) +
      '<div class="grid-2"><div class="card"><h3>Signal category distribution</h3>' + bars(sum.categories, { label: "name", value: "n" }) + "</div>" +
      '<div class="card"><h3>Monthly publication trend</h3>' + bars(sum.publication_trend.map((x) => ({ label: x.label, value: x.publications })), { label: "label", value: "value" }) +
      '<div class="note">' + esc(sum.note) + "</div></div></div>" +
      '<div id="sigTable"></div>';
    return { html, after(root) {
      animateBars(root);
      DataTable(root.querySelector("#sigTable"), {
        endpoint: "/api/signals", placeholder: "Search headline, company or description", defaultSort: "publication_date", defaultDir: "desc",
        onRow: (id) => openSignal(id),
        filters: [
          { name: "category", label: "Category", options: catOptions },
          { name: "scope", label: "Level", options: [{ value: "PE", label: "PE firm" }, { value: "PORTFOLIO", label: "Portfolio company" }] },
          { name: "from", label: "From", options: monthOptions },
          { name: "to", label: "To", options: monthOptions },
        ],
        columns: [
          { key: "publication_date", label: "Published", sort: "publication_date", fmt: (v) => esc(dateStr(v)) },
          { key: "title", label: "Headline", sort: "title", fmt: (v) => esc(v) },
          { key: "company", label: "Company", sort: "company" },
          { key: "pe_firm", label: "PE firm", fmt: (v) => esc(v || "—") },
          { key: "industry", label: "Industry", fmt: (v) => esc(v || "—") },
          { key: "category", label: "Category", sort: "category" },
          { key: "observed_in_workbooks", label: "Observed in workbooks", fmt: (v) => esc(v ? v.split(",").map(monthLabel).join(", ") : "—") },
          { key: "source_url", label: "Source", fmt: (v) => (v ? '<a href="' + esc(v) + '" target="_blank" rel="noopener noreferrer">Open</a>' : "—") },
        ],
      });
    } };
  }
  async function openSignal(id) {
    const d = await api("/api/signals/" + id);
    const s = d.signal;
    const body = '<h4>Source description</h4><p>' + esc(s.news_description || "No description in the source row.") + "</p>" +
      kv([["Publication date", dateStr(s.publication_date)], ["Publication month", monthLabel(s.publication_month)],
        ["Observed in workbooks", d.observed_in_reporting_months.map(monthLabel).join(", ") || "—"],
        ["Company", s.company_name], ["Industry", s.industry || s.primary_vertical], ["Level", s.scope === "PE" ? "PE firm" : "Portfolio company"],
        ["PE firm", s.pe_firm], ["Category", s.category]]) +
      '<div class="callout"><strong>Analytical interpretation (hypothesis):</strong> ' + esc(CHALLENGE_BY_CATEGORY[s.category] || "Review the source before drawing conclusions.") +
      '<br><strong>Potential Zinnov capability:</strong> ' + esc(CAPABILITY_BY_CATEGORY[s.category] || "To be assessed") + "</div>" +
      '<div class="callout warn">A news item is not a confirmed transaction. Check the original source before acting on it.</div>' +
      (s.news_url ? '<p><a href="' + esc(s.news_url) + '" target="_blank" rel="noopener noreferrer">Open original source</a></p>' : "") +
      '<h4>Related hypotheses</h4>' + (d.related_opportunities.length ? '<ul style="padding-left:18px">' + d.related_opportunities.map((o) => "<li>" + pill(o.priority) + " " + esc(o.capability) + " · " + esc(o.pe_firm) + "</li>").join("") + "</ul>" : '<div class="muted">None.</div>');
    openDrawer(s.news_title, [s.company_name, dateStr(s.publication_date)].join(" · "), body);
  }

  /* ---------- module 05 industry ---------- */
  async function renderIndustry() {
    const list = await api("/api/industry", { size: 100, sort: "portfolio_companies", dir: "desc" });
    const rows = list.rows;
    const totalCompanies = rows.reduce((a, r) => a + r.portfolio_companies, 0);
    const html = '<h1 class="page-title">Industry Intelligence</h1>' +
      '<p class="page-sub">Targeted-account intelligence by primary vertical for ' + esc(monthLabel(S.month)) + '. These are not comprehensive market statistics. Click an industry to open its companies.</p>' +
      kpis([
        { v: num(rows.length), l: "Industries in view", d: "Primary verticals with at least one company" },
        { v: num(totalCompanies), l: "Company-industry links", d: "A company with two firms counts twice" },
        { v: num(rows.reduce((a, r) => a + r.market_signals, 0)), l: "Portfolio signals in view", d: "Publication months Apr-Oct 2026" },
        { v: num(rows.reduce((a, r) => a + r.opportunities, 0)), l: "Opportunity hypotheses", d: "Company-level hypotheses in these industries" },
      ]) +
      '<div class="grid-2"><div class="card"><h3>Industry concentration (top 12 by companies)</h3>' + bars(rows.slice(0, 12).map((r) => ({ name: r.industry, value: r.portfolio_companies })), { label: "name", value: "value", click: "industry", key: "name" }) + "</div>" +
      '<div class="card"><h3>Market signals by industry (top 12)</h3>' + bars(rows.slice().sort((a, b) => b.market_signals - a.market_signals).slice(0, 12).map((r) => ({ name: r.industry, value: r.market_signals })), { label: "name", value: "value" }) + "</div></div>" +
      '<div id="indTable"></div>';
    return { html, after(root) {
      animateBars(root); bindClicks(root);
      DataTable(root.querySelector("#indTable"), {
        endpoint: "/api/industry", placeholder: "Search industry", defaultSort: "portfolio_companies", defaultDir: "desc",
        rowKey: "industry", onRow: (name) => openIndustry(name),
        columns: [
          { key: "industry", label: "Industry", sort: "industry" },
          { key: "portfolio_companies", label: "Portfolio companies", sort: "portfolio_companies", num: true },
          { key: "pe_firms", label: "PE firms", sort: "pe_firms", num: true },
          { key: "market_signals", label: "Market signals", sort: "market_signals", num: true },
          { key: "revenue_coverage", label: "Revenue reported", num: true, fmt: (v, r) => num(v) + " (" + pct(v, r.portfolio_companies) + ")" },
          { key: "it_spend_coverage", label: "IT spend reported", num: true, fmt: (v, r) => num(v) + " (" + pct(v, r.portfolio_companies) + ")" },
          { key: "opportunities", label: "Opportunity hypotheses", sort: "opportunities", num: true },
        ],
      });
    } };
  }
  async function openIndustry(name) {
    const d = await api("/api/industry/companies", { industry: name, size: 200 });
    const rows = d.rows;
    const body = '<h4>Sub-industries</h4>' + bars(d.sub_industries.map((x) => ({ name: x.name, value: x.n })), { label: "name", value: "value" }) +
      '<h4>Companies (' + num(d.total) + ')</h4>' + (d.total > rows.length ? '<div class="note">Showing the first ' + num(rows.length) + ". Use the Portfolio module filters for the full list.</div>" : "") +
      '<table><thead><tr><th>Company</th><th>Sub-industry</th><th>Region</th><th>PE firm(s)</th><th class="num">Revenue USD m</th></tr></thead><tbody>' +
      rows.map((r) => "<tr><td>" + esc(r.company) + "</td><td>" + esc(r.sub_industry || "—") + "</td><td>" + esc(r.region || "—") + "</td><td>" + esc(r.pe_firms) + '</td><td class="num">' + dec(r.revenue_usd_mm) + "</td></tr>").join("") + "</tbody></table>";
    openDrawer(name, "Industry drill-down for " + monthLabel(S.month), body);
  }

  /* ---------- module 06 stakeholders ---------- */
  async function renderStakeholders() {
    const s = await api("/api/stakeholders/summary");
    const k = s.kpis;
    const html = '<h1 class="page-title">Stakeholder Intelligence</h1>' +
      '<p class="page-sub">Decision-makers at the targeted firms. Verification was performed on ' + esc(dateStr(s.checked_on)) + " and is not re-verified in November. Successor candidates are unconfirmed. Contact emails are not shown. The reporting-month filter does not apply to this module.</p>" +
      kpis([
        { v: num(k.unique_stakeholders), l: "Unique stakeholders", d: "Rows in the verified file" },
        { v: num(k.verified_confirmed), l: "Verified (Confirmed)", d: "Status Confirmed on 4 Sep 2026" },
        { v: num(k.targeted_firms_with_stakeholders), l: "Targeted firms with stakeholders", d: "Of the 44 targeted firms. " + num(k.stakeholder_only_firms) + " stakeholder-only firms are labelled and not counted as targeted." },
        { v: num(k.da_m_aligned), l: "DA&M aligned", d: "Flagged for data, analytics and modernisation" },
        { v: num(k.cybersecurity_aligned), l: "Cybersecurity aligned", d: "Flagged for security" },
        { v: num(k.bfsi_aligned), l: "BFSI aligned", d: "Flagged for banking and financial services" },
        { v: num(k.healthcare_aligned), l: "Healthcare aligned", d: "Flagged for healthcare" },
        { v: num(k.requiring_review), l: "Requiring review", d: "Left organisation or title changed" },
      ]) +
      '<div class="grid-2"><div class="card"><h3>Verification status distribution</h3>' + bars(s.status, { label: "name", value: "n" }) + "</div>" +
      '<div class="card"><h3>Confidence distribution</h3>' + bars(s.confidence, { label: "name", value: "n" }) + "</div></div>" +
      '<div id="stkTable"></div>';
    return { html, after(root) {
      animateBars(root);
      DataTable(root.querySelector("#stkTable"), {
        endpoint: "/api/stakeholders", placeholder: "Search name or designation", defaultSort: "stakeholder", defaultDir: "asc",
        onRow: (id) => openStakeholder(id),
        filters: [
          { name: "status", label: "Verification", options: [{ value: "Confirmed", label: "Confirmed" }, { value: "Title Changed", label: "Title Changed" }, { value: "Left Organization", label: "Left Organization" }] },
          { name: "flag", label: "Sector", options: [{ value: "da_m", label: "DA&M" }, { value: "cybersecurity", label: "Cybersecurity" }, { value: "bfsi", label: "BFSI" }, { value: "healthcare", label: "Healthcare" }] },
        ],
        columns: [
          { key: "stakeholder", label: "Stakeholder", sort: "stakeholder" },
          { key: "pe_firm", label: "PE firm", sort: "pe_firm" },
          { key: "designation", label: "Designation" },
          { key: "current_company", label: "Current organisation" },
          { key: "sector_alignment", label: "Sector alignment", fmt: (v) => esc(v || "—") },
          { key: "verification_status", label: "Verification", sort: "verification_status", fmt: (v) => statusPill(v) },
          { key: "confidence", label: "Confidence", sort: "confidence" },
          { key: "last_checked", label: "Last checked", sort: "last_checked", fmt: (v) => esc(dateStr(v)) },
        ],
      });
    } };
  }
  async function openStakeholder(id) {
    const d = await api("/api/stakeholders/" + id);
    const s = d.stakeholder;
    const body = '<h4>Professional overview</h4>' + kv([
      ["PE firm", s.pe_firm], ["Designation on file", s.designation], ["Current organisation", s.current_company], ["Current title", s.current_title],
      ["Sector alignment", d.stakeholder.sector_alignment.length ? d.stakeholder.sector_alignment.join(", ") : "None flagged"],
      ["Account status", s.account_status]]) +
      '<h4>Verification evidence</h4>' + kv([["Verification", statusPill(s.verification_status)], ["Confidence", s.confidence], ["Checked on", dateStr(s.checked_on)],
      ["Evidence", s.evidence], ["Evidence URL", s.evidence_url ? '<a href="' + esc(s.evidence_url) + '" target="_blank" rel="noopener noreferrer">Source</a>' : null, true], ["Reviewer note", s.reviewer_note]]) +
      '<h4>Role tenure and career</h4>' + kv([["Current role tenure", s.current_role_tenure], ["Current role since", s.current_role_since], ["Career length", s.career_length], ["Prior roles", s.prior_roles]]) +
      (s.career_history ? '<div class="note" style="white-space:pre-wrap">' + esc(s.career_history) + "</div>" : "") +
      '<h4>Potential successor (unconfirmed)</h4>' + (s.successor_name ? kv([["Candidate", s.successor_name], ["Title", s.successor_title], ["Evidence", s.successor_evidence]]) + '<div class="callout warn">Successor candidates are not confirmed appointments.</div>' : '<div class="muted">None recorded.</div>') +
      '<h4>Outreach record</h4>' + kv([["Initial outreach date", dateStr(s.initial_outreach_date)], ["Follow-up date", dateStr(s.followup_date)], ["Follow-up response", s.followup_response && s.followup_response !== "-" ? s.followup_response : "Not logged"], ["Remark", s.remark]]) +
      '<h4>Related hypotheses at this firm</h4>' + (d.related_opportunities.length ? '<ul style="padding-left:18px">' + d.related_opportunities.map((o) => "<li>" + pill(o.priority) + " " + esc(o.capability) + " (" + dec(o.score, 0) + ")</li>").join("") + "</ul>" : '<div class="muted">None.</div>') +
      (s.linkedin_url ? '<p><a href="' + esc(s.linkedin_url) + '" target="_blank" rel="noopener noreferrer">Professional profile</a></p>' : "");
    openDrawer(s.name, s.pe_firm, body);
  }

  /* ---------- module 07 opportunities ---------- */
  async function renderOpportunities() {
    const s = await api("/api/opportunities/summary");
    const k = s.kpis;
    const caps = s.capability.map((c) => ({ value: c.name, label: c.name }));
    const heatInd = [...new Set(s.heatmap.map((h) => h.industry))].map((ind) => {
      const row = { industry: ind };
      ["Critical", "High", "Medium", "Low"].forEach((p) => { const f = s.heatmap.find((h) => h.industry === ind && h.priority === p); row[p] = f ? f.n : 0; });
      row.total = row.Critical + row.High + row.Medium + row.Low; return row;
    }).sort((a, b) => b.total - a.total).slice(0, 12);
    const heat = '<table class="heat"><thead><tr><th style="text-align:left">Industry</th><th>Critical</th><th>High</th><th>Medium</th><th>Low</th></tr></thead><tbody>' +
      heatInd.map((r) => "<tr><td style=\"text-align:left\">" + esc(r.industry) + "</td>" + ["Critical", "High", "Medium", "Low"].map((p) => {
        const alpha = Math.min(0.9, r[p] / Math.max(1, Math.max.apply(null, heatInd.map((x) => x[p]))));
        return '<td style="background:rgba(20,93,160,' + alpha.toFixed(2) + ');color:' + (alpha > 0.5 ? "#fff" : "var(--text)") + '">' + num(r[p]) + "</td>";
      }).join("") + "</tr>").join("") + "</tbody></table>";
    const html = '<h1 class="page-title">Opportunity Intelligence</h1>' +
      '<p class="page-sub">Hypotheses that connect captured news, reported financials and stakeholder alignment to Zinnov capabilities. Each is for human validation and is not a confirmed requirement, budget or win probability. Associations come from the 13 Nov 2026 snapshot, so the reporting-month filter does not change this module.</p>' +
      kpis([
        { v: num(k.total), l: "Potential opportunities", d: "Hypotheses after applying filters" },
        { v: num(k.critical), l: "Critical priority", d: "Score 85 to 100" },
        { v: num(k.high), l: "High priority", d: "Score 70 to 84" },
        { v: num(k.accounts), l: "PE accounts with hypotheses", d: "Firms with at least one hypothesis" },
        { v: num(k.companies), l: "Portfolio companies", d: "Companies with a company-level hypothesis" },
        { v: num(k.with_confirmed_stakeholders), l: "With confirmed stakeholders", d: "Firm has at least one Confirmed stakeholder" },
      ]) +
      '<div class="grid-2"><div class="card"><h3>Priority distribution</h3>' + bars(s.priority, { label: "name", value: "n" }) + "</div>" +
      '<div class="card"><h3>Zinnov capability alignment</h3>' + bars(s.capability.map((c) => ({ name: c.name, value: c.n })), { label: "name", value: "value" }) + "</div></div>" +
      '<div class="grid-2"><div class="card"><h3>Priority account ranking (top 12)</h3>' + bars(s.accounts.map((a) => ({ name: a.name, value: a.high_priority })), { label: "name", value: "value" }) +
      '<div class="note">Bars show Critical and High hypotheses per firm.</div></div>' +
      '<div class="card"><h3>Industry opportunity heatmap</h3>' + heat + '<div class="note">Intensity shows hypothesis count per priority band.</div></div></div>' +
      '<div class="card" style="margin-bottom:14px"><h3>Scoring model (transparent, configurable weights)</h3>' +
      '<div class="note">' + Object.keys(s.method.weights).map((w) => esc(w) + " " + s.method.weights[w] + "%").join(" · ") + ". Bands: Critical 85-100, High 70-84, Medium 50-69, Low below 50. Missing revenue scores the neutral 0.3 default and is flagged. " + esc(s.method.scope) + "</div></div>" +
      '<div id="oppTable"></div>';
    return { html, after(root) {
      animateBars(root);
      DataTable(root.querySelector("#oppTable"), {
        endpoint: "/api/opportunities", placeholder: "Search firm or company", defaultSort: "score", defaultDir: "desc",
        onRow: (id) => openOpportunity(id),
        filters: [
          { name: "priority", label: "Priority", options: [{ value: "Critical", label: "Critical" }, { value: "High", label: "High" }, { value: "Medium", label: "Medium" }, { value: "Low", label: "Low" }] },
          { name: "capability", label: "Capability", options: caps },
        ],
        columns: [
          { key: "pe_firm", label: "PE firm", sort: "pe_firm" },
          { key: "portfolio_company", label: "Portfolio company", sort: "portfolio_company" },
          { key: "triggering_signal", label: "Triggering signal", fmt: (v) => esc(v || "—") },
          { key: "zinnov_capability", label: "Zinnov capability" },
          { key: "score", label: "Score", sort: "score", num: true, fmt: (v) => dec(v, 1) },
          { key: "priority", label: "Priority", sort: "priority", fmt: (v) => pill(v) },
          { key: "evidence_confidence", label: "Evidence" },
          { key: "confirmed_stakeholder_count", label: "Confirmed stakeholders", num: true },
          { key: "recommended_action", label: "Recommended next action" },
        ],
      });
    } };
  }
  async function openOpportunity(id) {
    const d = await api("/api/opportunities/" + id);
    const o = d.opportunity; const sig = d.signal || {};
    const comps = o.component_scores || {};
    const weights = { signal_relevance: 25, capability_alignment: 25, scale: 20, recency: 15, evidence: 10, stakeholders: 5 };
    const labels = { signal_relevance: "Signal relevance", capability_alignment: "Capability alignment", scale: "Business scale", recency: "Signal recency", evidence: "Evidence quality", stakeholders: "Stakeholder availability" };
    const body = '<h4>1. What happened?</h4><p>' + esc(o.triggering_title || "No triggering signal") + " <span class=\"muted\">(" + esc(o.triggering_category || "") + " · " + esc(dateStr(o.publication_date)) + ")</span></p>" +
      '<h4>2. Why does it matter?</h4><p>' + esc(o.hypothesis_rationale || "") + "</p>" +
      '<h4>3. Potential business challenge</h4><p>' + esc(CHALLENGE_BY_CATEGORY[o.triggering_category] || "Review the source to identify the challenge.") + "</p>" +
      '<h4>4. How could Zinnov help?</h4><p><strong>' + esc(o.capability) + "</strong>. " + esc(o.recommended_action || "") + "</p>" +
      '<h4>5. Financial and technology spend context</h4>' + kv([["Revenue (USD m)", o.revenue_usd_mm === null ? "Not reported" : dec(o.revenue_usd_mm)], ["IT spend (USD m)", o.it_spend_usd_mm === null ? "Not reported" : dec(o.it_spend_usd_mm)], ["Industry", o.industry || "Firm-level"]]) +
      '<h4>6. Relevant stakeholders</h4>' + (d.stakeholders.length ? '<ul style="padding-left:18px">' + d.stakeholders.map((x) => "<li>" + esc(x.name) + " — " + esc(x.designation || "") + " " + statusPill(x.verification_status) + "</li>").join("") + "</ul>" : '<div class="muted">No stakeholders recorded for this firm.</div>') +
      '<h4>7. Evidence</h4>' + (sig.news_url ? '<p><a href="' + esc(sig.news_url) + '" target="_blank" rel="noopener noreferrer">Original source</a> · ' + esc(dateStr(sig.publication_date)) + "</p>" : '<div class="muted">No source link in the data.</div>') +
      '<div class="kv"><div>Evidence confidence</div><div>' + esc(o.evidence_confidence) + "</div></div>" +
      '<h4>8. How was the score calculated?</h4><table><thead><tr><th>Component</th><th class="num">Weight</th><th class="num">Value (0-1)</th></tr></thead><tbody>' +
      Object.keys(labels).map((key) => "<tr><td>" + esc(labels[key]) + '</td><td class="num">' + weights[key] + '%</td><td class="num">' + dec(comps[key], 2) + "</td></tr>").join("") +
      '</tbody></table><div class="note">Total score ' + dec(o.score, 1) + " (" + esc(o.priority) + "). " + esc(o.notes || "") + "</div>" +
      '<h4>9. Next step for business development</h4><p>' + esc(o.recommended_action || "") + "</p>" +
      '<div class="callout warn">' + esc(d.hypothesis_note) + "</div>";
    openDrawer(o.company || (o.pe_firm + " (firm-level)"), o.pe_firm + " · " + o.priority + " · score " + dec(o.score, 1), body);
  }

  /* ---------- module 08 outreach ---------- */
  async function renderOutreach() {
    const s = await api("/api/outreach/summary");
    const k = s.kpis;
    const statuses = s.status_breakdown.map((x) => ({ value: x.name, label: x.name }));
    const html = '<h1 class="page-title">Outreach Intelligence</h1>' +
      '<p class="page-sub">Recorded outreach fields from the stakeholder workbook. ' + esc(s.note) + "</p>" +
      kpis([
        { v: num(k.stakeholders_in_view), l: "Stakeholders in view", d: "Within the current firm filter" },
        { v: num(k.with_outreach_recorded), l: "Outreach date recorded", d: "Initial outreach date populated" },
        { v: num(k.with_followup_recorded), l: "Follow-up recorded", d: "Follow-up date populated" },
        { v: num(k.with_response_recorded), l: "Response recorded", d: "Follow-up response with a value other than a dash" },
        { v: num(k.without_outreach_recorded), l: "No outreach recorded", d: "No initial outreach date" },
        { v: num(k.requiring_review), l: "Requiring review", d: "Stakeholder not Confirmed" },
        { v: num(k.accounts_with_engagement), l: "Accounts with recorded engagement", d: "Firms with an outreach date" },
      ]) +
      '<div class="grid-2"><div class="card"><h3>Outreach status categories</h3>' + bars(s.status_breakdown, { label: "name", value: "n" }) + "</div>" +
      '<div class="card"><h3>Reading this view</h3><div class="note">An empty response is not treated as a rejection or as a successful engagement. Outreach dates are recorded fields; confirm them with the relationship owner before reporting engagement.</div></div></div>' +
      '<div id="outTable"></div>';
    return { html, after(root) {
      animateBars(root);
      DataTable(root.querySelector("#outTable"), {
        endpoint: "/api/outreach", placeholder: "Search stakeholder", onRow: (id) => openStakeholder(id),
        filters: [{ name: "status", label: "Outreach status", options: statuses }],
        columns: [
          { key: "stakeholder", label: "Stakeholder" },
          { key: "pe_firm", label: "PE firm" },
          { key: "designation", label: "Designation" },
          { key: "sector_alignment", label: "Sector alignment", fmt: (v) => esc(v || "—") },
          { key: "initial_outreach_date", label: "Initial outreach", fmt: (v) => esc(dateStr(v)) },
          { key: "followup_date", label: "Follow-up", fmt: (v) => esc(dateStr(v)) },
          { key: "followup_response", label: "Recorded response", fmt: (v) => esc(v && v !== "-" ? v : "Not logged") },
          { key: "outreach_status", label: "Status" },
          { key: "recommended_next_action", label: "Recommended next action" },
        ],
      });
    } };
  }

  const RENDER = {
    overview: renderOverview, accounts: renderAccounts, portfolio: renderPortfolio, signals: renderSignals,
    industry: renderIndustry, stakeholders: renderStakeholders, opportunities: renderOpportunities, outreach: renderOutreach,
  };

  /* ---------- global search and export ---------- */
  function bindGlobal() {
    $("#drawerClose").addEventListener("click", closeDrawer);
    $("#backdrop").addEventListener("click", closeDrawer);
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeDrawer(); });
    window.addEventListener("hashchange", renderCurrent);
  }

  async function init() {
    buildNav(); bindFilters(); bindGlobal();
    META = await api("/api/meta");
    if (!META.months.some((m) => m.value === S.month)) S.month = "2026-11";
    fillSelect($("#fFirm"), META.firms.map((f) => ({ value: String(f.id), label: f.name })), S.firm, "All PE firms");
    fillSelect($("#fIndustry"), META.industries.map((i) => ({ value: i, label: i })), S.industry, "All industries");
    fillSelect($("#fRegion"), META.regions.map((r) => ({ value: r, label: r })), S.region, "All regions");
    syncFilterControls();
    $("#coverage").textContent = META.coverage;
    if (!location.hash) location.hash = "#/overview";
    renderCurrent();
  }
  init().catch((err) => { $("#view").innerHTML = '<div class="error">Could not load the platform: ' + esc(err.message) + "</div>"; });
})();
