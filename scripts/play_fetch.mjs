// Google Play fetch helper for game-rank-monitor.
//
// Usage:
//   node scripts/play_fetch.mjs chart  --category GAME_CASUAL --collection TOP_FREE \
//        --num 100 --country us --lang en
//   node scripts/play_fetch.mjs apps   --ids com.a.b,com.c.d --country us --lang en
//
// Prints one JSON document to stdout; nonzero exit + stderr message on failure
// so the Python side can turn it into a per-dataset degradation.

import pkg from "google-play-scraper";
const gplay = pkg.default ?? pkg;

function arg(name, fallback) {
  const i = process.argv.indexOf(`--${name}`);
  return i > -1 && process.argv[i + 1] ? process.argv[i + 1] : fallback;
}

async function main() {
  const mode = process.argv[2];
  const country = arg("country", "us");
  const lang = arg("lang", "en");

  if (mode === "chart") {
    const category = gplay.category[arg("category", "GAME_CASUAL")];
    const collName = arg("collection", "TOP_FREE").toUpperCase().replace(/-/g, "_");
    const collection = gplay.collection[collName];
    const num = parseInt(arg("num", "100"), 10);
    if (!category) throw new Error(`unknown category: ${arg("category")}`);
    if (!collection) throw new Error(`unknown collection: ${arg("collection")}`);
    const rows = await gplay.list({ category, collection, num, country, lang });
    process.stdout.write(JSON.stringify(rows.map((r, i) => ({
      rank: i + 1,
      appId: r.appId ?? r.appIdOrDeveloperPage ?? null,
      title: r.title ?? "",
      developer: r.developer ?? "",
      developerId: r.developerId ?? null,
      icon: r.icon ?? "",
      score: r.score ?? 0,
      ratings: r.ratings ?? 0,
      price: r.price ?? 0,
    }))));
    return;
  }

  if (mode === "apps") {
    const ids = arg("ids", "").split(",").filter(Boolean);
    const CONCURRENCY = 8;
    const out = new Array(ids.length);
    let cursor = 0;
    async function worker() {
      while (cursor < ids.length) {
        const id = ids[cursor++];
        try {
          const a = await gplay.app({ appId: id, country, lang });
          // The lib returns `updated` as unix milliseconds; the Python side
          // stores ISO strings, so normalise at this boundary.
          if (typeof a.updated === "number") a.updated = new Date(a.updated).toISOString();
          out[ids.indexOf(id)] = a;
        } catch (e) {
          process.stderr.write(`app(${id}) failed: ${e.message}\n`);
        }
      }
    }
    await Promise.all(Array.from({ length: CONCURRENCY }, worker));
    process.stdout.write(JSON.stringify(out.filter(Boolean)));
    return;
  }

  throw new Error(`unknown mode: ${mode}`);
}

main().catch((e) => {
  process.stderr.write(`play_fetch error: ${e.message}\n`);
  process.exit(1);
});
