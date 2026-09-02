"""Block Kit digests, per slack_digest_spec.md.

Colour comes only from links, emoji, `code` spans and the primary button --
Block Kit offers nothing else. The rating dot is data: it encodes the rating
band, so it differs row to row rather than decorating every line the same way.

Section order is fixed: new releases, in/out, current top 10, movers, and --
weekly only -- publishers. Daily and weekly carry deliberately different
headers, icons and fallback text so the two are told apart at a glance in a
busy channel.
"""
from datetime import datetime, timedelta, timezone

from . import companies, config, store, viewdata

PLATFORM_BADGE = {"ios": "🍎", "play": "🤖"}


def _badge(e):
    return PLATFORM_BADGE.get(e.get("platform"), "")

MAX_BLOCKS = 50
SECTION_LIMIT = 2900          # Slack's ceiling is 3000; leave headroom.
FIELD_LIMIT = 1900            # Ceiling is 2000 per field.
DAILY_NEW_SHOWN = 12
WEEKLY_NEW_SHOWN = 15
LAUNCH_TODAY = "🚀"           # Marks a game that shipped today, not merely this window.
MAX_CHIPS = 3                 # Genre chips per release.
QUIET_MOVE = 3                # |delta| below this does not count as movement.
MOVERS_SHOWN = 5
OUT_SHOWN = 12
PUBS_SHOWN = 8

PERIOD = {
    "daily":  {"emoji": "📅", "label": "DAILY",  "icon": ":sunrise:"},
    "weekly": {"emoji": "🗓️", "label": "WEEKLY", "icon": ":bar_chart:"},
}


def dot(rating, count):
    if not count:
        return "⚪"
    if rating >= 4.7:
        return "🟢"
    if rating >= 4.0:
        return "🟡"
    return "🔴"


def rating_str(rating, count):
    return f"{rating:.2f}★ ({count:,})" if count else "no ratings yet"


def delta_str(d):
    if d is None:
        return "—"
    if d > 0:
        return f"▲{d}"
    if d < 0:
        return f"▼{abs(d)}"
    return "—"


def _section(text):
    return {"type": "section", "text": {"type": "mrkdwn", "text": text[:SECTION_LIMIT]}}


def _context(text):
    return {"type": "context", "elements": [{"type": "mrkdwn", "text": text[:SECTION_LIMIT]}]}


def _quote(lines):
    """Slack's only grouping device: a quote bar down the left of a run."""
    return "\n".join(f"> {ln}" for ln in lines)


def chips(r):
    """Genre labels as `code` spans -- the closest Block Kit has to a tag."""
    gs = r.get("genres") or []
    if isinstance(gs, str):
        gs = [g for g in gs.split(",") if g]
    return " ".join(f"`{g}`" for g in gs[:MAX_CHIPS])


def _mover_line(m):
    return (f"{delta_str(m['delta'])}  <{m['url']}|{m['name']}>{_paren(m.get('play_url'))}"
            + (f"  → `#{m['rank']}`" if m.get("rank") else ""))


def _top10_lines(rows):
    # The rank sits inside backticks so Slack renders it monospaced and the
    # column stays aligned; padding with plain spaces would be collapsed.
    return [f"`{r['rank']:>2}` {delta_str(r['delta']):>3}  "
            f"<{r['url']}|{r['name']}>{_paren(r.get('play_url'))}  "
            f"{r['rating']:.2f}★ · {r['artist']}" for r in rows]


def _paren(url):
    return f"({_android(url)})" if url else ""


def _android(url, label="And"):
    """Slack wants & escaped inside a link, and the Play URL carries one."""
    return f"<{url.replace('&', '&amp;')}|{label}>" if url else ""


def _play_for(e):
    """Chart events carry the bundle id; releases arrive with the URL built."""
    try:
        bundle = e["bundle_id"]
    except (IndexError, KeyError):
        bundle = ""
    return viewdata.play_url(bundle, e["name"])


