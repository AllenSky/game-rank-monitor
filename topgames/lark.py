"""Lark (Feishu) webhook delivery: Block Kit payloads -> interactive cards.

The digest is composed in Slack Block Kit. Rather than maintaining two
parallel builders, this module converts the Block Kit subset the digest
actually uses (header / section / fields / context / divider / actions)
into a Lark interactive card, and converts Slack mrkdwn to lark_md.

Delivery flow: slack.post() detects a Lark webhook URL and routes here,
so every existing call site (digest, realtime alert, test message)
works unchanged.
"""
import base64
import hashlib
import hmac
import json
import re
import time
import urllib.error
import urllib.request

from .slack import SlackError

LARK_HOSTS = ("open.feishu.cn", "open.larksuite.com", "open.larkoffice.com")
# Lark cards cap a single element's text; keep sections inside it.
ELEMENT_LIMIT = 30000

_LINK = re.compile(r"<([^<>|]+)(?:\|([^<>]*))?>")


def is_lark(url):
    return any(h in (url or "") for h in LARK_HOSTS)


def _md_segment(text):
    """mrkdwn -> lark_md inside a link-free segment."""
    text = re.sub(r"\*([^*\n]+)\*", r"**\1**", text)      # *bold*  -> **bold**
    text = re.sub(r"(?<![\w*])_([^_\n]+)_(?![\w*])", r"*\1*", text)  # _it_ -> *it*
    return text


def md(text):
    """Convert Slack mrkdwn text to lark_md, links first.

    URLs may contain underscores, so links are extracted before the italic
    pass instead of blind string replacement.
    """
    out, pos = [], 0
    for m in _LINK.finditer(text or ""):
        out.append(_md_segment(text[pos:m.start()]))
        url, label = m.group(1), m.group(2)
        # Labels carry mrkdwn too (a *bold* game name stays bold); the URL
        # itself is never converted -- underscores there are literal.
        out.append(f"[{_md_segment(label) if label else url}]({url})")
        pos = m.end()
    out.append(_md_segment(text[pos:]))
    return "".join(out)


def _text_of(block, key="text"):
    t = block.get(key) or {}
    return t.get("text", "") if isinstance(t, dict) else str(t or "")


def _elements(payload):
    """Block Kit blocks -> Lark card elements; the header becomes the card title."""
    elements, title, template = [], None, "blue"
    for block in payload.get("blocks", []):
        kind = block.get("type")
        if kind == "header":
            if title is None:
                title, template = _text_of(block, "text"), "turquoise"
                continue
            elements.append({"tag": "div", "text": {
                "tag": "lark_md", "content": "**" + _text_of(block, "text") + "**"}})
        elif kind == "section":
            content = _text_of(block)
            fields = block.get("fields") or []
            if not content and fields:
                content = "\n".join(_text_of(f) for f in fields)
            if content:
                elements.append({"tag": "div", "text": {
                    "tag": "lark_md", "content": md(content)[:ELEMENT_LIMIT]}})
        elif kind == "context":
            content = md("  ·  ".join(
                _text_of(e) for e in (block.get("elements") or []) if _text_of(e)))
            if content:
                elements.append({"tag": "note", "elements": [{
                    "tag": "lark_md", "content": content}]})
        elif kind == "divider":
            elements.append({"tag": "hr"})
        elif kind == "actions":
            buttons = []
            for btn in block.get("elements") or []:
                if btn.get("type") != "button":
                    continue
                buttons.append({
                    "tag": "button",
                    "text": {"tag": "plain_text",
                             "content": _text_of(btn, "text")[:24] or "Open"},
                    "url": btn.get("url") or "",
                    "type": "primary" if btn.get("style") == "primary" else "default",
                })
            if buttons:
                elements.append({"tag": "action", "actions": buttons})
    return elements, title, template


def to_card(payload):
    """A Slack webhook payload -> a Lark interactive-card webhook body."""
    elements, title, template = _elements(payload)
    card = {"elements": elements or [{"tag": "div", "text": {
        "tag": "lark_md", "content": md(payload.get("text") or "")}}]}
    if title:
        card["header"] = {"template": template,
                          "title": {"tag": "plain_text",
                                    "content": title[:300]}}
    return {"msg_type": "interactive", "card": card}


def sign(secret, timestamp=None):
    """Lark custom-bot signature.

    The HMAC key is "<timestamp>\n<secret>" and the message is empty --
    backwards from the usual convention, which is why hand-rolled attempts
    keep failing with 'sign match fail'.
    """
    ts = str(timestamp or int(time.time()))
    digest = hmac.new(f"{ts}\n{secret}".encode("utf-8"), b"",
                      hashlib.sha256).digest()
    return ts, base64.b64encode(digest).decode("utf-8")


def _secret():
    """The bot's signing secret from config (slack.lark_secret)."""
    from . import config
    return (config.load()["slack"].get("lark_secret") or "").strip()


def post(webhook_url, payload, timeout=15):
    """Send a Block Kit payload to a Lark webhook as an interactive card."""
    body = to_card(payload)
    secret = _secret()
    if secret:
        ts, sg = sign(secret)
        body["timestamp"] = ts
        body["sign"] = sg
    body = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        webhook_url, data=body,
        headers={"Content-Type": "application/json",
                 "User-Agent": "game-rank-monitor/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8", "replace") or "{}")
            if data.get("code") not in (0, None):
                raise SlackError(f"Lark rejected the message: {data}")
            return True
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace").strip()
        hint = ""
        if exc.code == 19021 or "sign match fail" in detail:
            hint = (" -- signature validation failed: check slack.lark_secret "
                    "in config.json matches the bot's 签名校验 string.")
        raise SlackError(f"Lark rejected the message ({exc.code} {detail}){hint}")
    except urllib.error.URLError as exc:
        raise SlackError(f"Could not reach Lark: {exc.reason}")
    except ValueError as exc:
        raise SlackError(f"Lark replied with invalid JSON: {exc}")
