"""Build the consolidated PE intelligence database from the nine source workbooks.

Usage:  python scripts/build_db.py <folder-with-the-nine-xlsx-files> <output-db-path>

Reporting month = month in the workbook name (snapshot). Publication month = the
Publication Date on each news row (what actually happened). The two are kept apart.
Only fields present in the source are stored. Stakeholder email addresses are NOT stored.
"""
import sys, re, json, sqlite3, math, datetime as dt
from pathlib import Path
from urllib.parse import urlparse
from collections import defaultdict, Counter
from openpyxl import load_workbook

# Each workbook is identified by the date in its file name (original names as uploaded).
# Label -> (reporting month, role). The reporting month is the month in the workbook name.
FILE_PATTERNS = [
    (r"30Apr", "2026-04", "portfolio_baseline"),   # 30 Apr 2026 targeted details (no signal sheets)
    (r"18May", "2026-05", "monthly"),              # 18 May 2026 workbook (holds April publications)
    (r"11(th)?Jun", "2026-06", "monthly"),              # 11 Jun 2026 workbook (holds May publications)
    (r"16Jul", "2026-07", "monthly"),              # 16 Jul 2026 workbook (holds June publications)
    (r"18Aug", "2026-08", "monthly"),              # 18 Aug 2026 workbook (holds July publications)
    (r"11Sep", "2026-09", "monthly"),              # 11 Sep 2026 workbook (holds August publications)
    (r"09Oct", "2026-10", "monthly"),              # 09 Oct 2026 workbook (holds September publications)
    (r"13Nov", "2026-11", "monthly"),              # 13 Nov 2026 workbook (holds October publications)
    (r"Stakeholders", "2026-09", "stakeholders"),  # PE stakeholders verified 09 Sep 2026
]
MONTH_ORDER = ["2026-04", "2026-05", "2026-06", "2026-07", "2026-08", "2026-09", "2026-10", "2026-11"]
SUFFIXES = re.compile(r"\b(incorporated|inc|llc|ltd|limited|corporation|corp|co|company|gmbh|ag|plc|lp|llp|n a|na|group|holdings|management)\b")

def norm(s):
    if s is None: return ""
    s = str(s).lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    s = SUFFIXES.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()

def clean(v):
    if v is None: return None
    if isinstance(v, str):
        v = v.strip()
        if v in ("", "-", "–", "NA", "N/A"): return None
    return v

def num(v):
    v = clean(v)
    if v is None: return None
    if isinstance(v, (int, float)): return float(v)
    try: return float(str(v).replace(",", ""))
    except ValueError: return None

DOMAIN_RE = re.compile(r"^([a-z0-9-]+\.)+[a-z]{2,}$")

def domain_key(url):
    """Return a bare host such as example.com, or None when the cell is not a usable domain."""
    url = clean(url)
    if not url: return None
    u = str(url).strip().lower()
    if "://" not in u: u = "http://" + u
    host = urlparse(u).netloc.split("@")[-1].split(":")[0]
    host = host[4:] if host.startswith("www.") else host
    return host if DOMAIN_RE.match(host or "") else None

def iso(d):
    return d.date().isoformat() if isinstance(d, dt.datetime) else (d.isoformat() if isinstance(d, dt.date) else clean(d))

def rows_of(ws):
    return list(ws.iter_rows(values_only=True))

def find_header(rows, must=("S.No",), search=10):
    for i, r in enumerate(rows[:search]):
        vals = [str(v).strip() if v is not None else "" for v in r]
        if any(m in vals for m in must):
            return i, vals
    raise ValueError("header not found")

def table(rows, hdr_idx, hdr):
    out = []
    for r in rows[hdr_idx + 1:]:
        if not any(v not in (None, "") for v in r): continue
        out.append({h: r[j] if j < len(r) else None for j, h in enumerate(hdr) if h})
    return out