def _newrel_line(r):
    """One line: title, publisher, rating if it has one, genre chips.

    An unrated game says nothing about its rating rather than saying it has
    none -- and with no rating there is no band for the dot to encode, so it
    goes too. No bold on the name: Slack renders *<url|text>* literally,
    asterisks and all, and the link colour already sets the title apart.
    """
    band = f"{dot(r['rating'], r['ratings'])} " if r["ratings"] else ""
    rated = f" · {rating_str(r['rating'], r['ratings'])}" if r["ratings"] else ""
    tag = chips(r)
    return (f"{band}<{r['url']}|{r['name']}>{_paren(r.get('play_url'))}"
            f"   {r['artist']}{rated}"
            + (f"   {tag}" if tag else "")
            + (f"  `TOP 100 #{r['rank']}`" if r.get("rank") else ""))


def _day_label(iso):
    try:
        return datetime.fromisoformat(iso).strftime("%b %d").upper()
    except ValueError:
        return "EARLIER"


def recent_releases(rows, days, shown):
    """Releases inside the window, newest first. The window is strict.

    Apple publishes no new-release feed, so this is a discovery sweep and some
    days it surfaces one game. That is the honest answer, so a thin window
    stays thin rather than quietly reaching further back.
    """
    inside = [r for r in rows if (r.get("days_old") or 0) <= days]
    inside = sorted(inside, key=lambda r: (r.get("released") or "", r["rating"]),
                    reverse=True)
    return inside[:shown], len(inside)


def launched_today(rows):
    return [r for r in rows if (r.get("days_old") or 0) == 0]


def group_by_day(rows):
    """Group releases by date, newest first.

    A day carrying three or more items stands alone. Thinner days merge with
    their neighbours, but only until the merged group itself reaches three --
    otherwise a fortnight of quiet days collapses into one meaningless range.
    """
    buckets = {}
    for r in rows:
        buckets.setdefault(r["released"], []).append(r)
    days = sorted(buckets, reverse=True)

    out, i = [], 0
    while i < len(days):
        if len(buckets[days[i]]) >= 3:
            out.append((_day_label(days[i]),
                        sorted(buckets[days[i]], key=lambda r: -r["rating"])))
            i += 1
            continue
        j, merged = i, []
        while j < len(days) and len(buckets[days[j]]) < 3 and len(merged) < 3:
            merged += buckets[days[j]]
            j += 1
        newest, oldest = _day_label(days[i]), _day_label(days[j - 1])
        if newest == oldest:
            label = newest
        elif newest.split()[0] == oldest.split()[0]:      # same month
            label = f"{oldest} – {newest.split()[1]}"
        else:
            label = f"{oldest} – {newest}"
        out.append((label, sorted(merged, key=lambda r: -r["rating"])))
        i = j
    return out


def _two_column(lines):
    """Top 10 as two side-by-side fields, as the spec lays it out."""
    half = (len(lines) + 1) // 2
    left, right = lines[:half], lines[half:]
    fields = [{"type": "mrkdwn", "text": "\n".join(left)[:FIELD_LIMIT]}]
    if right:
        fields.append({"type": "mrkdwn", "text": "\n".join(right)[:FIELD_LIMIT]})
    return {"type": "section", "fields": fields}


def release_blocks(rows, in_window, window_days):
    """The leading section: what shipped, grouped by day, with genre chips.

    Anything that launched *today* is called out in the subtitle and kept in
    its own group -- inside a 3- or 7-day window "new" otherwise blurs, and a
    same-day launch is the one thing worth reacting to immediately.
    """
    fresh = launched_today(rows)
    n = in_window
    caption = (f"*🆕 NEW RELEASES*  ·  _last {window_days} days_  ·  "
               f"`{n} game{'' if n == 1 else 's'}`"
               + (f"  ·  _showing the {len(rows)} newest_" if len(rows) < n else ""))
    if fresh:
        earlier = n - len(fresh)
        caption += (f"\n{LAUNCH_TODAY} *{len(fresh)} launched today*"
                    + (f"  ·  _{earlier} earlier in the window_" if earlier else ""))
    blocks = [_section(caption)]

    # group_by_day merges thin days into ranges, which would fold today into
    # "AUG 19 - 24" and lose exactly the distinction we just drew.
    if fresh:
        blocks.append(_section(f"*{LAUNCH_TODAY} TODAY*\n" +
                               _quote(_newrel_line(r) for r in
                                      sorted(fresh, key=lambda r: -r["rating"]))))
    rest = [r for r in rows if (r.get("days_old") or 0) != 0]
    for label, items in group_by_day(rest):
        blocks.append(_section(f"*{label}*\n" +
                               _quote(_newrel_line(r) for r in items)))
    more = in_window - len(rows)
    if more > 0:
        blocks.append(_context(f"_…and {more} more in the last {window_days} days_"))
    return blocks


