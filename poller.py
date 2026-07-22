#!/usr/bin/env python3
"""Frequent poller for sources a browser cannot fetch cross-origin.

Two outputs, both committed to the repo by the poll-feeds GitHub Action and
fetched same-origin by index.html:

  data/feeds.json        — normalized RSS items (political/diplomatic signals)
  data/ais_transits.json — hourly live-AIS vessel counts for Hormuz and
                           Bab el-Mandeb, collected from aisstream.io

The RSS part uses only the standard library. The AIS part needs the
`websocket-client` package (pip-installed in CI) and an AISSTREAM_KEY
environment variable; without either it skips cleanly.

Usage:  python3 poller.py            # RSS always, AIS if key + package present
"""
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
FEEDS_FILE = DATA / "feeds.json"
AIS_FILE = DATA / "ais_transits.json"

MAX_FEED_ITEMS = 60
MAX_PER_SOURCE = 25
AIS_KEEP_DAYS = 30

# (source label, feed URL, keep_all) — high-volume wires are keyword-filtered,
# low-volume official channels are kept whole.
FEEDS = [
    ("Trump · Truth Social", "https://trumpstruth.org/feed", True),
    ("White House", "https://www.whitehouse.gov/news/feed/", True),
    ("IAEA", "https://www.iaea.org/feeds/topnews", True),
    ("UN Press", "https://press.un.org/en/rss.xml", True),
    ("OFAC Sanctions", "https://ofac.treasury.gov/rss.xml", True),
    ("IRNA (Iran state wire)", "https://en.irna.ir/rss", False),
    ("Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml", False),
]

TAGS = {
    "strikes": ["strike", "missile", "drone", "airstrike", "attack", "explosion",
                "refinery", "pipeline", "airbase", "bombing"],
    "sanctions": ["sanction", "ofac", "designation", "embargo", "waiver"],
    "diplomacy": ["ceasefire", "cease-fire", "negotiat", "talks", "truce",
                  "agreement", "deal", "envoy", "mediation"],
    "nuclear": ["iaea", "nuclear", "enrichment", "centrifuge", "uranium"],
    "shipping": ["hormuz", "strait", "tanker", "vessel", "shipping", "red sea",
                 "bab el-mandeb", "suez", "freight"],
    "oil": ["oil", "crude", "brent", "wti", "opec", "petroleum", "barrel"],
}

# aisstream bounding boxes: [[south, west], [north, east]]
AIS_BOXES = {
    "hormuz": [[25.0, 56.0], [27.5, 57.8]],
    "bab": [[11.3, 42.5], [13.6, 45.2]],
}
AIS_LISTEN_SECONDS = int(os.environ.get("AIS_LISTEN_SECONDS", "600"))


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "hormuz-watch-poller/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def atomic_write_json(path: Path, obj) -> None:
    DATA.mkdir(exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1))
    tmp.replace(path)


def clean_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", text).strip()


def tag_for(title: str, summary: str) -> list:
    blob = (title + " " + summary).lower()
    return [tag for tag, words in TAGS.items() if any(w in blob for w in words)]


def parse_dt(raw: str) -> str:
    if not raw:
        return ""
    try:
        return parsedate_to_datetime(raw).astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError):
        pass
    try:  # Atom-style ISO
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat()
    except ValueError:
        return ""


def parse_feed(xml_bytes: bytes) -> list:
    """Parse RSS 2.0 or Atom into [{title, url, published, summary}]."""
    root = ET.fromstring(xml_bytes)
    items = []
    if root.tag.endswith("feed"):  # Atom
        ns = "{http://www.w3.org/2005/Atom}"
        for e in root.findall(f"{ns}entry"):
            link = ""
            for l in e.findall(f"{ns}link"):
                if l.get("rel", "alternate") == "alternate":
                    link = l.get("href", "")
                    break
            items.append({
                "title": clean_html(getattr(e.find(f"{ns}title"), "text", "")),
                "url": link,
                "published": parse_dt(clean_html(
                    getattr(e.find(f"{ns}published"), "text", "") or
                    getattr(e.find(f"{ns}updated"), "text", ""))),
                "summary": clean_html(getattr(e.find(f"{ns}summary"), "text", ""))[:400],
            })
    else:  # RSS 2.0
        for it in root.iter("item"):
            def txt(name):
                el = it.find(name)
                return clean_html(el.text if el is not None and el.text else "")
            items.append({
                "title": txt("title"),
                "url": txt("link"),
                "published": parse_dt(txt("pubDate") or txt("date")),
                "summary": txt("description")[:400],
            })
    return items


