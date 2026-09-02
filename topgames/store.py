"""SQLite persistence: app metadata, chart snapshots, and derived events."""
import os
import sqlite3
from datetime import datetime, timedelta, timezone

from .config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS apps (
  app_id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  artist TEXT, url TEXT, artist_url TEXT, icon TEXT,
  price REAL, formatted_price TEXT,
  genres TEXT, primary_genre TEXT, content_rating TEXT,
  release_date TEXT, version_date TEXT,
  avg_rating REAL, rating_count INTEGER,
  description TEXT,
  first_seen TEXT, last_seen TEXT
);
CREATE TABLE IF NOT EXISTS snapshots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  chart TEXT, genre_id INTEGER, country TEXT, captured_at TEXT
);
CREATE TABLE IF NOT EXISTS ranks (
  snapshot_id INTEGER, app_id INTEGER, rank INTEGER,
  PRIMARY KEY (snapshot_id, app_id)
);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TEXT, kind TEXT, chart TEXT, app_id INTEGER,
  rank INTEGER, prev_rank INTEGER, delta INTEGER,
  detail TEXT, notified INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_ranks_app ON ranks(app_id);
CREATE INDEX IF NOT EXISTS idx_events_created ON events(created_at);
CREATE INDEX IF NOT EXISTS idx_events_notified ON events(notified, kind);
CREATE INDEX IF NOT EXISTS idx_snapshots_chart ON snapshots(chart, captured_at);
"""


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path=DB_PATH):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    _migrate(conn)
    return conn


def _migrate(conn):
    """Add columns introduced after a database was first created."""
    have = {r["name"] for r in conn.execute("PRAGMA table_info(apps)")}
    for column, ddl in (("artist_url", "ALTER TABLE apps ADD COLUMN artist_url TEXT"),
                        ("bundle_id", "ALTER TABLE apps ADD COLUMN bundle_id TEXT")):
        if column not in have:
            conn.execute(ddl)
    # Which digests have gone out, so a run that GitHub starts eleven hours
    # late does not post a second copy of a message already sent.
    conn.execute("""CREATE TABLE IF NOT EXISTS digest_log (
        period TEXT NOT NULL, local_date TEXT NOT NULL, sent_at TEXT NOT NULL,
        PRIMARY KEY (period, local_date))""")
    conn.commit()


def digest_sent(conn, period, local_date):
    return conn.execute(
        "SELECT 1 FROM digest_log WHERE period=? AND local_date=?",
        (period, local_date)).fetchone() is not None


def mark_digest_sent(conn, period, local_date, sent_at):
    conn.execute("INSERT OR REPLACE INTO digest_log VALUES (?,?,?)",
                 (period, local_date, sent_at))
    conn.commit()


# Columns a record may omit; filled in so adding a field cannot break callers.
APP_COLUMNS = {
    "app_id", "name", "artist", "url", "artist_url", "bundle_id", "icon", "price",
    "formatted_price", "genres", "primary_genre", "content_rating",
    "release_date", "version_date", "avg_rating", "rating_count", "description",
}

APP_DEFAULTS = {
    "artist": "", "url": "", "artist_url": "", "bundle_id": "", "icon": "", "price": 0.0,
    "formatted_price": "", "genres": "", "primary_genre": "", "content_rating": "",
    "release_date": "", "version_date": "", "avg_rating": 0.0, "rating_count": 0,
    "description": "",
}


def upsert_apps(conn, records):
    """Insert or update app metadata, preserving the original first_seen."""
    ts = now_iso()
    for rec in records:
        rec = {**APP_DEFAULTS, **rec}
        rec = {k: v for k, v in rec.items() if k in APP_COLUMNS}
        conn.execute("""
            INSERT INTO apps (app_id, name, artist, url, artist_url, bundle_id, icon, price,
                formatted_price, genres, primary_genre, content_rating, release_date,
                version_date, avg_rating, rating_count, description, first_seen, last_seen)
            VALUES (:app_id,:name,:artist,:url,:artist_url,:bundle_id,:icon,:price,:formatted_price,
                :genres,:primary_genre,:content_rating,:release_date,:version_date,
                :avg_rating,:rating_count,:description,:ts,:ts)
            ON CONFLICT(app_id) DO UPDATE SET
                name=excluded.name, artist=excluded.artist, url=excluded.url,
                artist_url=excluded.artist_url, bundle_id=excluded.bundle_id,
                icon=excluded.icon, price=excluded.price,
                formatted_price=excluded.formatted_price, genres=excluded.genres,
                primary_genre=excluded.primary_genre,
                content_rating=excluded.content_rating,
                release_date=excluded.release_date, version_date=excluded.version_date,
                avg_rating=excluded.avg_rating, rating_count=excluded.rating_count,
                description=excluded.description, last_seen=excluded.last_seen
        """, dict(rec, ts=ts))
    conn.commit()


def is_first_time(conn, app_id):
    row = conn.execute("SELECT 1 FROM apps WHERE app_id=?", (app_id,)).fetchone()
    return row is None


def add_snapshot(conn, chart, genre_id, country, entries):
    """Persist a ranked chart. `entries` is [(rank, app_id)]."""
    cur = conn.execute(
        "INSERT INTO snapshots (chart, genre_id, country, captured_at) VALUES (?,?,?,?)",
        (chart, genre_id, country, now_iso()))
    snap_id = cur.lastrowid
    conn.executemany("INSERT INTO ranks (snapshot_id, app_id, rank) VALUES (?,?,?)",
                     [(snap_id, app_id, rank) for rank, app_id in entries])
    conn.commit()
    return snap_id


def recent_snapshots(conn, chart, limit=2):
    return conn.execute(
        "SELECT * FROM snapshots WHERE chart=? ORDER BY id DESC LIMIT ?",
        (chart, limit)).fetchall()


def snapshot_ranks(conn, snapshot_id):
    rows = conn.execute("SELECT app_id, rank FROM ranks WHERE snapshot_id=?",
                        (snapshot_id,)).fetchall()
    return {r["app_id"]: r["rank"] for r in rows}


def snapshot_before(conn, chart, iso_ts):
    """Newest snapshot captured at or before a timestamp -- used for weekly deltas."""
    return conn.execute(
        "SELECT * FROM snapshots WHERE chart=? AND captured_at<=? ORDER BY id DESC LIMIT 1",
        (chart, iso_ts)).fetchone()


def latest_chart(conn, chart):
    """The most recent chart joined to app metadata, ordered by rank."""
    snap = conn.execute("SELECT * FROM snapshots WHERE chart=? ORDER BY id DESC LIMIT 1",
                        (chart,)).fetchone()
    if not snap:
        return None, []
    rows = conn.execute("""
        SELECT r.rank, a.* FROM ranks r JOIN apps a ON a.app_id=r.app_id
        WHERE r.snapshot_id=? ORDER BY r.rank
    """, (snap["id"],)).fetchall()
    return snap, [dict(r) for r in rows]


def add_events(conn, events):
    ts = now_iso()
    conn.executemany("""
        INSERT INTO events (created_at, kind, chart, app_id, rank, prev_rank, delta, detail)
        VALUES (?,?,?,?,?,?,?,?)
    """, [(ts, e["kind"], e.get("chart", ""), e["app_id"], e.get("rank"),
           e.get("prev_rank"), e.get("delta"), e.get("detail", "")) for e in events])
    conn.commit()


def events_since(conn, iso_ts, kinds=None, unnotified_only=False):
    sql = """SELECT e.*, a.name, a.artist, a.url, a.bundle_id, a.icon, a.avg_rating,
                    a.rating_count, a.release_date, a.formatted_price
             FROM events e LEFT JOIN apps a ON a.app_id=e.app_id
             WHERE e.created_at >= ?"""
    params = [iso_ts]
    if kinds:
        sql += " AND e.kind IN (%s)" % ",".join("?" * len(kinds))
        params += list(kinds)
    if unnotified_only:
        sql += " AND e.notified = 0"
    sql += " ORDER BY e.id DESC"
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def mark_notified(conn, event_ids):
    if not event_ids:
        return
    conn.execute("UPDATE events SET notified=1 WHERE id IN (%s)"
                 % ",".join("?" * len(event_ids)), list(event_ids))
    conn.commit()


def app_rank_history(conn, app_id, chart, limit=60):
    return [dict(r) for r in conn.execute("""
        SELECT s.captured_at, r.rank FROM ranks r JOIN snapshots s ON s.id=r.snapshot_id
        WHERE r.app_id=? AND s.chart=? ORDER BY s.id DESC LIMIT ?
    """, (app_id, chart, limit)).fetchall()][::-1]


def stats(conn):
    def one(sql, *a):
        return conn.execute(sql, a).fetchone()[0]
    return {
        "apps": one("SELECT COUNT(*) FROM apps"),
        "snapshots": one("SELECT COUNT(*) FROM snapshots"),
        "events": one("SELECT COUNT(*) FROM events"),
        "last_refresh": one("SELECT COALESCE(MAX(captured_at),'never') FROM snapshots"),
    }


def prune(conn, keep_snapshots=180, keep_event_days=120):
    """Bound the database size.

    The whole file is committed to git on every scheduled run, so unbounded
    growth would bloat the repository history rather than just a disk.
    """
    rows = conn.execute(
        "SELECT id FROM snapshots ORDER BY id DESC LIMIT -1 OFFSET ?",
        (keep_snapshots,)).fetchall()
    dropped = [r["id"] for r in rows]
    if dropped:
        marks = ",".join("?" * len(dropped))
        conn.execute(f"DELETE FROM ranks WHERE snapshot_id IN ({marks})", dropped)
        conn.execute(f"DELETE FROM snapshots WHERE id IN ({marks})", dropped)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=keep_event_days)).isoformat()
    cur = conn.execute("DELETE FROM events WHERE created_at < ?", (cutoff,))
    removed_events = cur.rowcount
    # Rows in `apps` are never deleted. first_seen is the only thing that tells a
    # genuinely new release apart from one we have already reported, so dropping
    # an app would make it resurface as "new" the next time it is seen.
    conn.commit()
    conn.execute("VACUUM")
    return {"snapshots_dropped": len(dropped), "events_dropped": removed_events}
