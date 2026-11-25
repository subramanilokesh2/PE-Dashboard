"""ZINNOV | PE Intelligence Command Center: Flask API and static frontend.

Bound to 127.0.0.1 only. Reads the prebuilt SQLite database in data/intel.db.
All text files are read and written as UTF-8.
"""
import csv, io, json, math, sqlite3, sys
from pathlib import Path
from collections import Counter
from flask import Flask, request, jsonify, send_from_directory, Response, abort

BASE = Path(__file__).resolve().parent.parent
DB = BASE / "data" / "intel.db"
FRONTEND = BASE / "frontend"
MONTHS = ["2026-04", "2026-05", "2026-06", "2026-07", "2026-08", "2026-09", "2026-10", "2026-11"]
MONTH_LABEL = {m: ["Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov"][i] + " 2026" for i, m in enumerate(MONTHS)}
PRIORITY_ORDER = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
DATA_CAVEATS = [
    "Reporting month is the month in the workbook name. Publication month is the date on each news row. They differ: the 13 Nov workbook holds October news.",
    "The 30 Apr workbook has no signal sheets. April news appears in the 18 May workbook, so April is not zero market activity.",
    "Historical PE-to-portfolio associations are workbook snapshots. They are not verified current ownership.",
    "Stakeholder verification dates from 4 Sep 2026 (file dated 9 Sep). These were not re-verified in November.",
    "Successor candidates are unconfirmed suggestions, not appointments.",
    "Opportunity scores are prioritisation hypotheses for human validation. They are not win probabilities or confirmed demand.",
    "Stakeholder email addresses are excluded from this platform.",
    "Only 15 of the 44 targeted firms have stakeholder records. The stakeholder file also covers 15 firms that are not on the targeted list. Those firms are labelled and not counted as targeted accounts.",
    "Financial coverage is thin. Only about 238 snapshot companies report revenue and IT spend in the November workbook. Missing values are shown as Not reported.",
    "Opportunity category rules are deterministic. A source category such as Center Setup and Expansion can include items that are not GCC decisions, so each hypothesis needs review against its source.",
    "Revenue and IT spend are source-reported USD millions. Missing values are shown as missing, never as zero.",
]

app = Flask(__name__, static_folder=None)

def db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con

def ql(seq):
    return ",".join("?" * len(seq))

def split_multi(value, sep=","):
    return [x for x in (value or "").split(sep) if x.strip()]

class F:
    """Parsed global filters shared by every module."""
    def __init__(self, args):
        m = args.get("month") or "2026-11"
        self.month = m if m in MONTHS else "2026-11"
        self.firms = [int(x) for x in split_multi(args.get("firm")) if x.strip().isdigit()]
        self.industries = split_multi(args.get("industry"), "|")
        self.regions = split_multi(args.get("region"), "|")

    def company_clause(self, cl="c"):
        """Clauses for companies (and their links) under the snapshot month."""
        parts, params = [], []
        if self.industries:
            parts.append(f"{cl}.primary_vertical IN ({ql(self.industries)})"); params += self.industries
        if self.regions:
            parts.append(f"{cl}.hq_region IN ({ql(self.regions)})"); params += self.regions
        return parts, params

    def link_where(self):
        parts, params = ["l.reporting_month = ?"], [self.month]
        if self.firms:
            parts.append(f"l.firm_id IN ({ql(self.firms)})"); params += self.firms
        p, pa = self.company_clause("c")
        return " AND ".join(parts + p), params + pa

    def firm_clause(self, col="f.id"):
        if not self.firms: return "1=1", []
        return f"{col} IN ({ql(self.firms)})", list(self.firms)

def page_args(args, default_size=25):
    try: page = max(1, int(args.get("page", 1)))
    except ValueError: page = 1
    try: size = min(200, max(5, int(args.get("size", default_size))))
    except ValueError: size = default_size
    return page, size

def respond_list(rows, total, page, size, columns=None):
    if request.args.get("format") == "csv":
        buf = io.StringIO()
        if rows:
            w = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
            w.writeheader(); w.writerows(rows)
        return Response(buf.getvalue(), mimetype="text/csv; charset=utf-8",
                        headers={"Content-Disposition": "attachment; filename=export.csv"})
    return jsonify({"rows": rows, "total": total, "page": page, "size": size,
                    "pages": max(1, math.ceil(total / size))})

def sort_clause(args, allowed, default, tie=""):
    """ORDER BY from whitelisted sort keys only. tie is a qualified id column for stable paging."""
    key = args.get("sort") or default
    col = allowed.get(key, allowed[default])
    direction = "DESC" if (args.get("dir") or "").lower() == "desc" else "ASC"
    return f"ORDER BY {col} {direction}" + (f", {tie} ASC" if tie else "")

def search_like(term):
    return f"%{term.strip().lower()}%"

# ---------------------------------------------------------------- meta
@app.get("/api/meta")
def meta():
    con = db()
    firms = [dict(r) for r in con.execute("""SELECT id, canonical_name AS name, in_account_list FROM pe_firms
             WHERE in_account_list = 1 ORDER BY canonical_name""")]
    verticals = [r[0] for r in con.execute("""SELECT DISTINCT primary_vertical FROM companies
             WHERE has_profile = 1 AND primary_vertical IS NOT NULL ORDER BY primary_vertical""")]
    regions = [r[0] for r in con.execute("""SELECT DISTINCT hq_region FROM companies
             WHERE has_profile = 1 AND hq_region IS NOT NULL ORDER BY hq_region""")]
    cats = [r[0] for r in con.execute("SELECT DISTINCT category FROM market_signals ORDER BY category")]
    con.close()
    return jsonify({"months": [{"value": m, "label": MONTH_LABEL[m]} for m in MONTHS], "latest": "2026-11",
                    "firms": firms, "industries": verticals, "regions": regions, "categories": cats,
                    "priorities": ["Critical", "High", "Medium", "Low"],
                    "coverage": "Snapshots Apr-Nov 2026; news published Apr-Oct 2026"})

@app.get("/api/data-notes")
def data_notes():
    report_path = DB.with_suffix(".build_report.json")
    stats = {}
    if report_path.exists():
        stats = json.loads(report_path.read_text(encoding="utf-8")).get("stats", {})
    return jsonify({"caveats": DATA_CAVEATS, "build_stats": stats})

