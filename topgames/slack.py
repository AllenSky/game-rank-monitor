"""Slack Incoming Webhook delivery and Block Kit digest composition."""
import json
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

from . import store
from .signals import KIND_LABELS

EMOJI = {"new_entry": ":new:", "debut": ":rocket:", "exit": ":arrow_down_small:",
         "climb": ":chart_with_upwards_trend:", "fall": ":chart_with_downwards_trend:",
         "new_release": ":sparkles:"}
SLACK_TEXT_LIMIT = 2900  # Block Kit section limit is 3000; leave headroom.
MAX_BLOCKS = 50          # Hard Slack ceiling per message.
RESERVED_BLOCKS = 6      # Room for the remaining sections and the footer.


class SlackError(RuntimeError):
    pass


def post(webhook_url, payload, timeout=15):
    if not webhook_url:
        raise SlackError(
            "No webhook configured. Add slack.webhook_url to config.json.")
    from . import lark
    if lark.is_lark(webhook_url):
        return lark.post(webhook_url, payload, timeout)
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        webhook_url, data=body,
        headers={"Content-Type": "application/json", "User-Agent": "top-games/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8").strip()
            if text != "ok":
                raise SlackError(f"Slack replied {resp.status}: {text}")
            return True
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace").strip()
        hint = ""
        if exc.code == 404:
            hint = " -- the webhook URL looks wrong or was revoked."
        elif exc.code == 403:
            hint = " -- the app may have been removed from the channel."
        raise SlackError(f"Slack rejected the message ({exc.code} {detail}){hint}")
    except urllib.error.URLError as exc:
        raise SlackError(f"Could not reach Slack: {exc.reason}")


def _stars(rating):
    if not rating:
        return "unrated"
    return f"{rating:.2f}★"


def _current_new_releases(conn, cfg):
    """Every tracked release inside the new-release window, newest first."""
    days = cfg["signals"]["new_release_days"]
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    genre = cfg["genre"].replace("_", " ").title()
    rows = conn.execute("""
        SELECT app_id, name, artist, url, avg_rating, rating_count, release_date
        FROM apps WHERE release_date >= ? AND genres LIKE ?
        ORDER BY release_date DESC
    """, (cutoff, f"%{genre}%")).fetchall()
    return [dict(r, kind="new_release", detail="") for r in rows]


def _chunk_sections(lines, budget):
    """Split lines across as many sections as the char and block limits allow.

    Returns (blocks, dropped). New releases are never truncated to a fixed count
    -- only the hard Block Kit ceiling can cut the list, and the caller reports
    whatever had to be left out.
    """
    blocks, buf, size = [], [], 0
    for i, line in enumerate(lines):
        extra = len(line) + 1
        if buf and size + extra > SLACK_TEXT_LIMIT:
            if len(blocks) >= budget:
                return blocks, len(lines) - i
            blocks.append(_section("\n".join(buf)))
            buf, size = [], 0
        buf.append(line)
        size += extra
    if buf:
        if len(blocks) >= budget:
            return blocks, len(buf)
        blocks.append(_section("\n".join(buf)))
    return blocks, 0


def _line(ev, chart_ranks=None):
    """One markdown line describing an event."""
    name = ev.get("name") or f"app {ev['app_id']}"
    url = ev.get("url") or ""
    title = f"<{url}|{name}>" if url else f"*{name}*"
    artist = ev.get("artist") or ""
    bits = []
    if ev["kind"] in ("new_entry", "debut"):
        bits.append(f"entered at *#{ev['rank']}*")
    elif ev["kind"] == "climb":
        bits.append(f"*#{ev['prev_rank']} → #{ev['rank']}* (+{ev['delta']})")
    elif ev["kind"] == "fall":
        bits.append(f"*#{ev['prev_rank']} → #{ev['rank']}* ({ev['delta']})")
    elif ev["kind"] == "exit":
        bits.append(f"left from *#{ev['prev_rank']}*")
    elif ev["kind"] == "new_release":
        rel = (ev.get("release_date") or "")[:10]
        bits.append(f"released {rel}" if rel else "new release")
    rating = ev.get("avg_rating") or 0
    count = ev.get("rating_count") or 0
    if count:
        bits.append(f"{_stars(rating)} ({count:,})")
    rank = (chart_ranks or {}).get(ev.get("app_id"))
    if rank and ev["kind"] == "new_release":
        bits.append(f"`TOP 100 #{rank}`")
    tail = " · ".join(bits)
    return f"{EMOJI.get(ev['kind'],'•')} {title} — {artist}\n     {tail}"


def _play_paren(row):
    """(And) -- a Google Play search beside the App Store link.

    & has to be escaped inside a Slack link, and the search URL carries one.
    """
    url = row.get("play_url") if hasattr(row, "get") else None
    return f"(<{url.replace('&', '&amp;')}|And>)" if url else ""


def _section(text):
    return {"type": "section", "text": {"type": "mrkdwn", "text": text[:SLACK_TEXT_LIMIT]}}


