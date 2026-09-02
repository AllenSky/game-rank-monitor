"""Command line entry point."""
import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from . import (config, digest as digest_mod, signals, slack, sources,
               staticgen, store, viewdata, web)
from .scheduler import install_launchd, uninstall_launchd, schedule_status


def cmd_init(args, cfg):
    path = config.CONFIG_PATH
    if os.path.exists(path) and not args.force:
        print(f"{path} already exists (use --force to overwrite).")
    else:
        with open(path, "w") as fh:
            json.dump(config.DEFAULTS, fh, indent=2)
        print(f"Wrote {path}")
    config.save_example()
    store.connect()
    print("Database ready at data/topgames.db")
    print("\nNext: paste your Slack webhook URL into config.json "
          "(slack.webhook_url), then run:  python3 -m topgames refresh")
    return 0


def _releases_path(country):
    return os.path.join(config.ROOT, "data", f"releases-{country}.json")


def sweep_releases(cfg, country, primary):
    """Discover recent releases in one storefront.

    Availability and ratings are storefront-specific, so each country needs its
    own sweep. Only the primary gets the full genre vocabulary; the rest use the
    generic discovery terms, since the pool is shown cross-genre anyway.
    """
    recency = list(cfg.get("recency_terms") or [])
    if primary:
        terms = recency + list(cfg.get("search_terms") or []) + list(
            cfg.get("discovery_terms") or [])
    else:
        # The genre terms come along: without them a secondary storefront never
        # searches "sudoku" or "nonogram", so the genre it is tracked for is the
        # one it discovers worst.
        terms = recency + list(cfg.get("search_terms") or []) + list(
            cfg.get("discovery_terms_short")
            or cfg.get("discovery_terms") or [])
    # No date cut-off here: the dashboard offers an age filter over the whole
    # pool, so trimming to 30 days at fetch time would throw away the very
    # thing that filter exists to show.
    _fresh, found, errors = sources.sweep_new_releases(
        terms, country, None, within_days=36500, genre_name=None)
    games = {k: v for k, v in found.items() if v.get("is_game", True)}

    now = datetime.now(timezone.utc)
    rows = []
    for r in found.values():
        released = sources._parse_dt(r["release_date"])
        if not released:
            continue
        age = (now - released).days
        # Apple lists pre-orders with a future release date, which produced
        # entries like "-86d" sorting above everything actually released. A
        # game that has not launched is not a new release.
        if age < 0:
            continue
        # The sweep searches the whole store; only games belong in a game tracker.
        if not r.get("is_game", True):
            continue
        r["days_old"] = age
        rows.append({
            "app_id": r["app_id"], "name": r["name"], "artist": r["artist"],
            "url": r["url"], "artist_url": r.get("artist_url", ""),
            "bundle_id": r.get("bundle_id", ""),
            "play_url": viewdata.play_url(r.get("bundle_id"), r["name"]),
            "icon": r["icon"], "rating": round(r["avg_rating"] or 0, 2),
            "ratings": r["rating_count"] or 0,
            "released": (r["release_date"] or "")[:10],
            "days_old": r["days_old"],
            "genres": [g for g in (r["genres"] or "").split(",")
                       if g and g != "Games"],
        })
    # Newest first, then capped: the tail is years old and only inflates the
    # file the browser has to pull down.
    rows.sort(key=lambda r: r["released"], reverse=True)
    cap = int(cfg.get("release_pool_size", 3000))
    return rows[:cap], errors, games


def _previous_pool(country, cfg):
    """The pool this run should build on.

    The pools are gitignored, so a CI checkout starts without them and the
    merge below would have nothing to merge into -- which is how a throttled
    run managed to publish six recent releases in the first place. The last
    published pool is on the Pages site, which costs nothing to keep and is
    by definition what the site is serving right now.
    """
    try:
        with open(_releases_path(country)) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        pass
    base = (cfg.get("web") or {}).get("pages_url") or ""
    if not base:
        return []
    try:
        return sources._get_json(
            base.rstrip("/") + f"/releases/{country}.json", retries=1)
    except Exception:
        return []                      # first ever run, or the site is down


