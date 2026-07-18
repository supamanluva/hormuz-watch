# Hormuz Watch — Agent Guide

A static, single-page dashboard that tracks oil prices and shipping through the Strait of Hormuz during the 2026 US/Israel–Iran war. It pulls all data live in the visitor's browser from the CORS-open `straits.live` API, so there is no backend and no build step. A small Python history archiver runs once a day to preserve CSV snapshots.

## Project structure

```text
.
├── index.html                  # Entire application: HTML, CSS and vanilla JS
├── logger.py                   # Daily status / feed archiver (Python stdlib only)
├── README.md                   # Human-facing project overview and run instructions
├── .gitignore                  # Ignores history/logger.log and .light-test.html
├── .github/
│   └── workflows/
│       └── log-history.yml     # GitHub Action that runs logger.py daily and commits
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
- **Data API**: `https://straits.live` (CORS-open, no API key). It aggregates IMF PortWatch, Yahoo Finance / EIA, and GDELT + curated events.
- **History tooling**: Python 3 with only the standard library (`csv`, `io`, `urllib.request`, `pathlib`).
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
- Python scripts use the standard library only.
- CSV files are the canonical archive format.

## Testing

There are no automated tests in the repository. Verify changes by:

1. Running `python3 -m http.server` and loading the page.
2. Checking the browser console for API or render errors (headless Chrome screenshots work well for visual checks).
3. Running `python3 logger.py` and inspecting `history/status_history.csv` and the mirrored `history/*.csv` files.

## Deployment

Push to `main` on GitHub; GitHub Pages serves `index.html` from the repo root. The GitHub Action that commits daily history requires `contents: write` permission and pushes as the `hormuz-watch-bot` identity.

## Security considerations

- **No backend / no secrets**: All API calls happen in the browser from a public, keyless endpoint. There are no credentials or environment variables to protect.
- **External dependencies**: Leaflet and the straits.live API are loaded from third-party URLs. Changes to those endpoints can break the page.
- **Writable GitHub Action**: `log-history.yml` has `contents: write` and force-commits `history/` daily. Any change to the workflow or `logger.py` should be reviewed for injection risks, because the output is committed automatically.
- **CSV parsing**: The Python logger uses `csv.reader` on externally fetched data. It does not execute or evaluate the contents, but malformed CSV can cause archive failures.