def poll_feeds() -> None:
    items = []
    for source, url, keep_all in FEEDS:
        try:
            for it in parse_feed(fetch(url)):
                tags = tag_for(it["title"], it["summary"])
                if not keep_all and not tags:
                    continue  # skip unrelated wire stories
                if not it["title"] or not it["url"]:
                    continue
                items.append({
                    "source": source,
                    "title": it["title"],
                    "url": it["url"],
                    "published": it["published"],
                    "summary": it["summary"],
                    "tags": tags,
                    "highlight": source == "Trump · Truth Social",
                })
            print(f"feed ok: {source}")
        except Exception as e:  # one bad feed must not kill the run
            print(f"warn: feed {source}: {e}", file=sys.stderr)

    # merge with what we already had, dedupe by URL, keep newest
    old = []
    if FEEDS_FILE.exists():
        try:
            old = json.loads(FEEDS_FILE.read_text()).get("items", [])
        except (json.JSONDecodeError, OSError):
            old = []
    by_url = {}
    for it in old + items:
        if it.get("url"):
            by_url[it["url"]] = it
    merged = sorted(by_url.values(),
                    key=lambda x: x.get("published") or "", reverse=True)
    # cap per source so a chatty channel (Trump posts) can't crowd out
    # rare-but-important ones (OFAC designations, IAEA updates)
    per_source, capped = {}, []
    for it in merged:
        n = per_source.get(it["source"], 0)
        if n < MAX_PER_SOURCE:
            capped.append(it)
            per_source[it["source"]] = n + 1
    merged = capped[:MAX_FEED_ITEMS]
    atomic_write_json(FEEDS_FILE, {
        "asOf": datetime.now(timezone.utc).isoformat(),
        "items": merged,
    })
    print(f"feeds: {len(merged)} items → {FEEDS_FILE}")


def box_for(lat: float, lon: float):
    for key, ((s, w), (n, e)) in AIS_BOXES.items():
        if s <= lat <= n and w <= lon <= e:
            return key
    return None


def poll_ais() -> None:
    key = os.environ.get("AISSTREAM_KEY")
    if not key:
        print("AIS: AISSTREAM_KEY not set, skipping")
        return
    try:
        import websocket  # websocket-client, CI only
    except ImportError:
        print("AIS: websocket-client not installed, skipping", file=sys.stderr)
        return

    # vessels[mmsi] = {"tanker": bool|None, "boxes": set()}
    vessels = {}
    static_types = {}  # mmsi -> ship type from ShipStaticData
    print(f"AIS: listening {AIS_LISTEN_SECONDS}s …")
    ws = None
    for attempt in range(3):  # aisstream 503s ("envoy overloaded") are common; retry briefly
        try:
            ws = websocket.create_connection("wss://stream.aisstream.io/v0/stream", timeout=30)
            break
        except Exception as e:
            print(f"AIS: connect attempt {attempt + 1} failed: {e}", file=sys.stderr)
            ws = None
            time.sleep(20)
    if ws is None:
        return
    deadline = time.time() + AIS_LISTEN_SECONDS
    try:
        ws.send(json.dumps({
            "APIKey": key,
            "BoundingBoxes": list(AIS_BOXES.values()),
            "FilterMessageTypes": ["PositionReport", "ShipStaticData"],
        }))
        while time.time() < deadline:
            ws.settimeout(max(1, int(deadline - time.time())))
            try:
                msg = json.loads(ws.recv())
            except Exception as e:  # recv timeout ends the listening window
                if "timed out" in str(e).lower() or time.time() >= deadline:
                    break
                continue
            meta = msg.get("MetaData", {})
            mmsi = str(meta.get("MMSI") or "")
            if not mmsi:
                continue
            body = msg.get("Message", {})
            if "ShipStaticData" in body:
                static_types[mmsi] = body["ShipStaticData"].get("Type")
            lat, lon = meta.get("latitude"), meta.get("longitude")
            if lat is None or lon is None:
                continue
            box = box_for(lat, lon)
            if not box:
                continue
            v = vessels.setdefault(mmsi, {"boxes": set()})
            v["boxes"].add(box)
        ws.close()
    except Exception as e:
        print(f"warn: AIS stream failed: {e}", file=sys.stderr)
        if not vessels:
            return

    hour = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0).isoformat()
    counts = {"hour": hour}
    for key in AIS_BOXES:
        present = [m for m, v in vessels.items() if key in v["boxes"]]
        tankers = [m for m in present if static_types.get(m) is not None and 80 <= static_types[m] <= 89]
        counts[key + "_total"] = len(present)
        counts[key + "_tanker"] = len(tankers)

    if counts["hormuz_total"] + counts["bab_total"] == 0:
        # a connected-but-empty stream usually means degraded service, not an
        # empty ocean — keep the last good file instead of writing false zeros
        print("AIS: zero vessels observed, keeping previous file", file=sys.stderr)
        return

    history = []
    if AIS_FILE.exists():
        try:
            history = json.loads(AIS_FILE.read_text()).get("hours", [])
        except (json.JSONDecodeError, OSError):
            history = []
    history = [h for h in history if h.get("hour") != hour]
    history.append(counts)
    cutoff = time.time() - AIS_KEEP_DAYS * 86400
    history = [h for h in history
               if datetime.fromisoformat(h["hour"]).timestamp() >= cutoff]
    history.sort(key=lambda h: h["hour"])
    atomic_write_json(AIS_FILE, {
        "asOf": datetime.now(timezone.utc).isoformat(),
        "methodology": ("Unique MMSIs observed inside each strait bounding box during a "
                        "~10 min aisstream.io listening window per run (presence count, "
                        "not full transits; AIS-dark vessels are invisible). Tanker = AIS "
                        "ship type 80-89. Lower bound, best read as a trend."),
        "hours": history,
    })
    print(f"AIS: {counts} → {AIS_FILE} ({len(history)} hourly rows)")