def _merge_pool(country, rows, cfg):
    """Fold a sweep into the pool already published, newest metadata winning.

    Apple throttles hard from GitHub's IPs: one run lost 101 of the US sweep's
    107 search terms and published a pool of six recent releases. A sweep is a
    discovery sample, so a thin one means "found less this time", never "these
    games ceased to exist" -- merging makes a throttled run harmless.
    """
    merged = {}
    for r in _previous_pool(country, cfg):
        try:
            merged[r["app_id"]] = r
        except (TypeError, KeyError):
            continue
    for r in rows:                      # this run's metadata is the fresher one
        merged[r["app_id"]] = r
    # days_old was computed when the row was swept; carrying it forward would
    # freeze a game's age at whatever it was the day we last saw it.
    today = datetime.now(timezone.utc)
    for r in merged.values():
        released = sources._parse_dt(r.get("released"))
        if released and released.tzinfo is None:
            released = released.replace(tzinfo=timezone.utc)
        if released:
            r["days_old"] = (today - released).days
    out = sorted(merged.values(), key=lambda r: r.get("released") or "",
                 reverse=True)
    return out[:int(cfg.get("release_pool_size", 3000))]


def _view_path(d):
    return os.path.join(config.ROOT, "data", f"{d['slug']}.view.json")


def _fetch_snapshot(d):
    """Fetch and shape a chart-only dataset. Two requests, nothing persisted."""
    entries = sources.fetch_chart(d["country"], d["chart"],
                                  d["genre_id"], d["chart_size"])
    meta = sources.lookup([a for _, a in entries], d["country"])
    return viewdata.build_snapshot(entries, meta, d)


def _refresh_one(d):
    """Refresh a single dataset. Chart-only datasets keep no history."""
    if not d["history"]:
        view = _fetch_snapshot(d)
        # refresh and export run as separate processes, so hand the fetched
        # chart over on disk rather than re-requesting it minutes later.
        os.makedirs(os.path.dirname(_view_path(d)), exist_ok=True)
        with open(_view_path(d), "w") as fh:
            json.dump(view, fh, default=str)
        return {"chart_size": len(entries_count(view)), "baseline": False,
                "events": 0, "new_entries": 0, "exits": 0, "movers": 0,
                "new_releases": len(view["new_releases"]), "chart_only": True}
    conn = store.connect(d["db_path"])
    try:
        return signals.refresh(conn, d, verbose=False)
    finally:
        conn.close()


def entries_count(view):
    return view["items"]


