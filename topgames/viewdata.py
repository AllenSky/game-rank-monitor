"""Derive the figures the dashboard shows from stored snapshots.

Kept apart from rendering so the numbers can be checked on their own.
"""
import statistics
import urllib.parse
from datetime import datetime, timedelta, timezone

from . import store
from .config import GENRE_NAMES, GAME_GENRE_IDS

GAME_GENRES = {GENRE_NAMES[g] for g in GAME_GENRE_IDS if g in GENRE_NAMES}

HISTORY_POINTS = 12
PLAY_SEARCH = "https://play.google.com/store/search?c=apps&q="
PLAY_APP = "https://play.google.com/store/apps/details?hl=en&id="


def _bundle(row):
    """sqlite3.Row has no .get, and the column is null until a refresh fills it."""
    try:
        return row["bundle_id"] or ""
    except (IndexError, KeyError):
        return ""


def play_url(bundle_id, name=""):
    """A Google Play search for the same title.

    A direct details?id= link was tried first and mostly 404ed: publishers
    rarely reuse the iOS reverse-domain string on Android (com.x.game.ios,
    com.x.gameandroid, an entirely different domain). Searching the title
    lands on the right game far more often than a guessed package resolves,
    so the query wins over the guess.
    """
    query = (name or "").strip() or (bundle_id or "").strip()
    return PLAY_SEARCH + urllib.parse.quote(query) if query else ""


def _parse(iso):
    try:
        return datetime.fromisoformat((iso or "").replace("Z", "+00:00"))
    except ValueError:
        return None


def _genre_label(genres):
    """'Games,Board,Puzzle,Entertainment' -> 'Board / Puzzle'."""
    parts = [g for g in (genres or "").split(",") if g and g != "Games"]
    return " / ".join(parts[:2]) or "Puzzle"


def comparison_snapshot(conn, chart, target_days=7):
    """Newest snapshot at least `target_days` old, else the oldest we hold.

    Returns (snapshot_row, actual_days_apart). A brand-new database has only
    today's data, so the dashboard labels the delta column with the span it
    could actually measure rather than claiming a 7-day change it cannot see.
    """
    snaps = conn.execute(
        "SELECT * FROM snapshots WHERE chart=? ORDER BY id DESC", (chart,)).fetchall()
    if len(snaps) < 2:
        return None, 0
    newest = _parse(snaps[0]["captured_at"])
    for row in snaps[1:]:
        when = _parse(row["captured_at"])
        if when and newest and (newest - when).days >= target_days:
            return row, (newest - when).days
    oldest = snaps[-1]
    when = _parse(oldest["captured_at"])
    days = (newest - when).days if (when and newest) else 0
    return oldest, days


