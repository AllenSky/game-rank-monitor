"""Render the tracker as a static site plus pre-built Slack payloads.

GitHub Pages serves plain files, so the dashboard ships with its data inlined
rather than fetching from an API. The same run also writes the Slack slash
command responses, which lets the Cloudflare Worker stay a thin, near-zero-CPU
proxy: it verifies the request signature and returns a file built here.
"""
import json
import os
from datetime import datetime, timezone

from . import command, slack, store, viewdata
from .static_template import BODY, SCRIPT, STYLE

COUNTRY_NAMES = {"us": "United States", "gb": "United Kingdom", "de": "Germany",
                 "fr": "France", "jp": "Japan", "tr": "Türkiye", "ca": "Canada",
                 "au": "Australia", "kr": "South Korea", "cn": "China",
                 "br": "Brazil", "es": "Spain", "it": "Italy", "nl": "Netherlands",
                 "mx": "Mexico", "in": "India", "ru": "Russia", "pl": "Poland"}

PAGE = """<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="dark">
<title>__TITLE__</title>
<style>__STYLE__</style></head><body>
__BODY__
<script>__SCRIPT__</script>
</body></html>
"""


def _check_script(html):
    """Refuse to publish a page whose script will not parse.

    A duplicate declaration once shipped a completely blank dashboard: the
    markup was fine and every string check passed, but the script threw on load.
    node is present on the runner, so the parse is free.
    """
    import re
    import shutil
    import subprocess

    node = shutil.which("node")
    if not node:
        return
    match = re.search(r"<script>(.*?)</script>", html, re.S)
    if not match:
        return
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(match.group(1))
        tmp = fh.name
    try:
        proc = subprocess.run([node, "--check", tmp], capture_output=True, text=True)
    finally:
        os.unlink(tmp)
    if proc.returncode != 0:
        raise RuntimeError("generated page has a script error:\n"
                           + (proc.stderr or "").strip()[:600])


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        fh.write(text)


def build(conn, cfg, outdir="site", view=None, datasets=None):
    """Write the static site and the Slack payloads the Worker will serve.

    `view` lets a chart-only dataset pass a prebuilt payload instead of a
    database connection; `datasets` populates the header switcher.
    """
    if view is None:
        view = viewdata.build(conn, cfg)
    if view is None:
        raise RuntimeError("no chart data stored yet -- run `topgames refresh` first")

    genre = cfg["genre"].replace("_", " ").title()
    country = cfg["country"].upper()
    country_name = COUNTRY_NAMES.get(cfg["country"].lower(), country)
    stats = store.stats(conn) if conn is not None else {}

    data = dict(view)
    data.update({
        "genre": genre,
        "country": country,
        "country_name": country_name,
        "new_days": cfg["signals"]["new_release_days"],
        "db": stats,
        "digest": {
            "daily_time": cfg["slack"]["daily"].get("time", "09:00"),
            "daily": cfg["slack"]["daily"].get("include", []),
            "weekly_day": cfg["slack"]["weekly"].get("day", "monday").title(),
            "weekly_time": cfg["slack"]["weekly"].get("time", "09:00"),
            "weekly": cfg["slack"]["weekly"].get("include", []),
        },
        "worker_url": cfg["web"].get("worker_url", ""),
        "history": bool(cfg.get("history", True)),
        "slug": cfg.get("slug", ""),
        "datasets": datasets or [],
        "root": "../../" if cfg.get("outdir_rel") and outdir != "site" else "",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    })

    repo = cfg["web"].get("repo_url", "")
    actions = f"{repo}/actions/workflows/update.yml" if repo else "#"
    title = f"{genre}, {country_name} — Top {cfg['chart_size']}"

    html = (PAGE
            .replace("__STYLE__", STYLE)
            .replace("__BODY__", BODY
                     .replace("__SCOPE__", f"{cfg['country']} · ios · {cfg['genre']}")
                     .replace("__SYNC__", view["captured_at"][11:16])
                     .replace("__ACTIONS__", actions))
            .replace("__SCRIPT__", SCRIPT.replace("__DATA__",
                     json.dumps(data, default=str)))
            .replace("__TITLE__", title))

    _check_script(html)
    _write(os.path.join(outdir, "index.html"), html)
    # Tells GitHub Pages to publish files and folders beginning with an underscore.
    _write(os.path.join(outdir, ".nojekyll"), "")
    _write(os.path.join(outdir, "data", "chart.json"),
           json.dumps(data, indent=1, default=str))

    if conn is None:
        # No database for the command handlers to query, so the slash-command
        # payloads are rendered straight from the chart we just fetched.
        for name, payload in _payloads_from_view(view, cfg).items():
            _write(os.path.join(outdir, "slack", f"{name}.json"),
                   json.dumps(payload, default=str))
        return {"outdir": outdir, "chart_rows": len(view["items"]),
                "new": len(view["new_releases"]), "events": 0,
                "publishers": len(view["publishers"]), "span_days": 0,
                "slack_payloads": ["top100-25", "top100-50", "top100-100", "new"]}

    # Pre-render every slash-command response so the Worker does no real work.
    payloads = {
        "top100-25": command._chart_reply(conn, cfg, 25, False),
        "top100-50": command._chart_reply(conn, cfg, 50, False),
        "top100-100": command._chart_reply(conn, cfg, cfg["chart_size"], False),
        "new": command._new_reply(conn, cfg, False),
        "signals": command._signals_reply(conn, cfg, False),
        "help": command._reply([command._section(command.HELP)], "help"),
    }
    for name, payload in payloads.items():
        _write(os.path.join(outdir, "slack", f"{name}.json"),
               json.dumps(payload, default=str))

    # Payloads the Worker forwards verbatim when someone presses Share.
    for kind in ("movers", "new", "chart"):
        share = slack.build_share(conn, cfg, kind)
        if share:
            _write(os.path.join(outdir, "slack", f"share-{kind}.json"),
                   json.dumps(share, default=str))

    return {"outdir": outdir, "chart_rows": len(view["items"]),
            "new": sum(1 for i in view["items"] if i["is_new_release"]),
            "events": len(view["movers"]),
            "publishers": len(view["publishers"]),
            "span_days": view["span_days"],
            "slack_payloads": sorted(payloads)}


