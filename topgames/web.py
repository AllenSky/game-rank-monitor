"""Local web dashboard. Standard library only -- no framework to install."""
import json
import threading
import traceback
import urllib.parse
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import command, config, signals, slack, store
from .templates import PAGE


def _chart_payload(conn, cfg):
    """Current chart, annotated with movement against the previous snapshot."""
    snap, rows = store.latest_chart(conn, cfg["chart"])
    if not snap:
        return {"captured_at": None, "rows": []}
    snaps = store.recent_snapshots(conn, cfg["chart"], limit=2)
    prev = store.snapshot_ranks(conn, snaps[1]["id"]) if len(snaps) > 1 else {}
    cutoff = datetime.now(timezone.utc) - timedelta(days=cfg["signals"]["new_release_days"])
    out = []
    for r in rows:
        prev_rank = prev.get(r["app_id"])
        released = None
        try:
            released = datetime.fromisoformat(
                (r.get("release_date") or "").replace("Z", "+00:00"))
        except ValueError:
            pass
        out.append({
            "rank": r["rank"], "app_id": r["app_id"], "name": r["name"],
            "artist": r["artist"], "url": r["url"], "icon": r["icon"],
            "price": r["formatted_price"], "rating": r["avg_rating"],
            "ratings": r["rating_count"], "genres": r["genres"],
            "release_date": (r.get("release_date") or "")[:10],
            "prev_rank": prev_rank,
            "delta": (prev_rank - r["rank"]) if prev_rank else None,
            "is_new_entry": prev_rank is None and bool(prev),
            "is_new_release": bool(released and released >= cutoff),
        })
    return {"captured_at": snap["captured_at"], "rows": out,
            "has_previous": bool(prev)}


def _new_releases(conn, cfg, days=None):
    days = days or cfg["signals"]["new_release_days"]
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    rows = conn.execute("""
        SELECT * FROM apps
        WHERE release_date >= ? AND genres LIKE ?
        ORDER BY release_date DESC LIMIT 300
    """, (cutoff, f"%{cfg['genre'].replace('_',' ').title()}%")).fetchall()
    return [dict(r) for r in rows]


def _events(conn, days=7):
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    return store.events_since(conn, since)


