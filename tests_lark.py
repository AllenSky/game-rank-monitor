"""Lark converter tests (no network)."""
from topgames import lark

# --- markdown ---------------------------------------------------------------
assert lark.md("plain") == "plain"
assert lark.md("*bold* and _it_") == "**bold** and *it*"
assert lark.md("<http://x|Click>") == "[Click](http://x)"
assert lark.md("<http://x>") == "[http://x](http://x)"
# URLs containing underscores must survive the italic pass untouched
assert lark.md("<http://x/some_page_id|A _weird_ name>") == \
    "[A *weird* name](http://x/some_page_id)"
assert "`code` stays" in lark.md("`code` stays")
print("PASS: mrkdwn -> lark_md (bold/italic/links/underscore-safety)")

# --- detection --------------------------------------------------------------
assert lark.is_lark("https://open.feishu.cn/open-apis/bot/v2/hook/xxx")
assert lark.is_lark("https://open.larksuite.com/open-apis/bot/v2/hook/xxx")
assert not lark.is_lark("https://hooks.slack.com/services/T/B/X")
print("PASS: webhook detection (feishu/lark yes, slack no)")

# --- card shape -------------------------------------------------------------
card = lark.to_card({
    "text": "fallback",
    "blocks": [
        {"type": "header", "text": {"type": "plain_text", "text": "Title"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": "*Hi* <http://x|link>"}},
        {"type": "section", "fields": [
            {"type": "mrkdwn", "text": "a"}, {"type": "mrkdwn", "text": "b"}]},
        {"type": "context", "elements": [{"type": "mrkdwn", "text": "footer"}]},
        {"type": "divider"},
        {"type": "actions", "elements": [
            {"type": "button", "text": {"type": "plain_text", "text": "Open"},
             "url": "http://x", "style": "primary"}]},
    ]})
assert card["msg_type"] == "interactive"
assert card["card"]["header"]["title"]["content"] == "Title"
tags = [e["tag"] for e in card["card"]["elements"]]
assert tags == ["div", "div", "note", "hr", "action"], tags
assert card["card"]["elements"][0]["text"]["content"] == "**Hi** [link](http://x)"
assert card["card"]["elements"][1]["text"]["content"] == "a\nb"
btn = card["card"]["elements"][-1]["actions"][0]
assert btn["url"] == "http://x" and btn["type"] == "primary"
print("PASS: card structure (header/div/fields/note/hr/action)")

# --- no blocks -> text fallback ----------------------------------------------
assert lark.to_card({"text": "hello"})["card"]["elements"][0]["text"]["content"] == "hello"
print("PASS: text-only payload falls back to a div")

print("\nALL LARK TESTS PASSED")