def build(conn, cfg):
    """Assemble every figure the page renders."""
    chart = cfg["chart"]
    snap, rows = store.latest_chart(conn, chart)
    if not snap:
        return None

    base, span_days = comparison_snapshot(conn, chart, target_days=7)
    base_ranks = store.snapshot_ranks(conn, base["id"]) if base else {}

    # Rank history for the sparkline, covering exactly the period the delta
    # describes. Taking merely the newest N snapshots let the comparison point
    # fall outside the window, so a game could report a rank change while its
    # line sat perfectly flat.
    all_ids = [row["id"] for row in conn.execute(
        "SELECT id FROM snapshots WHERE chart=? ORDER BY id", (chart,))]
    start = all_ids.index(base["id"]) if base and base["id"] in all_ids else 0
    window = all_ids[start:]
    if len(window) > HISTORY_POINTS:
        # Thin the run evenly, always keeping the first and last points so the
        # ends still line up with the reported delta.
        step = (len(window) - 1) / (HISTORY_POINTS - 1)
        window = [window[round(i * step)] for i in range(HISTORY_POINTS)]
    order = {sid: i for i, sid in enumerate(window)}

    history = {}
    if window:
        rows_h = conn.execute(
            "SELECT snapshot_id, app_id, rank FROM ranks WHERE snapshot_id IN (%s)"
            % ",".join("?" * len(window)), window).fetchall()
        buckets = {}
        for r in rows_h:
            buckets.setdefault(r["app_id"], []).append(
                (order[r["snapshot_id"]], r["rank"]))
        history = {aid: [rank for _, rank in sorted(pairs)]
                   for aid, pairs in buckets.items()}

    publisher_counts = {}
    for r in rows:
        publisher_counts[r["artist"]] = publisher_counts.get(r["artist"], 0) + 1

    new_days = cfg["signals"]["new_release_days"]
    now = datetime.now(timezone.utc)
    items = []
    for r in rows:
        prev = base_ranks.get(r["app_id"])
        delta = (prev - r["rank"]) if prev is not None else None
        released = _parse(r.get("release_date"))
        age_days = (now - released).days if released else None
        items.append({
            "rank": r["rank"],
            "app_id": r["app_id"],
            "name": r["name"],
            "artist": r["artist"] or "Unknown",
            "url": r["url"],
            "icon": r["icon"],
            "genre": _genre_label(r["genres"]),
            "rating": round(r["avg_rating"] or 0, 2),
            "ratings": r["rating_count"] or 0,
            "released": (r.get("release_date") or "")[:10],
            "price": r["formatted_price"] or "Free",
            "delta": delta,
            "prev_rank": prev,
            "history": history.get(r["app_id"], []),
            "artist_url": r.get("artist_url") or "",
            "bundle_id": _bundle(r),
            "play_url": play_url(_bundle(r), r["name"]),
            "titles_charting": publisher_counts.get(r["artist"], 1),
            "is_new_release": age_days is not None and age_days <= new_days,
            "is_new_entry": prev is None and bool(base_ranks),
        })

    ratings = [i["rating"] for i in items if i["rating"]]
    climbing = sum(1 for i in items if (i["delta"] or 0) > 0)
    falling = sum(1 for i in items if (i["delta"] or 0) < 0)

    publishers = {}
    for i in items:
        p = publishers.setdefault(i["artist"], {
            "artist": i["artist"], "artist_url": i["artist_url"], "titles": 0,
            "best_rank": 999, "ratings_total": 0, "rating_sum": 0.0, "net_delta": 0})
        p["titles"] += 1
        p["best_rank"] = min(p["best_rank"], i["rank"])
        p["ratings_total"] += i["ratings"]
        p["rating_sum"] += i["rating"]
        p["net_delta"] += i["delta"] or 0
    for p in publishers.values():
        p["avg_rating"] = round(p["rating_sum"] / p["titles"], 2)
        del p["rating_sum"]
    publisher_list = sorted(publishers.values(),
                            key=lambda p: (-p["titles"], p["best_rank"]))

    movers = sorted([i for i in items if i["delta"]],
                    key=lambda i: -abs(i["delta"]))[:12]

    # New releases are drawn from the whole tracked genre, not just the chart.
    # Restricting them to charting titles is why this list looked almost empty:
    # very few brand-new games reach the top 100 in their first month.
    charted = {i["app_id"]: i["rank"] for i in items}
    cutoff = (now - timedelta(days=new_days)).isoformat()
    # Unfiltered on purpose: the dashboard offers a genre dropdown over these,
    # defaulting to the tracked genre but able to show everything found.
    fresh_rows = conn.execute("""
        SELECT * FROM apps WHERE release_date >= ?
        ORDER BY release_date DESC LIMIT 600
    """, (cutoff,)).fetchall()
    new_releases = []
    for r in fresh_rows:
        released = _parse(r["release_date"])
        if released and (now - released).days < 0:
            continue  # unreleased pre-order
        genres = [g for g in (r["genres"] or "").split(",") if g]
        if not any(g in GAME_GENRES for g in genres):
            continue  # an app the sweep turned up, not a game
        new_releases.append({
            "app_id": r["app_id"], "name": r["name"],
            "artist": r["artist"] or "Unknown", "url": r["url"] or "",
            "artist_url": r["artist_url"] or "", "icon": r["icon"] or "",
            "bundle_id": _bundle(r),
            "play_url": play_url(_bundle(r), r["name"]),
            "genre": _genre_label(r["genres"]),
            "rating": round(r["avg_rating"] or 0, 2),
            "ratings": r["rating_count"] or 0,
            "released": (r["release_date"] or "")[:10],
            "days_old": (now - released).days if released else None,
            "rank": charted.get(r["app_id"]),
            "genres": [g for g in genres if g != "Games"],
        })

    return {
        "captured_at": snap["captured_at"],
        "span_days": span_days,
        "items": items,
        "movers": movers,
        "new_releases": new_releases,
        "publishers": publisher_list,
        "stats": {
            "tracked": len(items),
            "climbing": climbing,
            "falling": falling,
            "median_rating": round(statistics.median(ratings), 2) if ratings else 0,
            "publishers": len(publishers),
            "new_releases": len(new_releases),
        },
    }


