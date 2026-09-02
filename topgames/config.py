"""Configuration loading and defaults."""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CONFIG_PATH = os.path.join(ROOT, "config.json")
DB_PATH = os.path.join(ROOT, "data", "topgames.db")

# Apple App Store genre ids. 6014 is Games; the 70xx range are its subgenres.
GENRES = {
    "games": 6014, "action": 7001, "adventure": 7002, "casual": 7003,
    "board": 7004, "card": 7005, "casino": 7006, "dice": 7007,
    "educational": 7008, "family": 7009, "music": 7011, "puzzle": 7012,
    "racing": 7013, "role_playing": 7014, "simulation": 7015, "sports": 7016,
    "strategy": 7017, "trivia": 7018, "word": 7019,
}

# 6014 is Games; 70xx are its subgenres. Anything outside this set is an app
# category (Entertainment, Books, Utilities) that the search sweep dragged in.
GAME_GENRE_IDS = {6014} | set(range(7001, 7020))

# Apple returns genre NAMES localised to the storefront ("パズル", "Quebra-cabeça")
# but genre IDS are the same everywhere. Everything user-facing is derived from
# the id so a filter written in English still works in Japan.
GENRE_NAMES = {
    6000: "Business", 6001: "Weather", 6002: "Utilities", 6003: "Travel",
    6004: "Sports", 6005: "Social Networking", 6006: "Reference",
    6007: "Productivity", 6008: "Photo & Video", 6009: "News",
    6010: "Navigation", 6011: "Music", 6012: "Lifestyle",
    6013: "Health & Fitness", 6014: "Games", 6015: "Finance",
    6016: "Entertainment", 6017: "Education", 6018: "Books", 6020: "Medical",
    6021: "Magazines & Newspapers", 6023: "Food & Drink", 6024: "Shopping",
    6027: "Graphics & Design",
    7001: "Action", 7002: "Adventure", 7003: "Casual", 7004: "Board",
    7005: "Card", 7006: "Casino", 7007: "Dice", 7008: "Educational",
    7009: "Family", 7011: "Music", 7012: "Puzzle", 7013: "Racing",
    7014: "Role Playing", 7015: "Simulation", 7016: "Sports",
    7017: "Strategy", 7018: "Trivia", 7019: "Word",
}

# Google Play categories for the genres we track. Play has no "shooting"
# category either -- shooters live under GAME_ACTION, same as Apple's Action.
PLAY_GENRES = {
    "games": "GAME", "action": "GAME_ACTION", "adventure": "GAME_ADVENTURE",
    "arcade": "GAME_ARCADE", "board": "GAME_BOARD", "card": "GAME_CARD",
    "casino": "GAME_CASINO", "casual": "GAME_CASUAL",
    "educational": "GAME_EDUCATIONAL", "music": "GAME_MUSIC",
    "puzzle": "GAME_PUZZLE", "racing": "GAME_RACING",
    "role_playing": "GAME_ROLE_PLAYING", "simulation": "GAME_SIMULATION",
    "sports": "GAME_SPORTS", "strategy": "GAME_STRATEGY",
    "trivia": "GAME_TRIVIA", "word": "GAME_WORD",
}
# Play datasets reuse the Apple genre id + 2000 as their numeric namespace.
PLAY_GENRE_ID_OFFSET = 2000
# iOS chart name -> Play chart name (collections in google-play-scraper terms).
PLAY_CHARTS = {
    "topfreeapplications": "top_free",
    "toppaidapplications": "top_paid",
    "topgrossingapplications": "grossing",
}