def _group(events, kind, limit):
    picked = [e for e in events if e["kind"] == kind]
    if kind in ("new_entry", "debut"):
        picked.sort(key=lambda e: e["rank"] or 999)
    elif kind == "climb":
        picked.sort(key=lambda e: -(e["delta"] or 0))
    elif kind == "fall":
        picked.sort(key=lambda e: (e["delta"] or 0))
    return picked[:limit], max(0, len(picked) - limit)


def build_digest(conn, cfg, period="daily", since=None):
    """Compose the Block Kit payload for a digest. Returns (payload, event_ids)."""
    slack_cfg = cfg["slack"][period]
    sig = cfg["signals"]
    limit = sig["max_items_per_section"]
    window = timedelta(days=1 if period == "daily" else 7)
    since = since or (datetime.now(timezone.utc) - window).isoformat(timespec="seconds")

    kinds = slack_cfg["include"]
    events = store.events_since(conn, since, kinds=kinds)
    event_ids = [e["id"] for e in events]

    # Current ranks, so a new release that has already charted can say so.
    _snap, _rows = store.latest_chart(conn, cfg["chart"], genre_id=cfg.get("genre_id"),
                          platform=cfg.get("platform", "ios"))
    chart_ranks = {r["app_id"]: r["rank"] for r in _rows}

    genre = cfg["genre"].replace("_", " ").title()
    country = cfg["country"].upper()
    label = "Daily" if period == "daily" else "Weekly"
    stamp = datetime.now().strftime("%b %d, %Y")
    heading = slack_cfg.get("title") or f"{label} {genre} Games Report — {country}"

    blocks = [
        {"type": "header", "text": {"type": "plain_text",
         "text": heading[:150], "emoji": True}},
        {"type": "context", "elements": [{"type": "mrkdwn",
         "text": f"{stamp} · chart: `{cfg['chart']}` · top {cfg['chart_size']}"}]},
    ]

    # Headline counters so the channel gets the answer without reading the list.
    entered = [e for e in events if e["kind"] in ("new_entry", "debut")]
    released = [e for e in events if e["kind"] == "new_release"]
    if entered or released:
        summary = []
        if entered:
            summary.append(f"*{len(entered)}* new to the top {cfg['chart_size']}")
        if released:
            summary.append(f"*{len(released)}* newly released")
        blocks.append(_section(" · ".join(summary)))
    else:
        blocks.append(_section(
            f":white_check_mark: No new games entered the top {cfg['chart_size']} "
            f"this {'day' if period=='daily' else 'week'}."))

    order = ["debut", "new_entry", "new_release", "climb", "fall", "exit"]
    for kind in order:
        if kind not in kinds:
            continue
        if kind == "new_release":
            # Sourced from the same query the dashboard uses, so the two always
            # agree. Reporting only newly-discovered releases would show a
            # different, smaller set than the page does.
            picked = _current_new_releases(conn, cfg)
            if not picked:
                continue
            charted = sum(1 for e in picked if chart_ranks.get(e["app_id"]))
            blocks.append({"type": "divider"})
            blocks.append(_section(
                f"*{KIND_LABELS[kind]}*  ({len(picked)}"
                + (f", {charted} in the top {cfg['chart_size']}" if charted else "") + ")"))
            budget = MAX_BLOCKS - len(blocks) - RESERVED_BLOCKS
            body, dropped = _chunk_sections(
                [_line(e, chart_ranks) for e in picked], budget)
            blocks.extend(body)
            if dropped:
                blocks.append({"type": "context", "elements": [{"type": "mrkdwn",
                    "text": f"_…and {dropped} more — see the dashboard_"}]})
            continue
        picked, extra = _group(events, kind, limit)
        if not picked:
            continue
        blocks.append({"type": "divider"})
        heading = f"*{KIND_LABELS[kind]}*  ({len(picked) + extra})"
        body = "\n".join(_line(e, chart_ranks) for e in picked)
        if extra:
            body += f"\n_…and {extra} more_"
        blocks.append(_section(f"{heading}\n{body}"))

    top_n = int(slack_cfg.get("show_top_n") or 0)
    if top_n:
        snap, rows = store.latest_chart(conn, cfg["chart"], genre_id=cfg.get("genre_id"),
                          platform=cfg.get("platform", "ios"))
        if rows:
            top = rows[:top_n]
            body = "\n".join(
                f"`{r['rank']:>3}` <{r['url']}|{r['name']}> — {_stars(r['avg_rating'])}"
                for r in top)
            blocks.append({"type": "divider"})
            blocks.append(_section(f"*Current top {len(top)}*\n{body}"))

    blocks.append({"type": "context", "elements": [{"type": "mrkdwn",
        "text": "Source: Apple App Store (iTunes RSS + Search API) · "
                "generated by top_games"}]})

    mention = cfg["slack"].get("mention") or ""
    if mention:
        blocks.insert(2, _section(mention))

    payload = {
        "username": cfg["slack"].get("username") or "Top Games Bot",
        "icon_emoji": cfg["slack"].get("icon_emoji") or ":jigsaw:",
        "text": f"{label} {genre} games report: {len(entered)} new to chart, "
                f"{len(released)} new releases",  # notification fallback text
        "blocks": blocks,
    }
    # An empty digest is only worth sending if the channel wants the heartbeat.
    if slack_cfg.get("skip_if_empty") and not events:
        return None, []
    return payload, event_ids


