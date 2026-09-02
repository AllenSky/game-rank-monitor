"""Company aggregation tests on a controlled database (no network)."""
import os
import tempfile
from datetime import datetime, timedelta, timezone

from topgames import companies, config, store

conn = store.connect(os.path.join(tempfile.mkdtemp(), "c.db"))
cfg = config.load("/tmp/__no_such_config.json")
DS = [d for d in config.datasets(cfg) if d["genre"] == "casual"]

NOW = datetime.now(timezone.utc)


def app(app_id, artist, rel_days=300, **kw):
    base = dict(
        app_id=app_id, name=f"Game {app_id}", artist=artist, url=f"http://x/{app_id}",
        icon="", price=0.0, formatted_price="Free", genres="Casual",
        primary_genre="Casual", content_rating="4+",
        release_date=(NOW - timedelta(days=rel_days)).isoformat(),
        version_date=(NOW - timedelta(days=2)).isoformat(), version="1.0",
        avg_rating=4.5, rating_count=1000, description="", platform="ios",
        store_id=str(app_id), bundle_id=f"com.t.{app_id}")
    base.update(kw)
    return base


# --- matching rule -----------------------------------------------------------
assert companies.is_match("Voodoo", "voodoo")
assert companies.is_match("SayGames Ltd", "SayGames")
assert not companies.is_match("Kingdom Studio", "King")   # prefix must end at a space
assert companies.is_match("King", "King")
assert not companies.is_match("", "King")
print("PASS: watch-name matching (exact ci / name+space prefix)")

# --- fixtures: two platforms, Voodoo on both ---------------------------------
ios_ids = [1, 2, 3]            # 1 = Voodoo, others noise
play_ids = [-1, -2]            # -1 = Voodoo play twin
store.upsert_apps(conn, [
    app(1, "Voodoo", bundle_id="com.voodoo.a"),
    app(2, "Other Studio"),
    app(3, "SayGames Ltd"),
    app(-1, "Voodoo", platform="play", store_id="com.voodoo.a",
        bundle_id="com.voodoo.a"),
    app(-2, "Another Studio", platform="play", store_id="com.x.b"),
])
snap_ios = store.add_snapshot(conn, "topfreeapplications", 7003, "us",
                              [(1, 1), (2, 2), (3, 3)], platform="ios")
snap_play = store.add_snapshot(conn, "top_free", 9003, "us",
                               [(1, -1), (2, -2)], platform="play")
# second snapshots: Voodoo ios 1->3 (delta -2), play stays #1
store.add_snapshot(conn, "topfreeapplications", 7003, "us",
                   [(1, 3), (2, 1), (3, 2)], platform="ios")
store.add_snapshot(conn, "top_free", 9003, "us",
                   [(1, -1), (2, -2)], platform="play")

# --- charting ----------------------------------------------------------------
titles = companies.charting(conn, ["Voodoo", "SayGames"], DS)
voodoo = [t for t in titles if t["platform"] == "play"]
# entries are (rank, app_id): play twin stays #1 across both snapshots.
assert len(voodoo) == 1 and voodoo[0]["rank"] == 1 and voodoo[0]["delta"] == 0, voodoo
ios_v = [t for t in titles if t["platform"] == "ios" and t["artist"] == "Voodoo"]
# ios: rank 1 -> 2 between snapshots, so delta (prev - rank) is -1.
assert ios_v[0]["rank"] == 2 and ios_v[0]["delta"] == -1, ios_v
say = [t for t in titles if t["artist"] == "SayGames Ltd"]
assert len(say) == 1
print("PASS: charting spans platforms with correct rank deltas")

# --- versions_since window logic ---------------------------------------------
old_iso = (NOW - timedelta(days=10)).isoformat(timespec="seconds")
today_iso = NOW.isoformat(timespec="seconds")
store.record_versions(conn, [
    {"app_id": 1, "version": "2.0", "version_date": old_iso},      # real old release
    {"app_id": -1, "version": "3.0", "version_date": today_iso},   # genuine fresh bump
])
rows = companies.versions_since(conn, (NOW - timedelta(days=1)).isoformat(timespec="seconds"))
assert [(r["app_id"], r["version"]) for r in rows] == [(-1, "3.0")], rows
watched = companies.versions_since(
    conn, (NOW - timedelta(days=1)).isoformat(timespec="seconds"), ["Voodoo"])
assert len(watched) == 1 and watched[0]["platform"] == "play"
print("PASS: versions_since filters by released_at, not just first_seen")

# --- update_frequency --------------------------------------------------------
store.record_versions(conn, [
    {"app_id": 3, "version": "1.1",
     "version_date": (NOW - timedelta(days=30)).isoformat()},
    {"app_id": 3, "version": "1.2",
     "version_date": (NOW - timedelta(days=20)).isoformat()},
    {"app_id": 3, "version": "1.3",
     "version_date": (NOW - timedelta(days=5)).isoformat()},
])
freq = companies.update_frequency(conn, 3, days=90)
assert freq["count"] == 3, freq
assert freq["avg_gap_days"] and abs(freq["avg_gap_days"] - 12.5) < 0.5, freq
assert companies.update_frequency(conn, 2, days=90)["count"] == 0
print(f"PASS: update_frequency count+gap ({freq})")

# --- watch_overview ----------------------------------------------------------
cfg["watch_developers"] = ["Voodoo", "SayGames", "King"]
ov = {o["name"]: o for o in companies.watch_overview(conn, cfg, DS)}
assert ov["Voodoo"]["any"] and len(ov["Voodoo"]["titles"]) == 2
assert len(ov["Voodoo"]["new_versions"]) == 1
assert ov["King"]["any"] is False
print("PASS: watch_overview shape and empty-company handling")

conn.close()
print("\nALL COMPANY TESTS PASSED")
