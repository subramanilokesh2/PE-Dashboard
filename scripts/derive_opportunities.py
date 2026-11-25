"""Derive hypothesis-level Zinnov opportunities from signals, financials and stakeholder alignment.

Usage: python scripts/derive_opportunities.py data/intel.db

Scope: company opportunities use the firm-to-company associations in the LATEST reporting snapshot
(current workbook), with news from all publication months. Firm-level opportunities come from PE-scope news.
Every opportunity is a hypothesis for human validation, not a confirmed client requirement.
"""
import sys, re, math, sqlite3, json
from collections import defaultdict
from datetime import date

AS_OF = date(2026, 10, 31)   # end of the latest publication month in the source data
WEIGHTS = {"signal_relevance": 0.25, "capability_alignment": 0.25, "scale": 0.20,
           "recency": 0.15, "evidence": 0.10, "stakeholders": 0.05}

CATEGORY_RULES = {
    "Mergers and Acquisitions": ("Commercial & Technology Due Diligence", 0.90, "Assess integration, synergy and technology risk around the deal."),
    "Center Setup and Expansion": ("Global Capability Centers (GCC)", 0.90, "Scope a captive or GCC build-out, location and operating model."),
    "Layoff": ("Cost Optimization & Operating Model Transformation", 0.80, "Review cost base and operating model after workforce reduction."),
    "Fundraise and Investments": ("PE Value Creation & Growth Advisory", 0.70, "Support growth plan and value-creation priorities after new capital."),
    "Mass Hiring": ("Engineering & Talent Transformation", 0.70, "Plan engineering capacity and talent model for the hiring ramp."),
    "Executive Movement": ("Operating Model & Leadership Transition", 0.60, "Engage the incoming leader on priorities and operating model."),
    "New Product Development and Product Launch": ("Digital Product Engineering & AI", 0.60, "Assess product engineering capacity and go-to-market technology needs."),
    "Deals and Partnerships": ("Technology Partnerships & Transformation", 0.60, "Map the partnership's technology and delivery implications."),
    "Financial and Market Activity": ("PE Advisory & Market Intelligence", 0.50, "Track the market activity and identify the advisory angle."),
}
KEYWORD_RULES = [
    (re.compile(r"\b(cyber|cybersecurity|breach|ransomware|zero trust|security platform)\b", re.I), "Cybersecurity", 0.70,
     "Evaluate security posture and remediation capacity."),
    (re.compile(r"\b(ai|generative|machine learning|automation|agentic)\b", re.I), "AI & Automation", 0.70,
     "Scope AI and automation use cases linked to the reported development."),
    (re.compile(r"\b(data|analytics|cloud|modernization|migration|platform)\b", re.I), "Data Analytics & Modernization", 0.60,
     "Assess data and platform modernization needs."),
]
NEXT_ACTION = {
    "Commercial & Technology Due Diligence": "Confirm deal status with the sponsor team, then prepare a technology due diligence outline.",
    "Global Capability Centers (GCC)": "Verify the GCC plan with the company's leadership before proposing a location study.",
    "Cost Optimization & Operating Model Transformation": "Check whether a cost programme is already underway before outreach.",
    "PE Value Creation & Growth Advisory": "Review the growth plan with the deal team and identify value-creation gaps.",
    "Engineering & Talent Transformation": "Confirm hiring scope and open roles before proposing a delivery model.",
    "Operating Model & Leadership Transition": "Map the new leader's priorities and send a relevant point of view.",
    "Digital Product Engineering & AI": "Validate product roadmap and engineering capacity before proposing support.",
    "Technology Partnerships & Transformation": "Check the partnership scope and whether Zinnov's ecosystem coverage adds value.",
    "PE Advisory & Market Intelligence": "Monitor further developments; no outreach until a clearer trigger appears.",
    "Cybersecurity": "Validate security priorities with the CISO or security leader before proposing work.",
    "AI & Automation": "Validate AI use case and budget ownership before proposing a pilot.",
    "Data Analytics & Modernization": "Confirm data modernization priorities with the technology leader.",
}

def priority_of(score):
    if score >= 85: return "Critical"
    if score >= 70: return "High"
    if score >= 50: return "Medium"
    return "Low"

