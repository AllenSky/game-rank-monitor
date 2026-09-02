"""Turn consecutive chart snapshots into the events worth telling Slack about."""
from datetime import datetime, timedelta, timezone

from . import sources, store

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

    Returns a summary dict. The first run establishes a baseline: there is no
    previous snapshot to diff against, so no chart-movement events are emitted.
    """
    country, chart = cfg["country"], cfg["chart"]
    genre_id, size = cfg["genre_id"], cfg["chart_size"]
    sig = cfg["signals"]
    log = (lambda m: print(m)) if verbose else (lambda m: None)

    log(f"Fetching {chart} top {size} ({cfg['genre']}, {country.upper()})...")
    entries = sources.fetch_chart(country, chart, genre_id, size)
    chart_ids = [app_id for _, app_id in entries]

    # Which of these has this database never seen before? Must be asked before upsert.
    unseen = {app_id for app_id in chart_ids if store.is_first_time(conn, app_id)}

    log(f"Enriching {len(chart_ids)} apps...")
    meta = sources.lookup(chart_ids, country)
    store.upsert_apps(conn, list(meta.values()))

    prev_snaps = store.recent_snapshots(conn, chart, limit=1)
    prev_ranks = store.snapshot_ranks(conn, prev_snaps[0]["id"]) if prev_snaps else {}
    is_baseline = not prev_ranks

    snap_id = store.add_snapshot(conn, chart, genre_id, country, entries)
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
                    "prev_rank": None, "delta": None,
                    "detail": f"entered at #{rank}" + (f", released {age}d ago" if fresh else ""),
                })
            else:
                delta = prev - rank  # positive means it moved up
                if abs(delta) >= sig["move_threshold"]:
                    events.append({
                        "kind": "climb" if delta > 0 else "fall",
                        "chart": chart, "app_id": app_id, "rank": rank,
                        "prev_rank": prev, "delta": delta,
                        "detail": f"#{prev} -> #{rank} ({delta:+d})",
                    })
        for app_id, prev in prev_ranks.items():
            if app_id not in curr_ranks:
                events.append({
                    "kind": "exit", "chart": chart, "app_id": app_id,
                    "rank": None, "prev_rank": prev, "delta": None,
                    "detail": f"left the chart from #{prev}",
                })

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
            "rank": None, "prev_rank": None, "delta": None,
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