# ---------------------------------------------------------------- 01 Executive overview
def build_overview(f, con):
    where, params = f.link_where()
    firm_sql, firm_params = f.firm_clause("pe.id")
    k = {}
    k["targeted_firms"] = con.execute(f"SELECT COUNT(*) FROM pe_firms pe WHERE in_account_list=1 AND {firm_sql}", firm_params).fetchone()[0]
    k["matched_accounts"] = con.execute(f"""SELECT COUNT(DISTINCT l.firm_id) FROM firm_portfolio_links l JOIN companies c ON c.id=l.company_id
        JOIN pe_firms pe ON pe.id=l.firm_id WHERE pe.in_account_list=1 AND {where}""", params).fetchone()[0]
    k["portfolio_companies"] = con.execute(f"""SELECT COUNT(DISTINCT l.company_id) FROM firm_portfolio_links l
        JOIN companies c ON c.id=l.company_id WHERE {where}""", params).fetchone()[0]
    k["detailed_profiles"] = con.execute(f"""SELECT COUNT(DISTINCT l.company_id) FROM firm_portfolio_links l
        JOIN companies c ON c.id=l.company_id WHERE {where} AND (','||c.profile_months||',') LIKE ?""",
        params + [f"%,{f.month},%"]).fetchone()[0]
    k["industries_covered"] = con.execute(f"""SELECT COUNT(DISTINCT c.primary_vertical) FROM firm_portfolio_links l
        JOIN companies c ON c.id=l.company_id WHERE {where} AND c.primary_vertical IS NOT NULL""", params).fetchone()[0]
    k["companies_with_it_spend"] = con.execute(f"""SELECT COUNT(DISTINCT cf.company_id) FROM company_financials cf
        JOIN firm_portfolio_links l ON l.company_id=cf.company_id AND l.reporting_month=cf.reporting_month
        JOIN companies c ON c.id=l.company_id WHERE cf.metric='it_spend' AND {where}""", params).fetchone()[0]
    k["companies_with_revenue"] = con.execute(f"""SELECT COUNT(DISTINCT cf.company_id) FROM company_financials cf
        JOIN firm_portfolio_links l ON l.company_id=cf.company_id AND l.reporting_month=cf.reporting_month
        JOIN companies c ON c.id=l.company_id WHERE cf.metric='revenue' AND {where}""", params).fetchone()[0]
    sig_where, sig_params = signal_scope(f, None, None, None, None)
    k["unique_market_signals"] = con.execute(f"SELECT COUNT(*) FROM market_signals s WHERE {sig_where}", sig_params).fetchone()[0]
    stk_where, stk_params = stakeholder_scope(f)
    k["verified_stakeholders"] = con.execute(f"SELECT COUNT(*) FROM stakeholders s WHERE verification_status='Confirmed' AND {stk_where}", stk_params).fetchone()[0]
    opp_where, opp_params = opportunity_scope(f)
    k["high_priority_opportunities"] = con.execute(f"""SELECT COUNT(*) FROM opportunities o LEFT JOIN companies c ON c.id=o.company_id
        WHERE o.priority IN ('Critical','High') AND {opp_where}""", opp_params).fetchone()[0]
    # trends across all snapshot months (respects firm / industry / region filters)
    trend = []
    for m in MONTHS:
        g = F({"month": m, "firm": ",".join(map(str, f.firms)), "industry": "|".join(f.industries), "region": "|".join(f.regions)})
        w, p = g.link_where()
        trend.append({"month": m, "label": MONTH_LABEL[m], "portfolio_companies": con.execute(f"""SELECT COUNT(DISTINCT l.company_id) FROM firm_portfolio_links l
            JOIN companies c ON c.id=l.company_id WHERE {w}""", p).fetchone()[0],
            "profiled_companies": con.execute(f"""SELECT COUNT(DISTINCT l.company_id) FROM firm_portfolio_links l JOIN companies c ON c.id=l.company_id
            WHERE {w} AND (','||c.profile_months||',') LIKE ?""", p + [f"%,{m},%"]).fetchone()[0]})
    signal_trend = [dict(r) for r in con.execute(f"""SELECT s.publication_month AS month, COUNT(*) AS signals FROM market_signals s
        WHERE {sig_where} AND s.publication_month IS NOT NULL GROUP BY 1 ORDER BY 1""", sig_params)]
    for r in signal_trend: r["label"] = MONTH_LABEL.get(r["month"], r["month"])
    priority_dist = [dict(r) for r in con.execute(f"""SELECT o.priority, COUNT(*) n FROM opportunities o LEFT JOIN companies c ON c.id=o.company_id
        WHERE {opp_where} GROUP BY o.priority""", opp_params)]
    industry = [dict(r) for r in con.execute(f"""SELECT c.primary_vertical AS name, COUNT(DISTINCT l.company_id) AS companies
        FROM firm_portfolio_links l JOIN companies c ON c.id=l.company_id WHERE {where} AND c.primary_vertical IS NOT NULL
        GROUP BY 1 ORDER BY 2 DESC LIMIT 10""", params)]
    firm_rank = [dict(r) for r in con.execute(f"""SELECT pe.id, pe.canonical_name AS name, COUNT(DISTINCT l.company_id) AS companies
        FROM firm_portfolio_links l JOIN companies c ON c.id=l.company_id JOIN pe_firms pe ON pe.id=l.firm_id
        WHERE pe.in_account_list=1 AND {where}
        GROUP BY pe.id ORDER BY 3 DESC LIMIT 10""", params)]
    return k, trend, signal_trend, priority_dist, industry, firm_rank

@app.get("/api/overview")
def overview():
    f = F(request.args)
    con = db()
    k, trend, signal_trend, priority_dist, industry, firm_rank = build_overview(f, con)
    narrative = build_narrative(f, con, k, trend, signal_trend, priority_dist, industry, firm_rank)
    con.close()
    kpi_defs = {
        "targeted_firms": "PE firms in the targeted account list (44). Matched to snapshot month.",
        "matched_accounts": "Targeted firms with at least one portfolio company in the selected snapshot.",
        "portfolio_companies": "Unique companies linked to a targeted firm in the selected snapshot.",
        "detailed_profiles": "Portfolio companies that have a full dashboard profile in the selected snapshot.",
        "unique_market_signals": "Unique news items, de-duplicated across workbooks. Publication months Apr-Oct 2026.",
        "industries_covered": "Distinct primary verticals among snapshot portfolio companies.",
        "verified_stakeholders": "Stakeholders with status Confirmed in the 9 Sep 2026 verification file.",
        "high_priority_opportunities": "Critical or High hypotheses, scored 70 and above. Hypotheses only.",
        "companies_with_it_spend": "Snapshot companies with reported IT spend in the selected month.",
        "companies_with_revenue": "Snapshot companies with reported revenue in the selected month.",
    }
    return jsonify({"month": f.month, "kpis": k, "kpi_definitions": kpi_defs, "trend": trend,
                    "signal_trend": signal_trend, "priority_distribution": priority_dist,
                    "industry_concentration": industry, "firm_ranking": firm_rank, "narrative": narrative})

