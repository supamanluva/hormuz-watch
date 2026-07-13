# Hormuz Watch

**Live at: https://supamanluva.github.io/hormuz-watch/**

Dashboard tracking oil prices and shipping through the Strait of Hormuz
during the 2026 US/Israel–Iran war. Roughly 20% of global oil transits the
strait; it has been effectively closed to commercial shipping since 2026-02-28.

## What it shows

- **Verdict chip** — is the strait open or closed, and for how many days
- **Stat tiles** — Brent & WTI price (24 h change), daily transits vs the
  pre-crisis baseline of ~88 ships/day, tanker count, stranded vessels,
  war-risk insurance multiple
- **Crisis pressure / escalation meters** — straits.live Hormuz Index
- **Oil price chart** — Brent + WTI intraday history (Yahoo Finance / EIA)
- **Daily transits chart** — tankers vs other cargo per day (IMF PortWatch),
  with the pre-crisis median as a reference line
- **Supply buffers** — US Strategic Petroleum Reserve & Cushing stocks
  (EIA weekly) and Hormuz-bypass pipeline utilization
- **Events feed** — strikes, ship attacks, closure/negotiation news
  (GDELT + curated, 15-min refresh)

All data is fetched by the visitor's browser straight from the CORS-open
straits.live API, so the published page is always current — no backend,
no rebuilds.

## Run it

```sh
cd ~/hormuz-watch
python3 -m http.server 8181
# open http://localhost:8181
```

Tiles refresh every 60 s, charts every 5 min. Time-range buttons (7/30/90
days/All) scope both charts; each chart has a table view.

## Data source

Everything comes from the free tier of the [straits.live API](https://straits.live/api)
(CORS-open, no key), which aggregates:

- **IMF PortWatch** chokepoint 6 — daily AIS-derived transit counts
  (publishes with ~1 week lag)
- **Yahoo Finance / EIA** — Brent & WTI prices
- **GDELT + curated** — war/diplomacy events

## Build your own history

Some feeds only retain limited history. `logger.py` (stdlib only) appends the
daily one-row status snapshot to `history/status_history.csv` and mirrors the
full-history oil/transit/event CSVs:

```sh
python3 logger.py
```

Cron it daily, e.g. `crontab -e`:

```
15 9 * * * cd $HOME/hormuz-watch && python3 logger.py >> history/logger.log 2>&1
```

## Ideas / next steps

- Correlate transit count vs Brent (lagged) once enough history accumulates
- Alerting: notify when Brent moves > X% or transits fall below a threshold
  (straits.live also has RSS: `/feed.xml`, `/status/feed.xml`)
- Premium endpoints exist (per-vessel AIS manifests, $0.01–0.25 via x402)
  if you ever want ship-level data