def build_index(entries, outdir="site"):
    """A root page listing every published dataset, plus a machine-readable manifest."""
    now = datetime.now(timezone.utc)
    cards = []
    for e in sorted(entries, key=lambda x: (not x["primary"], x["title"])):
        try:
            age_h = (now - datetime.fromisoformat(e["captured_at"])).total_seconds() / 3600
        except (ValueError, TypeError):
            age_h = 999
        stale = age_h > 36
        top = "".join(
            f'<li><span>{i+1}</span> {_esc(n)}</li>' for i, n in enumerate(e["top3"]))
        cards.append(f"""
        <a class="card" href="{_esc(e['path'])}/">
          <div class="card-head">
            <h2>{_esc(e['title'])}</h2>
            {'<span class="badge primary">primary</span>' if e['primary'] else ''}
            {'<span class="badge stale">stale</span>' if stale else ''}
          </div>
          <ol class="top3">{top}</ol>
          <div class="meta">{e['tracked']} tracked · synced {_esc(e['captured_at'][11:16])} UTC</div>
        </a>""")

    html = INDEX_PAGE.replace("__CARDS__", "".join(cards)).replace(
        "__COUNT__", str(len(entries)))
    _write(os.path.join(outdir, "index.html"), html)
    write_manifest(entries, outdir)
    return {"datasets": len(entries)}


def write_releases(country, rows, outdir="site"):
    """Publish one storefront's release pool for the dashboard to fetch."""
    _write(os.path.join(outdir, "releases", f"{country}.json"),
           json.dumps(rows, default=str))


def write_manifest(entries, outdir="site"):
    _write(os.path.join(outdir, "manifest.json"),
           json.dumps(entries, indent=1, default=str))


def _esc(v):
    return (str(v).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


INDEX_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="dark"><title>Top Games — charts</title>
<style>
:root{--bg:#0a0c10;--surface:#0f131a;--line:#1c222c;--ink:#e6ebf2;--dim:#8b95a5;
  --faint:#5c6675;--mint:#3ddc84;--signal:#ffd23f;
  --mono:ui-monospace,SFMono-Regular,Menlo,monospace;
  --sans:-apple-system,BlinkMacSystemFont,"Segoe UI",Inter,sans-serif}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
  font-family:var(--sans);padding:34px 22px 70px}