def watched_blocks(overview, max_titles=6, max_versions=4):
    """The watched-companies section: charting titles + fresh version bumps."""
    rows, blocks = [], []
    for comp in overview:
        if not comp["any"]:
            continue
        badges = []
        if comp["titles"]:
            plats = sorted({t["platform"] for t in comp["titles"]})
            badges.append(f"{len(comp['titles'])} charting (" +
                          "/".join(PLATFORM_BADGE.get(p, p) for p in plats) + ")")
        if comp["new_versions"]:
            badges.append(f"{len(comp['new_versions'])} update"
                          + ("s" if len(comp["new_versions"]) > 1 else ""))
        lines = [f"👁 *{comp['name']}* — " + " · ".join(badges)] if badges else []
        for t in comp["titles"][:max_titles]:
            move = ""
            if t["delta"]:
                arrow = "▲" if t["delta"] > 0 else "▼"
                move = f" {arrow}{abs(t['delta'])}"
            freq = t.get("update_frequency") or {}
            cadence = (f" · {freq['count']}↑/90d"
                       if freq.get("count") else "")
            lines.append(f"  {_badge(t)} `#{t['rank']}` <{t['url']}|{t['name']}>"
                         f" ({t['platform']}·{t['genre']}){move}{cadence}")
        for v in comp["new_versions"][:max_versions]:
            day = (v["first_seen"] or "")[:10]
            lines.append(f"  {_badge(v)} ⬆ <{v['url']}|{v['name']}> "
                         f"v{v['version']} ({day})")
        rows += lines
    if not rows:
        return []
    text = "\n".join(rows[:30])
    blocks.append(_section("*👁 WATCHED COMPANIES*"))
    blocks.append(_section(text[:SECTION_LIMIT]))
    return blocks


def in_out_blocks(entered, exited, period_label):
    """`In` carries each game's live rank; `out` is a plain comma list."""
    if not entered and not exited:
        return []
    blocks = [_section(f"*🔄 IN AND OUT*  ·  _{period_label}_")]
    if entered:
        rows = sorted(entered, key=lambda e: e.get("rank") or 999)
        blocks.append(_section(
            f"*In* `{len(entered)}`\n" + _quote(
                f"{_badge(e)} `#{e['rank']}`  <{e['url']}|{e['name']}>"
                f"{_paren(_play_for(e))} — {e['artist']}"
                for e in rows)))
    if exited:
        names = ", ".join(f"<{e['url']}|{e['name']}>{_paren(_play_for(e))}"
                          for e in exited[:OUT_SHOWN])
        more = len(exited) - OUT_SHOWN
        if more > 0:
            names += f", …and {more} more"
        blocks.append(_section(f"*Out* `{len(exited)}`\n" + _quote([names])))
    return blocks


def mover_blocks(up, down, period_label):
    if not up and not down:
        return []
    blocks = [_section(f"*📊 MOVERS*  ·  _{period_label}_  ·  "
                       f"_{len(up)} up, {len(down)} down_")]
    if up:
        blocks.append(_section("*Climbing*\n" +
                               _quote(_mover_line(m) for m in up[:MOVERS_SHOWN])))
    if down:
        blocks.append(_section("*Falling*\n" +
                               _quote(_mover_line(m) for m in down[:MOVERS_SHOWN])))
    return blocks


