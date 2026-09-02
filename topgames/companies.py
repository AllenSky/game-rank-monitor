"""Company-level aggregation across platforms.

The watch list is plain names in config (watch_developers). Matching is
case-insensitive on exact equality or a `name + space` prefix, so
"SayGames" matches "SayGames Ltd" while "King" does not match
"Kingdom Studio".
"""
from datetime import datetime, timedelta, timezone

from . import store


def is_match(artist, name):
    a = (artist or "").strip().lower()
    n = (name or "").strip().lower()
    return bool(a) and bool(n) and (a == n or a.startswith(n + " "))


def matches_any(artist, names):
    return any(is_match(artist, n) for n in (names or []))


def charting(conn, names, datasets):
    """Apps by watched developers on the latest snapshot of every dataset.

    Returns a flat list of dicts with dataset context and the rank change
    against the previous snapshot of that dataset.
    """
    out = []
    for d in datasets:
        snap, rows = store.latest_chart(conn, d["chart"],
                                        genre_id=d["genre_id"],
                                        platform=d["platform"])
        if not snap:
            continue
        snaps = store.recent_snapshots(conn, d["chart"], limit=2,
                                       genre_id=d["genre_id"],
                                       platform=d["platform"])
        prev_ranks = store.snapshot_ranks(conn, snaps[1]["id"]) if len(snaps) > 1 else {}
        for r in rows:
            if not matches_any(r["artist"], names):
                continue
            prev = prev_ranks.get(r["app_id"])
            out.append({
                "app_id": r["app_id"], "name": r["name"], "artist": r["artist"],
                "url": r["url"], "icon": r["icon"], "bundle_id": r.get("bundle_id", ""),
                "platform": d["platform"], "genre": d["genre"],
                "slug": d["slug"], "rank": r["rank"], "prev_rank": prev,
                "delta": (prev - r["rank"]) if prev is not None else None,
                "version": r.get("version") or "",
                "version_date": r.get("version_date") or "",
            })
    return out


def versions_since(conn, iso_ts, names=None):
    """Version rows first recorded since `iso_ts`, optionally watched-only."""
    # first_seen bounds what the tracker can know about; released_at bounds
    # what actually happened in the window. Both are needed: released_at alone
    # would replay history on every run, first_seen alone reports a whole
    # backfilled catalogue as brand new on day one.
    sql = """SELECT v.app_id, v.version, v.released_at, v.first_seen,
                    a.name, a.artist, a.url, a.platform, a.bundle_id
             FROM app_versions v JOIN apps a ON a.app_id = v.app_id
             WHERE v.first_seen >= ?
               AND (v.released_at >= ? OR v.released_at = '')"""
    params = [iso_ts, iso_ts]
    names = names or []
    clauses = []
    for n in names:
        clauses.append("(lower(a.artist) = ? OR lower(a.artist) LIKE ?)")
        low = n.strip().lower()
        params += [low, low + " %"]
    if clauses:
        sql += " AND (" + " OR ".join(clauses) + ")"
    sql += " ORDER BY v.first_seen DESC"
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def update_frequency(conn, app_id, days=90):
    """Derived update cadence for one app over a lookback window.

    Returns {"count": n, "avg_gap_days": float|None}. count is version rows
    whose first_seen falls inside the window -- new installs of the tracker
    backfill one row per app, so early numbers read high until history builds.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)) \
        .isoformat(timespec="seconds")
    # The cadence a player experiences follows release dates, not our
    # observation dates; first_seen is the fallback for rows without one.
    rows = conn.execute(
        """SELECT released_at, first_seen FROM app_versions
           WHERE app_id=? AND first_seen>=?""",
        (app_id, cutoff)).fetchall()
    times = []
    for r in rows:
        for candidate in (r["released_at"], r["first_seen"]):
            if not candidate:
                continue
            try:
                times.append(datetime.fromisoformat(candidate.replace("Z", "+00:00")))
            except ValueError:
                continue
            break
    if not times:
        return {"count": 0, "avg_gap_days": None}
    gap = None
    if len(times) > 1:
        span = (max(times) - min(times)).total_seconds() / 86400
        gap = round(span / (len(times) - 1), 1)
    return {"count": len(times), "avg_gap_days": gap}


def watch_overview(conn, cfg, datasets, since_iso=None):
    """Everything the digest's watched-companies section needs, one call."""
    names = [n for n in (cfg.get("watch_developers") or []) if n.strip()]
    if not names:
        return []
    since_iso = since_iso or (datetime.now(timezone.utc) - timedelta(days=1)) \
        .isoformat(timespec="seconds")
    titles = charting(conn, names, datasets)
    versions = versions_since(conn, since_iso, names)
    out = []
    for name in names:
        mine = [t for t in titles if is_match(t["artist"], name)]
        mine.sort(key=lambda t: (t["platform"], t["rank"]))
        vers = [v for v in versions if is_match(v["artist"], name)]
        for t in mine:
            t["update_frequency"] = update_frequency(conn, t["app_id"])
        out.append({
            "name": name, "titles": mine, "new_versions": vers,
            "any": bool(mine or vers),
        })
    return out