h1{font-size:30px;letter-spacing:-.028em;margin:0}
.lede{color:var(--dim);font-size:13.5px;margin:9px 0 28px}
.grid{display:grid;gap:13px;grid-template-columns:repeat(auto-fill,minmax(268px,1fr));
  max-width:1180px}
.card{display:block;text-decoration:none;color:inherit;background:var(--surface);
  border:1px solid var(--line);border-radius:11px;padding:16px;transition:border-color .12s}
.card:hover{border-color:var(--mint)}
.card-head{display:flex;align-items:center;gap:8px;margin-bottom:11px}
h2{font-size:15px;margin:0;font-weight:600;letter-spacing:-.01em}
.badge{font-family:var(--mono);font-size:9.5px;font-weight:700;text-transform:uppercase;
  letter-spacing:.06em;padding:2px 6px;border-radius:4px}
.badge.primary{background:rgba(61,220,132,.16);color:var(--mint)}
.badge.stale{background:rgba(255,210,63,.16);color:var(--signal)}
.top3{list-style:none;margin:0;padding:0;font-size:12.5px;color:var(--dim)}
.top3 li{padding:3px 0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.top3 span{font-family:var(--mono);color:var(--faint);margin-right:8px}
.meta{font-family:var(--mono);font-size:11px;color:var(--faint);margin-top:11px;
  padding-top:10px;border-top:1px solid var(--line)}
</style></head><body>
<h1>Top Games</h1>
<p class="lede">__COUNT__ App Store charts, refreshed daily from the iTunes RSS feed.</p>
<div class="grid">__CARDS__</div>
</body></html>
"""


def _payloads_from_view(view, cfg):
    """Slash-command and share payloads for a dataset that keeps no history."""
    scope = f"{cfg['genre'].replace('_', ' ').title()} · {cfg['country'].upper()}"
    stamp = view["captured_at"][:16].replace("T", " ")

    def chart_reply(limit, in_channel=False):
        rows = view["items"][:limit]
        lines = [f"`{r['rank']:>3}` <{r['url']}|{r['name'][:38]}> — "
                 f"{r['rating']:.2f}★" if r["rating"] else
                 f"`{r['rank']:>3}` <{r['url']}|{r['name'][:38]}>" for r in rows]
        blocks = [command._section(
            f"*Top {len(rows)} {scope}*\n_captured {stamp} UTC_")]
        for start in range(0, len(lines), command.LINES_PER_SECTION):
            blocks.append(command._section(
                "\n".join(lines[start:start + command.LINES_PER_SECTION])))
        return command._reply(blocks, f"Top {len(rows)} {scope}", in_channel)

    def new_reply():
        rows = view["new_releases"][:25]
        if not rows:
            return command._reply(
                [command._section(f"No recent releases in the {scope} chart.")], "none")
        lines = [f"• <{r['url']}|{r['name'][:38]}> — {r['released']} · "
                 f"{r['rating']:.2f}★" for r in rows]
        blocks = [command._section(f"*New releases in the {scope} chart*")]
        for start in range(0, len(lines), command.LINES_PER_SECTION):
            blocks.append(command._section(
                "\n".join(lines[start:start + command.LINES_PER_SECTION])))
        return command._reply(blocks, "new releases")

    out = {
        "top100-25": chart_reply(25),
        "top100-50": chart_reply(50),
        "top100-100": chart_reply(cfg["chart_size"]),
        "new": new_reply(),
        "help": command._reply([command._section(command.HELP)], "help"),
        # No history means no movement to report.
        "signals": command._reply([command._section(
            f"*{scope}* is a chart-only view — rank movement is tracked for the "
            "primary chart only.")], "no signals"),
        "share-chart": chart_reply(25, in_channel=True),
        "share-new": new_reply(),
        "share-movers": command._reply([command._section(
            f"*{scope}* does not track rank movement.")], "no movers"),
    }
    for k in ("share-chart", "share-new", "share-movers"):
        out[k] = dict(out[k])
        out[k]["username"] = cfg["slack"].get("username") or "top_games"
        out[k]["icon_emoji"] = cfg["slack"].get("icon_emoji") or ":jigsaw:"
    return out