# GDELT is polled server-side: its API answers without CORS headers whenever it
# rate-limits, which makes browser-side fetches unreliable. Its per-IP limit is
# shared across all GitHub-Actions runners, so 429s are common — retry with
# backoff and accept that some runs simply skip (the last good file persists).
GDELT_FILE = DATA / "gdelt.json"
GDELT_QUERIES = {
    # US/Iran-sourced news tone about Iran — negotiation rhetoric index
    "tone": ("iran (sourcecountry:us OR sourcecountry:ir)", "tonechart", "30d"),
    # strike-on-energy-infrastructure reporting volume
    "strikeVol": ('(refinery OR pipeline OR tanker OR "oil terminal") (attack OR strike OR missile OR drone)',
                  "timelinevol", "14d"),
}


def gdelt_series(query: str, mode: str, timespan: str) -> list:
    url = ("https://api.gdeltproject.org/api/v2/doc/doc?query=" +
           urllib.parse.quote(query) + f"&mode={mode}&format=json&timespan={timespan}")
    j = None
    for attempt in range(3):
        try:
            j = json.loads(fetch(url))
            break
        except Exception as e:
            if attempt == 2:
                raise
            print(f"gdelt: attempt {attempt + 1} failed ({e}), backing off", file=sys.stderr)
            time.sleep(60)
    arr = j.get("timeline") or j.get("data") or (j if isinstance(j, list) else [])
    out = []
    for d in arr:
        if not isinstance(d, dict):
            continue
        v = d.get("value", d.get("count", d.get("tone")))
        t = d.get("datetime") or d.get("date")
        if v is not None and t:
            out.append({"t": t, "v": float(v)})
    return out


def poll_gdelt() -> None:
    # fetch each series independently: one query being rate-limited must not
    # cost the other (CI/shared IPs get 429s often; any success is kept)
    tone, vol = [], []
    try:
        tone = gdelt_series(*GDELT_QUERIES["tone"])
    except Exception as e:
        print(f"warn: gdelt tone: {e}", file=sys.stderr)
    time.sleep(10)
    try:
        vol = gdelt_series(*GDELT_QUERIES["strikeVol"])
    except Exception as e:
        print(f"warn: gdelt strikeVol: {e}", file=sys.stderr)
    # merge into the previous file so a series that failed keeps its last value
    out = {"asOf": datetime.now(timezone.utc).isoformat()}
    if GDELT_FILE.exists():
        try:
            prev_file = json.loads(GDELT_FILE.read_text())
            for k in ("tone", "strikeVol"):
                if k in prev_file:
                    out[k] = prev_file[k]
        except (json.JSONDecodeError, OSError):
            pass
    if len(tone) > 7:
        out["tone"] = {"latest": tone[-1]["v"], "delta7": tone[-1]["v"] - tone[-8]["v"]}
    if len(vol) > 2:
        prev = [p["v"] for p in vol[-8:-1]]
        out["strikeVol"] = {"latest": vol[-1]["v"],
                            "avg7": sum(prev) / len(prev) if prev else 0,
                            "hist": vol}
    if len(out) > 1:
        atomic_write_json(GDELT_FILE, out)
        print(f"gdelt: {list(out.keys())[1:]} → {GDELT_FILE}")
    else:
        print("warn: gdelt: no usable series, keeping previous file", file=sys.stderr)


if __name__ == "__main__":
    poll_feeds()
    poll_gdelt()
    poll_ais()