def build_narrative(f, con, k, trend, signal_trend, priority_dist, industry, firm_rank):
    """Deterministic, data-driven executive narrative. Every figure is computed from the database."""
    m_label = MONTH_LABEL[f.month]
    sig_w, sig_p = signal_scope(f, None, None, None, None)
    total_sig = sum(s["signals"] for s in signal_trend)
    top_cat = con.execute(f"SELECT category, COUNT(*) n FROM market_signals s WHERE {sig_w} GROUP BY category ORDER BY n DESC LIMIT 3", sig_p).fetchall()
    cat_counts = {r["category"]: r["n"] for r in con.execute(f"SELECT category, COUNT(*) n FROM market_signals s WHERE {sig_w} GROUP BY category", sig_p)}
    crit = next((p["n"] for p in priority_dist if p["priority"] == "Critical"), 0)
    high = next((p["n"] for p in priority_dist if p["priority"] == "High"), 0)
    top_firm = firm_rank[0] if firm_rank else None
    top_ind = industry[0] if industry else None
    pe_news = con.execute(f"SELECT COUNT(*) FROM market_signals s WHERE {sig_w} AND s.scope='PE'", sig_p).fetchone()[0]
    ma = cat_counts.get("Mergers and Acquisitions", 0)
    fund = cat_counts.get("Fundraise and Investments", 0)
    exec_moves = cat_counts.get("Executive Movement", 0)
    gcc = cat_counts.get("Center Setup and Expansion", 0)
    layoffs = cat_counts.get("Layoff", 0)
    hiring = cat_counts.get("Mass Hiring", 0)
    first, last = trend[0], trend[-1]
    confirmed_firms = con.execute("""SELECT COUNT(DISTINCT s.firm_id) FROM stakeholders s JOIN pe_firms f ON f.id=s.firm_id
        WHERE s.verification_status='Confirmed' AND f.in_account_list=1""").fetchone()[0]
    targeted_with_stake = con.execute("""SELECT COUNT(DISTINCT s.firm_id) FROM stakeholders s JOIN pe_firms f ON f.id=s.firm_id
        WHERE f.in_account_list=1""").fetchone()[0]
    non_list_firms = con.execute("""SELECT COUNT(DISTINCT s.firm_id) FROM stakeholders s JOIN pe_firms f ON f.id=s.firm_id
        WHERE f.in_account_list=0""").fetchone()[0]
    lead_firms = con.execute(f"""SELECT pe.canonical_name AS name, SUM(CASE WHEN o.priority IN ('Critical','High') THEN 1 ELSE 0 END) AS hp,
        COUNT(*) AS total, SUM(CASE WHEN o.confirmed_stakeholder_count>0 THEN 1 ELSE 0 END) AS confirmed_led
        FROM opportunities o JOIN pe_firms pe ON pe.id=o.firm_id LEFT JOIN companies c ON c.id=o.company_id
        WHERE {opportunity_scope(f)[0]} GROUP BY pe.id ORDER BY hp DESC, total DESC LIMIT 3""", opportunity_scope(f)[1]).fetchall()
    lead_inds = con.execute(f"""SELECT c.primary_vertical AS name, COUNT(*) AS n FROM opportunities o JOIN companies c ON c.id=o.company_id
        WHERE o.priority IN ('Critical','High') AND {opportunity_scope(f)[0]} AND c.primary_vertical IS NOT NULL
        GROUP BY 1 ORDER BY 2 DESC LIMIT 3""", opportunity_scope(f)[1]).fetchall()
    outreach_recorded = con.execute("SELECT COUNT(*) FROM stakeholders WHERE initial_outreach_date IS NOT NULL").fetchone()[0]
    review = con.execute("SELECT COUNT(*) FROM stakeholders WHERE verification_status<>'Confirmed'").fetchone()[0]
    sec = []
    sec.append({"title": "A. Executive intelligence assessment", "paragraphs": [
        f"The platform covers {k['targeted_firms']} targeted PE firms. In the {m_label} snapshot, {k['matched_accounts']} of them have at least one portfolio company, "
        f"and those firms link to {k['portfolio_companies']:,} unique companies. {k['detailed_profiles']:,} of those companies have a detailed dashboard profile, "
        f"which is {round(100 * k['detailed_profiles'] / max(1, k['portfolio_companies']))}% of the snapshot.",
        f"Captured news totals {total_sig:,} unique items published between April and October 2026. Of these, {pe_news:,} are PE-level and the rest concern portfolio companies. "
        f"Stakeholder records exist for {targeted_with_stake} of the {k['targeted_firms']} targeted firms, and {k['verified_stakeholders']} stakeholders are confirmed "
        f"({confirmed_firms} targeted firms have at least one confirmed contact). The verification dates from 4 September. {non_list_firms} stakeholder firms sit outside the targeted list and are labelled.",
        "Coverage is uneven. The 30 April workbook has no signal sheets, so April news appears only in the 18 May workbook. Financial coverage is thin: "
        f"{k['companies_with_revenue']} companies report revenue this month, so the platform shows gaps as 'Not reported' rather than zero."]})
    sec.append({"title": "B. What has changed?", "paragraphs": [
        f"Portfolio coverage moved from {first['portfolio_companies']:,} companies in {first['label']} to {last['portfolio_companies']:,} in {last['label']} "
        f"within the selected filters. Profiled companies moved from {first['profiled_companies']:,} to {last['profiled_companies']:,}, "
        "so detailed coverage and raw portfolio size do not always move together.",
        "Most captured news in the view: " + "; ".join(f"{r['category']} ({r['n']:,})" for r in top_cat) + ".",
        f"Fundraising ({fund:,}) and M&A ({ma:,}) items lead the deal-related news. Centre set-ups ({gcc:,}), executive moves ({exec_moves:,}), "
        f"mass hiring ({hiring:,}) and layoffs ({layoffs:,}) are smaller but more directly relevant to delivery and operating-model work."]})
    sec.append({"title": "C. Strategic account priorities", "paragraphs": [
        (f"{top_firm['name']} has the largest snapshot portfolio in view, with {top_firm['companies']:,} companies. Scale alone does not signal need, so use the "
         "priority ranking below to decide where to start.") if top_firm else "No targeted firm matches the current filters.",
        "Firms with the most Critical or High hypotheses: " + "; ".join(f"{r['name']} ({r['hp']:,} of {r['total']:,})" for r in lead_firms) + "." if lead_firms else "No hypotheses match the current filters.",
        f"The model flags {crit:,} Critical and {high:,} High hypotheses. Check the triggering news before any outreach."]})
    sec.append({"title": "D. Portfolio-level business developments", "paragraphs": [
        "Captured news covers financing, M&A, executive moves, centre set-ups, product launches and layoffs. Each item links to its source. "
        "A news item is not a confirmed transaction, and deal values appear only where the source reports them.",
        f"In this view, {cat_counts.get('New Product Development and Product Launch', 0):,} items concern product development or launches. "
        "These are useful for product-engineering and AI conversations but do not on their own show a buying decision."]})
    sec.append({"title": "E. Zinnov opportunity assessment", "paragraphs": [
        (f"The largest concentration of portfolio companies is in {top_ind['name']} ({top_ind['companies']:,} companies). " if top_ind else "")
        + "Opportunities map to Zinnov capabilities such as commercial due diligence, Global Capability Centres, cost optimisation and digital product engineering.",
        ("Critical and High hypotheses cluster in: " + "; ".join(f"{r['name']} ({r['n']:,})" for r in lead_inds) + ".") if lead_inds else "",
        "These are analytical hypotheses. They are not confirmed client requirements, budgets or pipeline."]})
    sec.append({"title": "F. Recommended leadership actions", "paragraphs": [
        "1. Review the Critical and High hypotheses for firms with confirmed stakeholders first, starting with the firms listed in section C.",
        "2. Open each triggering news item at its source and confirm the event before any outreach.",
        f"3. Re-verify the {review} stakeholders who are not Confirmed (Left Organization or Title Changed) before relying on them.",
        f"4. Note that {outreach_recorded} stakeholders carry an outreach date. Confirm whether those dates reflect real engagement before reporting it."]})
    return [dict(s, paragraphs=[p for p in s["paragraphs"] if p]) for s in sec]

# ---------------------------------------------------------------- scopes shared by modules
def signal_scope(f, date_from, date_to, category, q, scope=None):
    """Filters for market_signals. Firm filter: PE news for the firm plus news for its current portfolio.
    Industry or region filters apply to portfolio news only (PE-level news has no vertical)."""
    parts, params = ["1=1"], []
    narrow = bool(f.industries or f.regions)
    if scope:
        parts.append("s.scope = ?"); params.append(scope)
    if narrow:
        parts.append("s.scope = 'PORTFOLIO'")
    if f.firms:
        pe_part = f"(s.scope='PE' AND s.firm_id IN ({ql(f.firms)}))"
        port_part = (f"(s.scope='PORTFOLIO' AND s.company_id IN (SELECT company_id FROM firm_portfolio_links "
                     f"WHERE reporting_month=? AND firm_id IN ({ql(f.firms)})))")
        parts.append(f"({pe_part if not narrow else '0'} OR {port_part})" if not narrow else port_part)
        params += (list(f.firms) if not narrow else []) + [f.month] + list(f.firms)
    if f.industries:
        parts.append(f"s.company_id IN (SELECT id FROM companies WHERE primary_vertical IN ({ql(f.industries)}))")
        params += f.industries
    if f.regions:
        parts.append(f"s.company_id IN (SELECT id FROM companies WHERE hq_region IN ({ql(f.regions)}))")
        params += f.regions
    if date_from:
        parts.append("s.publication_month >= ?"); params.append(date_from)
    if date_to:
        parts.append("s.publication_month <= ?"); params.append(date_to)
    if category:
        parts.append("s.category = ?"); params.append(category)
    if q:
        parts.append("(lower(s.news_title) LIKE ? OR lower(coalesce(s.news_description,'')) LIKE ? OR lower(s.company_name) LIKE ?)")
        term = search_like(q); params += [term, term, term]
    return " AND ".join(parts), params

def stakeholder_scope(f, status=None, flags=None):
    parts, params = ["1=1"], []
    if f.firms:
        parts.append(f"s.firm_id IN ({ql(f.firms)})"); params += f.firms
    if status:
        parts.append("s.verification_status = ?"); params.append(status)
    for fl in flags or []:
        parts.append(f"s.{fl} = 1")
    return " AND ".join(parts), params

def opportunity_scope(f, priority=None, capability=None):
    parts, params = ["1=1"], []
    if f.firms:
        parts.append(f"o.firm_id IN ({ql(f.firms)})"); params += f.firms
    if f.industries:
        parts.append(f"c.primary_vertical IN ({ql(f.industries)})"); params += f.industries
    if f.regions:
        parts.append(f"c.hq_region IN ({ql(f.regions)})"); params += f.regions
    if priority:
        parts.append("o.priority = ?"); params.append(priority)
    if capability:
        parts.append("o.capability = ?"); params.append(capability)
    return " AND ".join(parts), params

