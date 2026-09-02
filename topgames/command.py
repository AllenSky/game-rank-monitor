"""Slash command endpoint (/top100).

Slack posts form-encoded requests here and expects a reply within 3 seconds.
Anything slower (a refresh takes ~25s) is acknowledged immediately and the real
answer is delivered afterwards to the request's response_url.
"""
import hashlib
import hmac
import json
import threading
import time
import urllib.parse
import urllib.request

from . import signals, store

MAX_SECTION = 2900          # Slack's section limit is 3000; leave headroom.
LINES_PER_SECTION = 20      # ~1400 chars, comfortably inside the limit.
REPLAY_WINDOW = 60 * 5      # Reject anything older than 5 minutes.

HELP = (
    "*`/top100` — App Store chart lookup*\n"
    "`/top100` — the current top 25\n"
    "`/top100 50` — the top 50 (max 100)\n"
    "`/top100 new` — games released recently\n"
    "`/top100 signals` — recent chart movement\n"
    "`/top100 refresh` — pull fresh data from Apple (takes ~25s)\n"
    "`/top100 share` — post the top 25 visibly to the channel\n"
)


def verify(signing_secret, timestamp, signature, raw_body):
    """Confirm a request genuinely came from Slack.

    Without this anyone who learns the URL could trigger the command, so a
    missing secret is treated as a failure rather than skipped.
    """
    if not signing_secret:
        return False, "no signing secret configured"
    if not timestamp or not signature:
        return False, "missing signature headers"
    try:
        if abs(time.time() - int(timestamp)) > REPLAY_WINDOW:
            return False, "stale timestamp"
    except ValueError:
        return False, "bad timestamp"
    base = b"v0:" + timestamp.encode() + b":" + raw_body
    mine = "v0=" + hmac.new(signing_secret.encode(), base, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(mine, signature):
        return False, "signature mismatch"
    return True, ""


def _stars(r):
    return f"{r:.2f}★" if r else "—"


def _section(text):
    return {"type": "section", "text": {"type": "mrkdwn", "text": text[:MAX_SECTION]}}


def _chunk(lines, header):
    """Split a long list across sections so no block exceeds Slack's limit."""
    blocks = [_section(header)]
    for start in range(0, len(lines), LINES_PER_SECTION):
        blocks.append(_section("\n".join(lines[start:start + LINES_PER_SECTION])))
    return blocks


def _reply(blocks, text, in_channel=False):
    return {
        "response_type": "in_channel" if in_channel else "ephemeral",
        "text": text,
        "blocks": blocks,
    }


def _chart_reply(conn, cfg, limit, in_channel):
    snap, rows = store.latest_chart(conn, cfg["chart"])
    if not rows:
        return _reply([_section(
            ":warning: No data stored yet. Run `/top100 refresh` first.")],
            "no data")
    snaps = store.recent_snapshots(conn, cfg["chart"], limit=2)
    prev = store.snapshot_ranks(conn, snaps[1]["id"]) if len(snaps) > 1 else {}
    rows = rows[:limit]
    lines = []
    for r in rows:
        p = prev.get(r["app_id"])
        if not prev:
            move = ""
        elif p is None:
            move = "  :new:"
        elif p - r["rank"] > 0:
            move = f"  ▲{p - r['rank']}"
        elif p - r["rank"] < 0:
            move = f"  ▼{r['rank'] - p}"
        else:
            move = "  ·"
        lines.append(f"`{r['rank']:>3}` <{r['url']}|{r['name'][:38]}> "
                     f"— {_stars(r['avg_rating'])}{move}")
    genre = cfg["genre"].replace("_", " ").title()
    header = (f"*Top {len(rows)} {genre} — {cfg['country'].upper()}*\n"
              f"_captured {snap['captured_at'][:16].replace('T',' ')} UTC_")
    return _reply(_chunk(lines, header), f"Top {len(rows)} {genre}", in_channel)


def _new_reply(conn, cfg, in_channel):
    from .web import _new_releases
    rows = _new_releases(conn, cfg)[:25]
    if not rows:
        return _reply([_section("No recent releases stored yet.")], "none")
    lines = [f"• <{r['url']}|{r['name'][:38]}> — {(r['release_date'] or '')[:10]} "
             f"· {_stars(r['avg_rating'])}" for r in rows]
    genre = cfg["genre"].replace("_", " ").title()
    return _reply(_chunk(lines, f"*New {genre} releases* (last "
                  f"{cfg['signals']['new_release_days']} days)"),
                  "new releases", in_channel)


def _signals_reply(conn, cfg, in_channel):
    from datetime import datetime, timedelta, timezone
    since = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    evs = store.events_since(conn, since)[:25]
    if not evs:
        return _reply([_section(
            "No chart movement recorded in the last 7 days.")], "no signals")
    lines = [f"• `{e['kind']}` <{e['url']}|{(e['name'] or '?')[:34]}> — {e['detail']}"
             for e in evs]
    return _reply(_chunk(lines, "*Signals — last 7 days*"), "signals", in_channel)


def _post_response(response_url, payload):
    req = urllib.request.Request(
        response_url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=15).read()
    except Exception as exc:
        print(f"delayed slash response failed: {exc}")


def _refresh_async(cfg, response_url):
    """Run a refresh off the request thread and report back when it finishes."""
    def work():
        conn = store.connect()
        try:
            s = signals.refresh(conn, cfg, verbose=False)
            msg = (f":white_check_mark: Refreshed — {s['chart_size']} ranked, "
                   f"*{s['new_entries']}* new in chart, *{s['new_releases']}* new "
                   f"releases, {s['movers']} big movers.")
            if s["baseline"]:
                msg = (":white_check_mark: Baseline stored. Run `/top100 refresh` "
                       "again later to start seeing movement.")
            _post_response(response_url, _reply([_section(msg)], "refreshed"))
        except Exception as exc:
            _post_response(response_url,
                           _reply([_section(f":x: Refresh failed: {exc}")], "failed"))
        finally:
            conn.close()
    threading.Thread(target=work, daemon=True).start()


def handle(cfg, form):
    """Route a parsed slash command payload to a Slack reply dict."""
    text = (form.get("text", [""])[0] or "").strip().lower()
    response_url = (form.get("response_url", [""])[0] or "")
    conn = store.connect()
    try:
        if text in ("help", "?"):
            return _reply([_section(HELP)], "help")
        if text == "refresh":
            if not response_url:
                return _reply([_section("No response_url supplied.")], "error")
            _refresh_async(cfg, response_url)
            return _reply([_section(
                ":hourglass_flowing_sand: Pulling fresh data from Apple — "
                "this takes about 25 seconds. I'll post the result here.")],
                "refreshing")
        if text.startswith("new"):
            return _new_reply(conn, cfg, in_channel=False)
        if text.startswith("signal"):
            return _signals_reply(conn, cfg, in_channel=False)
        if text.startswith("share"):
            return _chart_reply(conn, cfg, 25, in_channel=True)
        limit = 25
        if text.isdigit():
            limit = max(1, min(int(text), cfg["chart_size"]))
        elif text:
            return _reply([_section(f":question: Unknown option `{text}`.\n\n{HELP}")],
                          "help")
        return _chart_reply(conn, cfg, limit, in_channel=False)
    finally:
        conn.close()