def build_realtime_alert(cfg, events):
    """A compact 'a new game just entered the chart' alert."""
    genre = cfg["genre"].replace("_", " ").title()
    lines = "\n".join(_line(e) for e in events[:10])
    return {
        "username": cfg["slack"].get("username") or "Top Games Bot",
        "icon_emoji": cfg["slack"].get("icon_emoji") or ":jigsaw:",
        "text": f"{len(events)} new game(s) entered the {genre} top {cfg['chart_size']}",
        "blocks": [
            _section(f":rotating_light: *New in the {genre} top "
                     f"{cfg['chart_size']} ({cfg['country'].upper()})*\n{lines}"),
        ],
    }


def test_message(cfg):
    return {
        "username": cfg["slack"].get("username") or "Top Games Bot",
        "icon_emoji": cfg["slack"].get("icon_emoji") or ":jigsaw:",
        "text": "top_games connection test",
        "blocks": [_section(
            ":white_check_mark: *top_games is connected.*\n"
            f"Tracking `{cfg['chart']}` · {cfg['genre']} · "
            f"{cfg['country'].upper()} · top {cfg['chart_size']}.")],
    }


def build_share(conn, cfg, kind):
    """Ready-to-post payloads for the dashboard's Share button.

    Built here, published as static files, and forwarded verbatim by the Worker
    so the endpoint can never be made to post arbitrary text into the channel.
    """
    from . import viewdata
    view = viewdata.build(conn, cfg)
    if view is None:
        return None
    scope = f"{cfg['genre'].replace('_',' ').title()} · {cfg['country'].upper()}"
    base = {"username": cfg["slack"].get("username") or "Top Games Bot",
            "icon_emoji": cfg["slack"].get("icon_emoji") or ":jigsaw:"}
    span = f"{view['span_days']} day(s)" if view["span_days"] >= 1 else "today"

    if kind == "movers":
        movers = view["movers"]
        up = [m for m in movers if m["delta"] > 0]
        down = [m for m in movers if m["delta"] < 0]
        if not movers:
            body = "_No rank movement recorded yet._"
        else:
            line = lambda m: (
                f"{'▲' if m['delta'] > 0 else '▼'} <{m['url']}|{m['name']}>"
                f"{_play_paren(m)} "
                f"{'up' if m['delta'] > 0 else 'down'} {abs(m['delta'])} — now #{m['rank']}")
            body = "\n".join([line(m) for m in up] + [line(m) for m in down])
        blocks = [_section(f"*Movers — {scope}*\n"
                           f"_{len(up)} up · {len(down)} down over {span}_\n\n{body}")]
        text = f"Movers {scope}: {len(up)} up, {len(down)} down"

    elif kind == "new":
        rows = view["new_releases"]
        charted = sum(1 for r in rows if r["rank"])
        lines = [f"• <{r['url']}|{r['name']}>{_play_paren(r)} — {r['artist']} · "
                 f"{(str(round(r['rating'],2)) + '★') if r['rating'] else 'no ratings yet'}"
                 f" · {r['released']}" + (f"  `TOP 100 #{r['rank']}`" if r["rank"] else "")
                 for r in rows]
        head = (f"*New releases — {scope}*\n_{len(rows)} in the last "
                f"{cfg['signals']['new_release_days']} days · {charted} in the top "
                f"{cfg['chart_size']}_")
        blocks = [_section(head)]
        chunks, dropped = _chunk_sections(lines, MAX_BLOCKS - 3)
        blocks += chunks
        if dropped:
            blocks.append({"type": "context", "elements": [
                {"type": "mrkdwn", "text": f"_…and {dropped} more_"}]})
        text = f"New releases {scope}: {len(rows)} ({charted} charting)"

    else:  # current chart
        rows = view["items"][:25]
        body = "\n".join(
            f"`{r['rank']:>2}` <{r['url']}|{r['name']}>{_play_paren(r)} — "
            f"{r['artist']} · {r['rating']:.2f}★"
            for r in rows)
        blocks = [_section(f"*Top {len(rows)} — {scope}*\n\n{body}")]
        text = f"Top {len(rows)} {scope}"

    url = cfg["web"].get("repo_url", "")
    blocks.append({"type": "context", "elements": [{"type": "mrkdwn",
        "text": f"Shared from the dashboard · captured {view['captured_at'][:16]} UTC"}]})
    return dict(base, text=text, blocks=blocks)
