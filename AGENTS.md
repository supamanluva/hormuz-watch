# Hormuz Watch — Agent Guide

A static, single-page dashboard that tracks oil prices and shipping through the Strait of Hormuz during the 2026 US/Israel–Iran war. It pulls core status data live in the visitor's browser from the CORS-open `straits.live` API, so there is no backend and no build step. A trigger-monitoring layer adds keyless browser-side sources (CFTC, Polymarket, ECB FX) plus a repo poller (GitHub Actions) that collects sources browsers can't fetch cross-origin (RSS, GDELT, aisstream.io) into `data/`. A small Python history archiver runs once a day to preserve CSV snapshots.

## Project structure

```text
.
├── index.html                  # Entire application: HTML, CSS and vanilla JS
├── logger.py                   # Daily status / feed archiver (Python stdlib only)
├── poller.py                   # ~20-min poller: RSS feeds, GDELT, aisstream → data/
├── README.md                   # Human-facing project overview and run instructions
├── .gitignore                  # Ignores history/logger.log and .light-test.html
├── .github/
│   └── workflows/
│       ├── log-history.yml     # GitHub Action that runs logger.py daily and commits
│       └── poll-feeds.yml      # GitHub Action that runs poller.py ~every 20 min and commits data/
├── data/
│   ├── feeds.json              # Political signals (Trump, White House, IAEA, UN, OFAC, IRNA, Al Jazeera)
│   ├── gdelt.json              # US–Iran rhetoric tone + strike-report volume (server-side; GDELT is CORS-unreliable)
│   └── ais_transits.json       # Hourly live-AIS presence counts, Hormuz + Bab el-Mandeb (needs AISSTREAM_KEY secret)
└── history/
    ├── events.csv              # Mirrored war/diplomacy event feed
    ├── oil.csv                 # Mirrored Brent/WTI price history
    ├── status_history.csv      # Appended daily one-row status snapshots
    └── transits.csv          # Mirrored daily AIS transit counts
```

## Technology stack

- **Frontend**: Plain HTML5, CSS and vanilla JavaScript in one file. No frameworks, bundlers or package managers.
- **Maps**: Leaflet 1.9.4 loaded from `unpkg.com`.
- **Fonts**: Archivo + Inter from Google Fonts (with system-font fallbacks).
- **Charts**: hand-rolled SVG (no chart library); the Leaflet map tiles follow the active theme.
- **Styling**: CSS custom properties (`[data-theme]`) with a dark-first design and a manual light/dark toggle persisted in `localStorage` (key `hw-theme`).
- **Data APIs**:
  - `https://straits.live` (CORS-open, no key) — core status: IMF PortWatch, Yahoo Finance / EIA, GDELT + curated events.
  - Keyless browser-side: CFTC COT via Socrata (`publicreporting.cftc.gov`), Polymarket Gamma (`gamma-api.polymarket.com`), Frankfurter ECB FX (`api.frankfurter.dev`).
  - Free embedded keys (constants at the top of the script in `index.html`; quota-limited, not secret): `EIA_KEY` (EIA API v2 weekly stocks — its futures route was discontinued April 2024), `FIRMS_KEY` (NASA FIRMS fire detections). Cards degrade gracefully while a constant is still `"PUT_KEY_HERE"`.
  - Repo-polled into `data/` (fetched same-origin): political RSS feeds, GDELT DOC API, aisstream.io live AIS (`AISSTREAM_KEY` GitHub repo secret — never in code).
- **History tooling**: Python 3 with only the standard library (`csv`, `io`, `urllib.request`, `pathlib`). `poller.py` is stdlib-only too, except the AIS step which uses `websocket-client` (pip-installed in CI only).
- **Hosting**: Static site published on GitHub Pages at `https://supamanluva.github.io/hormuz-watch/`.
- **Automation**: GitHub Actions (`ubuntu-latest`) cron job.

## Build and run

There is no build step.

Local preview:

```sh
cd ~/hormuz-watch
python3 -m http.server 8181
# open http://localhost:8181
```