def cmd_refresh(args, cfg):
    """Refresh every configured dataset, isolating failures."""
    ds = config.datasets(cfg)
    only = getattr(args, "platform", None)
    if only:
        ds = [d for d in ds if d["platform"] == only]
    failed = []
    swept = {}

    # One release sweep per storefront, shared by that country's charts.
    # The sweep is Apple-only, so a play-scoped refresh skips it entirely.
    if cfg.get("sweep_countries", True) and only in (None, "ios"):
        primary_country = config.primary(cfg)["country"]
        def sweep_one(country):
            try:
                rows, errs, found = sweep_releases(cfg, country,
                                                   country == primary_country)
                rows = _merge_pool(country, rows, cfg)
                os.makedirs(os.path.dirname(_releases_path(country)), exist_ok=True)
                with open(_releases_path(country), "w") as fh:
                    json.dump(rows, fh, default=str)
                return country, rows, errs, found, None
            except Exception as exc:
                return country, None, None, None, exc

        # One storefront at a time: each sweep is already 8-way concurrent
        # internally, and stacking countries on top of that made Apple start
        # dropping requests (68-94 failed terms per country).
        with ThreadPoolExecutor(max_workers=1) as pool:
            for country, rows, errs, found, exc in pool.map(
                    sweep_one, sorted({d["country"] for d in ds})):
                if exc is not None:
                    failed.append((f"releases-{country}", exc))
                    print(f"  releases {country:20} FAILED: {exc}", file=sys.stderr)
                    continue
                recent = sum(1 for r in rows
                             if (r["days_old"] or 9999)
                             <= cfg["signals"]["new_release_days"])
                swept[country] = found
                print(f"  releases {country:20} {len(rows):>5} pooled, "
                      f"{recent} in the last {cfg['signals']['new_release_days']}d"
                      + (f" ({len(errs)} term errors)" if errs else ""))
    # The primary writes SQLite, so it runs on its own; the chart-only datasets
    # only write their own JSON file and are safe to fan out.
    # The storefront sweep above already found every recent game; handing it
    # to the signals pass keeps SQLite and the published pool in step and
    # spares Apple a second identical sweep.
    for d in ds:
        d["_swept"] = swept.get(d["country"])
    primary = [d for d in ds if d["history"]]
    others = [d for d in ds if not d["history"]]

    def run(d):
        try:
            return d, _refresh_one(d), None
        except Exception as exc:
            return d, None, exc

    results = [run(d) for d in primary]
    if others:
        with ThreadPoolExecutor(max_workers=6) as pool:
            results += list(pool.map(run, others))

    for d, summary, exc in results:
        tag = f"{d['slug']}{' (chart only)' if not d['history'] else ''}"
        if exc is not None:
            failed.append((d["slug"], exc))
            print(f"  {tag:26} FAILED: {exc}", file=sys.stderr)
            import traceback
            traceback.print_exc(limit=4)
        else:
            print(f"  {tag:26} {summary['chart_size']:>3} ranked · "
                  f"{summary['new_entries']} new · {summary['movers']} movers · "
                  f"{summary['new_releases']} releases")
    if failed:
        print(f"\n{len(failed)} of {len(ds)} datasets failed", file=sys.stderr)
        return 1
    return 0


def _cmd_refresh_primary(args, cfg):
    conn = store.connect()
    summary = signals.refresh(conn, cfg)
    print(f"\nSnapshot #{summary['snapshot_id']}: {summary['chart_size']} ranked apps, "
          f"{summary['genre_pool']} apps in genre pool")
    print(f"  new in chart : {summary['new_entries']}")
    print(f"  dropped out  : {summary['exits']}")
    print(f"  big movers   : {summary['movers']}")
    print(f"  new releases : {summary['new_releases']}")

    # Optional immediate alert when something enters the chart.
    if cfg["slack"].get("realtime_new_entry") and not summary["baseline"]:
        since = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        fresh = store.events_since(conn, since, kinds=["new_entry", "debut"],
                                   unnotified_only=True)
        if fresh:
            try:
                slack.post(cfg["slack"]["webhook_url"],
                           slack.build_realtime_alert(cfg, fresh))
                store.mark_notified(conn, [e["id"] for e in fresh])
                print(f"  posted realtime alert for {len(fresh)} new entries")
            except slack.SlackError as exc:
                print(f"  slack alert failed: {exc}", file=sys.stderr)
    conn.close()
    return 0


def local_now(cfg):
    """Now, in the timezone the schedule is written in."""
    name = (cfg.get("slack") or {}).get("timezone") or "UTC"
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo(name))
    except Exception:
        return datetime.now(timezone.utc)


def digest_is_due(conn, cfg, period, now=None):
    """Whether this run is the one that should post.

    GitHub runs scheduled jobs best-effort: most mornings the 06:00 UTC cron
    starts within the hour, but one started eleven hours late and posted the
    daily digest at 8pm. The workflow now gets several attempts, and the
    decision to post moves here -- past the target hour, in the configured
    timezone, and not already sent today.
    """
    now = now or local_now(cfg)
    target = (cfg["slack"][period].get("time") or "09:00").split(":")[0]
    if now.hour < int(target):
        return False, f"before {target}:00 {now.tzname() or 'local'}"
    day = now.date().isoformat()
    if period == "weekly":
        want = (cfg["slack"]["weekly"].get("day") or "monday").lower()
        days = ["monday", "tuesday", "wednesday", "thursday", "friday",
                "saturday", "sunday"]
        if want in days and now.weekday() != days.index(want):
            return False, f"weekly runs on {want}"
        # One weekly per week, keyed by the Monday it belongs to.
        day = (now.date() - timedelta(days=now.weekday())).isoformat()
    if store.digest_sent(conn, period, day):
        return False, f"already sent for {day}"
    return True, day