def publisher_blocks(items):
    """Company first, then how many it has charting, then exactly which ranks.

    The old form led with a bare count and a net rank delta summed across a
    publisher's titles, which read as noise; the ranks themselves are the
    thing anyone actually wanted.
    """
    ranks = {}
    urls = {}
    for r in items:
        ranks.setdefault(r["artist"], []).append(r["rank"])
        urls.setdefault(r["artist"], r.get("artist_url"))
    pubs = [(a, sorted(rs)) for a, rs in ranks.items() if len(rs) > 1]
    pubs.sort(key=lambda p: (-len(p[1]), p[1][0]))
    if not pubs:
        return []
    lines = []
    for artist, rs in pubs[:PUBS_SHOWN]:
        # Bold only when it is not a link: *<url|text>* renders literally.
        name = (f"<{urls[artist]}|{artist}>" if urls.get(artist)
                else f"*{artist}*")
        lines.append(f"{name} — {len(rs)} games — "
                     + ", ".join(f"#{n}" for n in rs))
    return [_section("*🏢 PUBLISHERS IN THE TOP 100*\n" + _quote(lines))]


def _actions(cfg, new_count, weekly):
    dash = cfg["web"].get("pages_url") or cfg["web"].get("repo_url") or ""
    if not dash:
        return None
    els = [{"type": "button", "style": "primary",
            "text": {"type": "plain_text", "text": "Open dashboard"}, "url": dash}]
    if new_count:
        els.append({"type": "button",
                    "text": {"type": "plain_text", "text": "All new releases"},
                    "url": dash})
    if weekly:
        # The spec's action_id button needs a bot token and an interactivity
        # endpoint; an incoming webhook has neither, so this links out instead.
        els.append({"type": "button",
                    "text": {"type": "plain_text", "text": "Movers"}, "url": dash})
    return {"type": "actions", "elements": els[:5]}


def _entries_exits(conn, cfg, since):
    """Where each game ended the window, not every move it made inside it.

    Over a week a game can enter, drop out and enter again. Listing it under
    both headings reads as a data error, so only its latest event counts --
    which is also the one that says where it stands now.
    """
    events = store.events_since(conn, since,
                                kinds=["new_entry", "debut", "exit"])
    latest, seen = [], set()
    for e in events:                       # newest first
        if e["app_id"] in seen:
            continue
        seen.add(e["app_id"])
        latest.append(e)
    entered = [e for e in latest if e["kind"] != "exit"]
    exited = [e for e in latest if e["kind"] == "exit"]
    return entered, exited


