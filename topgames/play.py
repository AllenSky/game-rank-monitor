"""Google Play data source.

Apple's keyless endpoints have no Play equivalent: Google publishes no top
charts API. The PyPI `google-play-scraper` package only exposes app/search/
reviews -- the chart `list()` lives in the Node.js package (facundoolano),
so this module shells out to scripts/play_fetch.mjs, which owns the network
side. If node, the package, or Google itself is unavailable the caller
degrades to iOS-only rather than failing the run.

The public shape mirrors `sources` so signals/refresh treats both platforms
the same way:
    fetch_chart() -> [(rank, app_id)]
    enrich()      -> {app_id: record}
"""
import hashlib
import json
import os
import subprocess
import threading

from .sources import SourceError

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HELPER = os.path.join(ROOT, "scripts", "play_fetch.mjs")
PLAY_APP_URL = "https://play.google.com/store/apps/details?id="
PLAY_DEV_URL = "https://play.google.com/store/apps/dev?id="

_NODE_CACHE = {}


def _node_bin():
    """Locate node; cached. Returns None when absent."""
    if "bin" not in _NODE_CACHE:
        for candidate in ("node", "/usr/local/bin/node", "/opt/homebrew/bin/node"):
            try:
                subprocess.run([candidate, "--version"], capture_output=True,
                               timeout=10, check=True)
                _NODE_CACHE["bin"] = candidate
                break
            except Exception:
                continue
        else:
            _NODE_CACHE["bin"] = None
    return _NODE_CACHE["bin"]


def available():
    """True when node + the helper + its node_modules are all in place."""
    return bool(_node_bin()) and os.path.exists(HELPER) and \
        os.path.isdir(os.path.join(ROOT, "node_modules", "google-play-scraper"))


def unavailable_reason():
    if not _node_bin():
        return "node not found on PATH"
    if not os.path.exists(HELPER):
        return f"helper script missing: {HELPER}"
    return "node_modules/google-play-scraper missing -- run: npm install"


def app_id_for(package):
    """Stable 64-bit integer id for a Play package name.

    The `apps` table keys on an INTEGER app_id that the iTunes trackId
    occupies on the iOS side; Play package names are strings, so they are
    hashed into the same numeric space. `bundle_id` keeps the package name
    itself, and iOS records carry the same string, so one title found on
    both stores joins on bundle_id.
    """
    digest = hashlib.md5(("play:" + package).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big", signed=True)


def _fetch(mode, *args, timeout=120):
    """Run the node helper and parse its JSON stdout."""
    if not available():
        raise SourceError(unavailable_reason())
    cmd = [_node_bin(), HELPER, mode] + [str(a) for a in args]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=timeout, cwd=ROOT)
    except subprocess.TimeoutExpired:
        raise SourceError(f"play helper timed out after {timeout}s: {mode}")
    if proc.returncode != 0:
        tail = (proc.stderr or "").strip().splitlines()[-1:] or ["(no stderr)"]
        raise SourceError(f"play helper failed: {tail[0]}")
    try:
        return json.loads(proc.stdout)
    except ValueError:
        raise SourceError("play helper returned invalid JSON")


def fetch_chart(country="us", chart="top_free", category="GAME_CASUAL",
                limit=100, lang="en"):
    """Return [(rank, app_id)] for a Play top chart, rank starting at 1."""
    rows = _fetch("chart", "--category", category, "--collection", chart,
                  "--num", limit, "--country", country, "--lang", lang)
    out = []
    for row in rows[:limit]:
        package = row.get("appId")
        if not package:
            continue
        out.append((row["rank"], app_id_for(package)))
    if not out:
        raise SourceError(
            f"play chart returned no usable entries: {category}/{chart}/{country}")
    return out


def normalize(raw):
    """Flatten a google-play-scraper app() result into the stored shape."""
    package = raw.get("appId") or ""
    if not package:
        return None
    shots = [u for u in (raw.get("screenshots") or []) if isinstance(u, str)][:5]
    price = raw.get("price") or 0.0
    return {
        "app_id": app_id_for(package),
        "name": raw.get("title") or "(unknown)",
        "artist": raw.get("developer") or "",
        "url": PLAY_APP_URL + package,
        "artist_url": (PLAY_DEV_URL + str(raw["developerId"])
                       if raw.get("developerId") else PLAY_APP_URL + package),
        "bundle_id": package,          # == iOS bundleId for cross-store joins
        "store_id": package,
        "platform": "play",
        "icon": raw.get("icon") or "",
        "price": float(price),
        "formatted_price": "Free" if not price else f"{price:g}",
        "genres": raw.get("genre") or "",
        "primary_genre": raw.get("genre") or "",
        "content_rating": raw.get("contentRating") or "",
        # Play's `released` is display text ("Sep 2, 2026"), not ISO; keep raw.
        "release_date": raw.get("released") or "",
        # `updated` is an ISO timestamp -- the Play-side version history date.
        "version_date": raw.get("updated") or "",
        "version": raw.get("version") or "",
        "avg_rating": float(raw.get("score") or 0.0),
        "rating_count": int(raw.get("ratings") or 0),
        "description": (raw.get("description") or "")[:1500],
        "screenshots": json.dumps(shots),
    }


def enrich(packages, country="us", lang="en", timeout=300):
    """Fetch full app() details for package names. Returns {app_id: record}.

    Failures are per-app (the helper skips them on stderr); an app that
    cannot be enriched simply stays absent from the result.
    """
    if not packages:
        return {}
    raws = _fetch("apps", "--ids", ",".join(packages),
                  "--country", country, "--lang", lang, timeout=timeout)
    found = {}
    for raw in raws:
        rec = normalize(raw)
        if rec:
            found[rec["app_id"]] = rec
    return found


def chart_meta(country="us", chart="top_free", category="GAME_CASUAL",
               limit=100, lang="en"):
    """The list() rows themselves: enough for apps-upsert without app() detail.

    Short metadata (appId/title/developer/icon/score) is upserted for every
    chart entry; enrich() then layers full detail (screenshots/description/
    version) onto the chart head only.
    """
    rows = _fetch("chart", "--category", category, "--collection", chart,
                  "--num", limit, "--country", country, "--lang", lang)
    out = []
    for rank, raw in enumerate(rows[:limit], start=1):
        package = raw.get("appId") or ""
        if not package:
            continue
        price = float(raw.get("price") or 0.0)
        out.append({
            "app_id": app_id_for(package),
            "name": raw.get("title") or "",
            "artist": raw.get("developer") or "",
            "url": PLAY_APP_URL + package,
            "artist_url": (PLAY_DEV_URL + str(raw["developerId"])
                           if raw.get("developerId") else ""),
            "bundle_id": package, "store_id": package, "platform": "play",
            "icon": raw.get("icon") or "",
            "price": price,
            "formatted_price": "Free" if not price else f"{price:g}",
            # list() rows carry no genre; enrich() fills it from app().
            "genres": "", "primary_genre": "", "content_rating": "",
            "release_date": "", "version_date": "", "version": "",
            "avg_rating": float(raw.get("score") or 0.0),
            "rating_count": int(raw.get("ratings") or 0),
            "description": "", "screenshots": "[]",
            "_package": package, "_rank": rank,
        })
    if not out:
        raise SourceError(
            f"play chart returned no usable entries: {category}/{chart}/{country}")
    return out
