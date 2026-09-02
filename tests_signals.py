"""Verify the diff engine on controlled snapshots (no network)."""
import os, tempfile, json
from datetime import datetime, timezone, timedelta
from topgames import store, slack, config, digest as digest_mod

db = os.path.join(tempfile.mkdtemp(), "t.db")
conn = store.connect(db)
cfg = config.load()
cfg["slack"]["webhook_url"] = ""   # never send during tests

def app(i, name, days_old=400):
    rel = (datetime.now(timezone.utc) - timedelta(days=days_old)).isoformat()
    return dict(app_id=i, name=name, artist=f"Studio {i}", url=f"http://x/{i}",
        icon="", price=0.0, formatted_price="Free", genres="Games,Puzzle",
        primary_genre="Games", content_rating="4+", release_date=rel,
        version_date=rel, avg_rating=4.5, rating_count=1000, description="")

# --- snapshot 1: apps 1..5 at ranks 1..5
store.upsert_apps(conn, [app(i, f"Game {i}") for i in range(1, 6)])
s1 = store.add_snapshot(conn, "topfreeapplications", 7012, "us",
                        [(r, r) for r in range(1, 6)])

# --- snapshot 2: app 3 gone; NEW app 9 (fresh release) enters at #2;
#     app 5 climbs 5->1 (+4); app 1 falls 1->5 (-4)
store.upsert_apps(conn, [app(9, "Brand New Game", days_old=3)])
new_order = [(1, 5), (2, 9), (3, 2), (4, 4), (5, 1)]   # (rank, app_id)
s2 = store.add_snapshot(conn, "topfreeapplications", 7012, "us", new_order)

prev = store.snapshot_ranks(conn, s1)
curr = {aid: r for r, aid in new_order}

# replicate signals.refresh's diff with a threshold of 3
events, THRESH, NEW_DAYS = [], 3, 30
for aid, rank in curr.items():
    p = prev.get(aid)
    if p is None:
        row = conn.execute("SELECT release_date FROM apps WHERE app_id=?", (aid,)).fetchone()
        age = (datetime.now(timezone.utc) -
               datetime.fromisoformat(row["release_date"])).days
        events.append({"kind": "debut" if age <= NEW_DAYS else "new_entry",
                       "app_id": aid, "rank": rank, "prev_rank": None,
                       "delta": None, "detail": f"entered at #{rank}"})
    else:
        d = p - rank
        if abs(d) >= THRESH:
            events.append({"kind": "climb" if d > 0 else "fall", "app_id": aid,
                           "rank": rank, "prev_rank": p, "delta": d,
                           "detail": f"#{p} -> #{rank}"})
for aid, p in prev.items():
    if aid not in curr:
        events.append({"kind": "exit", "app_id": aid, "rank": None,
                       "prev_rank": p, "delta": None, "detail": f"left from #{p}"})
store.add_events(conn, events)

kinds = sorted(e["kind"] for e in events)
print("events:", kinds)
assert "debut" in kinds, "fresh new entrant must be flagged as a debut"
assert "exit" in kinds, "app 3 leaving the chart must be detected"
assert "climb" in kinds and "fall" in kinds, "big movers must be detected"
assert sum(1 for k in kinds if k == "exit") == 1

d = next(e for e in events if e["kind"] == "debut")
assert d["app_id"] == 9 and d["rank"] == 2, d
c = next(e for e in events if e["kind"] == "climb")
assert c["delta"] == 4 and c["app_id"] == 5, c
f = next(e for e in events if e["kind"] == "fall")
assert f["delta"] == -4 and f["app_id"] == 1, f
print("PASS: diff engine detects entries, exits, climbs, falls")

# --- the digest builds from stored state without a webhook
since = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
cfg["signals"]["move_threshold"] = 3
payload, ids = digest_mod.build(conn, cfg, "daily")
assert payload is not None, "a day with a debut and an exit must still post"
assert payload["blocks"][0]["type"] in ("header", "context")
text = json.dumps(payload)
assert "Brand New Game" in text, "the new chart entrant must appear in the digest"
# Movers and releases come from current state; only entries and exits are events,
# so only those get marked as sent.
entry_exit = [e for e in events if e["kind"] in ("debut", "new_entry", "exit")]
assert len(ids) == len(entry_exit), (len(ids), len(entry_exit))
print(f"PASS: digest built -- {len(payload['blocks'])} blocks, {len(ids)} events marked")

# --- formatters behave as the spec describes
assert digest_mod.dot(4.8, 100) == "\U0001F7E2"
assert digest_mod.dot(4.2, 100) == "\U0001F7E1"
assert digest_mod.dot(3.0, 100) == "\U0001F534"
assert digest_mod.dot(0, 0) == "\u26AA", "an unrated app must not look rated"
assert digest_mod.delta_str(5) == "\u25B25" and digest_mod.delta_str(-5) == "\u25BC5"
assert digest_mod.delta_str(0) == "\u2014"
assert digest_mod.rating_str(4.5, 0) == "no ratings yet"
print("PASS: rating dots and delta arrows encode the data, not decoration")

# --- notified events are not resent
store.mark_notified(conn, ids)
again = store.events_since(conn, since, kinds=["debut", "new_entry", "exit"],
                           unnotified_only=True)
assert not again, f"already-sent events leaked back in: {again}"
print("PASS: sent events are not resent")

# --- a quiet day still posts, compressed rather than silent
conn2 = store.connect(os.path.join(tempfile.mkdtemp(), "e.db"))
store.upsert_apps(conn2, [app(i, f"Calm {i}") for i in range(1, 4)])
store.add_snapshot(conn2, "topfreeapplications", 7012, "us", [(r, r) for r in range(1, 4)])
store.add_snapshot(conn2, "topfreeapplications", 7012, "us", [(r, r) for r in range(1, 4)])
p2, i2 = digest_mod.build(conn2, cfg, "daily")
assert p2 is not None, "silence is indistinguishable from a broken schedule"
assert "chart unchanged" in json.dumps(p2), json.dumps(p2)[:200]
assert len(p2["blocks"]) == 1, "a quiet day should compress to a single line"
print("PASS: a quiet day posts the compressed form instead of going silent")

print("\nALL TESTS PASSED")
