"""Turn consecutive chart snapshots into the events worth telling Slack about."""
from datetime import datetime, timedelta, timezone

from . import play, sources, store

KIND_LABELS = {
    "new_entry": "New in the chart",
    "debut": "New release that charted",
    "exit": "Dropped out",
    "climb": "Climbing",
    "fall": "Falling",
    "new_release": "New release",
}


def _days_since(iso):
    dt = sources._parse_dt(iso)
    if not dt:
        return None
    return (datetime.now(timezone.utc) - dt).days


def _released_since(record, cutoff):
    released = sources._parse_dt(record.get("release_date"))
    if released is None:
        return False
    if released.tzinfo is None:
        released = released.replace(tzinfo=timezone.utc)
    return released >= cutoff


def refresh(conn, cfg, verbose=True):
    """Pull the chart plus new releases, store them, and derive events.

    Dispatches on cfg["platform"]. Returns a summary dict. The first run
    establishes a baseline: there is no previous snapshot to diff against,
    so no chart-movement events are emitted.
    """
    if cfg.get("platform") == "play":
        return _refresh_play(conn, cfg, verbose)
    return _refresh_ios(conn, cfg, verbose)


def _store_chart(conn, cfg, entries, meta, platform):
    """Snapshot a chart and diff it against the previous one.

    Platform-independent: `entries` is [(rank, app_id)], `meta` is the
    enriched {app_id: record} used to tell new releases apart from plain
    new entries. Returns (snapshot_id, events, is_baseline).
    """
    chart, genre_id, country = cfg["chart"], cfg["genre_id"], cfg["country"]
    sig = cfg["signals"]

    prev_snaps = store.recent_snapshots(conn, chart, limit=1,
                                        genre_id=genre_id, platform=platform)
    prev_ranks = store.snapshot_ranks(conn, prev_snaps[0]["id"]) if prev_snaps else {}
    is_baseline = not prev_ranks

    snap_id = store.add_snapshot(conn, chart, genre_id, country, entries,
                                 platform=platform)
    curr_ranks = {app_id: rank for rank, app_id in entries}

    events = []
    if not is_baseline:
        for app_id, rank in curr_ranks.items():
            prev = prev_ranks.get(app_id)
            if prev is None:
                rec = meta.get(app_id, {})
                age = _days_since(rec.get("release_date", ""))
                fresh = age is not None and age <= sig["new_release_days"]
                events.append({
                    "kind": "debut" if fresh else "new_entry",
                    "chart": chart, "app_id": app_id, "rank": rank,
                    "prev_rank": None, "delta": None, "platform": platform,
                    "genre_id": genre_id,
                    "detail": f"entered at #{rank}" + (f", released {age}d ago" if fresh else ""),
                })
            else:
                delta = prev - rank  # positive means it moved up
                if abs(delta) >= sig["move_threshold"]:
                    events.append({
                        "kind": "climb" if delta > 0 else "fall",
                        "chart": chart, "app_id": app_id, "rank": rank,
                        "prev_rank": prev, "delta": delta, "platform": platform,
                        "genre_id": genre_id,
                        "detail": f"#{prev} -> #{rank} ({delta:+d})",
                    })
        for app_id, prev in prev_ranks.items():
            if app_id not in curr_ranks:
                events.append({
                    "kind": "exit", "chart": chart, "app_id": app_id,
                    "rank": None, "prev_rank": prev, "delta": None,
                    "platform": platform, "genre_id": genre_id,
                    "detail": f"left the chart from #{prev}",
                })
    return snap_id, events, is_baseline


