/**
 * Slack slash-command endpoint for /top100.
 *
 * All the real work happens in the scheduled GitHub Action, which publishes
 * ready-made Slack payloads to GitHub Pages. This Worker only verifies that a
 * request genuinely came from Slack and hands back the matching file, which
 * keeps it far inside the free plan's 10ms CPU budget.
 */

const REPLAY_WINDOW = 60 * 5; // seconds

const enc = new TextEncoder();

function hex(buf) {
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

/** Length-independent comparison, so timing cannot leak the expected signature. */
function safeEqual(a, b) {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

async function verify(secret, timestamp, signature, body) {
  if (!secret) return "no signing secret configured";
  if (!timestamp || !signature) return "missing signature headers";
  const age = Math.abs(Math.floor(Date.now() / 1000) - Number(timestamp));
  if (!Number.isFinite(age) || age > REPLAY_WINDOW) return "stale timestamp";
  const key = await crypto.subtle.importKey(
    "raw", enc.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const mac = await crypto.subtle.sign("HMAC", key, enc.encode(`v0:${timestamp}:${body}`));
  return safeEqual(`v0=${hex(mac)}`, signature) ? null : "signature mismatch";
}

const HELP_TEXT =
  "*`/top100` — App Store chart lookup*\n" +
  "`/top100` — top 25 · `/top100 50` · `/top100 100`\n" +
  "`/top100 new` — recent releases\n" +
  "`/top100 signals` — chart movement\n" +
  "`/top100 share` — post the top 25 to the channel\n";

function message(text, inChannel = false) {
  return {
    response_type: inChannel ? "in_channel" : "ephemeral",
    text: text.replace(/[*`<>|]/g, ""),
    blocks: [{ type: "section", text: { type: "mrkdwn", text } }],
  };
}

/** Map the user's argument onto one of the published payload files. */
function route(text) {
  const t = (text || "").trim().toLowerCase();
  if (t === "" || t === "25") return { file: "top100-25" };
  if (t === "50") return { file: "top100-50" };
  if (t === "100") return { file: "top100-100" };
  if (/^\d+$/.test(t)) {
    const n = Number(t);
    return { file: n <= 25 ? "top100-25" : n <= 50 ? "top100-50" : "top100-100" };
  }
  if (t.startsWith("new")) return { file: "new" };
  if (t.startsWith("signal")) return { file: "signals" };
  if (t.startsWith("share")) return { file: "top100-25", inChannel: true };
  if (t === "help" || t === "?") return { inline: message(HELP_TEXT) };
  if (t === "refresh") {
    return { inline: message(
      ":information_source: Data refreshes automatically on a schedule — there is " +
      "nothing to trigger by hand. The timestamp on the dashboard shows how current " +
      "it is.") };
  }
  // Echo the token back so the user can see their typo, but strip it to plain
  // word characters first: it is untrusted input heading into a Slack message.
  const shown = t.replace(/[^a-z0-9 _-]/gi, "").slice(0, 24) || "(unrecognised)";
  return { inline: message(`:question: Unknown option \`${shown}\`.\n\n${HELP_TEXT}`) };
}

const SHARE_KINDS = new Set(["movers", "new", "chart"]);

// Only datasets listed in the DATASETS var can be reached. The token is matched
// against this list and the URL is built from the MATCHED ENTRY, never from the
// user's string, so nothing a caller types can steer the fetch.
function allowedDatasets(env) {
  return String(env.DATASETS || "")
    .split(",").map(s => s.trim()).filter(Boolean);
}

const COUNTRY_RE = /^[a-z]{2}$/;
const GENRE_RE = /^[a-z_]{2,20}$/;

/**
 * Pull a country/genre pair out of the command's words, in any order.
 * Returns {dataset, rest} where dataset is "" for the primary chart.
 */
function pickDataset(words, env) {
    const allow = allowedDatasets(env);
    if (!allow.length) return { dataset: "", rest: words, error: null };

    const countries = new Set(allow.map(d => d.split("/")[0]));
    const genres = new Set(allow.map(d => d.split("/")[1]));
    let country = "", genre = "";
    const rest = [];
    for (const w of words) {
      if (!country && COUNTRY_RE.test(w) && countries.has(w)) { country = w; continue; }
      if (!genre && GENRE_RE.test(w) && genres.has(w)) { genre = w; continue; }
      rest.push(w);
    }
    if (!country && !genre) return { dataset: "", rest, error: null };

    const primary = allow[0].split("/");
    const want = `${country || primary[0]}/${genre || primary[1]}`;
    const match = allow.find(d => d === want);
    if (!match) {
      return { dataset: "", rest,
        error: `No chart published for \`${want}\`. Available: ` +
               allow.map(d => "`" + d + "`").join(", ") };
    }
    // The primary lives at the root path for backwards compatibility.
    return { dataset: match === allow[0] ? "" : match, rest, error: null };
}
const SHARE_COOLDOWN = 60; // seconds between shares of the same kind

function cors(env, extra = {}) {
  // Only the published dashboard may call this from a browser.
  let origin = "*";
  try { origin = new URL(env.PAGES_BASE).origin; } catch {}
  return {
    "Access-Control-Allow-Origin": origin,
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    ...extra,
  };
}

/**
 * Forward a prebuilt payload to Slack.
 *
 * The body carries only a kind, never text: the message itself is a file the
 * scheduled job published, so this endpoint cannot be used to post arbitrary
 * content into the channel. A short cooldown bounds how often a public page can
 * trigger it.
 */
const MAX_SHARE_ROWS = 60;
const SECTION_LIMIT = 2800;

/**
 * Compose the release message from the caller's filters.
 *
 * The caller sends a store, a genre and an age -- never text. The rows come
 * from the pool this project published, so the endpoint still cannot be made to
 * post arbitrary content: the worst a caller can do is ask for a different
 * slice of the user's own data.
 */
async function buildFilteredReleases(env, filters) {
  const allow = allowedDatasets(env);
  const countries = new Set(allow.map(d => d.split("/")[0]));

  const store = String(filters.store || "").toLowerCase();
  if (!/^[a-z]{2}$/.test(store) || !countries.has(store)) {
    const err = new Error("unknown store"); err.status = 400; throw err;
  }
  // Genre is only ever compared against values already in the published file.
  const genre = String(filters.genre || "all").slice(0, 40);
  const ageRaw = String(filters.age || "30");
  const age = ageRaw === "all" ? Infinity : Math.min(Math.max(Number(ageRaw) || 30, 1), 36500);

  const url = `${env.PAGES_BASE.replace(/\/$/, "")}/releases/${store}.json`;
  const res = await fetch(url, { cf: { cacheTtl: 60 } });
  if (!res.ok) {
    const err = new Error(`no release data for ${store.toUpperCase()}`);
    err.status = 502; throw err;
  }
  let rows = await res.json();

  if (Number.isFinite(age)) rows = rows.filter(r => (r.days_old ?? 1e9) <= age);
  if (genre !== "all") rows = rows.filter(r => (r.genres || []).includes(genre));

  const total = rows.length;
  const shown = rows.slice(0, MAX_SHARE_ROWS);
  const scope = `${genre === "all" ? "All genres" : genre} · ${store.toUpperCase()}`;
  const window = Number.isFinite(age) ? `the last ${age} days` : "all time";

  const lines = shown.map(r => {
    const dot = !r.ratings ? "⚪" : r.rating >= 4.7 ? "🟢" : r.rating >= 4.0 ? "🟡" : "🔴";
    const rating = r.ratings ? `${r.rating.toFixed(2)}★ (${r.ratings.toLocaleString("en-US")})`
                             : "no ratings yet";
    // & must be escaped inside a Slack link, and the Play URL carries one.
    const play = r.play_url ? `(<${r.play_url.replace(/&/g, "&amp;")}|And>)` : "";
    return `${dot} <${r.url}|${r.name}>${play}  ${r.artist} · ${rating} · ${r.released}`;
  });

  const blocks = [{ type: "section", text: { type: "mrkdwn",
    text: `*New releases — ${scope}*\n_${total} in ${window}` +
          (total > shown.length ? `, showing ${shown.length}` : "") + `_` } }];
  let buf = [], size = 0;
  for (const line of lines) {
    if (buf.length && size + line.length + 1 > SECTION_LIMIT) {
      blocks.push({ type: "section", text: { type: "mrkdwn", text: buf.join("\n") } });
      buf = []; size = 0;
    }
    buf.push(line); size += line.length + 1;
  }
  if (buf.length)
    blocks.push({ type: "section", text: { type: "mrkdwn", text: buf.join("\n") } });
  if (total > shown.length)
    blocks.push({ type: "context", elements: [{ type: "mrkdwn",
      text: `_…and ${total - shown.length} more on the dashboard_` }] });

  return {
    username: "top_games",
    icon_emoji: ":jigsaw:",
    text: `New releases ${scope}: ${total} in ${window}`,
    blocks: blocks.slice(0, 50),
  };
}

async function handleShare(request, env) {
  if (!env.SLACK_WEBHOOK_URL) {
    return Response.json({ error: "Worker has no SLACK_WEBHOOK_URL secret set" },
      { status: 500, headers: cors(env) });
  }
  let kind = "", dataset = "", filters = null;
  try {
    const body = await request.json();
    kind = body.kind;
    dataset = String(body.dataset || "");
    if (body.filters && typeof body.filters === "object") filters = body.filters;
  } catch {}
  if (!SHARE_KINDS.has(kind)) {
    return Response.json({ error: "unknown share kind" },
      { status: 400, headers: cors(env) });
  }
  if (dataset) {
    // Same rule as the slash command: only a published dataset is reachable,
    // and the path is built from the matched entry.
    const match = allowedDatasets(env).find(d => d === dataset);
    if (!match) {
      return Response.json({ error: "unknown dataset" },
        { status: 400, headers: cors(env) });
    }
    dataset = match === allowedDatasets(env)[0] ? "" : match;
  }

  const cache = caches.default;
  const filterKey = filters
    ? `${filters.store || ""}-${filters.genre || ""}-${filters.age || ""}` : "";
  const marker = new Request(
    `https://share.local/${dataset}/${kind}/${encodeURIComponent(filterKey)}`);
  if (await cache.match(marker)) {
    return Response.json(
      { error: `Already shared ${kind} in the last ${SHARE_COOLDOWN}s` },
      { status: 429, headers: cors(env) });
  }

  let payload;
  if (kind === "new" && filters) {
    try {
      payload = await buildFilteredReleases(env, filters);
    } catch (err) {
      return Response.json({ error: err.message },
        { status: err.status || 502, headers: cors(env) });
    }
  } else {
    const src = `${env.PAGES_BASE.replace(/\/$/, "")}${dataset ? "/" + dataset : ""}/slack/share-${kind}.json`;
    try {
      const res = await fetch(src, { cf: { cacheTtl: 60 } });
      if (!res.ok) throw new Error(`upstream ${res.status}`);
      payload = await res.json();
    } catch (err) {
      return Response.json({ error: `Could not load the message (${err.message})` },
        { status: 502, headers: cors(env) });
    }
  }

  const post = await fetch(env.SLACK_WEBHOOK_URL, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!post.ok) {
    const detail = await post.text().catch(() => "");
    return Response.json({ error: `Slack rejected it (${post.status} ${detail})` },
      { status: 502, headers: cors(env) });
  }

  await cache.put(marker, new Response("1", {
    headers: { "Cache-Control": `max-age=${SHARE_COOLDOWN}` } }));
  return Response.json({ ok: true, message: `Posted ${kind} to Slack` },
    { headers: cors(env) });
}

// GitHub runs scheduled workflows best-effort: one started eleven hours late,
// and the next day none of four crons fired at all. Cloudflare's cron triggers
// are punctual, so the schedule lives here and GitHub's own crons stay on as a
// backup -- `digest --if-due` makes a double trigger a no-op rather than a
// duplicate message.
async function dispatchRefresh(env) {
  if (!env.GITHUB_TOKEN || !env.GITHUB_REPO) {
    console.log("scheduled: GITHUB_TOKEN/GITHUB_REPO unset, nothing to do");
    return;
  }
  const url = `https://api.github.com/repos/${env.GITHUB_REPO}` +
              `/actions/workflows/${env.GITHUB_WORKFLOW || "update.yml"}/dispatches`;
  const res = await fetch(url, {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${env.GITHUB_TOKEN}`,
      "Accept": "application/vnd.github+json",
      "User-Agent": "topgames-scheduler",
      "Content-Type": "application/json",
    },
    // "auto" here is the intent: the workflow resolves daily vs weekly from
    // the day of the week and runs `digest --if-due`, so whichever trigger
    // (this Worker, a GitHub cron, or a manual UI run) gets there first past
    // the scheduled hour posts -- exactly one digest per day.
    body: JSON.stringify({ ref: env.GITHUB_REF || "main",
                           inputs: { send_digest: "auto" } }),
  });
  // GitHub answers a permissions problem with 403 and a body that names it;
  // the status alone cannot tell a bad token from a missing scope.
  const detail = res.ok ? "" : ` ${(await res.text()).slice(0, 300)}`;
  console.log(`scheduled: workflow dispatch -> ${res.status}${detail}`);
}

export default {
  async scheduled(event, env, ctx) {
    ctx.waitUntil(dispatchRefresh(env));
  },

  async fetch(request, env) {
    const path = new URL(request.url).pathname;

    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: cors(env) });
    }
    if (path === "/share") {
      if (request.method !== "POST") {
        return new Response("share endpoint", { status: 405, headers: cors(env) });
      }
      return handleShare(request, env);
    }
    if (request.method !== "POST") {
      return new Response("top100 slash command endpoint", { status: 405 });
    }
    const body = await request.text();
    const problem = await verify(
      env.SLACK_SIGNING_SECRET,
      request.headers.get("X-Slack-Request-Timestamp"),
      request.headers.get("X-Slack-Signature"),
      body);
    if (problem) {
      // Deliberately terse: an unverified request may not be from Slack at all.
      return new Response("unauthorized", { status: 401 });
    }

    const form = new URLSearchParams(body);
    const words = (form.get("text") || "").trim().toLowerCase().split(/\s+/).filter(Boolean);
    const picked = pickDataset(words, env);
    if (picked.error) return Response.json(message(picked.error));
    const target = route(picked.rest.join(" "));
    if (target.inline) {
      return Response.json(target.inline);
    }

    const prefix = picked.dataset ? `/${picked.dataset}` : "";
    const url =
      `${env.PAGES_BASE.replace(/\/$/, "")}${prefix}/slack/${target.file}.json`;
    let payload;
    try {
      const upstream = await fetch(url, { cf: { cacheTtl: 300, cacheEverything: true } });
      if (!upstream.ok) {
        return Response.json(message(
          `:warning: Could not load chart data (upstream ${upstream.status}). ` +
          `The scheduled job may not have published yet.`));
      }
      payload = await upstream.json();
    } catch (err) {
      // A network failure or malformed JSON must still produce a Slack-shaped
      // reply; an exception here would surface to the user as a raw error.
      return Response.json(message(
        ":warning: Chart data is temporarily unreachable. Please try again shortly."));
    }
    if (target.inChannel) payload.response_type = "in_channel";
    return Response.json(payload);
  },
};