# ---------------------------------------------------------------- 02 PE account intelligence
@app.get("/api/accounts")
def accounts():
    f = F(request.args)
    con = db()
    page, size = page_args(request.args)
    fw, fp = f.firm_clause("pe.id")
    q = request.args.get("q", "").strip()
    qsql, qp = ("AND lower(pe.canonical_name) LIKE ?", [search_like(q)]) if q else ("", [])
    link_w, link_p = f.link_where()
    base = f"""FROM pe_firms pe
        LEFT JOIN pe_account_snapshots snap ON snap.firm_id=pe.id AND snap.reporting_month=?
        WHERE pe.in_account_list=1 AND {fw} {qsql}"""
    rows_sql = f"""SELECT pe.id, pe.canonical_name AS firm, snap.status AS account_status,
        (SELECT COUNT(DISTINCT l.company_id) FROM firm_portfolio_links l JOIN companies c ON c.id=l.company_id
           WHERE l.firm_id=pe.id AND l.reporting_month=?) AS portfolio_companies,
        (SELECT COUNT(DISTINCT l.company_id) FROM firm_portfolio_links l JOIN companies c ON c.id=l.company_id
           WHERE l.firm_id=pe.id AND l.reporting_month=? AND (','||c.profile_months||',') LIKE ?) AS matched_profiles,
        (SELECT COUNT(*) FROM market_signals s WHERE s.scope='PE' AND s.firm_id=pe.id) AS pe_signals,
        (SELECT COUNT(*) FROM stakeholders st WHERE st.firm_id=pe.id) AS stakeholders,
        (SELECT COUNT(*) FROM opportunities o WHERE o.firm_id=pe.id) AS opportunities,
        (SELECT COUNT(*) FROM opportunities o WHERE o.firm_id=pe.id AND o.priority IN ('Critical','High')) AS high_priority,
        (SELECT MAX(reporting_month) FROM firm_portfolio_links l WHERE l.firm_id=pe.id) AS latest_period
        {base}"""
    sort_map = {"firm": "firm", "account_status": "account_status", "portfolio_companies": "portfolio_companies",
                "matched_profiles": "matched_profiles", "pe_signals": "pe_signals", "stakeholders": "stakeholders",
                "opportunities": "opportunities", "high_priority": "high_priority", "latest_period": "latest_period"}
    order = sort_clause(request.args, {k: v for k, v in sort_map.items()}, "portfolio_companies", "pe.id")
    params = [f.month, f.month, f.month, f"%,{f.month},%"] + fp + qp
    total = con.execute(f"SELECT COUNT(*) {base}", [f.month] + fp + qp).fetchone()[0]
    if request.args.get("format") == "csv":
        rows = [dict(r) for r in con.execute(rows_sql + " " + order, params)]
        con.close(); return respond_list(rows, total, 1, total)
    rows = [dict(r) for r in con.execute(rows_sql + " " + order + " LIMIT ? OFFSET ?", params + [size, (page - 1) * size])]
    for r in rows:
        r["latest_period_label"] = MONTH_LABEL.get(r["latest_period"], "-") if r["latest_period"] else "-"
    con.close()
    return respond_list(rows, total, page, size)

@app.get("/api/accounts/<int:firm_id>")
def account_profile(firm_id):
    f = F(request.args)
    con = db()
    firm = con.execute("SELECT * FROM pe_firms WHERE id=?", (firm_id,)).fetchone()
    if not firm: abort(404)
    history = [dict(r) for r in con.execute("""SELECT reporting_month AS month, status, portfolio_count FROM pe_account_snapshots
        WHERE firm_id=? ORDER BY reporting_month""", (firm_id,))]
    for h in history: h["label"] = MONTH_LABEL.get(h["month"], h["month"])
    companies = [dict(r) for r in con.execute("""SELECT c.id, c.display_name AS name, c.primary_vertical AS industry,
        c.hq_region AS region, c.has_profile, l.platform_status FROM firm_portfolio_links l JOIN companies c ON c.id=l.company_id
        WHERE l.firm_id=? AND l.reporting_month=? ORDER BY c.display_name LIMIT 300""", (firm_id, f.month))]
    industries = [dict(r) for r in con.execute("""SELECT c.primary_vertical AS name, COUNT(*) n FROM firm_portfolio_links l
        JOIN companies c ON c.id=l.company_id WHERE l.firm_id=? AND l.reporting_month=? AND c.primary_vertical IS NOT NULL
        GROUP BY 1 ORDER BY 2 DESC LIMIT 8""", (firm_id, f.month))]
    regions = [dict(r) for r in con.execute("""SELECT c.hq_region AS name, COUNT(*) n FROM firm_portfolio_links l
        JOIN companies c ON c.id=l.company_id WHERE l.firm_id=? AND l.reporting_month=? AND c.hq_region IS NOT NULL
        GROUP BY 1 ORDER BY 2 DESC LIMIT 8""", (firm_id, f.month))]
    fin = con.execute("""SELECT SUM(CASE WHEN cf.metric='revenue' THEN cf.value_usd_mm END) AS revenue,
        SUM(CASE WHEN cf.metric='it_spend' THEN cf.value_usd_mm END) AS it_spend,
        COUNT(DISTINCT CASE WHEN cf.metric='revenue' THEN cf.company_id END) AS rev_n,
        COUNT(DISTINCT CASE WHEN cf.metric='it_spend' THEN cf.company_id END) AS it_n
        FROM firm_portfolio_links l JOIN company_financials cf ON cf.company_id=l.company_id AND cf.reporting_month=l.reporting_month
        WHERE l.firm_id=? AND l.reporting_month=? AND cf.fiscal_year=(SELECT MAX(fiscal_year) FROM company_financials WHERE reporting_month=l.reporting_month)""",
        (firm_id, f.month)).fetchone()
    pe_signals = [dict(r) for r in con.execute("""SELECT id, news_title AS title, category, publication_month, publication_date, news_url AS url
        FROM market_signals WHERE scope='PE' AND firm_id=? ORDER BY publication_date DESC LIMIT 25""", (firm_id,))]
    portfolio_signal_count = con.execute("""SELECT COUNT(*) FROM market_signals s WHERE s.scope='PORTFOLIO' AND s.company_id IN
        (SELECT company_id FROM firm_portfolio_links WHERE firm_id=? AND reporting_month=?)""", (firm_id, f.month)).fetchone()[0]
    stakeholders = [dict(r) for r in con.execute("""SELECT id, name, designation, verification_status, confidence FROM stakeholders
        WHERE firm_id=? ORDER BY verification_status, name""", (firm_id,))]
    opps = [dict(r) for r in con.execute("""SELECT o.id, o.capability, o.score, o.priority, c.display_name AS company
        FROM opportunities o LEFT JOIN companies c ON c.id=o.company_id WHERE o.firm_id=? ORDER BY o.score DESC LIMIT 15""", (firm_id,))]
    con.close()
    return jsonify({"firm": dict(firm), "history": history, "companies": companies, "industries": industries,
                    "regions": regions, "financials": {"revenue_usd_mm": fin["revenue"], "it_spend_usd_mm": fin["it_spend"],
                    "companies_with_revenue": fin["rev_n"], "companies_with_it_spend": fin["it_n"]},
                    "pe_signals": pe_signals, "portfolio_signal_count": portfolio_signal_count,
                    "stakeholders": stakeholders, "top_opportunities": opps,
                    "month": f.month, "month_label": MONTH_LABEL[f.month]})

# ---------------------------------------------------------------- 03 Portfolio intelligence
@app.get("/api/portfolio/summary")
def portfolio_summary():
    f = F(request.args)
    con = db()
    where, params = f.link_where()
    base = f"FROM firm_portfolio_links l JOIN companies c ON c.id=l.company_id WHERE {where}"
    k = {
        "unique_companies": con.execute(f"SELECT COUNT(DISTINCT l.company_id) {base}", params).fetchone()[0],
        "matched_links": con.execute(f"SELECT COUNT(*) {base} AND l.platform_status IS NOT NULL", params).fetchone()[0],
        "unmatched_links": con.execute(f"SELECT COUNT(*) {base} AND l.platform_status IS NULL", params).fetchone()[0],
        "detailed_profiles": con.execute(f"SELECT COUNT(DISTINCT l.company_id) {base} AND (','||c.profile_months||',') LIKE ?", params + [f"%,{f.month},%"]).fetchone()[0],
        "with_signals": con.execute(f"""SELECT COUNT(DISTINCT l.company_id) {base} AND l.company_id IN
            (SELECT company_id FROM market_signals WHERE scope='PORTFOLIO' AND company_id IS NOT NULL)""", params).fetchone()[0],
        "with_revenue": con.execute(f"""SELECT COUNT(DISTINCT l.company_id) {base} AND l.company_id IN
            (SELECT company_id FROM company_financials WHERE metric='revenue' AND reporting_month=?)""", params + [f.month]).fetchone()[0],
        "with_it_spend": con.execute(f"""SELECT COUNT(DISTINCT l.company_id) {base} AND l.company_id IN
            (SELECT company_id FROM company_financials WHERE metric='it_spend' AND reporting_month=?)""", params + [f.month]).fetchone()[0],
    }
    industry = [dict(r) for r in con.execute(f"""SELECT COALESCE(c.primary_vertical,'Not recorded') AS name, COUNT(DISTINCT l.company_id) AS n
        {base} GROUP BY 1 ORDER BY 2 DESC LIMIT 12""", params)]
    region = [dict(r) for r in con.execute(f"""SELECT COALESCE(c.hq_region,'Not recorded') AS name, COUNT(DISTINCT l.company_id) AS n
        {base} GROUP BY 1 ORDER BY 2 DESC""", params)]
    firm_cov = [dict(r) for r in con.execute(f"""SELECT pe.canonical_name AS name, COUNT(DISTINCT l.company_id) AS n
        FROM firm_portfolio_links l JOIN companies c ON c.id=l.company_id JOIN pe_firms pe ON pe.id=l.firm_id
        WHERE pe.in_account_list=1 AND {where} GROUP BY pe.id ORDER BY 2 DESC LIMIT 15""", params)]
    scatter = [dict(r) for r in con.execute(f"""SELECT c.id, c.display_name AS name,
        (SELECT value_usd_mm FROM company_financials cf WHERE cf.company_id=c.id AND cf.metric='revenue' AND cf.reporting_month=?
           ORDER BY fiscal_year DESC LIMIT 1) AS revenue,
        (SELECT value_usd_mm FROM company_financials cf WHERE cf.company_id=c.id AND cf.metric='it_spend' AND cf.reporting_month=?
           ORDER BY fiscal_year DESC LIMIT 1) AS it_spend
        FROM companies c WHERE c.id IN (SELECT DISTINCT l.company_id {base}) LIMIT 3000""", [f.month, f.month] + params)]
    scatter = [s for s in scatter if s["revenue"] and s["it_spend"]]
    trend = []
    for m in MONTHS:
        g = F({"month": m, "firm": ",".join(map(str, f.firms)), "industry": "|".join(f.industries), "region": "|".join(f.regions)})
        w, p = g.link_where()
        trend.append({"month": m, "label": MONTH_LABEL[m], "companies": con.execute(f"""SELECT COUNT(DISTINCT l.company_id)
            FROM firm_portfolio_links l JOIN companies c ON c.id=l.company_id WHERE {w}""", p).fetchone()[0]})
    con.close()
    return jsonify({"month": f.month, "kpis": k, "industry": industry, "region": region, "firm_coverage": firm_cov,
                    "revenue_it_scatter": scatter, "trend": trend})

