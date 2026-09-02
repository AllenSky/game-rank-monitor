# top_games

Tracks the **US App Store Puzzle charts** and **new puzzle releases**, shows them in a
local web dashboard, and posts daily/weekly digests to Slack — including an explicit
signal when a game **enters or leaves the top 100**.

Pure Python standard library. No pip install, no API keys.

---

## Quick start

```bash
python3 -m topgames init
```

```bash
python3 -m topgames refresh
```

```bash
python3 -m topgames serve
```

Then open <http://127.0.0.1:8765>.

> The **first** `refresh` only stores a baseline — there is nothing to compare against yet.
> Movement and "new in chart" signals appear from the **second** refresh onward.

---

## Where the data comes from

| Need | Source | Notes |
|---|---|---|
| Top 100 Puzzle chart (US) | iTunes RSS `topfreeapplications` + `genre=7012` | The **only** Apple endpoint that still filters a chart to a single game subgenre. |
| Ratings, release dates, publisher, icon | iTunes **Lookup** API | 100 ids per request, one request per refresh. |
| New releases | iTunes **Search** API swept over ~15 terms | Filtered to apps Apple tags `Puzzle`, then by release date. |

All keyless, all `https://itunes.apple.com/*`.

### Two honest limitations

1. **The RSS chart feed is undocumented and formally deprecated.** It works today (verified
   returning a full 100-entry Puzzle chart), but Apple could retire it without notice. If it
   ever goes dark, `sources.fetch_chart` is the single function to swap out. The newer
   `rss.marketingtools.apple.com` API is *not* a drop-in replacement — it returns 404 for every
   genre parameter and carries no genre metadata, which is why it isn't used here.
2. **New-release discovery is search-based, so it is not exhaustive.** Apple's RSS
   "new applications" feed *ignores* its genre parameter (it returns spreadsheet editors and
   habit trackers, not games), so it is unusable. The search sweep finds relevance-ranked
   results, which means a brand-new game with zero ratings may not surface on day one. It gets
   caught on a later run once it gains any traction — the database's `first_seen` column is what
   makes that reliable rather than the feed itself.

Changing `"genre": "puzzle"` in `config.json` to `word`, `board`, `strategy`, `casual`, etc.
retargets everything; the genre id map is in `topgames/config.py`.

---

## Connecting Slack

1. Go to <https://api.slack.com/apps> → **Create New App** → **From scratch**.
2. Name it (e.g. `Top Games`) and pick your workspace.
3. In the sidebar choose **Incoming Webhooks** and toggle **Activate Incoming Webhooks** on.
4. Click **Add New Webhook to Workspace**, pick the destination channel, and **Allow**.
5. Copy the webhook URL (`https://hooks.slack.com/services/T…/B…/…`) into `config.json`:

```json
{ "slack": { "webhook_url": "https://hooks.slack.com/services/XXX/YYY/ZZZ" } }
```

6. Verify it:

```bash
python3 -m topgames slack-test
```

Treat the webhook URL as a secret — anyone holding it can post to that channel. It lives only
in `config.json`, which is gitignored.

---

## Scheduling the digests

Times, days, and which signals each digest carries are set in `config.json`:

```json
"daily":  { "enabled": true, "time": "09:00",
            "include": ["debut","new_entry","new_release","climb","exit"] },
"weekly": { "enabled": true, "day": "monday", "time": "09:00",
            "include": ["debut","new_entry","new_release","climb","fall","exit"],
            "show_full_chart": true }
```

Install the macOS jobs (launchd — unlike cron it catches up after the Mac has been asleep):

```bash
python3 -m topgames schedule install
```

```bash
python3 -m topgames schedule status
```

```bash
python3 -m topgames schedule uninstall
```

Each job runs `topgames run <period>`, which refreshes and then posts in one step. Logs land in
`data/daily.log` and `data/weekly.log`. **Re-run `schedule install` after changing the times.**

Setting `"realtime_new_entry": true` also fires an immediate alert on any refresh where a game
enters the chart, instead of waiting for the next digest.

---

## The signals

| Signal | Meaning |
|---|---|
| `debut` | A game released in the last 30 days **entered the chart** — the headline signal. |
| `new_entry` | An older game entered the chart. |
| `exit` | A game dropped out of the top 100. |
| `climb` / `fall` | Moved at least `move_threshold` places (default 10). |
| `new_release` | A new puzzle game appeared in the store, chart or not. |

Daily deliberately omits `fall` to keep the channel quiet; the weekly recap includes it.

## Commands