class Builder:
    def __init__(self):
        self.report = []
        self.firm_by_alias = {}      # norm alias -> firm id
        self.firms = {}              # firm id -> dict
        self.companies = {}          # company key -> dict
        self.company_by_name = {}    # norm name -> company key (prefer domain keys)
        self.signals = {}            # dedupe key -> dict
        self.sig_obs = []            # (dedupe key, reporting month, workbook tag, row number)
        self.links = {}              # (firm id, company key, month) -> dict
        self.fin = {}                # (company key, month, fy, metric) -> value
        self.snapshots = {}          # (firm id, month) -> dict
        self.stakeholders = []
        self.firm_counts = defaultdict(int)
        self.dash_rows = []

    def log(self, msg): self.report.append(msg)

    # ---------- firms ----------
    def firm_id(self, name, create=True, source=""):
        key = norm(name)
        if not key: return None
        if key in self.firm_by_alias: return self.firm_by_alias[key]
        if not create: return None
        fid = len(self.firms) + 1
        self.firms[fid] = {"id": fid, "canonical_name": str(name).strip(), "requested_name": None,
                           "draup_name": None, "in_account_list": 0, "source": source}
        self.firm_by_alias[key] = fid
        self.log(f"firm not in account list, created: {name} ({source})")
        return fid

    def add_firm_alias(self, fid, name):
        if name and norm(name): self.firm_by_alias.setdefault(norm(name), fid)

    # ---------- companies ----------
    def build_entities(self):
        """Merge dashboard rows into one company entity per real company.
        Rows join when they share a normalised name or a valid domain (union-find)."""
        parent = {}
        def find(x):
            parent.setdefault(x, x)
            while parent[x] != x:
                parent[x] = parent[parent[x]]; x = parent[x]
            return x
        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb: parent[rb] = ra
        for r in self.dash_rows:
            find("name:" + r["nk"])
            if r["domain"]: union("name:" + r["nk"], "dom:" + r["domain"])
        groups = defaultdict(list)
        for r in self.dash_rows: groups[find("name:" + r["nk"])].append(r)
        used_keys = set()
        for root, rows in groups.items():
            rows = sorted(rows, key=lambda x: (x["month"], x["seq"]))
            latest = rows[-1]
            domain = next((x["domain"] for x in reversed(rows) if x["domain"]), None)
            base = ("d:" + domain) if domain else ("n:" + latest["nk"])
            key, k = base, 2
            while key in used_keys:
                key = f"{base}#{k}"; k += 1
            used_keys.add(key)
            names_here = {x["nk"] for x in rows}
            c = {"key": key, "display_name": latest["name"], "norm_name": latest["nk"], "domain": domain,
                 "dashboard_months": {x["month"] for x in rows}, "link_months": set(), "signal_count": 0,
                 "stub": 0, "member_names": names_here}
            for attr in ("founded_year","primary_vertical","sub_vertical","hq_location","hq_country","hq_region","company_type"):
                val = None
                for x in rows:
                    v = x["attrs"].get(attr)
                    if v is not None and str(v).strip() not in ("0", ""): val = v
                c[attr] = val
            self.companies[key] = c
            for nk in names_here: self.company_by_name[nk] = key
            for x in rows:
                for metric, fy, v in x["fin"]:
                    self.fin[(key, x["month"], fy, metric)] = v
        self.log(f"dashboard rows {len(self.dash_rows)} -> company entities {len(self.companies)}")

    def resolve_company(self, name):
        nk = norm(name)
        if not nk: return None
        if nk in self.company_by_name: return self.company_by_name[nk]
        key = "n:" + nk
        base, k = key, 2
        while key in self.companies:
            key = f"{base}#{k}"; k += 1
        self.companies[key] = {"key": key, "display_name": str(name).strip(), "norm_name": nk, "domain": None,
                               "dashboard_months": set(), "link_months": set(), "signal_count": 0, "stub": 1,
                               "member_names": {nk}}
        self.company_by_name[nk] = key
        return key

    # ---------- parsing ----------
    def load_account_status(self, ws, month):
        rows = rows_of(ws)
        hi, hdr = find_header(rows, must=("Requested Firm Name",), search=8)
        for r in table(rows, hi, hdr):
            req, draup = clean(r.get("Requested Firm Name")), clean(r.get("Draup Name"))
            if not req and not draup: continue
            canon = req or draup
            fid = None
            for cand in (draup, req):
                if cand and norm(cand) in self.firm_by_alias:
                    fid = self.firm_by_alias[norm(cand)]; break
            if fid is None:
                fid = len(self.firms) + 1
                self.firms[fid] = {"id": fid, "canonical_name": str(canon).strip(), "requested_name": req,
                                   "draup_name": draup, "in_account_list": 1, "source": "account_status"}
            f = self.firms[fid]
            f["in_account_list"] = 1
            f["requested_name"] = f["requested_name"] or req
            f["draup_name"] = draup or f["draup_name"]
            f["canonical_name"] = str(req or draup).strip()
            self.add_firm_alias(fid, req); self.add_firm_alias(fid, draup)
            status = clean(r.get("Status/Comment")) or clean(r.get("Status"))
            comment = clean(r.get("Status/Comment")) if "Status/Comment" in r else None
            self.snapshots[(fid, month)] = {"firm_id": fid, "reporting_month": month,
                                            "requested_name": req, "draup_name": draup,
                                            "status": status, "portfolio_count": None}

    def load_signals(self, ws, month, tag, scope):
        rows = rows_of(ws)
        hi, hdr = find_header(rows, must=("S.No",), search=8)
        for n, r in enumerate(table(rows, hi, hdr), start=hi + 2):
            name = clean(r.get("Company Name")); title = clean(r.get("News Title"))
            if not name or not title: continue
            url = clean(r.get("News URL")); desc = clean(r.get("News Description"))
            pub = r.get("Publication Date")
            pub_iso = iso(pub)
            pub_month = pub_iso[:7] if pub_iso else None
            cat = clean(r.get("Signal Category")) or "Uncategorised"
            vertical = clean(r.get("Primary Vertical"))
            if scope == "PE":
                fid = self.firm_id(name, create=True, source="signal")
                owner = {"firm_id": fid, "company_key": None}
            else:
                ck = self.resolve_company(name)
                owner = {"firm_id": None, "company_key": ck}
                if vertical and ck in self.companies and not self.companies[ck].get("primary_vertical"):
                    self.companies[ck]["primary_vertical"] = vertical
            dkey = "|".join([scope, norm(name), norm(title), (url or "").strip().lower()])
            s = self.signals.get(dkey)
            if s is None:
                s = self.signals[dkey] = {"dedupe_key": dkey, "scope": scope, **owner, "company_name": str(name).strip(),
                                          "primary_vertical": vertical, "news_title": title, "news_description": desc,
                                          "news_url": url, "category": cat, "publication_date": pub_iso,
                                          "publication_month": pub_month, "source_tag": tag, "row_number": n}
            else:
                if not s.get("news_description") and desc: s["news_description"] = desc
            self.sig_obs.append((dkey, month, tag, n))
            if owner["company_key"]: self.companies[owner["company_key"]]["signal_count"] += 0

    def load_dashboard(self, ws, month, tag):
        rows = rows_of(ws)
        hi, hdr = find_header(rows, must=("S.No",), search=8)
        sub = rows[hi + 1] if hi + 1 < len(rows) else ()
        # Financial year labels sit in the row below the header; attach each to nearest metric header.
        metric_cols = {}
        current = None
        for j in range(len(hdr)):
            h = hdr[j]
            if h in ("Revenue (USD Mm)", "IT Spend (USD Mm)"):
                current = "revenue" if h.startswith("Revenue") else "it_spend"
            yv = sub[j] if j < len(sub) else None
            if current and isinstance(yv, (int, float)) and 2000 < int(yv) < 2100:
                metric_cols[j] = (current, int(yv))
        data_rows = [r for r in rows[hi + 2:] if any(v not in (None, "") for v in r)]
        col = {h: j for j, h in enumerate(hdr) if h}
        for r in data_rows:
            name = clean(r[col["Draup Portfolio Name"]]) if "Draup Portfolio Name" in col else None
            if not name: continue
            domain = clean(r[col["Domain URL"]]) if "Domain URL" in col else None
            def g(h): return clean(r[col[h]]) if h in col and col[h] < len(r) else None
            firm = g("PE Firm Name")
            fy = g("Founded Year")
            attrs = {"domain": domain_key(domain), "founded_year": int(fy) if isinstance(fy, (int, float)) else None,
                     "primary_vertical": g("Primary Vertical"), "sub_vertical": g("Sub Vertical"),
                     "hq_location": g("Headquarter's Location"), "hq_country": g("Headquarter's Country"),
                     "hq_region": g("Headquarter's Region"), "company_type": g("Company Type"), "_dashboard": True}
            fin = []
            for j, (metric, fy_) in metric_cols.items():
                if j < len(r):
                    v = num(r[j])
                    if v is not None: fin.append((metric, fy_, v))
            self.dash_rows.append({"name": str(name).strip(), "nk": norm(name), "domain": domain_key(domain),
                                   "month": month, "attrs": attrs, "fin": fin, "seq": len(self.dash_rows)})
            if firm:
                self.firm_id(firm, create=True, source="dashboard")

    def load_links(self, ws, month, tag):
        rows = rows_of(ws)
        hi, hdr = find_header(rows, must=("S.No",), search=8)
        for r in table(rows, hi, hdr):
            firm = clean(r.get("PE Firm Name")) or clean(r.get("PE Firm"))
            shortl = clean(r.get("Shortlisted Portfolio Name")) or clean(r.get("Portfolio Company Name"))
            draup = clean(r.get("Draup Portfolio Name")) or shortl
            if not firm or not draup: continue
            fid = self.firm_id(firm, create=True, source="links")
            ck = self.resolve_company(draup)
            self.companies[ck]["link_months"].add(month)
            platform = clean(r.get("Platform Status")) or clean(r.get("Company Present in Draup Platform (Yes/-)"))
            sig = clean(r.get("Signal Presence for Portfolio Companies (Yes/-)"))
            k = (fid, ck, month)
            self.links[k] = {"firm_id": fid, "company_key": ck, "reporting_month": month,
                             "shortlisted_name": shortl, "matched_name": draup,
                             "platform_status": platform, "signal_presence": sig, "source_tag": tag,
                             "primary_vertical": clean(r.get("Primary Vertical"))}

    def load_pe_firm_status(self, ws, month):
        rows = rows_of(ws)
        hi, hdr = find_header(rows, must=("S.No",), search=8)
        for r in table(rows, hi, hdr):
            name = clean(r.get("PE Firm")); cnt = num(r.get("Portfolio Count")); status = clean(r.get("Status"))
            if not name: continue
            fid = self.firm_id(name, create=True, source="firm_status")
            self.add_firm_alias(fid, name)
            self.snapshots[(fid, month)] = {"firm_id": fid, "reporting_month": month, "requested_name": None,
                                            "draup_name": name, "status": status,
                                            "portfolio_count": int(cnt) if cnt is not None else None}

    def load_stakeholders(self, path):
        wb = load_workbook(path, data_only=True)
        ws = wb["Sheet1"]
        rows = rows_of(ws)
        hdr = [str(v).strip() if v is not None else "" for v in rows[0]]
        # real hyperlink targets for LinkedIn cells
        links = {}
        for row in ws.iter_rows(min_row=2):
            for c in row:
                if c.hyperlink is not None and c.hyperlink.target: links[(c.row, c.column)] = c.hyperlink.target
        li_col = hdr.index("LinkedIn Profile") + 1
        for i, r in enumerate(rows[1:], start=2):
            rec = {h: r[j] for j, h in enumerate(hdr) if h and j < len(r)}
            pe = clean(rec.get("PE"))
            if not pe or not clean(rec.get("PE Leaders")): continue
            fid = self.firm_id(pe, create=True, source="stakeholders")
            self.add_firm_alias(fid, pe)
            li = links.get((i, li_col)) or clean(rec.get("Evidence URL")) if str(clean(rec.get("LinkedIn Profile")) or "").lower() == "link" else clean(rec.get("LinkedIn Profile"))
            flag = lambda k: str(clean(rec.get(k)) or "").strip().lower() == "yes"
            def d(k):
                return iso(rec.get(k)) if isinstance(rec.get(k), (dt.datetime, dt.date)) else clean(rec.get(k))
            self.stakeholders.append({
                "sr_no": clean(rec.get("Sr. No.")), "firm_id": fid, "name": str(clean(rec.get("PE Leaders"))).strip(),
                "designation": clean(rec.get("Designation")), "da_m": flag("DA&M"), "cybersecurity": flag("Cybersecurity"),
                "bfsi": flag("BFSI"), "healthcare": flag("Healthcare"), "in_organization": clean(rec.get("Yes/No")),
                "linkedin_url": li, "verification_status": clean(rec.get("Verification Status")),
                "current_company": clean(rec.get("Current Company")), "current_title": clean(rec.get("Current Title")),
                "proposed_status": clean(rec.get("Proposed Status (col G)")), "evidence_url": clean(rec.get("Evidence URL")),
                "evidence": clean(rec.get("Evidence")), "confidence": clean(rec.get("Confidence")),
                "successor_name": clean(rec.get("Successor - Name")), "successor_title": clean(rec.get("Successor - Title")),
                "successor_linkedin": clean(rec.get("Successor - LinkedIn")), "successor_evidence": clean(rec.get("Successor - Evidence")),
                "checked_on": d("Checked On"), "reviewer_note": clean(rec.get("Reviewer Note")),
                "current_role_tenure": clean(rec.get("Current Role Tenure")), "current_role_since": clean(rec.get("Current Role Since")),
                "career_length": clean(rec.get("Career Length (1st role→now)")), "prior_roles": clean(rec.get("# Prior Roles")),
                "career_history": clean(rec.get("Career History (dated)")),
                "initial_outreach_date": d("Initial Outreach Date"), "followup_date": d("Follow-Up Date"),
                "followup_response": clean(rec.get("Follow-Up Response")), "remark": clean(rec.get("Remark/Notes")),
                "source_row": i,
            })
        self.log(f"stakeholders loaded: {len(self.stakeholders)}")

    # ---------- output ----------
    def write(self, out_path):
        out = Path(out_path)
        if out.exists(): out.unlink()
        con = sqlite3.connect(out)
        con.executescript(SCHEMA)
        # firms
        for f in self.firms.values():
            con.execute("INSERT INTO pe_firms(id,canonical_name,requested_name,draup_name,in_account_list,source) VALUES (?,?,?,?,?,?)",
                        (f["id"], f["canonical_name"], f["requested_name"], f["draup_name"], f["in_account_list"], f["source"]))
        # companies
        cid = {}
        for n, (k, c) in enumerate(sorted(self.companies.items()), start=1):
            cid[k] = n
            months = sorted(c["dashboard_months"])
            con.execute("""INSERT INTO companies(id,company_key,display_name,norm_name,domain,founded_year,primary_vertical,
                sub_vertical,hq_location,hq_country,hq_region,company_type,has_profile,profile_months,link_months,stub)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (n, k, c["display_name"], c["norm_name"], c.get("domain"), c.get("founded_year"), c.get("primary_vertical"),
                 c.get("sub_vertical"), c.get("hq_location"), c.get("hq_country"), c.get("hq_region"), c.get("company_type"),
                 1 if months else 0, ",".join(months), ",".join(sorted(c["link_months"])), c.get("stub", 0)))
        # financials
        for (k, m, fy, metric), v in self.fin.items():
            con.execute("INSERT OR REPLACE INTO company_financials(company_id,reporting_month,fiscal_year,metric,value_usd_mm) VALUES (?,?,?,?,?)",
                        (cid[k], m, fy, metric, v))
        # links
        for (fid, k, m), l in self.links.items():
            con.execute("""INSERT INTO firm_portfolio_links(firm_id,company_id,reporting_month,shortlisted_name,matched_name,
                platform_status,signal_presence,primary_vertical,source_tag) VALUES (?,?,?,?,?,?,?,?,?)""",
                (fid, cid[k], m, l["shortlisted_name"], l["matched_name"], l["platform_status"], l["signal_presence"],
                 l["primary_vertical"], l["source_tag"]))
        # account snapshots with derived portfolio counts
        per_firm_month = Counter((l["firm_id"], l["reporting_month"]) for l in self.links.values())
        for (fid, m), s in self.snapshots.items():
            cnt = s["portfolio_count"] if s["portfolio_count"] is not None else per_firm_month.get((fid, m), 0)
            con.execute("""INSERT INTO pe_account_snapshots(firm_id,reporting_month,requested_name,draup_name,status,
                portfolio_count) VALUES (?,?,?,?,?,?)""", (fid, m, s["requested_name"], s["draup_name"], s["status"], cnt))
        # signals
        sid = {}
        for n, (k, s) in enumerate(self.signals.items(), start=1):
            sid[k] = n
            con.execute("""INSERT INTO market_signals(id,dedupe_key,scope,firm_id,company_id,company_name,primary_vertical,
                news_title,news_description,news_url,category,publication_date,publication_month,source_tag,row_number)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (n, k, s["scope"], s.get("firm_id"), cid.get(s.get("company_key")), s["company_name"], s.get("primary_vertical"),
                 s["news_title"], s.get("news_description"), s.get("news_url"), s["category"], s["publication_date"],
                 s["publication_month"], s["source_tag"], s["row_number"]))
        for k, m, tag, row in self.sig_obs:
            con.execute("INSERT INTO signal_observations(signal_id,reporting_month,source_tag,source_row) VALUES (?,?,?,?)",
                        (sid[k], m, tag, row))
        # stakeholders
        for n, s in enumerate(self.stakeholders, start=1):
            cols = ["sr_no","firm_id","name","designation","da_m","cybersecurity","bfsi","healthcare","in_organization",
                    "linkedin_url","verification_status","current_company","current_title","proposed_status","evidence_url",
                    "evidence","confidence","successor_name","successor_title","successor_linkedin","successor_evidence",
                    "checked_on","reviewer_note","current_role_tenure","current_role_since","career_length","prior_roles",
                    "career_history","initial_outreach_date","followup_date","followup_response","remark","source_row"]
            vals = [int(s[c]) if isinstance(s[c], bool) else s[c] for c in cols]
            con.execute(f"INSERT INTO stakeholders(id,{','.join(cols)}) VALUES (?,{','.join('?'*len(cols))})", [n] + vals)
        con.commit()
        con.close()
        return sid, cid

