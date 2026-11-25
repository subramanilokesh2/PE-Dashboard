# BUILD_STATUS: ZINNOV PE Intelligence Command Center

Build date: 25 Nov 2026. Source: nine workbooks in the PE-Platform project (Apr to Nov 2026 snapshots, Apr to Oct 2026 news, stakeholder file dated 9 Sep 2026).

## What was built

All eight modules are implemented and reachable from the navigation:

1. Executive Overview: ten KPI cards with definitions, a six-section narrative of about 500 words computed from the database, trend and distribution charts, and data caveats.
2. PE Account Intelligence: account funnel, ranking, searchable and sortable directory, CSV export, and a firm profile drawer.
3. Portfolio Intelligence: KPI cards, industry, region and firm distributions, revenue versus IT spend scatter (missing values excluded), directory, and company profile drawer.
4. Market Signals: unique news items, category and publication trends, filters (category, level, publication month range, keyword), and a signal drawer with source link.
5. Industry Intelligence: industry table with coverage columns, concentration chart, and an industry drill-down to companies.
6. Stakeholder Intelligence: verification KPIs, status and confidence distributions, directory with sector and status filters, and profile drawer (successors labelled as unconfirmed).
7. Opportunity Intelligence: priority distribution, capability alignment, account ranking, industry heatmap, directory with filters, and a nine-question detail drawer with score components.
8. Outreach Intelligence: recorded outreach fields with derived status categories, directory with status filter, and a stakeholder drawer.

Global filters: reporting month, PE firm, industry and region, shared across modules, with reset, a filter count, and persistence in the browser.

## What was verified (actual runs)

- `tests\test_api.py`: 13 tests pass. They cover all endpoints, CSV exports, the 44-firm target list, overview counts against the database, 24,493 unique signals, no duplicate domains or normalised names, no email exposure, missing financials returned as null, opportunity score bands, publication versus reporting month separation, and outreach wording.
- Browser run (headless Chromium): all eight modules load with data and open a drawer. Zero console or page errors.
- Filter check in the browser: selecting a firm changes the overview to that firm's snapshot (1 targeted firm, 94 companies in November). Adding an industry narrows it further. Reset restores totals (44 firms, 4,931 companies).
- Rebuild from the original workbook file names produced identical counts to the earlier build.

## Key figures in the database

| Item | Value |
|---|---|
| Targeted PE firms (account list) | 44 |
| Stakeholder-only firms (not on target list) | 15 |
| Companies (merged entities) | 5,639 (3,403 with profiles; 2,236 name-only stubs) |
| Portfolio links, Apr to Nov snapshots | 39,473 |
| Unique market signals | 24,493 (843 PE-level; 23,650 portfolio-level) |
| Stakeholders | 228 (201 Confirmed, 17 Left Organization, 10 Title Changed) |
| Opportunity hypotheses | 8,251 (395 Critical, 3,317 High, 4,538 Medium, 1 Low) |

## Data handling decisions

- Reporting month comes from the workbook name. Publication month comes from each news row.
- Company identity: rows merge when they share a valid domain or a normalised name. Legal suffixes are ignored for matching only. Invalid domain cells (for example, a company name in the domain column) are ignored.
- The requested firm name is the display name. The Draup match is shown alongside it.
- Historical associations are shown as snapshot records. They are not presented as verified ownership.
- Missing revenue and IT spend stay missing. The only exception is opportunity scale, which uses a neutral 0.3 and is flagged in the notes.
- Stakeholder email addresses are not stored or displayed. Successor candidates are labelled as unconfirmed.
- Source workbook file names do not appear in the interface.

## Deviations from the brief (read before presenting)

- **Stack**: Flask, SQLite and vanilla JavaScript were used instead of FastAPI, React, Vite, Tailwind, shadcn/ui, TanStack and Zustand. The build environment cannot reach package registries, which is the same limitation that shaped the October build. The app needs no Node.js and no build step.
- **Charts**: hand-written SVG and CSS bars, not ECharts or Recharts. Animation is CSS only (no Motion library).
- **Narrative**: deterministic templates over computed figures. No AI model is used, so every sentence traces to a query.
- **Filters**: single-select dropdowns, not searchable multi-select. Filters do not cascade (every option stays visible). Numeric range sliders and removable chips are not implemented.
- **Not implemented**: column show/hide, three-company comparison, full-text search index, server-side Excel export (CSV exports are provided), and a company-level "IT spend as % of revenue" trend.
- **Windows scripts**: `SETUP.bat`, `START.bat`, `find_port.py` and `wait_ready.py` were written to the brief but were not executed on Windows in this environment. The manual commands in the README use the same steps.
- **Branding**: the palette uses the provisional Zinnov fallback colours from the brief, not verified brand values. The wordmark is text only. No logo was created.
- **Time**: the brief allowed 20 minutes. The build took longer. The result is a working, tested application, not the full specification.

## Data caveats (also shown in the app)

1. The reporting month and publication month differ. The 13 Nov workbook contains October news.
2. The 30 Apr workbook has no signal sheets. April news appears in the 18 May workbook.
3. Only 15 of the 44 targeted firms have stakeholder records.
4. Only about 238 snapshot companies report revenue and IT spend in November. August and September are sparser still.
5. Stakeholder verification is dated 4 Sep 2026 and not re-verified.
6. 194 stakeholders have an outreach date. These values may be planned or bulk-entered. Empty responses are not treated as rejections.
7. Some "Center Setup and Expansion" items describe data-centre or infrastructure news. Category-to-capability rules are deterministic, so each hypothesis needs review against its source.
8. The 18 May workbook's internal label says March and April. Its dated rows are April, and the builder uses the rows.

## Open items

- Confirm the firm and company counts with the data owner. The source summary and the data differ slightly (for example, 43 versus 44 firms).
- Run `START.bat` on a Windows laptop and complete a visual review in the browser at 1920 by 1080 and on a laptop-sized screen.
- Decide whether to refresh stakeholder LinkedIn checks before the CEO session. The current data is from early September.