The dashboard auto-refreshes tiles every 60 seconds and full data/charts every 5 minutes.

## Repo poller (`poller.py`)

Runs every ~20 minutes via `.github/workflows/poll-feeds.yml`, commits `data/`:

- **RSS → `data/feeds.json`**: normalizes and keyword-tags items from trumpstruth.org (Trump posts, highlighted), White House, IAEA, UN press, OFAC, IRNA and Al Jazeera. Merges with previous runs, dedupes by URL, caps per source (25) and total (60).
- **GDELT → `data/gdelt.json`**: US/Iran rhetoric tone (`tonechart`) and energy-infrastructure strike-report volume (`timelinevol`). Polled server-side because GDELT omits CORS headers on rate-limited responses, breaking browser fetches.
- **AIS → `data/ais_transits.json`**: opens an aisstream.io websocket for ~10 min per run over two bounding boxes (Hormuz, Bab el-Mandeb) and writes hourly unique-MMSI presence counts (total + tanker). Requires the `AISSTREAM_KEY` repo secret; skips cleanly without it.

Run locally (RSS + GDELT always, AIS if `AISSTREAM_KEY` and `websocket-client` are present):

```sh
python3 poller.py
```

## History archiver (`logger.py`)

`logger.py` fetches the current `/data/status.csv` and appends one row to `history/status_history.csv` per calendar day. It also mirrors the full-history feeds `events.csv`, `oil.csv` and `transits.csv` from `/data/*`.

Run locally:

```sh
python3 logger.py
```

In CI it is run daily at 10:20 UTC by `.github/workflows/log-history.yml`, which commits `history/` to the repo.

## Code conventions

- Keep the frontend in a single self-contained `index.html` file.
- Vanilla JS only; no npm dependencies or bundlers.
- CSS uses custom properties scoped to `[data-theme="dark"]` / `[data-theme="light"]`; the theme toggle re-renders charts and switches map tiles.
- Python scripts use the standard library only (exception: `poller.py`'s AIS step imports `websocket-client`, installed in CI only).
- CSV files are the canonical archive format; JSON files in `data/` are the canonical poller-output format.

## Testing

There are no automated tests in the repository. Verify changes by:

1. Running `python3 -m http.server` and loading the page.
2. Checking the browser console for API or render errors (headless Chrome screenshots work well for visual checks).
3. Running `python3 logger.py` and inspecting `history/status_history.csv` and the mirrored `history/*.csv` files.
4. Running `python3 poller.py` and inspecting `data/feeds.json` / `data/gdelt.json` (AIS skips without `AISSTREAM_KEY`).

## Deployment

Push to `main` on GitHub; GitHub Pages serves `index.html` from the repo root. The GitHub Action that commits daily history requires `contents: write` permission and pushes as the `hormuz-watch-bot` identity.

## Security considerations

- **No backend / one repo secret**: Browser-side API calls use public keyless endpoints plus two embedded quota-limited keys (`EIA_KEY`, `FIRMS_KEY`) — these are rate-limit tokens by design, not secrets. The only true secret is `AISSTREAM_KEY`, stored as a GitHub Actions repo secret and used only by `poller.py` in CI; it must never be committed.
- **External dependencies**: Leaflet and the straits.live API are loaded from third-party URLs, and the trigger layer adds CFTC/Polymarket/Frankfurter/EIA/FIRMS/GDELT plus several RSS feeds. Changes to any of those endpoints can break parts of the page — every source is optional and fails independently.
- **Writable GitHub Actions**: `log-history.yml` force-commits `history/` daily and `poll-feeds.yml` commits `data/` every ~20 min, both with `contents: write`. Any change to the workflows, `logger.py` or `poller.py` should be reviewed for injection risks, because the output is committed automatically. `poller.py` additionally parses third-party RSS/JSON/websocket data — it writes it verbatim into JSON files (no code execution), but malformed input can cause poll failures.
- **CSV parsing**: The Python logger uses `csv.reader` on externally fetched data. It does not execute or evaluate the contents, but malformed CSV can cause archive failures.