SCHEMA = """
CREATE TABLE pe_firms(id INTEGER PRIMARY KEY, canonical_name TEXT NOT NULL, requested_name TEXT, draup_name TEXT,
  in_account_list INTEGER, source TEXT);
CREATE TABLE pe_account_snapshots(firm_id INTEGER, reporting_month TEXT, requested_name TEXT, draup_name TEXT,
  status TEXT, portfolio_count INTEGER, PRIMARY KEY(firm_id, reporting_month));
CREATE TABLE companies(id INTEGER PRIMARY KEY, company_key TEXT UNIQUE, display_name TEXT, norm_name TEXT, domain TEXT,
  founded_year INTEGER, primary_vertical TEXT, sub_vertical TEXT, hq_location TEXT, hq_country TEXT, hq_region TEXT,
  company_type TEXT, has_profile INTEGER, profile_months TEXT, link_months TEXT, stub INTEGER);
CREATE TABLE company_financials(company_id INTEGER, reporting_month TEXT, fiscal_year INTEGER, metric TEXT,
  value_usd_mm REAL, PRIMARY KEY(company_id, reporting_month, fiscal_year, metric));
CREATE TABLE firm_portfolio_links(id INTEGER PRIMARY KEY, firm_id INTEGER, company_id INTEGER, reporting_month TEXT,
  shortlisted_name TEXT, matched_name TEXT, platform_status TEXT, signal_presence TEXT, primary_vertical TEXT, source_tag TEXT);
CREATE TABLE market_signals(id INTEGER PRIMARY KEY, dedupe_key TEXT UNIQUE, scope TEXT, firm_id INTEGER, company_id INTEGER,
  company_name TEXT, primary_vertical TEXT, news_title TEXT, news_description TEXT, news_url TEXT, category TEXT,
  publication_date TEXT, publication_month TEXT, source_tag TEXT, row_number INTEGER);
CREATE TABLE signal_observations(signal_id INTEGER, reporting_month TEXT, source_tag TEXT, source_row INTEGER);
CREATE TABLE stakeholders(id INTEGER PRIMARY KEY, sr_no INTEGER, firm_id INTEGER, name TEXT, designation TEXT,
  da_m INTEGER, cybersecurity INTEGER, bfsi INTEGER, healthcare INTEGER, in_organization TEXT, linkedin_url TEXT,
  verification_status TEXT, current_company TEXT, current_title TEXT, proposed_status TEXT, evidence_url TEXT, evidence TEXT,
  confidence TEXT, successor_name TEXT, successor_title TEXT, successor_linkedin TEXT, successor_evidence TEXT,
  checked_on TEXT, reviewer_note TEXT, current_role_tenure TEXT, current_role_since TEXT, career_length TEXT,
  prior_roles TEXT, career_history TEXT, initial_outreach_date TEXT, followup_date TEXT, followup_response TEXT,
  remark TEXT, source_row INTEGER);
CREATE INDEX ix_links_firm ON firm_portfolio_links(firm_id, reporting_month);
CREATE INDEX ix_links_company ON firm_portfolio_links(company_id);
CREATE INDEX ix_sig_company ON market_signals(company_id, publication_month);
CREATE INDEX ix_sig_firm ON market_signals(firm_id);
CREATE INDEX ix_sig_month ON market_signals(publication_month);
CREATE INDEX ix_fin ON company_financials(company_id);
CREATE INDEX ix_stk_firm ON stakeholders(firm_id);
"""

