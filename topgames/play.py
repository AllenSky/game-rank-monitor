"""Google Play data source.

Apple's keyless endpoints have no Play equivalent: Google publishes no top
charts API, so this module wraps the `google-play-scraper` PyPI package
(pure Python, unofficial). If the package is missing or Google is
unreachable, the caller degrades to iOS-only rather than failing the run.

The public shape mirrors `sources` so signals/refresh treats both platforms
the same way:
    fetch_chart() -> [(rank, app_id)]
    enrich()      -> {app_id: record}
"""
import hashlib
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from .sources import SourceError

PLAY_APP_URL = "https://play.google.com/store/apps/details?id="
PLAY_DEV_URL = "https://play.google.com/store/apps/dev?id="

try:
    import google_play_scraper as gplay
    _GPLAY_IMPORT_ERROR = None
except Exception as _exc:  # not installed, or its deps broke on this python
    gplay = None
    _GPLAY_IMPORT_ERROR = _exc

_ENRICH_WORKERS = 8


def available():
    """True when the scraper package can be imported."""
    return gplay is not None


def unavailable_reason():
    return f"google-play-scraper unavailable: {_GPLAY_IMPORT_ERROR}"


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


def _retry(fn, tries=3, what=""):
    last = None
    for attempt in range(tries):
        try:
            return fn()
        except Exception as exc:
            last = exc
            if attempt < tries - 1:
                time.sleep(1.0 * (attempt + 1))
    raise SourceError(f"play request failed after {tries} tries: {what} ({last})")


def _call_list(category, chart, num, country, lang):
    """Call gplay.list tolerating num/number signature drift across versions."""
    import inspect
    params = inspect.signature(gplay.list).parameters
    kwargs = dict(category=category, collection=chart, country=country, lang=lang)
    if "number" in params:
        kwargs["number"] = num
    elif "num" in params:
        kwargs["num"] = num
    return gplay.list(**kwargs)


def _norm_collection(chart):
    """Map our chart names to the package's Collection enum values."""
    name = {"top_free": "TOP_FREE", "top_paid": "TOP_PAID",
            "grossing": "GROSSING"}.get(chart, "TOP_FREE")
    coll = getattr(gplay, "collection", None) or getattr(gplay, "Collection", None)
    if coll is not None and hasattr(coll, name):
        return getattr(coll, name)
    return name  # newer versions also accept plain strings


def fetch_chart(country="us", chart="top_free", category="GAME_CASUAL",
                limit=100, lang="en"):
    """Return [(rank, app_id)] for a Play top chart, rank starting at 1."""
    if not available():
        raise SourceError(unavailable_reason())
    coll = _norm_collection(chart)
    results = _retry(lambda: _call_list(category, coll, limit, country, lang),
                     what=f"list({category}/{chart}/{country})")
    out = []
    for rank, row in enumerate(results[:limit], start=1):
        package = row.get("appId") or row.get("appIdOrDeveloperPage")
        if not package:
            continue
        out.append((rank, app_id_for(package)))
    if not out:
        raise SourceError(f"play chart returned no usable entries: {category}/{chart}/{country}")
    return out


def normalize(raw, package=None):
    """Flatten a google-play-scraper app() result into the stored shape."""
    package = package or raw.get("appId") or ""
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


def enrich(packages, country="us", lang="en", workers=_ENRICH_WORKERS):
    """Fetch full app() details for package names. Returns {app_id: record}.

    Failures are per-app: an app that cannot be enriched simply stays absent,
    and chart metadata (from list()) is still upserted by the caller.
    """
    if not available():
        raise SourceError(unavailable_reason())
    found = {}

    def one(pkg):
        try:
            raw = _retry(lambda: gplay.app(pkg, country=country, lang=lang),
                         tries=2, what=f"app({pkg})")
            rec = normalize(raw, pkg)
            return (rec["app_id"], rec) if rec else None
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for item in pool.map(one, packages):
            if item:
                found[item[0]] = item[1]
    return found


def chart_meta(country="us", chart="top_free", category="GAME_CASUAL",
               limit=100, lang="en"):
    """The list() rows themselves: enough for apps-upsert without app() detail.

    list() returns short metadata (appId/title/developer/icon/score/price),
    which is upserted for every chart entry; enrich() then layers full detail
    (screenshots/description/version) onto the chart head only.
    """
    if not available():
        raise SourceError(unavailable_reason())
    coll = _norm_collection(chart)
    results = _retry(lambda: _call_list(category, coll, limit, country, lang),
                     what=f"list({category}/{chart}/{country})")
    rows = []
    for rank, raw in enumerate(results[:limit], start=1):
        package = raw.get("appId") or ""
        if not package:
            continue
        rec = {
            "app_id": app_id_for(package), "name": raw.get("title") or "",
            "artist": raw.get("developer") or "", "url": PLAY_APP_URL + package,
            "artist_url": "", "bundle_id": package, "store_id": package,
            "platform": "play", "icon": raw.get("icon") or "",
            "price": float(raw.get("price") or 0.0),
            "formatted_price": "Free" if not raw.get("price") else f"{raw.get('price'):g}",
            "genres": (raw.get("genre") or "").replace(" & ", " ").replace(",", " ").strip(),
            "primary_genre": "", "content_rating": "", "release_date": "",
            "version_date": "", "version": "",
            "avg_rating": float(raw.get("score") or 0.0),
            "rating_count": int(raw.get("ratings") or 0),
            "description": "", "screenshots": "[]",
            "_package": package, "_rank": rank,
        }
        rows.append(rec)
    if not rows:
        raise SourceError(f"play chart returned no usable entries: {category}/{chart}/{country}")
    return rows