def build(conn, cfg, period="daily"):
    """Return (payload, event_ids). payload is None when nothing should post."""
    view = viewdata.build(conn, cfg)
    if view is None:
        return None, []

    weekly = period == "weekly"
    style = PERIOD["weekly" if weekly else "daily"]
    window = timedelta(days=7 if weekly else 1)
    since = (datetime.now(timezone.utc) - window).isoformat(timespec="seconds")
    slack_cfg = cfg["slack"][period]

    genre = cfg["genre"].replace("_", " ").title()
    country = cfg["country"].upper()
    tracked = [g.replace("_", " ").title()
               for g in (cfg.get("genres_tracked") or [cfg["genre"]])]
    scope_label = " + ".join(dict.fromkeys(tracked)) if len(tracked) > 1 else genre
    scope = f"{scope_label} · {country}"
    dash = cfg["web"].get("pages_url") or cfg["web"].get("repo_url") or ""
    tz = cfg["slack"].get("timezone", "UTC")

    movers = view["movers"]
    up = sorted([m for m in movers if m["delta"] > 0], key=lambda m: -m["delta"])
    down = sorted([m for m in movers if m["delta"] < 0], key=lambda m: m["delta"])
    entered, exited = _entries_exits(conn, cfg, since)
    new_rel = view["new_releases"]
    event_ids = [e["id"] for e in entered + exited]

    now = datetime.now()
    new_days = int(slack_cfg.get("new_days") or (7 if weekly else 3))
    shown, in_window = recent_releases(
        new_rel, new_days, WEEKLY_NEW_SHOWN if weekly else DAILY_NEW_SHOWN)
    fresh_today = launched_today(shown)
    # Repeated in the subtitle and the notification text: a same-day launch
    # should be visible without opening the message.
    today_tag = (f"  ·  {LAUNCH_TODAY} *{len(fresh_today)} launched today*"
                 if fresh_today else "")
    today_short = f" ({len(fresh_today)} today)" if fresh_today else ""
    top10 = view["items"][:10]
    period_label = "this week" if weekly else "vs yesterday"

    if weekly:
        first = now - timedelta(days=6)
        # "Aug 18-24" reads better than "Aug 18-Aug 24" when the week
        # does not straddle a month boundary.
        end = now.strftime("%d") if first.month == now.month else now.strftime("%b %d")
        title = (f"{style['emoji']} WEEKLY ROUNDUP · {scope} · "
                 f"{first.strftime('%b %d')}–{end}")
        sub = (f"_Week in review_  ·  `{cfg['chart']}`  ·  top {cfg['chart_size']}  ·  "
               f"*{in_window}* new releases{today_tag}  ·  "
               f"{len(entered)} in, {len(exited)} out")
        next_run = f'Monday {slack_cfg.get("time", "09:00")} {tz}'
        fallback = (f"[WEEKLY] {scope} — {in_window} new releases{today_short}, "
                    f"{len(entered)} in, {len(exited)} out")
    else:
        title = f"{style['emoji']} DAILY · {scope} · {now.strftime('%a, %b %d')}"
        sub = (f"_Since yesterday_  ·  `{cfg['chart']}`  ·  top {cfg['chart_size']}  ·  "
               f"new releases across all genres{today_tag}")
        next_run = f'tomorrow {slack_cfg.get("time", "09:00")} {tz}'
        fallback = (f"[DAILY] {scope} — {in_window} new{today_short}, "
                    f"{len(up)} up, {len(down)} down, {len(entered)} in")

    # A day with nothing at all to say still posts: silence is
    # indistinguishable from a broken schedule.
    real_movement = [m for m in movers if abs(m["delta"]) >= QUIET_MOVE]
    if not weekly and not real_movement and not entered and not shown:
        link = f" <{dash}|Open>" if dash else ""
        return {
            "username": cfg["slack"].get("username") or "top_games",
            "icon_emoji": slack_cfg.get("icon_emoji") or style["icon"],
            "text": f"[DAILY] {scope} — chart unchanged",
            "blocks": [_context(
                f"{style['emoji']} *DAILY* · {scope} · {now.strftime('%a, %b %d')} — "
                f"chart unchanged, no new entries or releases.{link}")],
        }, event_ids

    blocks = [
        {"type": "header",
         "text": {"type": "plain_text", "text": title[:150], "emoji": True}},
        _context(sub),
    ]
    if shown:
        blocks += [{"type": "divider"}]
        blocks += release_blocks(shown, in_window, new_days)

    io = in_out_blocks(entered, exited, "this week" if weekly else "since yesterday")
    if io:
        blocks += [{"type": "divider"}] + io

    overview = companies.watch_overview(conn, cfg, config.datasets(cfg), since)
    wb = watched_blocks(overview)
    if wb:
        blocks += [{"type": "divider"}] + wb

    blocks += [{"type": "divider"},
               _section("*🏆 CURRENT TOP 10*" + ("  ·  _7-day change_" if weekly else "")),
               _two_column(_top10_lines(top10))]

    mv = mover_blocks(up, down, "7 days" if weekly else "vs yesterday")
    if mv:
        blocks += [{"type": "divider"}] + mv

    if weekly:
        pubs = publisher_blocks(view["items"])
        if pubs:
            blocks += [{"type": "divider"}] + pubs

    act = _actions(cfg, len(new_rel), weekly)
    if act:
        blocks.append(act)
    blocks.append(_context(
        f"🍎 App Store + 🤖 Google Play · next run {next_run}"))

    if len(blocks) > MAX_BLOCKS:
        blocks = blocks[:MAX_BLOCKS - 1] + [_context("_truncated to fit Slack's block limit_")]

    mention = cfg["slack"].get("mention") or ""
    if mention:
        blocks.insert(2, _section(mention))

    return {
        "username": cfg["slack"].get("username") or "top_games",
        "icon_emoji": slack_cfg.get("icon_emoji") or style["icon"],
        "text": fallback,
        "blocks": blocks,
    }, event_ids