def main(folder, out_db):
    b = Builder()
    folder = Path(folder)
    files, FILE_MAP = {}, {}
    for p in sorted(folder.glob("*.xlsx")):
        for pattern, month, role in FILE_PATTERNS:
            if __import__("re").search(pattern, p.name, __import__("re").IGNORECASE):
                if pattern in files: sys.exit(f"Two workbooks match {pattern}: {files[pattern].name} and {p.name}")
                files[pattern] = p
                FILE_MAP[pattern] = (month, role)
    missing = [pat for pat, _, _ in FILE_PATTERNS if pat not in files]
    if missing:
        sys.exit(f"Missing workbooks for: {missing}. Expected nine .xlsx files with dates 30Apr, 18May, 11Jun, 16Jul, 18Aug, 11Sep, 09Oct, 13Nov and the Stakeholders file.")
    # Account status and dashboards in month order; links after dashboards; signals after companies exist.
    ordered = sorted([t for t in FILE_MAP if FILE_MAP[t][1] != "stakeholders"], key=lambda t: MONTH_ORDER.index(FILE_MAP[t][0]))
    # Source tag = the matched date label, e.g. "13Nov"; stored in the database, not shown in the UI.
    # Pass 1: account status, firm status and company dashboards for every month
    for tag in ordered:
        month = FILE_MAP[tag][0]
        wb = load_workbook(files[tag], read_only=True, data_only=True)
        names = wb.sheetnames
        if "PE Firms Account Status" in names: b.load_account_status(wb["PE Firms Account Status"], month)
        if "PE Firm Status" in names: b.load_pe_firm_status(wb["PE Firm Status"], month)
        if "Portfolio Company Dashboard" in names: b.load_dashboard(wb["Portfolio Company Dashboard"], month, tag)
        wb.close()
    b.build_entities()
    # Pass 2: portfolio links and news signals, resolved to the merged company entities
    for tag in ordered:
        month = FILE_MAP[tag][0]
        wb = load_workbook(files[tag], read_only=True, data_only=True)
        names = wb.sheetnames
        if "Portfolio Companies List" in names: b.load_links(wb["Portfolio Companies List"], month, tag)
        if "Signals for PE Firms" in names: b.load_signals(wb["Signals for PE Firms"], month, tag, "PE")
        if "Signals for Portfolio Companies" in names: b.load_signals(wb["Signals for Portfolio Companies"], month, tag, "PORTFOLIO")
        wb.close()
        b.log(f"loaded {tag} as reporting month {month}")
    b.load_stakeholders(files["Stakeholders"])
    sid, cid = b.write(out_db)
    # run-level validation report
    con = sqlite3.connect(out_db)
    stats = {
        "pe_firms": con.execute("SELECT COUNT(*) FROM pe_firms").fetchone()[0],
        "pe_firms_in_account_list": con.execute("SELECT COUNT(*) FROM pe_firms WHERE in_account_list=1").fetchone()[0],
        "companies_total": con.execute("SELECT COUNT(*) FROM companies").fetchone()[0],
        "companies_with_profile": con.execute("SELECT COUNT(*) FROM companies WHERE has_profile=1").fetchone()[0],
        "companies_stub": con.execute("SELECT COUNT(*) FROM companies WHERE stub=1").fetchone()[0],
        "market_signals_unique": con.execute("SELECT COUNT(*) FROM market_signals").fetchone()[0],
        "signal_observations": con.execute("SELECT COUNT(*) FROM signal_observations").fetchone()[0],
        "stakeholders": con.execute("SELECT COUNT(*) FROM stakeholders").fetchone()[0],
        "links": con.execute("SELECT COUNT(*) FROM firm_portfolio_links").fetchone()[0],
    }
    con.close()
    report = {"stats": stats, "log": b.report}
    Path(out_db).with_suffix(".build_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(stats, indent=2))

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
