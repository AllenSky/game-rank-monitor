"""Apple App Store data sources.

Three endpoints do the work, all keyless:

* the legacy iTunes RSS chart feed, which is the only Apple source that still
  filters a top-100 chart down to a single game subgenre (e.g. Puzzle);
* the iTunes Search API, swept across several terms to discover new releases,
  because the RSS "newapplications" feed ignores its genre parameter;
* the iTunes Lookup API, which enriches ids with ratings and release dates.
"""
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from .config import GAME_GENRE_IDS, GENRE_NAMES

RSS = "https://itunes.apple.com/{country}/rss/{chart}/limit={limit}/genre={genre}/json"
SEARCH = "https://itunes.apple.com/search"
LOOKUP = "https://itunes.apple.com/lookup"
UA = "top-games/1.0 (+local chart tracker)"
LOOKUP_BATCH = 100  # Verified: the lookup endpoint returns all 100 ids in one call.
# Requests are network-bound and Apple serves this volume comfortably: a
# 107-term sweep ran at ~46 req/min with zero errors. Concurrency is what
# removes the wall-clock cost, not shorter sleeps.
WORKERS = 6


class SourceError(RuntimeError):
    pass


def fetch_all(urls, timeout=30, workers=WORKERS):
    """Fetch many URLs at once, preserving order. Failures come back as None."""
    def one(u):
        try:
            return _get_json(u, timeout=timeout)
        except SourceError:
            return None
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(one, urls))


def _get_json(url, timeout=30, retries=3):
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:  # network flakiness and Apple rate limiting
            last = exc
            if attempt < retries - 1:
                # A 403 here is throttling, not a permanent refusal, and it
                # needs a longer pause than an ordinary network blip.
                throttled = getattr(exc, "code", None) == 403
                time.sleep((2.0 if throttled else 1.0) * (attempt + 1))
    raise SourceError(f"request failed after {retries} tries: {url} ({last})")