DEFAULTS = {
    "country": "us",
    "genre": "casual",
    # Platforms tracked; the cross product with countries x genres_tracked
    # below defines the datasets. Google Play has no CN storefront.
    "platforms": ["ios", "play"],
    "watch_developers": ["Voodoo", "SayGames", "King", "Loom"],
    # Which datasets get their own Top-10 section in the digest.
    "digest_top10_datasets": ["us-ios-casual", "us-play-casual"],
    "play": {
        # Full app() detail (screenshots, description, version, updated) is
        # one request per app; enrich only the chart head to bound the cost.
        "detail_top_n": 100,
        "lang": "en",
    },
    # Charts to publish. The primary keeps full history (rank deltas, movers,
    # the Slack digest); the rest are chart-only, fetched fresh each run and
    # stored nowhere, which is why they cost 2 requests instead of 17.
    # Add an entry here and to worker/wrangler.toml's DATASETS to publish more.
    # Charts are the cross product of these. Each costs 2 requests and ~3.4s.
    "countries": ["us"],
    # Every Apple games genre, so the dashboard's genre filter is a real
    # browser rather than a shortlist. Each adds 2 requests per country.
    # Every Apple games genre that actually publishes a chart. Dice (7007) and
    # Educational (7008) are omitted: their feeds return zero entries in every
    # storefront, so they would only ever appear as failures.
    "genres_tracked": ["casual", "action"],
    # Explicit entries override the cross product entirely.
    "datasets": [],
    "chart": "topfreeapplications",
    "chart_size": 100,
    "slack": {
        "webhook_url": "",
        # Only needed for the /top100 slash command, not for digests.
        "signing_secret": "",
        "username": "Top Games Bot",
        "icon_emoji": ":jigsaw:",
        # Which signals get posted, and in which digest.
        # The zone the digest times below are written in. The GitHub workflow
        # cron is UTC, so it is set to the matching UTC hour; Europe/Istanbul has
        # no DST, which is why a fixed cron stays correct year-round.
        "timezone": "Asia/Shanghai",
        # Text prepended to every digest, e.g. "<!here>" or "<!subteam^ID>".
        "mention": "",
        "daily": {
            "enabled": True,
            "time": "09:30",
            "include": ["debut", "new_entry", "new_release", "climb", "exit"],
            # How far back the "new releases" section looks, in days.
            "new_days": 2,
            # Skip posting entirely on a day with nothing to report, instead of
            # sending "no new games" into the channel every morning.
            "skip_if_empty": False,
            # Append the current top N. 0 turns the section off.
            "show_top_n": 0,
            "title": "",          # blank uses "Daily <Genre> Games Report"
        },
        "weekly": {
            "enabled": True,
            "day": "monday",
            "time": "09:30",
            "include": ["debut", "new_entry", "new_release", "climb", "fall", "exit"],
            "new_days": 7,
            "skip_if_empty": False,
            "show_top_n": 10,
            "title": "",
            "show_full_chart": True,
        },
        # Post the moment a new game enters the chart, without waiting for a digest.
        "realtime_new_entry": False,
    },
    "signals": {
        # A rank move of at least this many places is worth reporting.
        "move_threshold": 10,
        # An app counts as a "new release" if published within this many days.
        "new_release_days": 30,
        # Cap list lengths in Slack so messages stay readable.
        "max_items_per_section": 10,
    },
    # Generic terms swept alongside the genre-specific ones below. Without these
    # the discovery pool inherits the genre's vocabulary and the "all genres"
    # view has almost nothing extra in it.
    "discovery_terms": [
        # Mechanics and themes rather than genre names: the Search API ranks by
        # relevance, so broad vocabulary is what widens the discovery pool.
        "game", "games", "3d", "online", "multiplayer", "offline", "fun",
        "arcade", "adventure", "racing", "strategy", "simulator", "idle",
        "tycoon", "card game", "board game", "rpg", "shooter", "battle", "war",
        "fight", "ninja", "zombie", "survival", "sniper", "quest", "story",
        "horror", "mystery", "car", "drift", "bike", "moto", "drive", "soccer",
        "football", "basketball", "golf", "tennis", "pool", "bowling", "farm",
        "city", "cooking", "restaurant", "salon", "doctor", "runner", "jump",
        "dash", "relaxing", "kids", "baby", "coloring", "drawing", "learn",
        "math", "pixel", "retro", "anime", "cute", "pet", "dragon", "magic",
        "tower", "defense", "craft", "build", "sort", "stack", "draw", "paint",
        "clicker", "casino", "slots", "poker", "bingo", "chess", "quiz",
        "trivia", "mahjong", "solitaire", "bubble", "candy", "jelly", "farm 3d",
        "simulation", "clash", "hero", "legend", "empire", "kingdom",
    ],
    # Non-primary storefronts sweep this subset rather than all 92 terms. The
    # long tail mostly rediscovers the same apps, and those storefronts throttle
    # hard enough that the extra terms cost minutes for very little.
    # Apple's search is relevance-ranked with no date sort, so genre words
    # return whatever is established -- "puzzle" comes back with a median age
    # of five years and one game from the last month. These few phrases are
    # the exception: they hit a recency bucket where nearly every result is
    # weeks old, and between them they surface roughly three times what the
    # entire genre vocabulary finds. Every storefront gets them.
    "recency_terms": [
        "new game", "newest game", "latest game", "new games free",
        "new free games", "new games",
    ],
    "discovery_terms_short": [
        "game", "games", "arcade", "puzzle", "action", "adventure", "racing",
        "strategy", "simulator", "idle", "rpg", "card", "board", "casino",
        "sports", "kids", "shooter", "battle", "farm", "match",
    ],
    "sweep_countries": True,
    # Upper bound on releases published per storefront, newest first.
    "release_pool_size": 3000,
    "search_terms": [
        "puzzle", "jigsaw", "sudoku", "match 3", "block puzzle", "word puzzle",
        "brain", "escape room", "merge", "tile", "crossword", "logic",
        "hidden object", "solitaire", "nonogram",
    ],
    "web": {
        "host": "127.0.0.1", "port": 8765,
        # When the server is reached through a tunnel or proxy, only the signed
        # /slack/command endpoint is served. Set true to publish the dashboard
        # and its unauthenticated /api routes as well -- rarely what you want.
        "expose_dashboard": False,
        # Linked from the dashboard's "Send digest" control.
        "repo_url": "https://github.com/AllenSky/game-rank-monitor",
        # Deployed Cloudflare Worker, e.g. https://topgames-slash.<you>.workers.dev
        # Required for the dashboard's "Share to Slack" button.
        "worker_url": "",
        # Public dashboard URL, used for the digest's buttons.
        "pages_url": "https://allensky.github.io/game-rank-monitor",
    },
}


