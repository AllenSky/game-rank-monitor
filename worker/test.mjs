import worker from "./worker.js";

// A throwaway value: the test signs and verifies with the same secret, so it
// only has to match itself. Never put the real signing secret in the repo.
const SECRET = process.env.SLACK_SIGNING_SECRET || "test-signing-secret";
const env = { SLACK_SIGNING_SECRET: SECRET, PAGES_BASE: "http://127.0.0.1:8766" };
const enc = new TextEncoder();

async function sign(body, ts, secret = SECRET) {
  const key = await crypto.subtle.importKey("raw", enc.encode(secret),
    { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const mac = await crypto.subtle.sign("HMAC", key, enc.encode(`v0:${ts}:${body}`));
  return "v0=" + [...new Uint8Array(mac)].map(b => b.toString(16).padStart(2, "0")).join("");
}

async function call(text, { secret = SECRET, ts = null } = {}) {
  const body = new URLSearchParams({ command: "/top100", text,
    response_url: "https://hooks.slack.com/commands/X", user_name: "alkan" }).toString();
  const stamp = ts ?? String(Math.floor(Date.now() / 1000));
  const req = new Request("https://w.dev/", { method: "POST", body,
    headers: { "Content-Type": "application/x-www-form-urlencoded",
      "X-Slack-Request-Timestamp": stamp,
      "X-Slack-Signature": await sign(body, stamp, secret) } });
  const t0 = performance.now();
  const res = await worker.fetch(req, env);
  return { status: res.status, ms: performance.now() - t0,
           json: res.status === 200 ? await res.json() : null };
}

let fails = 0;
const check = (label, cond, extra = "") => {
  if (!cond) fails++;
  console.log(`  ${cond ? "PASS" : "FAIL"}  ${label}${extra ? "  " + extra : ""}`);
};

console.log("=== SECURITY ===");
check("valid signature -> 200", (await call("")).status === 200);
check("wrong secret -> 401", (await call("", { secret: "nope" })).status === 401);
check("stale timestamp -> 401",
  (await call("", { ts: String(Math.floor(Date.now() / 1000) - 9999) })).status === 401);
const getRes = await worker.fetch(new Request("https://w.dev/"), env);
check("GET -> 405", getRes.status === 405);

console.log("\n=== ROUTING ===");
for (const [text, expect] of [["", "chart"], ["50", "chart"], ["100", "chart"],
    ["7", "chart"], ["new", "new"], ["signals", "signals"], ["share", "chart"],
    ["help", "help"], ["refresh", "info"], ["zzz", "help"]]) {
  const r = await call(text);
  const blocks = r.json?.blocks?.length ?? 0;
  const type = r.json?.response_type;
  check(`/top100 ${text || "(none)"}`.padEnd(22), r.status === 200 && blocks > 0,
    `${type}, ${blocks} blocks, ${r.ms.toFixed(1)}ms`);
}

console.log("\n=== BEHAVIOUR ===");
const share = await call("share");
check("share is in_channel", share.json.response_type === "in_channel");
const plain = await call("");
check("default is ephemeral", plain.json.response_type === "ephemeral");
const big = await call("100");
const rows = big.json.blocks.slice(1)
  .reduce((n, b) => n + b.text.text.split("\n").length, 0);
check("/top100 100 returns 100 rows", rows === 100, `got ${rows}`);
check("blocks within Slack limit", big.json.blocks.length <= 50,
  `${big.json.blocks.length} blocks`);
check("no section over 3000 chars",
  big.json.blocks.every(b => b.text.text.length <= 3000));

console.log("\n=== UPSTREAM FAILURE ===");
const broken = await worker.fetch(new Request("https://w.dev/", { method: "POST",
  body: (() => new URLSearchParams({ text: "" }).toString())(),
  headers: { "X-Slack-Request-Timestamp": String(Math.floor(Date.now() / 1000)),
    "X-Slack-Signature": await sign(new URLSearchParams({ text: "" }).toString(),
      String(Math.floor(Date.now() / 1000))) } }),
  { ...env, PAGES_BASE: "http://127.0.0.1:8799" });
const brokenJson = broken.status === 200 ? await broken.json() : null;
check("unreachable Pages degrades gracefully",
  broken.status === 200 && /temporarily unreachable/.test(brokenJson?.blocks?.[0]?.text?.text ?? ""),
  `status ${broken.status}`);

console.log(fails === 0 ? "\nALL WORKER TESTS PASSED" : `\n${fails} FAILURE(S)`);
process.exit(fails === 0 ? 0 : 1);