def _parse_dt(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def fetch_chart(country="us", chart="topfreeapplications", genre_id=7012, limit=100):
    """Return [(rank, app_id)] for a store chart, rank starting at 1."""
    url = RSS.format(country=country, chart=chart, limit=limit, genre=genre_id)
    data = _get_json(url)
    entries = data.get("feed", {}).get("entry", []) or []
    if isinstance(entries, dict):  # Apple collapses a single-entry feed to an object
        entries = [entries]
    out = []
    for rank, entry in enumerate(entries, start=1):
        try:
            out.append((rank, int(entry["id"]["attributes"]["im:id"])))
        except (KeyError, TypeError, ValueError):
            continue
    if not out:
        raise SourceError(f"chart feed returned no usable entries: {url}")
    return out


def lookup(app_ids, country="us"):
    """Enrich ids with full metadata. Returns {app_id: record}."""
    found = {}
    ids = [str(i) for i in app_ids]
    urls = [LOOKUP + "?" + urllib.parse.urlencode(
                {"id": ",".join(ids[s:s + LOOKUP_BATCH]), "country": country})
            for s in range(0, len(ids), LOOKUP_BATCH)]
    for data in fetch_all(urls):
        if not data:
            continue
        for raw in data.get("results", []):
            record = normalize(raw)
            if record:
                found[record["app_id"]] = record
    return found


def canonical_genres(raw):
    """Storefront-independent genre names for a record.

    `genres` comes back localised per storefront, so matching on it silently
    fails outside English markets. `genreIds` is stable, so names are mapped
    from those and only fall back to the localised strings if an id is unknown.
    """
    ids = []
    for gid in raw.get("genreIds") or []:
        try:
            ids.append(int(gid))
        except (TypeError, ValueError):
            continue
    named = [GENRE_NAMES[g] for g in ids if g in GENRE_NAMES]
    return named or list(raw.get("genres") or [])


def game_genres(raw):
    """Only the game categories, or [] if this is not a game at all.

    The sweep searches the whole store, so it turns up book apps and ASMR
    players alongside games. Their categories have no business in a game
    genre filter.
    """
    ids = []
    for gid in raw.get("genreIds") or []:
        try:
            ids.append(int(gid))
        except (TypeError, ValueError):
            continue
    return [GENRE_NAMES[g] for g in ids
            if g in GAME_GENRE_IDS and g in GENRE_NAMES]


def is_game(raw):
    return bool(game_genres(raw))


def normalize(raw):
    """Flatten an iTunes record into the shape we store."""
    app_id = raw.get("trackId")
    if not app_id:
        return None
    # Screenshots and description are stored for the app-detail views. The
    # description was historically dropped ("half the database file"), so it
    # is truncated instead; screenshots are URLs only, capped at 5.
    shots = [u for u in (raw.get("screenshotUrls") or [])
             if isinstance(u, str) and u][:5]
    description = (raw.get("description") or "")[:1500]
    return {
        "app_id": int(app_id),
        "name": raw.get("trackName") or "(unknown)",
        "artist": raw.get("artistName") or "",
        "url": raw.get("trackViewUrl") or "",
        "artist_url": raw.get("artistViewUrl") or "",
        # com.company.game -- the closest thing to a cross-store identity, used
        # to look the same title up on Google Play.
        "bundle_id": raw.get("bundleId") or "",
        "store_id": str(app_id),
        "platform": "ios",
        "icon": raw.get("artworkUrl100") or "",
        "price": float(raw.get("price") or 0.0),
        "formatted_price": raw.get("formattedPrice") or "",
        # Built from ids, not from the storefront's localised names.
        "genres": ",".join(game_genres(raw) or canonical_genres(raw)),
        "is_game": is_game(raw),
        "primary_genre": raw.get("primaryGenreName") or "",
        "content_rating": raw.get("contentAdvisoryRating") or "",
        "release_date": raw.get("releaseDate") or "",
        "version_date": raw.get("currentVersionReleaseDate") or "",
        "version": raw.get("version") or "",
        "avg_rating": float(raw.get("averageUserRating") or 0.0),
        "rating_count": int(raw.get("userRatingCount") or 0),
        "description": description,
        "screenshots": json.dumps(shots),
    }


def sweep_new_releases(terms, country="us", genre_id=7012, within_days=30,
                       genre_name="Puzzle", limit=200):
    """Discover recently released games in a genre.

    The RSS new-releases feed ignores its genre parameter, so instead we sweep
    the Search API across several terms, keep only records Apple actually tags
    with the target genre, and filter by release date. Search is relevance
    ranked, so a brand-new game with no ratings yet may not surface until it
    gains some traction -- the local database's first_seen column is what
    catches those on a later run.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=within_days)
    seen = {}
    errors = []

    urls = []
    for term in terms:
        params = {"term": term, "country": country, "media": "software",
                  "entity": "software", "limit": limit}
        if genre_id:
            params["genreId"] = genre_id
        urls.append(SEARCH + "?" + urllib.parse.urlencode(params))

    for term, data in zip(terms, fetch_all(urls)):
        if data is None:
            errors.append(f"{term}: request failed")
            continue
        for raw in data.get("results", []):
            record = normalize(raw)
            if record:
                # Everything the sweep turns up is kept so the dashboard can
                # show unfiltered releases; the genre split happens below.
                record["in_genre"] = bool(
                    genre_name and genre_name in (raw.get("genres") or []))
                seen[record["app_id"]] = record

    fresh = []
    for record in seen.values():
        released = _parse_dt(record["release_date"])
        if released and released >= cutoff:
            record["days_old"] = (datetime.now(timezone.utc) - released).days
            # `fresh` drives the digest, which stays scoped to the tracked genre.
            if record.get("in_genre", True):
                fresh.append(record)
    fresh.sort(key=lambda r: r["days_old"])
    return fresh, seen, errors