def cmd_digest(args, cfg):
    conn = store.connect(config.primary(cfg)["db_path"])
    stamp = None
    if getattr(args, "if_due", False):
        due, stamp = digest_is_due(conn, cfg, args.period)
        if not due:
            print(f"Skipping {args.period} digest: {stamp}")
            return 0
    payload, ids = digest_mod.build(conn, config.primary(cfg), args.period)
    if payload is None:
        print(f"Nothing to report and skip_if_empty is on -- no {args.period} digest sent.")
        return 0
    if not (cfg["slack"].get("webhook_url") or "").strip():
        # No Slack configured yet (e.g. first CI validation runs): posting is
        # impossible, and failing here would take the Pages deploy down with it.
        print(f"No slack webhook configured -- {args.period} digest built "
              f"({len(ids)} signals) but not sent.")
        return 0
    if args.dry_run:
        print(json.dumps(payload, indent=2))
        print(f"\n(dry run -- {len(ids)} signals would be marked as notified)",
              file=sys.stderr)
        return 0
    try:
        slack.post(cfg["slack"]["webhook_url"], payload)
    except slack.SlackError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    store.mark_notified(conn, ids)
    if stamp:
        store.mark_digest_sent(conn, args.period, stamp,
                               local_now(cfg).isoformat(timespec="seconds"))
    print(f"Sent {args.period} digest covering {len(ids)} signals.")
    conn.close()
    return 0


def cmd_run(args, cfg):
    """Refresh then send -- the single command a scheduled job calls."""
    rc = cmd_refresh(args, cfg)
    if rc:
        return rc
    return cmd_digest(args, cfg)


def cmd_slack_test(args, cfg):
    try:
        slack.post(cfg["slack"]["webhook_url"], slack.test_message(cfg))
    except slack.SlackError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print("Test message sent.")
    return 0


def cmd_serve(args, cfg):
    web.serve(cfg, args.host, args.port)
    return 0


def cmd_chart(args, cfg):
    cfg = config.primary(cfg)
    conn = store.connect(cfg["db_path"])
    snap, rows = store.latest_chart(conn, cfg["chart"], genre_id=cfg.get("genre_id"),
                          platform=cfg.get("platform", "ios"))
    if not snap:
        print("No data yet -- run:  python3 -m topgames refresh")
        return 1
    print(f"{cfg['chart']} / {cfg['genre']} / {cfg['country'].upper()} "
          f"@ {snap['captured_at']}\n")
    for r in rows[:args.limit]:
        rating = f"{r['avg_rating']:.2f}★" if r["avg_rating"] else "  —  "
        print(f"{r['rank']:>3}. {r['name'][:44]:44} {rating:>7} "
              f"{r['rating_count']:>9,}  {r['artist'][:26]}")
    conn.close()
    return 0