```bash
python3 -m topgames refresh              # pull chart + new releases, derive signals
python3 -m topgames chart --limit 20     # print the stored chart
python3 -m topgames digest daily --dry-run   # print the Slack payload, send nothing
python3 -m topgames digest weekly        # build and send
python3 -m topgames run daily            # refresh then send (what the scheduler calls)
python3 -m topgames serve --port 8765    # dashboard
```

## Tests

```bash
python3 tests_signals.py
```

Covers the diff engine (entries, exits, climbs, falls), digest composition, resend
suppression, and the empty-week case. Runs offline against synthetic snapshots.

---

## The `/top100` slash command (optional)

Digests are **outbound only** — the webhook needs no public server. A slash command is the
opposite: Slack must POST *into* your machine, so it needs a public HTTPS **Request URL**.

The endpoint is `POST /slack/command`, served by `topgames serve`.

### 1. Get the signing secret

In your Slack app → **Basic Information** → **App Credentials** → **Signing Secret** → Show → copy
it into `config.json`:

```json
{ "slack": { "signing_secret": "abc123..." } }
```

This is not optional. Every request is verified with an HMAC over the raw body plus a 5-minute
replay window; unverified requests get a 401. Without the secret the endpoint refuses everything,
because anyone who learned the URL could otherwise trigger it.

### 2. Expose the local server

```bash
brew install cloudflared
```

```bash
cloudflared tunnel --url http://localhost:8765
```

It prints a public `https://<random>.trycloudflare.com` URL. Your Request URL is that plus the
path:

```
https://<random>.trycloudflare.com/slack/command
```

Quick tunnels get a **new URL every restart**, and only work while both the tunnel and
`topgames serve` are running. For something permanent, use a named Cloudflare tunnel with your own
domain, or host the app on a small always-on box.

### 3. Fill in the Slack form

| Field | Value |
|---|---|
| Command | `/top100` |
| Request URL | `https://<your-tunnel>/slack/command` |
| Short Description | `Print the App Store Top 100 Apps` |
| Usage Hint | `[25\|50\|100 \| new \| signals \| refresh \| share]` |

Save, then reinstall the app to the workspace when Slack prompts.

### What the command does

| Input | Result |
|---|---|
| `/top100` | Top 25, with ▲▼ movement — visible only to you |
| `/top100 50` | Top 50 (max 100) |
| `/top100 new` | Recently released games |
| `/top100 signals` | Chart movement from the last 7 days |
| `/top100 refresh` | Pulls fresh data from Apple (~25s) |
| `/top100 share` | Posts the top 25 **visibly to the channel** |
| `/top100 help` | Usage |

Replies are ephemeral by default so the channel does not fill with 100-row tables; `share` is the
deliberate exception. `refresh` exceeds Slack's 3-second deadline, so it acknowledges immediately
and delivers the result to the `response_url` when the pull finishes.

### Tunnel exposure

A tunnel publishes the *whole* server, not just the endpoint you wanted. That would leave
`POST /api/slack-test` and `POST /api/digest` reachable by anyone holding the URL — an open
invitation to post into your Slack channel.

So when a request arrives carrying proxy headers (`CF-Connecting-IP`, `Cf-Ray`,
`X-Forwarded-For`, …), only `/slack/command` is served; everything else gets a 403. The
dashboard stays fully available on `127.0.0.1`, which is the only place it should be.

Set `web.expose_dashboard: true` to opt out — but note the `/api` routes have no authentication
of their own, so this genuinely does publish them.

---

## Checking the data yourself

`verify.py` diffs a published chart against Apple's own web chart:

```bash
python3 verify.py us puzzle
```

```bash
python3 verify.py tr strategy
```

It reports two different things, because they mean different things:

* **membership** — are the same apps present? A missing app is a real bug.
* **position** — are they in the same order? Charts reshuffle through the day, and
  our snapshot is fixed while Apple's page is live, so a few positions moving is
  normal drift, not an error.

Apple renders roughly the first 25 positions server-side and lazy-loads the rest, so
that is as deep as an automated check can go. To eyeball a chart by hand:

```
https://apps.apple.com/<country>/charts/iphone/<genre>-games/<genre_id>
```

e.g. <https://apps.apple.com/us/charts/iphone/puzzle-games/7012>. The genre ids are in
`topgames/config.py`.

### New releases are a sample, not a census

The chart is exact — it comes straight from Apple's ranked feed. **New releases are
not.** Apple publishes no endpoint that lists every new release: the RSS
"newapplications" feed ignores its genre parameter and returns stale data, so this
project discovers releases by sweeping the Search API across a set of terms.

Search is relevance-ranked, so a brand-new game with no ratings often does not
surface at all. Expect the release list to be a useful sample of what is launching,
not a complete registry — the real number of new iOS games per month is in the
thousands, and no free Apple endpoint enumerates them.