def _merge(base, override):
    """Deep-merge override into a copy of base."""
    out = dict(base)
    for key, val in (override or {}).items():
        if isinstance(val, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], val)
        else:
            out[key] = val
    return out


# Environment overrides, so CI can supply secrets without a config file in the repo.
ENV_MAP = {
    "TOPGAMES_SLACK_WEBHOOK": ("slack", "webhook_url"),
    "TOPGAMES_SLACK_SIGNING_SECRET": ("slack", "signing_secret"),
    "TOPGAMES_LARK_SECRET": ("slack", "lark_secret"),
    "TOPGAMES_GENRE": ("genre",),
    "TOPGAMES_COUNTRY": ("country",),
    "TOPGAMES_CHART": ("chart",),
}


def _apply_env(cfg):
    for var, path in ENV_MAP.items():
        value = os.environ.get(var)
        if not value:
            continue
        target = cfg
        for key in path[:-1]:
            target = target.setdefault(key, {})
        target[path[-1]] = value
    return cfg


def load(path=CONFIG_PATH):
    user = {}
    if os.path.exists(path):
        with open(path) as fh:
            user = json.load(fh)
    cfg = _apply_env(_merge(DEFAULTS, user))
    cfg["genre_id"] = GENRES.get(cfg["genre"], GENRES["puzzle"])
    return cfg


def save_example(path=None):
    path = path or os.path.join(ROOT, "config.example.json")
    with open(path, "w") as fh:
        json.dump(DEFAULTS, fh, indent=2)
    return path


def datasets(cfg):
    """Resolve cfg into one fully-populated config per dataset.

    The cross product is platforms x countries x genres_tracked. Every
    dataset keeps history in the single shared database (platform/chart/
    genre_id namespaced), which is what cross-platform company views and
    digests are built on. The `primary` dataset is the first one and feeds
    the legacy single-dataset code paths (web server, slash command).
    """
    raw = cfg.get("datasets") or []
    if not raw:
        countries = cfg.get("countries") or [cfg["country"]]
        genres_t = cfg.get("genres_tracked") or [cfg["genre"]]
        platforms = cfg.get("platforms") or ["ios"]
        raw = [{"platform": p, "country": c, "genre": g,
                "primary": p == platforms[0] and c == cfg["country"]
                and g == cfg["genre"],
                "history": True}
               for p in platforms for c in countries for g in genres_t]
        if not any(d["primary"] for d in raw):
            raw[0]["primary"] = True

    out, seen_primary = [], False
    for entry in raw:
        country = (entry.get("country") or cfg["country"]).lower()
        genre = (entry.get("genre") or cfg["genre"]).lower()
        platform = (entry.get("platform") or "ios").lower()
        primary = bool(entry.get("primary")) and not seen_primary
        if primary:
            seen_primary = True
        apple_id = GENRES.get(genre, GENRES["casual"])
        d = dict(cfg)
        d.update({
            "platform": platform,
            "country": country,
            "genre": genre,
            "genre_id": apple_id + (PLAY_GENRE_ID_OFFSET if platform == "play" else 0),
            "play_category": PLAY_GENRES.get(genre, "GAME_CASUAL"),
            "chart": (PLAY_CHARTS.get(entry.get("chart", cfg["chart"]), "top_free")
                      if platform == "play"
                      else entry.get("chart", cfg["chart"])),
            "chart_size": int(entry.get("chart_size", cfg["chart_size"])),
            "slug": f"{country}-{platform}-{genre}",
            "outdir_rel": f"{country}/{platform}/{genre}",
            "primary": primary,
            "history": bool(entry.get("history", True)),
        })
        d["db_path"] = (DB_PATH if d["history"]
                        else os.path.join(ROOT, "data", f"{d['slug']}.db"))
        out.append(d)

    if not seen_primary and out:
        out[0]["primary"] = True
        out[0]["history"] = True
        out[0]["db_path"] = DB_PATH
    return out


def primary(cfg):
    for d in datasets(cfg):
        if d["primary"]:
            return d
    return datasets(cfg)[0]