def cmd_export(args, cfg):
    """Publish every dataset into its own subtree, plus a root index."""
    ds = config.datasets(cfg)
    listing = [{"country": d["country"], "genre": d["genre"], "slug": d["slug"],
                "path": d["outdir_rel"],
                "country_name": staticgen.COUNTRY_NAMES.get(
                    d["country"], d["country"].upper()),
                "title": f"{d['genre'].replace('_',' ').title()} · {d['country'].upper()}",
                "primary": d["primary"]} for d in ds]
    outdir = getattr(args, "outdir", "site") or "site"
    entries, failed = [], []

    for d in ds:
        try:
            view = None
            if not d["history"]:
                path = _view_path(d)
                if os.path.exists(path):
                    with open(path) as fh:
                        view = json.load(fh)
                else:
                    view = _fetch_snapshot(d)
            conn = store.connect(d["db_path"]) if d["history"] else None
            try:
                sub = os.path.join(outdir, d["outdir_rel"])
                res = staticgen.build(conn, d, sub, view=view, datasets=listing)
                if d["primary"]:
                    # Keep the legacy root paths alive for the deployed Worker.
                    staticgen.build(conn, d, outdir, view=view, datasets=listing)
                meta = next(x for x in listing if x["slug"] == d["slug"])
                v = view if view is not None else viewdata.build(conn, d)
                entries.append(dict(meta, captured_at=v["captured_at"],
                                    tracked=v["stats"]["tracked"],
                                    top3=[i["name"] for i in v["items"][:3]]))
                print(f"  {d['slug']:26} {res['chart_rows']:>3} rows -> {sub}")
            finally:
                if conn:
                    conn.close()
        except Exception as exc:
            failed.append(d["slug"])
            print(f"  {d['slug']:26} FAILED: {exc}", file=sys.stderr)
            import traceback
            traceback.print_exc()

    for country in sorted({d["country"] for d in ds}):
        src = _releases_path(country)
        if os.path.exists(src):
            with open(src) as fh:
                staticgen.write_releases(country, json.load(fh), outdir)

    if entries:
        # No landing page: the root IS the primary dashboard, and country and
        # genre are filters inside it like every other filter.
        staticgen.write_manifest(entries, outdir)
        print(f"  manifest -> {outdir}/manifest.json ({len(entries)} datasets)")
    return 1 if failed else 0


def _cmd_export_single(args, cfg):
    conn = store.connect()
    if args.prune:
        print("pruned:", store.prune(conn))
    result = staticgen.build(conn, cfg, args.outdir)
    print(f"Wrote {result['outdir']}/ -- {result['chart_rows']} chart rows, "
          f"{result['new']} new releases, {result['events']} signals")
    print("Slack payloads:", ", ".join(result["slack_payloads"]))
    conn.close()
    return 0


def cmd_schedule(args, cfg):
    if args.action == "install":
        return install_launchd(cfg)
    if args.action == "uninstall":
        return uninstall_launchd()
    return schedule_status()


def build_parser():
    p = argparse.ArgumentParser(
        prog="topgames",
        description="Track App Store puzzle-game charts and push digests to Slack.")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init", help="create config.json and the database")
    p_init.add_argument("--force", action="store_true")

    p_ref = sub.add_parser("refresh", help="pull the chart and new releases, derive signals")
    p_ref.add_argument("--platform", choices=["ios", "play"], default=None,
                       help="refresh only this platform's datasets")

    p_serve = sub.add_parser("serve", help="start the web dashboard")
    p_serve.add_argument("--port", default=None)
    p_serve.add_argument("--host", default=None)

    d = sub.add_parser("digest", help="build and send a Slack digest")
    d.add_argument("period", choices=["daily", "weekly"])
    d.add_argument("--dry-run", action="store_true",
                   help="print the Slack payload instead of sending it")
    d.add_argument("--if-due", action="store_true", dest="if_due",
                   help="post only past the scheduled hour, and only once a day")

    r = sub.add_parser("run", help="refresh then send a digest (for scheduled jobs)")
    r.add_argument("period", choices=["daily", "weekly"])
    r.add_argument("--dry-run", action="store_true")

    sub.add_parser("slack-test", help="post a connection test to Slack")
    c = sub.add_parser("chart", help="print the stored chart")
    c.add_argument("--limit", type=int, default=100)

    e = sub.add_parser("export", help="render the static site and Slack payloads")
    e.add_argument("--outdir", default="site")
    e.add_argument("--prune", action="store_true",
                   help="trim old snapshots before exporting")

    s = sub.add_parser("schedule", help="manage macOS launchd jobs")
    s.add_argument("action", choices=["install", "uninstall", "status"])
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    cfg = config.load()
    handlers = {
        "init": cmd_init, "refresh": cmd_refresh, "digest": cmd_digest,
        "run": cmd_run, "slack-test": cmd_slack_test, "serve": cmd_serve,
        "chart": cmd_chart, "schedule": cmd_schedule, "export": cmd_export,
    }
    return handlers[args.cmd](args, cfg)