@app.get("/api/portfolio")
def portfolio():
    f = F(request.args)
    con = db()
    page, size = page_args(request.args)
    where, params = f.link_where()
    q = request.args.get("q", "").strip()
    qsql, qp = ("AND (lower(c.display_name) LIKE ? OR lower(coalesce(c.domain,'')) LIKE ?)", [search_like(q), search_like(q)]) if q else ("", [])
    base = f"""FROM firm_portfolio_links l JOIN companies c ON c.id=l.company_id JOIN pe_firms pe ON pe.id=l.firm_id
        WHERE {where} {qsql}"""
    sel = f"""SELECT c.id, c.display_name AS company, GROUP_CONCAT(DISTINCT pe.canonical_name) AS pe_firms,
        COUNT(DISTINCT l.firm_id) AS firm_count, c.primary_vertical AS industry, c.sub_vertical AS sub_industry,
        c.hq_location AS headquarters, c.hq_country AS country, c.hq_region AS region, c.company_type,
        (SELECT value_usd_mm FROM company_financials cf WHERE cf.company_id=c.id AND cf.metric='revenue' AND cf.reporting_month=? ORDER BY fiscal_year DESC LIMIT 1) AS revenue_usd_mm,
        (SELECT value_usd_mm FROM company_financials cf WHERE cf.company_id=c.id AND cf.metric='it_spend' AND cf.reporting_month=? ORDER BY fiscal_year DESC LIMIT 1) AS it_spend_usd_mm,
        CASE WHEN (','||c.profile_months||',') LIKE ? THEN 'Profiled' ELSE 'Not profiled' END AS match_status,
        (SELECT COUNT(*) FROM market_signals s WHERE s.company_id=c.id AND s.scope='PORTFOLIO') AS signal_count,
        (SELECT o.priority FROM opportunities o WHERE o.company_id=c.id ORDER BY o.score DESC LIMIT 1) AS opportunity_priority
        {base} GROUP BY c.id"""
    sort_map = {"company": "company", "industry": "industry", "revenue_usd_mm": "revenue_usd_mm",
                "it_spend_usd_mm": "it_spend_usd_mm", "signal_count": "signal_count", "firm_count": "firm_count",
                "opportunity_priority": "opportunity_priority"}
    order = sort_clause(request.args, sort_map, "company", "c.id")
    params_all = [f.month, f.month, f"%,{f.month},%"] + params + qp
    total = con.execute(f"SELECT COUNT(*) FROM (SELECT c.id {base} GROUP BY c.id)", params + qp).fetchone()[0]
    if request.args.get("format") == "csv":
        rows = [dict(r) for r in con.execute(sel + " " + order, params_all)]
    else:
        rows = [dict(r) for r in con.execute(sel + " " + order + " LIMIT ? OFFSET ?", params_all + [size, (page - 1) * size])]
    con.close()
    return respond_list(rows, total, page, size)

@app.get("/api/portfolio/<int:company_id>")
def company_profile(company_id):
    con = db()
    c = con.execute("SELECT * FROM companies WHERE id=?", (company_id,)).fetchone()
    if not c: abort(404)
    c = dict(c)
    assoc = [dict(r) for r in con.execute("""SELECT pe.canonical_name AS pe_firm, pe.id AS firm_id, l.reporting_month AS month,
        l.shortlisted_name, l.platform_status FROM firm_portfolio_links l JOIN pe_firms pe ON pe.id=l.firm_id
        WHERE l.company_id=? ORDER BY l.reporting_month DESC, pe.canonical_name""", (company_id,))]
    fin = [dict(r) for r in con.execute("""SELECT reporting_month AS month, fiscal_year, metric, value_usd_mm
        FROM company_financials WHERE company_id=? ORDER BY reporting_month, fiscal_year, metric""", (company_id,))]
    latest_rev = next((r for r in sorted(fin, key=lambda x: (x["month"], x["fiscal_year"]), reverse=True) if r["metric"] == "revenue"), None)
    latest_it = next((r for r in sorted(fin, key=lambda x: (x["month"], x["fiscal_year"]), reverse=True) if r["metric"] == "it_spend"), None)
    it_pct = None
    if latest_rev and latest_it and latest_rev["value_usd_mm"] and latest_it["fiscal_year"] == latest_rev["fiscal_year"]:
        it_pct = round(100 * latest_it["value_usd_mm"] / latest_rev["value_usd_mm"], 1)
    signals = [dict(r) for r in con.execute("""SELECT s.id, s.news_title AS title, s.category, s.publication_month, s.publication_date, s.news_url AS url
        FROM market_signals s WHERE s.company_id=? AND s.scope='PORTFOLIO' ORDER BY s.publication_date DESC LIMIT 40""", (company_id,))]
    opps = [dict(r) for r in con.execute("""SELECT o.id, pe.canonical_name AS pe_firm, o.capability, o.score, o.priority, o.evidence_confidence
        FROM opportunities o JOIN pe_firms pe ON pe.id=o.firm_id WHERE o.company_id=? ORDER BY o.score DESC LIMIT 20""", (company_id,))]
    con.close()
    return jsonify({"company": c, "associations": assoc, "financials": fin,
                    "latest_revenue_usd_mm": latest_rev["value_usd_mm"] if latest_rev else None,
                    "latest_revenue_year": latest_rev["fiscal_year"] if latest_rev else None,
                    "latest_it_spend_usd_mm": latest_it["value_usd_mm"] if latest_it else None,
                    "latest_it_spend_year": latest_it["fiscal_year"] if latest_it else None,
                    "it_spend_pct_of_revenue": it_pct, "signals": signals, "opportunities": opps})

# ---------------------------------------------------------------- 04 Market signals
@app.get("/api/signals/summary")
def signals_summary():
    f = F(request.args)
    con = db()
    w, p = signal_scope(f, request.args.get("from"), request.args.get("to"), None, None)
    k = {
        "unique_signals": con.execute(f"SELECT COUNT(*) FROM market_signals s WHERE {w}", p).fetchone()[0],
        "pe_firm_signals": con.execute(f"SELECT COUNT(*) FROM market_signals s WHERE {w} AND s.scope='PE'", p).fetchone()[0],
        "portfolio_signals": con.execute(f"SELECT COUNT(*) FROM market_signals s WHERE {w} AND s.scope='PORTFOLIO'", p).fetchone()[0],
        "companies_with_signals": con.execute(f"SELECT COUNT(DISTINCT s.company_id) FROM market_signals s WHERE {w} AND s.company_id IS NOT NULL", p).fetchone()[0],
    }
    categories = [dict(r) for r in con.execute(f"SELECT s.category AS name, COUNT(*) n FROM market_signals s WHERE {w} GROUP BY 1 ORDER BY 2 DESC", p)]
    by_pub = [dict(r) for r in con.execute(f"""SELECT s.publication_month AS month, COUNT(*) AS publications FROM market_signals s
        WHERE {w} GROUP BY 1 ORDER BY 1""", p)]
    obs = [dict(r) for r in con.execute(f"""SELECT o.reporting_month AS month, COUNT(DISTINCT o.signal_id) AS in_workbook
        FROM signal_observations o JOIN market_signals s ON s.id=o.signal_id WHERE {w} GROUP BY 1 ORDER BY 1""", p)]
    for r in by_pub + obs: r["label"] = MONTH_LABEL.get(r["month"], r["month"])
    latest = [dict(r) for r in con.execute(f"""SELECT s.id, s.news_title AS title, s.company_name AS company, s.category,
        s.publication_date, s.scope FROM market_signals s WHERE {w} ORDER BY s.publication_date DESC LIMIT 8""", p)]
    con.close()
    return jsonify({"kpis": k, "categories": categories, "publication_trend": by_pub, "workbook_trend": obs,
                    "latest": latest, "note": "Publication months are shown from row dates. Reporting months are workbook months."})