class Handler(BaseHTTPRequestHandler):
    cfg = None
    lock = threading.Lock()

    # Headers a reverse proxy or Cloudflare tunnel adds. Their presence means the
    # request arrived from the public internet rather than from this machine.
    REMOTE_HEADERS = ("CF-Connecting-IP", "Cf-Ray", "X-Forwarded-For",
                      "X-Real-IP", "Cf-Ipcountry")

    def _is_remote(self):
        return any(self.headers.get(h) for h in self.REMOTE_HEADERS)

    def _blocked_remote(self, path):
        """Only the signed slash-command endpoint may be reached from outside.

        Exposing the server through a tunnel would otherwise hand anyone who
        learns the URL an unauthenticated POST /api/slack-test, i.e. the ability
        to post into the user's Slack channel.
        """
        if not self._is_remote():
            return False
        if path == "/slack/command":
            return False
        if self.cfg and self.cfg.get("web", {}).get("expose_dashboard"):
            return False
        return True

    def log_message(self, fmt, *args):  # quieter console
        pass

    def _send(self, code, body, ctype="application/json"):
        raw = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, default=str))

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path, qs = parsed.path, urllib.parse.parse_qs(parsed.query)
        cfg = Handler.cfg
        if self._blocked_remote(path):
            return self._send(403, "forbidden", "text/plain")
        try:
            if path == "/":
                return self._send(200, PAGE, "text/html; charset=utf-8")
            conn = store.connect()
            try:
                if path == "/api/chart":
                    return self._json(_chart_payload(conn, cfg))
                if path == "/api/new-releases":
                    days = int(qs.get("days", [cfg["signals"]["new_release_days"]])[0])
                    return self._json({"rows": _new_releases(conn, cfg, days)})
                if path == "/api/events":
                    return self._json({"rows": _events(conn, int(qs.get("days", [7])[0]))})
                if path == "/api/stats":
                    data = store.stats(conn)
                    data.update({
                        "genre": cfg["genre"], "chart": cfg["chart"],
                        "country": cfg["country"].upper(),
                        "chart_size": cfg["chart_size"],
                        "slack_configured": bool(cfg["slack"].get("webhook_url")),
                        "daily": cfg["slack"]["daily"], "weekly": cfg["slack"]["weekly"],
                    })
                    return self._json(data)
                if path == "/api/history":
                    app_id = int(qs.get("app_id", ["0"])[0])
                    return self._json({"rows": store.app_rank_history(
                        conn, app_id, cfg["chart"])})
            finally:
                conn.close()
            return self._json({"error": "not found"}, 404)
        except Exception as exc:
            traceback.print_exc()
            return self._json({"error": str(exc)}, 500)

    def _slash(self, cfg):
        """Handle an inbound Slack slash command."""
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        raw = self.rfile.read(length) if length else b""
        # Log every attempt: silence here is the main clue that Slack never
        # reached us at all, which is a different problem from a rejected request.
        stamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
        agent = (self.headers.get("User-Agent") or "?")[:40]
        form_peek = urllib.parse.parse_qs(raw.decode("utf-8", "replace"))
        print(f"[{stamp}] /slack/command from {agent} "
              f"cmd={form_peek.get('command',['?'])[0]} "
              f"text={form_peek.get('text',[''])[0]!r} "
              f"user={form_peek.get('user_name',['?'])[0]}", flush=True)
        ok, why = command.verify(
            cfg["slack"].get("signing_secret", ""),
            self.headers.get("X-Slack-Request-Timestamp"),
            self.headers.get("X-Slack-Signature"),
            raw)
        if not ok:
            # 401 rather than a Slack-visible message: an unverified request is
            # not necessarily from Slack at all.
            print(f"  -> REJECTED: {why}", flush=True)
            return self._send(401, "unauthorized", "text/plain")
        print("  -> accepted", flush=True)
        form = urllib.parse.parse_qs(raw.decode("utf-8"))
        try:
            return self._json(command.handle(cfg, form))
        except Exception as exc:
            traceback.print_exc()
            return self._json({"response_type": "ephemeral",
                               "text": f"Command failed: {exc}"})

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)
        cfg = Handler.cfg
        if self._blocked_remote(path):
            return self._send(403, "forbidden", "text/plain")

        if path == "/slack/command":
            return self._slash(cfg)

        try:
            conn = store.connect()
            try:
                if path == "/api/refresh":
                    # Serialize refreshes so two clicks cannot interleave snapshots.
                    if not Handler.lock.acquire(blocking=False):
                        return self._json({"error": "a refresh is already running"}, 409)
                    try:
                        return self._json(signals.refresh(conn, cfg, verbose=False))
                    finally:
                        Handler.lock.release()
                if path == "/api/slack-test":
                    slack.post(cfg["slack"]["webhook_url"], slack.test_message(cfg))
                    return self._json({"ok": True})
                if path == "/api/digest":
                    period = qs.get("period", ["daily"])[0]
                    dry = qs.get("dry", ["0"])[0] == "1"
                    payload, ids = slack.build_digest(conn, cfg, period)
                    if dry:
                        return self._json({"ok": True, "dry_run": True, "payload": payload})
                    slack.post(cfg["slack"]["webhook_url"], payload)
                    store.mark_notified(conn, ids)
                    return self._json({"ok": True, "events": len(ids)})
            finally:
                conn.close()
            return self._json({"error": "not found"}, 404)
        except slack.SlackError as exc:
            return self._json({"error": str(exc)}, 400)
        except Exception as exc:
            traceback.print_exc()
            return self._json({"error": str(exc)}, 500)


def serve(cfg, host=None, port=None):
    host = host or cfg["web"]["host"]
    port = int(port or cfg["web"]["port"])
    Handler.cfg = cfg
    httpd = ThreadingHTTPServer((host, port), Handler)
    url = f"http://{host}:{port}"
    print(f"top_games dashboard -> {url}")
    print("Press Ctrl+C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        httpd.server_close()