def main(db):
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    con.execute("DROP TABLE IF EXISTS opportunities")
    con.execute("""CREATE TABLE opportunities(id INTEGER PRIMARY KEY, firm_id INTEGER, company_id INTEGER, scope TEXT,
        capability TEXT, triggering_signal_id INTEGER, triggering_title TEXT, triggering_category TEXT,
        publication_date TEXT, score REAL, priority TEXT, evidence_confidence TEXT, component_json TEXT,
        revenue_usd_mm REAL, it_spend_usd_mm REAL, stakeholder_count INTEGER, confirmed_stakeholder_count INTEGER,
        recommended_action TEXT, hypothesis_rationale TEXT, notes TEXT)""")
    latest = con.execute("SELECT MAX(reporting_month) m FROM firm_portfolio_links").fetchone()["m"]
    # latest revenue / IT spend per company (most recent fiscal year, any month)
    fin = {}
    for r in con.execute("""SELECT company_id, metric, fiscal_year, value_usd_mm FROM company_financials
                            ORDER BY reporting_month, fiscal_year"""):
        fin[(r["company_id"], r["metric"])] = (r["fiscal_year"], r["value_usd_mm"])
    stake = defaultdict(lambda: {"total": 0, "confirmed": 0})
    for r in con.execute("SELECT firm_id, verification_status FROM stakeholders"):
        stake[r["firm_id"]]["total"] += 1
        if r["verification_status"] == "Confirmed": stake[r["firm_id"]]["confirmed"] += 1
    # company-level associations in latest snapshot
    assoc = {}
    for r in con.execute("SELECT firm_id, company_id FROM firm_portfolio_links WHERE reporting_month=?", (latest,)):
        assoc.setdefault(r["company_id"], set()).add(r["firm_id"])
    # firms that are in the targeted account list only
    in_list = {r["id"] for r in con.execute("SELECT id FROM pe_firms WHERE in_account_list=1")}
    signals = con.execute("""SELECT id, scope, firm_id, company_id, news_title, news_description, news_url, category,
                                    publication_date FROM market_signals""").fetchall()
    best = {}   # (scope key) -> best candidate
    rows_out = []
    def evaluate(sig, firm_id, company_id, capability, base_rel, rationale, align):
        if firm_id not in in_list: return
        text = f"{sig['news_title'] or ''} {sig['news_description'] or ''}"
        rev = fin.get((company_id, "revenue")) if company_id else None
        itx = fin.get((company_id, "it_spend")) if company_id else None
        rev_v = rev[1] if rev and rev[1] else None
        itx_v = itx[1] if itx and itx[1] else None
        if rev_v: scale = min(1.0, math.log10(rev_v + 1) / math.log10(10000))
        else: scale = 0.3
        d = date.fromisoformat(sig["publication_date"][:10]) if sig["publication_date"] else AS_OF
        age = (AS_OF - d).days
        recency = 1.0 if age <= 30 else 0.8 if age <= 60 else 0.6 if age <= 90 else 0.4 if age <= 150 else 0.2
        has_url = bool(sig["news_url"]); has_desc = bool(sig["news_description"])
        evidence = 1.0 if has_url and has_desc else 0.6 if has_url else 0.2
        st = stake[firm_id]
        stakeholder = 1.0 if st["confirmed"] else 0.5 if st["total"] else 0.0
        comp = {"signal_relevance": base_rel, "capability_alignment": align, "scale": round(scale, 3),
                "recency": recency, "evidence": evidence, "stakeholders": stakeholder}
        score = round(100 * sum(WEIGHTS[k] * v for k, v in comp.items()), 1)
        conf = "High" if evidence >= 0.9 else "Medium" if evidence >= 0.5 else "Low"
        notes = []
        if rev_v is None: notes.append("Revenue not available: scale scored at the neutral 0.3 default")
        if not has_desc: notes.append("No news description in source")
        if st["total"] == 0: notes.append("No stakeholders recorded for this PE firm")
        key = (firm_id, company_id, capability)
        cand = dict(firm_id=firm_id, company_id=company_id, scope="company" if company_id else "firm",
                    capability=capability, triggering_signal_id=sig["id"], triggering_title=sig["news_title"],
                    triggering_category=sig["category"], publication_date=sig["publication_date"], score=score,
                    priority=priority_of(score), evidence_confidence=conf, component_json=json.dumps(comp),
                    revenue_usd_mm=rev_v, it_spend_usd_mm=itx_v, stakeholder_count=st["total"],
                    confirmed_stakeholder_count=st["confirmed"], recommended_action=NEXT_ACTION.get(capability, "Validate before outreach."),
                    hypothesis_rationale=rationale, notes="; ".join(notes))
        cur = best.get(key)
        if cur is None or cand["score"] > cur["score"]: best[key] = cand

    for s in signals:
        if s["scope"] == "PE":
            if s["firm_id"] is None: continue
            rule = CATEGORY_RULES.get(s["category"])
            if rule:
                evaluate(s, s["firm_id"], None, rule[0], rule[1], rule[2], 1.0)
            continue
        cid = s["company_id"]
        if cid is None or cid not in assoc: continue
        rule = CATEGORY_RULES.get(s["category"])
        text = f"{s['news_title'] or ''} {s['news_description'] or ''}"
        for firm_id in assoc[cid]:
            if rule:
                evaluate(s, firm_id, cid, rule[0], rule[1], rule[2], 1.0)
            for pat, cap, rel, why in KEYWORD_RULES:
                if pat.search(text):
                    evaluate(s, firm_id, cid, cap, rel, why, 0.7)
    cur = con.cursor()
    for cand in best.values():
        cur.execute("""INSERT INTO opportunities(firm_id,company_id,scope,capability,triggering_signal_id,triggering_title,
            triggering_category,publication_date,score,priority,evidence_confidence,component_json,revenue_usd_mm,
            it_spend_usd_mm,stakeholder_count,confirmed_stakeholder_count,recommended_action,hypothesis_rationale,notes)
            VALUES (:firm_id,:company_id,:scope,:capability,:triggering_signal_id,:triggering_title,:triggering_category,
            :publication_date,:score,:priority,:evidence_confidence,:component_json,:revenue_usd_mm,:it_spend_usd_mm,
            :stakeholder_count,:confirmed_stakeholder_count,:recommended_action,:hypothesis_rationale,:notes)""", cand)
    con.execute("CREATE INDEX ix_opp_firm ON opportunities(firm_id, priority)")
    con.commit()
    counts = dict(con.execute("SELECT priority, COUNT(*) FROM opportunities GROUP BY priority").fetchall())
    print("opportunities:", con.execute("SELECT COUNT(*) FROM opportunities").fetchone()[0], counts)
    con.close()

if __name__ == "__main__":
    main(sys.argv[1])