@app.get("/api/signals")
def signals():
    f = F(request.args)
    con = db()
    page, size = page_args(request.args)
    w, p = signal_scope(f, request.args.get("from"), request.args.get("to"), request.args.get("category") or None,
                        request.args.get("q", "").strip() or None, request.args.get("scope") or None)
    base = f"""FROM market_signals s LEFT JOIN pe_firms pe ON pe.id=s.firm_id LEFT JOIN companies c ON c.id=s.company_id
        LEFT JOIN signal_observations so ON so.signal_id=s.id WHERE {w}"""
    sort_map = {"publication_date": "s.publication_date", "company": "s.company_name", "category": "s.category", "title": "s.news_title"}
    order = sort_clause(request.args, sort_map, "publication_date", "s.id")
    if "dir" not in request.args and "sort" not in request.args: order = "ORDER BY s.publication_date DESC, s.id ASC"
    sel = f"""SELECT s.id, s.scope, s.news_title AS title, s.news_description AS description, s.company_name AS company,
        COALESCE(pe.canonical_name, '') AS pe_firm, c.primary_vertical AS industry, s.category, s.publication_date,
        s.publication_month, s.news_url AS source_url, GROUP_CONCAT(DISTINCT so.reporting_month) AS observed_in_workbooks
        {base} GROUP BY s.id"""
    total = con.execute(f"SELECT COUNT(DISTINCT s.id) {base}", p).fetchone()[0]
    if request.args.get("format") == "csv":
        rows = [dict(r) for r in con.execute(sel + " " + order, p)]
    else:
        rows = [dict(r) for r in con.execute(sel + " " + order + " LIMIT ? OFFSET ?", p + [size, (page - 1) * size])]
    con.close()
    return respond_list(rows, total, page, size)

@app.get("/api/signals/<int:signal_id>")
def signal_detail(signal_id):
    con = db()
    s = con.execute("""SELECT s.*, pe.canonical_name AS pe_firm, c.display_name AS company_profile_name, c.primary_vertical AS industry
        FROM market_signals s LEFT JOIN pe_firms pe ON pe.id=s.firm_id LEFT JOIN companies c ON c.id=s.company_id WHERE s.id=?""", (signal_id,)).fetchone()
    if not s: abort(404)
    obs = [r[0] for r in con.execute("SELECT DISTINCT reporting_month FROM signal_observations WHERE signal_id=? ORDER BY 1", (signal_id,))]
    related_opps = [dict(r) for r in con.execute("""SELECT o.id, pe.canonical_name AS pe_firm, o.capability, o.score, o.priority
        FROM opportunities o JOIN pe_firms pe ON pe.id=o.firm_id WHERE o.triggering_signal_id=? ORDER BY o.score DESC LIMIT 10""", (signal_id,))]
    con.close()
    d = dict(s)
    d.pop("dedupe_key", None)
    return jsonify({"signal": d, "observed_in_reporting_months": obs, "related_opportunities": related_opps})

# ---------------------------------------------------------------- 05 Industry intelligence
@app.get("/api/industry")
def industry():
    f = F(request.args)
    con = db()
    page, size = page_args(request.args, 30)
    where, params = f.link_where()
    base = f"""FROM firm_portfolio_links l JOIN companies c ON c.id=l.company_id WHERE {where} AND c.primary_vertical IS NOT NULL"""
    q = request.args.get("q", "").strip()
    qsql = "AND lower(c.primary_vertical) LIKE ?" if q else ""
    qp = [search_like(q)] if q else []
    grp = f"""SELECT c.primary_vertical AS industry, COUNT(DISTINCT l.company_id) AS portfolio_companies,
        COUNT(DISTINCT l.firm_id) AS pe_firms,
        (SELECT COUNT(*) FROM market_signals s WHERE s.scope='PORTFOLIO' AND s.company_id IN
            (SELECT company_id FROM firm_portfolio_links x JOIN companies cx ON cx.id=x.company_id WHERE cx.primary_vertical=c.primary_vertical AND x.reporting_month=?)) AS market_signals,
        COUNT(DISTINCT CASE WHEN (SELECT 1 FROM company_financials cf WHERE cf.company_id=l.company_id AND cf.metric='revenue' AND cf.reporting_month=?) THEN l.company_id END) AS revenue_coverage,
        COUNT(DISTINCT CASE WHEN (SELECT 1 FROM company_financials cf WHERE cf.company_id=l.company_id AND cf.metric='it_spend' AND cf.reporting_month=?) THEN l.company_id END) AS it_spend_coverage,
        (SELECT COUNT(*) FROM opportunities o JOIN companies co ON co.id=o.company_id WHERE co.primary_vertical=c.primary_vertical) AS opportunities
        {base} {qsql} GROUP BY c.primary_vertical"""
    order = sort_clause(request.args, {"industry": "industry", "portfolio_companies": "portfolio_companies", "pe_firms": "pe_firms",
                        "market_signals": "market_signals", "opportunities": "opportunities"}, "portfolio_companies")
    if "dir" not in request.args and "sort" not in request.args: order = "ORDER BY portfolio_companies DESC, industry ASC"
    total = con.execute(f"SELECT COUNT(*) FROM (SELECT c.primary_vertical {base} {qsql} GROUP BY c.primary_vertical)", params + qp).fetchone()[0]
    rows = [dict(r) for r in con.execute(grp + " " + order + " LIMIT ? OFFSET ?",
                                         [f.month, f.month, f.month] + params + qp + [size, (page - 1) * size])]
    con.close()
    return respond_list(rows, total, page, size)

@app.get("/api/industry/companies")
def industry_companies():
    f = F(request.args)
    vertical = request.args.get("industry", "")
    con = db()
    page, size = page_args(request.args)
    where, params = f.link_where()
    base = f"""FROM firm_portfolio_links l JOIN companies c ON c.id=l.company_id JOIN pe_firms pe ON pe.id=l.firm_id
        WHERE {where} AND c.primary_vertical = ?"""
    sel = f"""SELECT c.id, c.display_name AS company, c.sub_vertical AS sub_industry, c.hq_region AS region,
        GROUP_CONCAT(DISTINCT pe.canonical_name) AS pe_firms,
        (SELECT value_usd_mm FROM company_financials cf WHERE cf.company_id=c.id AND cf.metric='revenue' AND cf.reporting_month=? ORDER BY fiscal_year DESC LIMIT 1) AS revenue_usd_mm
        {base} GROUP BY c.id ORDER BY c.display_name"""
    total = con.execute(f"SELECT COUNT(DISTINCT c.id) {base}", params + [vertical]).fetchone()[0]
    rows = [dict(r) for r in con.execute(sel + " LIMIT ? OFFSET ?", [f.month] + params + [vertical, size, (page - 1) * size])]
    sub = [dict(r) for r in con.execute(f"""SELECT COALESCE(c.sub_vertical,'Not recorded') AS name, COUNT(DISTINCT c.id) AS n {base}
        GROUP BY 1 ORDER BY 2 DESC LIMIT 10""", params + [vertical])]
    con.close()
    return jsonify({"rows": rows, "total": total, "page": page, "size": size,
                    "pages": max(1, math.ceil(total / size)), "sub_industries": sub, "industry": vertical})