def build_snapshot(entries, meta, cfg):
    """Build the view payload from a freshly fetched chart, with no history.

    Same shape as build(), with the history-derived fields empty: the template
    already renders a null delta as a dash and a short history as a flat spark,
    so nothing downstream needs to branch.
    """
    now = datetime.now(timezone.utc)
    new_days = cfg["signals"]["new_release_days"]

    publisher_counts = {}
    for _rank, app_id in entries:
        rec = meta.get(app_id)
        if rec:
            publisher_counts[rec["artist"]] = publisher_counts.get(rec["artist"], 0) + 1

    items = []
    for rank, app_id in entries:
        r = meta.get(app_id)
        if not r:
            continue
        released = _parse(r.get("release_date"))
        age = (now - released).days if released else None
        items.append({
            "rank": rank, "app_id": app_id, "name": r["name"],
            "artist": r["artist"] or "Unknown", "url": r["url"],
            "artist_url": r.get("artist_url") or "", "icon": r["icon"],
            "bundle_id": _bundle(r),
            "play_url": play_url(_bundle(r), r["name"]),
            "genre": _genre_label(r["genres"]),
            "rating": round(r["avg_rating"] or 0, 2),
            "ratings": r["rating_count"] or 0,
            "released": (r.get("release_date") or "")[:10],
            "price": r["formatted_price"] or "Free",
            "delta": None, "prev_rank": None, "history": [],
            "titles_charting": publisher_counts.get(r["artist"], 1),
            "is_new_release": age is not None and age <= new_days,
            "is_new_entry": False,
        })

    publishers = {}
    for i in items:
        p = publishers.setdefault(i["artist"], {
            "artist": i["artist"], "artist_url": i["artist_url"], "titles": 0,
            "best_rank": 999, "ratings_total": 0, "rating_sum": 0.0, "net_delta": 0})
        p["titles"] += 1
        p["best_rank"] = min(p["best_rank"], i["rank"])
        p["ratings_total"] += i["ratings"]
        p["rating_sum"] += i["rating"]
    for p in publishers.values():
        p["avg_rating"] = round(p["rating_sum"] / p["titles"], 2)
        del p["rating_sum"]

    ratings = [i["rating"] for i in items if i["rating"]]
    return {
        "captured_at": now.isoformat(timespec="seconds"),
        "span_days": 0,
        "items": items,
        "movers": [],
        "new_releases": [i for i in items if i["is_new_release"]],
        "publishers": sorted(publishers.values(),
                             key=lambda p: (-p["titles"], p["best_rank"])),
        "stats": {
            "tracked": len(items), "climbing": 0, "falling": 0,
            "median_rating": round(statistics.median(ratings), 2) if ratings else 0,
            "publishers": len(publishers),
            "new_releases": sum(1 for i in items if i["is_new_release"]),
        },
    }
