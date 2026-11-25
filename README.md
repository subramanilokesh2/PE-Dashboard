# ZINNOV | PE Intelligence Command Center

Eight modules for leadership review of targeted PE firms, portfolio companies, market news, stakeholders, opportunity hypotheses and outreach records.

## What you need

- Windows with **Python 3.13** installed and added to PATH (python.org installer, tick "Add python.exe to PATH").
- Visual Studio Code (optional, for opening the folder and using its terminal).
- No administrator rights are needed. No Node.js is needed: the front end is plain HTML, CSS and JavaScript.
- A modern browser (Edge or Chrome).

## Run it (first time)

1. Extract the whole ZIP to a folder such as `C:\Users\<you>\Documents\ZINNOV_PE_Intelligence_Command_Center`. Do not run it from inside the ZIP.
2. Open the folder in VS Code: *File > Open Folder*.
3. Open the terminal (*Terminal > New Terminal*). It opens PowerShell by default.
4. Run setup once:

   ```powershell
   .\SETUP.bat
   ```

5. Start the platform:

   ```powershell
   .\START.bat
   ```

   The script finds a free localhost port from 5055, starts the server, waits until it is ready and opens your browser at `http://127.0.0.1:<port>/`.
6. To stop, close the minimised **ZINNOV server** window in the taskbar.

You can also double-click `SETUP.bat` and `START.bat` in File Explorer.

## Run it manually (if the .bat files are blocked)

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe backend\app.py 5055
```

Then open `http://127.0.0.1:5055/` in your browser.

## Tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

These 13 tests call every API endpoint, reconcile key counts with the database, and check the data rules (no duplicate companies, no contact emails, missing financials shown as null, publication month kept separate from reporting month).

Optional browser check (needs internet access to install Playwright once):

```powershell
.\.venv\Scripts\python.exe -m pip install playwright
.\.venv\Scripts\python.exe -m playwright install chromium
.\.venv\Scripts\python.exe tests\browser_smoke.py http://127.0.0.1:5055
```

## Rebuild the database from the workbooks (optional)

The package already includes `data\intel.db`, so you do not need this for the demo. To rebuild from the nine source workbooks, keep them in one folder. The builder identifies each file by the date in its name (30Apr, 18May, 11Jun, 16Jul, 18Aug, 11Sep, 09Oct, 13Nov and the Stakeholders file).

```powershell
.\.venv\Scripts\python.exe scripts\build_db.py "C:\path\to\workbooks" data\intel.db
.\.venv\Scripts\python.exe scripts\derive_opportunities.py data\intel.db
```

The build writes `data\intel.build_report.json` with counts and an event log.

## How the data is organised

- **Reporting month** is the month in each workbook's name. It drives the portfolio, account and financial snapshots.
- **Publication month** is the date on each news row. The 13 Nov workbook holds October news. The 30 Apr workbook has no signal sheets, so April news appears in the 18 May workbook.
- **Historical associations** are snapshot records. They are not verified current ownership.
- **Stakeholder verification** is dated 4 Sep 2026 and was not re-run.
- **Opportunities** are hypotheses for human validation, scored with the weights shown in the Opportunity Intelligence module.
- **Stakeholder email addresses** are not stored or displayed.

## Folder layout

```
backend\app.py                 Flask API + static front end (binds to 127.0.0.1 only)
frontend\index.html            Single page shell
frontend\static\app.js         All eight modules, filters, tables, drawers, charts
frontend\static\styles.css     Zinnov palette and motion (respects reduced-motion)
data\intel.db                  Consolidated SQLite database (no credentials)
data\intel.build_report.json   Build counts and log
scripts\build_db.py            Workbook ingestion and normalisation
scripts\derive_opportunities.py Opportunity scoring
scripts\find_port.py           Picks a free localhost port
scripts\wait_ready.py          Waits for the server before opening the browser
tests\test_api.py              API and data-rule tests
tests\browser_smoke.py         Optional browser check
SETUP.bat / START.bat          One-click Windows setup and launch
requirements.txt               Flask (runtime), openpyxl (rebuild only)
BUILD_STATUS.md                What was built, what was verified, known limits
CEO_DEMO_GUIDE.md              Three-minute demonstration script
```

## Troubleshooting

- **"Python was not found"**: install Python 3.13 and tick *Add python.exe to PATH*, then close and reopen VS Code.
- **"Dependency installation failed"**: check internet or proxy access, then run `SETUP.bat` again.
- **Port in use**: `START.bat` chooses the next free port automatically. Use the address it prints.
- **Blank page or errors**: check the *ZINNOV server* window. Re-extract the ZIP in full if `data\intel.db` or `frontend\index.html` is missing.
- **Filters seem stuck**: click *Reset filters* in the top bar. Filter choices are remembered in the browser.