# ---------------------------------------------------------------- 06 Stakeholders
@app.get("/api/stakeholders/summary")
def stakeholders_summary():
    f = F(request.args)
    con = db()
    w, p = stakeholder_scope(f)
    k = {
        "unique_stakeholders": con.execute(f"SELECT COUNT(*) FROM stakeholders s WHERE {w}", p).fetchone()[0],
        "verified_confirmed": con.execute(f"SELECT COUNT(*) FROM stakeholders s WHERE {w} AND s.verification_status='Confirmed'", p).fetchone()[0],
        "firms_with_coverage": con.execute(f"SELECT COUNT(DISTINCT s.firm_id) FROM stakeholders s WHERE {w}", p).fetchone()[0],
        "da_m_aligned": con.execute(f"SELECT COUNT(*) FROM stakeholders s WHERE {w} AND s.da_m=1", p).fetchone()[0],
        "cybersecurity_aligned": con.execute(f"SELECT COUNT(*) FROM stakeholders s WHERE {w} AND s.cybersecurity=1", p).fetchone()[0],
        "bfsi_aligned": con.execute(f"SELECT COUNT(*) FROM stakeholders s WHERE {w} AND s.bfsi=1", p).fetchone()[0],
        "healthcare_aligned": con.execute(f"SELECT COUNT(*) FROM stakeholders s WHERE {w} AND s.healthcare=1", p).fetchone()[0],
        "requiring_review": con.execute(f"SELECT COUNT(*) FROM stakeholders s WHERE {w} AND s.verification_status<>'Confirmed'", p).fetchone()[0],
    }
    status = [dict(r) for r in con.execute(f"SELECT s.verification_status AS name, COUNT(*) n FROM stakeholders s WHERE {w} GROUP BY 1 ORDER BY 2 DESC", p)]
    confidence = [dict(r) for r in con.execute(f"SELECT COALESCE(s.confidence,'Not recorded') AS name, COUNT(*) n FROM stakeholders s WHERE {w} GROUP BY 1", p)]
    tenure = [dict(r) for r in con.execute(f"""SELECT COALESCE(s.current_role_tenure,'Not recorded') AS name, COUNT(*) n
        FROM stakeholders s WHERE {w} GROUP BY 1 ORDER BY 2 DESC LIMIT 12""", p)]
    k["targeted_firms_with_stakeholders"] = con.execute("""SELECT COUNT(DISTINCT s.firm_id) FROM stakeholders s JOIN pe_firms f ON f.id=s.firm_id
        WHERE f.in_account_list=1""").fetchone()[0]
    k["stakeholder_only_firms"] = con.execute("""SELECT COUNT(DISTINCT s.firm_id) FROM stakeholders s JOIN pe_firms f ON f.id=s.firm_id
        WHERE f.in_account_list=0""").fetchone()[0]
    con.close()
    return jsonify({"kpis": k, "status": status, "confidence": confidence, "tenure": tenure,
                    "checked_on": "2026-09-04", "file_date": "2026-09-09",
                    "note": "Verification was performed on 4 Sep 2026 and not re-run for November."})

@app.get("/api/stakeholders")
def stakeholders():
    f = F(request.args)
    con = db()
    page, size = page_args(request.args)
    parts, params = ["1=1"], []
    w, p = stakeholder_scope(f, request.args.get("status") or None,
                             [fl for fl in split_multi(request.args.get("flag")) if fl in ("da_m", "cybersecurity", "bfsi", "healthcare")])
    q = request.args.get("q", "").strip()
    qsql, qp = ("AND (lower(s.name) LIKE ? OR lower(coalesce(s.designation,'')) LIKE ?)", [search_like(q), search_like(q)]) if q else ("", [])
    base = f"FROM stakeholders s JOIN pe_firms pe ON pe.id=s.firm_id WHERE {w} {qsql}"
    sel = f"""SELECT s.id, s.name AS stakeholder, pe.canonical_name AS pe_firm, s.designation, s.current_company,
        s.current_title, s.verification_status, s.confidence, s.checked_on AS last_checked, s.linkedin_url AS profile_link,
        CASE WHEN s.da_m=1 THEN 'DA&M ' ELSE '' END || CASE WHEN s.cybersecurity=1 THEN 'Cyber ' ELSE '' END ||
        CASE WHEN s.bfsi=1 THEN 'BFSI ' ELSE '' END || CASE WHEN s.healthcare=1 THEN 'Healthcare' ELSE '' END AS sector_alignment
        {base}"""
    order = sort_clause(request.args, {"stakeholder": "s.name", "pe_firm": "pe.canonical_name", "verification_status": "s.verification_status",
                        "confidence": "s.confidence", "last_checked": "s.checked_on"}, "stakeholder", "s.id")
    total = con.execute(f"SELECT COUNT(*) {base}", p + qp).fetchone()[0]
    if request.args.get("format") == "csv":
        rows = [dict(r) for r in con.execute(sel + " " + order, p + qp)]
    else:
        rows = [dict(r) for r in con.execute(sel + " " + order + " LIMIT ? OFFSET ?", p + qp + [size, (page - 1) * size])]
    con.close()
    return respond_list(rows, total, page, size)

@app.get("/api/stakeholders/<int:sid>")
def stakeholder_profile(sid):
    con = db()
    s = con.execute("""SELECT s.*, pe.canonical_name AS pe_firm FROM stakeholders s JOIN pe_firms pe ON pe.id=s.firm_id WHERE s.id=?""", (sid,)).fetchone()
    if not s: abort(404)
    d = dict(s)
    for k in ("initial_outreach_date", "followup_date"):
        d[k] = d.get(k)
    acct = con.execute("SELECT status FROM pe_account_snapshots WHERE firm_id=? ORDER BY reporting_month DESC LIMIT 1", (s["firm_id"],)).fetchone()
    opps = [dict(r) for r in con.execute("""SELECT id, capability, score, priority FROM opportunities WHERE firm_id=? ORDER BY score DESC LIMIT 8""", (s["firm_id"],))]
    con.close()
    d["account_status"] = acct["status"] if acct else None
    d["sector_alignment"] = [k for k, lab in (("da_m", "DA&M"), ("cybersecurity", "Cybersecurity"), ("bfsi", "BFSI"), ("healthcare", "Healthcare")) if d[k]]
    return jsonify({"stakeholder": d, "related_opportunities": opps})

# ---------------------------------------------------------------- 07 Opportunity intelligence
@app.get("/api/opportunities/summary")
def opp_summary():
    f = F(request.args)
    con = db()
    w, p = opportunity_scope(f)
    k = {
        "total": con.execute(f"SELECT COUNT(*) FROM opportunities o LEFT JOIN companies c ON c.id=o.company_id WHERE {w}", p).fetchone()[0],
        "critical": con.execute(f"SELECT COUNT(*) FROM opportunities o LEFT JOIN companies c ON c.id=o.company_id WHERE {w} AND o.priority='Critical'", p).fetchone()[0],
        "high": con.execute(f"SELECT COUNT(*) FROM opportunities o LEFT JOIN companies c ON c.id=o.company_id WHERE {w} AND o.priority='High'", p).fetchone()[0],
        "accounts": con.execute(f"SELECT COUNT(DISTINCT o.firm_id) FROM opportunities o LEFT JOIN companies c ON c.id=o.company_id WHERE {w}", p).fetchone()[0],
        "companies": con.execute(f"SELECT COUNT(DISTINCT o.company_id) FROM opportunities o LEFT JOIN companies c ON c.id=o.company_id WHERE {w} AND o.company_id IS NOT NULL", p).fetchone()[0],
        "with_confirmed_stakeholders": con.execute(f"SELECT COUNT(*) FROM opportunities o LEFT JOIN companies c ON c.id=o.company_id WHERE {w} AND o.confirmed_stakeholder_count>0", p).fetchone()[0],
    }
    priority = [dict(r) for r in con.execute(f"SELECT o.priority AS name, COUNT(*) n FROM opportunities o LEFT JOIN companies c ON c.id=o.company_id WHERE {w} GROUP BY 1", p)]
    capability = [dict(r) for r in con.execute(f"SELECT o.capability AS name, COUNT(*) n, ROUND(AVG(o.score),1) AS avg_score FROM opportunities o LEFT JOIN companies c ON c.id=o.company_id WHERE {w} GROUP BY 1 ORDER BY 2 DESC", p)]
    accounts = [dict(r) for r in con.execute(f"""SELECT pe.canonical_name AS name, COUNT(*) AS opportunities,
        SUM(CASE WHEN o.priority IN ('Critical','High') THEN 1 ELSE 0 END) AS high_priority
        FROM opportunities o JOIN pe_firms pe ON pe.id=o.firm_id LEFT JOIN companies c ON c.id=o.company_id WHERE {w}
        GROUP BY pe.id ORDER BY 3 DESC, 2 DESC LIMIT 12""", p)]
    heat = [dict(r) for r in con.execute(f"""SELECT COALESCE(c.primary_vertical,'Firm-level') AS industry, o.priority, COUNT(*) n
        FROM opportunities o LEFT JOIN companies c ON c.id=o.company_id WHERE {w} GROUP BY 1, 2""", p)]
    con.close()
    return jsonify({"kpis": k, "priority": priority, "capability": capability, "accounts": accounts, "heatmap": heat,
                    "method": {"weights": {"Signal relevance": 25, "Zinnov capability alignment": 25, "Business scale": 20,
                               "Signal recency": 15, "Evidence quality": 10, "Stakeholder availability": 5},
                               "bands": {"Critical": "85-100", "High": "70-84", "Medium": "50-69", "Low": "below 50"},
                               "as_of": "2026-10-31", "scope": "Associations from the 13 Nov 2026 snapshot; news Apr-Oct 2026."}})