def _refresh_ios(conn, cfg, verbose=True):
    country, chart = cfg["country"], cfg["chart"]
    genre_id, size = cfg["genre_id"], cfg["chart_size"]
    sig = cfg["signals"]
    log = (lambda m: print(m)) if verbose else (lambda m: None)

    log(f"Fetching {chart} top {size} ({cfg['genre']}, iOS {country.upper()})...")
    entries = sources.fetch_chart(country, chart, genre_id, size)
    chart_ids = [app_id for _, app_id in entries]

    # Which of these has this database never seen before? Must be asked before upsert.
    unseen = {app_id for app_id in chart_ids if store.is_first_time(conn, app_id)}

    log(f"Enriching {len(chart_ids)} apps...")
    meta = sources.lookup(chart_ids, country)
    store.upsert_apps(conn, list(meta.values()))
    store.record_versions(conn, list(meta.values()))

    snap_id, events, is_baseline = _store_chart(conn, cfg, entries, meta, "ios")

    # New releases across the whole genre, not just the ones that charted.
    shared = cfg.get("_swept")
    if shared is not None:
        # cmd_refresh already swept this storefront, using the recency terms
        # that actually surface new games. Sweeping again here would spend a
        # second round of requests to store a thinner result than the site is
        # publishing -- which is how the digest came to report nine new
        # releases on a day the dashboard listed forty-two.
        log(f"Reusing the storefront sweep ({len(shared)} games).")
        cutoff = datetime.now(timezone.utc) - timedelta(
            days=sig["new_release_days"])
        all_found, errors = dict(shared), []
        fresh = [r for r in all_found.values() if _released_since(r, cutoff)]
    else:
        log(f"Sweeping {len(cfg['search_terms'])} genre terms + "
            f"{len(cfg.get('discovery_terms') or [])} discovery terms...")
        genre_name = cfg["genre"].replace("_", " ").title()
        # Genre terms are searched inside the genre; discovery terms are
        # searched across the whole store so other genres' releases surface.
        fresh, all_found, errors = sources.sweep_new_releases(
            cfg["search_terms"], country, genre_id,
            within_days=sig["new_release_days"], genre_name=genre_name)
        for term_set, gid in ((cfg.get("recency_terms") or [], None),
                              (cfg.get("discovery_terms") or [], None)):
            if not term_set:
                continue
            _f, wide, wide_errs = sources.sweep_new_releases(
                term_set, country, gid,
                within_days=sig["new_release_days"], genre_name=None)
            fresh += [r for r in _f if r["app_id"] not in all_found]
            all_found.update({k: v for k, v in wide.items()
                              if k not in all_found})
            errors += wide_errs
    for err in errors:
        log(f"  warning: search term failed -- {err}")

    # On a baseline run every swept app is first-time, so emitting these would
    # report the entire back catalogue as brand new.
    novel = [] if is_baseline else [
        r for r in fresh if store.is_first_time(conn, r["app_id"])]
    store.upsert_apps(conn, list(all_found.values()))
    for rec in novel:
        events.append({
            "kind": "new_release", "chart": "", "app_id": rec["app_id"],
            "rank": None, "prev_rank": None, "delta": None, "platform": "ios",
            "detail": f"released {rec['days_old']}d ago ({rec['release_date'][:10]})",
        })

    store.add_events(conn, events)
    summary = {
        "snapshot_id": snap_id, "chart_size": len(entries),
        "baseline": is_baseline, "events": len(events),
        "new_entries": sum(1 for e in events if e["kind"] in ("new_entry", "debut")),
        "exits": sum(1 for e in events if e["kind"] == "exit"),
        "movers": sum(1 for e in events if e["kind"] in ("climb", "fall")),
        "new_releases": len(novel),
        "genre_pool": len(all_found),
        "first_seen_in_chart": len(unseen),
        "errors": errors,
    }
    if is_baseline:
        log("Baseline snapshot stored -- run refresh again to start seeing movement.")
    return summary


def _refresh_play(conn, cfg, verbose=True):
    country, chart = cfg["country"], cfg["chart"]
    category, size = cfg["play_category"], cfg["chart_size"]
    pcfg = cfg.get("play") or {}
    top_n = int(pcfg.get("detail_top_n", 100))
    lang = pcfg.get("lang", "en")
    log = (lambda m: print(m)) if verbose else (lambda m: None)

    if not play.available():
        raise sources.SourceError(play.unavailable_reason())

    log(f"Fetching Play {chart} top {size} ({category}, {country.upper()})...")
    rows = play.chart_meta(country, chart, category, size, lang)
    entries = [(r["_rank"], r["app_id"]) for r in rows]
    chart_ids = [app_id for _, app_id in entries]
    unseen = {app_id for app_id in chart_ids if store.is_first_time(conn, app_id)}

    # Short list() metadata first so every chart entry is at least named.
    store.upsert_apps(conn, [{k: v for k, v in r.items() if not k.startswith("_")}
                             for r in rows])

    # Full detail (screenshots/description/version) on the chart head only:
    # app() is one request per package, so the cost is bounded by top_n.
    head = [r["_package"] for r in rows[:top_n]]
    log(f"Enriching top {len(head)} Play apps...")
    meta = play.enrich(head, country, lang)
    store.upsert_apps(conn, list(meta.values()))
    store.record_versions(conn, list(meta.values()))

    snap_id, events, is_baseline = _store_chart(conn, cfg, entries, meta, "play")
    store.add_events(conn, events)
    log("Baseline snapshot stored -- run refresh again to start seeing movement."
        if is_baseline else
        f"{len(events)} play chart events.")
    return {
        "snapshot_id": snap_id, "chart_size": len(entries),
        "baseline": is_baseline, "events": len(events),
        "new_entries": sum(1 for e in events if e["kind"] in ("new_entry", "debut")),
        "exits": sum(1 for e in events if e["kind"] == "exit"),
        "movers": sum(1 for e in events if e["kind"] in ("climb", "fall")),
        "new_releases": 0,   # Play release discovery is not wired up yet
        "genre_pool": len(rows),
        "first_seen_in_chart": len(unseen),
        "errors": [],
    }
