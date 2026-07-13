#!/usr/bin/env python3
"""Append the current Hormuz status snapshot to a local CSV history.

straits.live only retains limited history on some feeds; running this daily
(cron/systemd timer) builds your own archive alongside the dashboard.

Usage:  python3 logger.py            # append snapshot + refresh full-history CSVs
"""
import csv
import io
import sys
import urllib.request
from pathlib import Path

BASE = "https://straits.live"
HERE = Path(__file__).resolve().parent
HIST = HERE / "history"
SNAPSHOT_FILE = HIST / "status_history.csv"
MIRRORS = {  # full-history feeds worth mirroring verbatim
    "oil.csv": f"{BASE}/data/oil.csv",
    "transits.csv": f"{BASE}/data/transits.csv",
    "events.csv": f"{BASE}/data/events.csv",
}


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "hormuz-watch-logger/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8")


def append_snapshot() -> None:
    HIST.mkdir(exist_ok=True)
    text = fetch(f"{BASE}/data/status.csv")
    rows = list(csv.reader(io.StringIO(text)))
    if len(rows) < 2:
        sys.exit("unexpected status.csv shape")
    header, snapshot = rows[0], rows[1]

    existing = []
    if SNAPSHOT_FILE.exists():
        existing = list(csv.reader(SNAPSHOT_FILE.open()))
    # dedupe: skip if we already logged this calendar day (as_of is column 0)
    day = snapshot[0][:10]
    if any(r and r[0][:10] == day for r in existing[1:]):
        print(f"already logged {day}, skipping snapshot")
    else:
        new_file = not existing
        with SNAPSHOT_FILE.open("a", newline="") as f:
            w = csv.writer(f)
            if new_file:
                w.writerow(header)
            w.writerow(snapshot)
        print(f"logged snapshot for {day} → {SNAPSHOT_FILE}")


def mirror_feeds() -> None:
    for name, url in MIRRORS.items():
        try:
            (HIST / name).write_text(fetch(url))
            print(f"mirrored {name}")
        except Exception as e:  # keep going; one bad feed shouldn't kill the run
            print(f"warn: {name}: {e}", file=sys.stderr)


if __name__ == "__main__":
    append_snapshot()
    mirror_feeds()