@app.get("/api/opportunities")
def opportunities():
    f = F(request.args)
    con = db()
    page, size = page_args(request.args)
    w, p = opportunity_scope(f, request.args.get("priority") or None, request.args.get("capability") or None)
    q = request.args.get("q", "").strip()
    qsql, qp = ("AND (lower(coalesce(c.display_name,'')) LIKE ? OR lower(pe.canonical_name) LIKE ?)", [search_like(q), search_like(q)]) if q else ("", [])
    base = f"""FROM opportunities o JOIN pe_firms pe ON pe.id=o.firm_id LEFT JOIN companies c ON c.id=o.company_id WHERE {w} {qsql}"""
    sel = f"""SELECT o.id, pe.canonical_name AS pe_firm, COALESCE(c.display_name, 'Firm-level (PE news)') AS portfolio_company,
        o.triggering_title AS triggering_signal, o.triggering_category AS signal_category, o.capability AS zinnov_capability,
        o.score, o.priority, o.evidence_confidence, o.confirmed_stakeholder_count, o.stakeholder_count,
        o.recommended_action, o.publication_date"""
    order = sort_clause(request.args, {"score": "o.score", "pe_firm": "pe.canonical_name", "portfolio_company": "c.display_name",
                        "priority": "o.priority", "publication_date": "o.publication_date"}, "score", "o.id")
    if "dir" not in request.args and "sort" not in request.args: order = "ORDER BY o.score DESC, o.id ASC"
    total = con.execute(f"SELECT COUNT(*) {base}", p + qp).fetchone()[0]
    if request.args.get("format") == "csv":
        rows = [dict(r) for r in con.execute(sel + " " + base + " " + order, p + qp)]
    else:
        rows = [dict(r) for r in con.execute(sel + " " + base + " " + order + " LIMIT ? OFFSET ?", p + qp + [size, (page - 1) * size])]
    con.close()
    return respond_list(rows, total, page, size)

@app.get("/api/opportunities/<int:oid>")
def opportunity_detail(oid):
    con = db()
    o = con.execute("""SELECT o.*, pe.canonical_name AS pe_firm, c.display_name AS company, c.primary_vertical AS industry,
        c.sub_vertical AS sub_industry, c.hq_region AS region, c.domain AS domain
        FROM opportunities o JOIN pe_firms pe ON pe.id=o.firm_id LEFT JOIN companies c ON c.id=o.company_id WHERE o.id=?""", (oid,)).fetchone()
    if not o: abort(404)
    d = dict(o)
    d["component_scores"] = json.loads(d.pop("component_json") or "{}")
    sig = con.execute("SELECT id, news_title, news_description, news_url, category, publication_date, publication_month FROM market_signals WHERE id=?", (o["triggering_signal_id"],)).fetchone()
    stake = [dict(r) for r in con.execute("""SELECT id, name, designation, verification_status, confidence FROM stakeholders WHERE firm_id=?
        ORDER BY (verification_status='Confirmed') DESC, name LIMIT 8""", (o["firm_id"],))]
    con.close()
    return jsonify({"opportunity": d, "signal": dict(sig) if sig else None, "stakeholders": stake,
                    "hypothesis_note": "Hypothesis for human validation. Not a confirmed requirement, budget or pipeline value."})

# ---------------------------------------------------------------- 08 Outreach
def outreach_status(row):
    if row["followup_response"] and str(row["followup_response"]).strip() not in ("-", ""):
        return "Response recorded"
    if row["followup_date"]: return "Follow-up recorded, no response logged"
    if row["initial_outreach_date"]: return "Initial outreach date recorded"
    return "No outreach recorded"

def next_action(row):
    st = outreach_status(row)
    if row["verification_status"] != "Confirmed": return "Re-verify contact before outreach"
    if st == "Response recorded": return "Review the recorded response and agree the next step"
    if st.startswith("Follow-up"): return "Review whether a further follow-up is appropriate"
    if st.startswith("Initial"): return "Confirm outreach status and log any response"
    return "Consider initial outreach after validating the account opportunity"

@app.get("/api/outreach/summary")
def outreach_summary():
    f = F(request.args)
    con = db()
    w, p = stakeholder_scope(f)
    rows = [dict(r) for r in con.execute(f"""SELECT s.*, pe.canonical_name AS pe_firm FROM stakeholders s JOIN pe_firms pe ON pe.id=s.firm_id WHERE {w}""", p)]
    con.close()
    statuses = Counter(outreach_status(r) for r in rows)
    kpis = {
        "stakeholders_in_view": len(rows),
        "with_outreach_recorded": sum(1 for r in rows if r["initial_outreach_date"]),
        "with_followup_recorded": sum(1 for r in rows if r["followup_date"]),
        "with_response_recorded": sum(1 for r in rows if r["followup_response"] and str(r["followup_response"]).strip() not in ("-", "")),
        "without_outreach_recorded": sum(1 for r in rows if not r["initial_outreach_date"]),
        "requiring_review": sum(1 for r in rows if r["verification_status"] != "Confirmed"),
        "accounts_with_engagement": len({r["firm_id"] for r in rows if r["initial_outreach_date"]}),
    }
    return jsonify({"kpis": kpis, "status_breakdown": [{"name": k, "n": v} for k, v in statuses.most_common()],
                    "note": "Outreach dates appear for every stakeholder in the source file, so they may be planned or bulk-entered. "
                            "Treat them as recorded fields, not verified engagement. Empty responses are not treated as rejections."})

@app.get("/api/outreach")
def outreach():
    f = F(request.args)
    con = db()
    page, size = page_args(request.args)
    w, p = stakeholder_scope(f, None, [])
    q = request.args.get("q", "").strip()
    qsql, qp = ("AND lower(s.name) LIKE ?", [search_like(q)]) if q else ("", [])
    base = f"FROM stakeholders s JOIN pe_firms pe ON pe.id=s.firm_id WHERE {w} {qsql}"
    all_rows = [dict(r) for r in con.execute(f"""SELECT s.id, s.name AS stakeholder, pe.canonical_name AS pe_firm, s.designation,
        CASE WHEN s.da_m=1 THEN 'DA&M ' ELSE '' END || CASE WHEN s.cybersecurity=1 THEN 'Cyber ' ELSE '' END ||
        CASE WHEN s.bfsi=1 THEN 'BFSI ' ELSE '' END || CASE WHEN s.healthcare=1 THEN 'Healthcare' ELSE '' END AS sector_alignment,
        s.initial_outreach_date, s.followup_date, s.followup_response, s.remark, s.verification_status
        {base} ORDER BY pe.canonical_name, s.name""", p + qp)]
    for r in all_rows:
        r["outreach_status"] = outreach_status(r)
        r["recommended_next_action"] = next_action(r)
    status_f = request.args.get("status")
    if status_f: all_rows = [r for r in all_rows if r["outreach_status"] == status_f]
    total = len(all_rows)
    rows = all_rows if request.args.get("format") == "csv" else all_rows[(page - 1) * size:(page - 1) * size + size]
    for r in rows: r.pop("verification_status", None)
    con.close()
    return respond_list(rows, total, page, size)

# ---------------------------------------------------------------- static frontend
@app.get("/")
def index():
    return send_from_directory(FRONTEND, "index.html")

@app.get("/static/<path:name>")
def static_files(name):
    return send_from_directory(FRONTEND / "static", name)

@app.errorhandler(404)
def not_found(e):
    if request.path.startswith("/api/"):
        return jsonify({"error": "not found"}), 404
    return send_from_directory(FRONTEND, "index.html")

@app.errorhandler(500)
def server_error(e):
    return jsonify({"error": "internal error", "detail": str(e)}), 500

if __name__ == "__main__":
    if not DB.exists():
        sys.exit(f"Database not found at {DB}. Run scripts/build_db.py first.")
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5055
    app.run(host="127.0.0.1", port=port, debug=False)
