"""Endpoint, reconciliation and data-rule tests. Run:  python -m unittest discover -s tests -v"""
import sys, json, sqlite3, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
import app as A  # noqa: E402

class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = A.app.test_client()
        cls.con = sqlite3.connect(A.DB)

    @classmethod
    def tearDownClass(cls):
        cls.con.close()

    def get(self, url):
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200, f"{url} -> {r.status_code}")
        return r

    def test_every_endpoint_responds(self):
        urls = ["/api/meta", "/api/data-notes", "/api/overview", "/api/accounts", "/api/accounts/1",
                "/api/portfolio/summary", "/api/portfolio?size=5&sort=revenue_usd_mm&dir=desc",
                "/api/portfolio?firm=1&q=zscaler", "/api/portfolio/1", "/api/signals/summary",
                "/api/signals?size=5", "/api/signals?firm=1&size=5", "/api/signals?industry=Enterprise%20Software&scope=PORTFOLIO",
                "/api/signals/1", "/api/industry", "/api/industry/companies?industry=Enterprise%20Software&size=3",
                "/api/stakeholders/summary", "/api/stakeholders?size=5", "/api/stakeholders/1",
                "/api/opportunities/summary", "/api/opportunities?priority=Critical&size=5", "/api/opportunities/1",
                "/api/outreach/summary", "/api/outreach?size=5", "/api/outreach?status=No%20outreach%20recorded"]
        for u in urls:
            self.get(u)

    def test_csv_exports(self):
        for u in ["/api/accounts?format=csv", "/api/portfolio?format=csv&firm=1", "/api/signals?format=csv&category=Layoff",
                  "/api/stakeholders?format=csv", "/api/opportunities?format=csv&priority=Critical", "/api/outreach?format=csv"]:
            r = self.get(u)
            self.assertIn("text/csv", r.headers["Content-Type"], u)

    def test_meta_has_44_targeted_firms(self):
        firms = self.get("/api/meta").get_json()["firms"]
        self.assertEqual(len(firms), 44)

    def test_overview_portfolio_count_matches_database(self):
        k = self.get("/api/overview?month=2026-11").get_json()["kpis"]
        expected = self.con.execute("""SELECT COUNT(DISTINCT l.company_id) FROM firm_portfolio_links l
            JOIN pe_firms pe ON pe.id=l.firm_id WHERE l.reporting_month='2026-11'""").fetchone()[0]
        self.assertEqual(k["portfolio_companies"], expected)

    def test_unique_signals_match_build_report(self):
        total = self.get("/api/signals/summary").get_json()["kpis"]["unique_signals"]
        self.assertEqual(total, self.con.execute("SELECT COUNT(*) FROM market_signals").fetchone()[0])
        self.assertEqual(total, 24493)

    def test_no_duplicate_domains_or_names(self):
        dup_dom = self.con.execute("SELECT COUNT(*) FROM (SELECT domain FROM companies WHERE domain IS NOT NULL GROUP BY domain HAVING COUNT(*)>1)").fetchone()[0]
        dup_name = self.con.execute("SELECT COUNT(*) FROM (SELECT norm_name FROM companies GROUP BY norm_name HAVING COUNT(*)>1)").fetchone()[0]
        self.assertEqual(dup_dom, 0)
        self.assertEqual(dup_name, 0)

    def test_stakeholder_email_never_exposed(self):
        body = self.get("/api/stakeholders/1").get_data(as_text=True).lower()
        self.assertNotIn("email", body)
        self.assertNotIn("@", body)

    def test_missing_financials_are_null_not_zero(self):
        rows = self.get("/api/portfolio?size=200&sort=revenue_usd_mm&dir=asc").get_json()["rows"]
        missing = [r for r in rows if r["revenue_usd_mm"] is None]
        self.assertTrue(len(missing) > 0)
        self.assertTrue(all(r["revenue_usd_mm"] != 0 for r in rows))

    def test_opportunity_scores_and_bands(self):
        rows = self.con.execute("SELECT score, priority FROM opportunities").fetchall()
        self.assertTrue(rows)
        for score, prio in rows:
            self.assertTrue(0 <= score <= 100)
            band = "Critical" if score >= 85 else "High" if score >= 70 else "Medium" if score >= 50 else "Low"
            self.assertEqual(prio, band)

    def test_publication_month_is_not_reporting_month(self):
        # 13 Nov workbook holds October news: no publication in November should exist
        n = self.con.execute("SELECT COUNT(*) FROM market_signals WHERE publication_month='2026-11'").fetchone()[0]
        self.assertEqual(n, 0)
        obs = self.con.execute("SELECT COUNT(*) FROM signal_observations WHERE reporting_month='2026-11'").fetchone()[0]
        self.assertGreater(obs, 0)

    def test_april_has_no_signal_observations_from_its_own_workbook(self):
        n = self.con.execute("SELECT COUNT(*) FROM signal_observations WHERE reporting_month='2026-04'").fetchone()[0]
        self.assertEqual(n, 0)

    def test_outreach_empty_response_not_counted_as_rejection(self):
        body = self.get("/api/outreach/summary").get_json()
        self.assertIn("status_breakdown", body)
        names = [x["name"] for x in body["status_breakdown"]]
        self.assertFalse(any("reject" in n.lower() for n in names))

    def test_all_months_filter_is_safe(self):
        for m in ["2026-04", "2026-11", "2026-99"]:
            self.get(f"/api/overview?month={m}")

if __name__ == "__main__":
    unittest.main()
