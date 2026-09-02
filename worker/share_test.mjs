import worker from "./worker.js";
let posted = [];
const realFetch = globalThis.fetch;
globalThis.fetch = async (url, opts) => {
  if (String(url).includes("hooks.slack.test")) {
    posted.push(JSON.parse(opts.body));
    return new Response("ok", { status: 200 });
  }
  return realFetch(url, opts);
};
// caches.default is not present in plain Node; stub the cooldown store.
const store = new Map();
globalThis.caches = { default: {
  async match(req){ return store.get(req.url); },
  async put(req, res){ store.set(req.url, res); } } };

const env = { PAGES_BASE: "http://127.0.0.1:8766",
              SLACK_WEBHOOK_URL: "https://hooks.slack.test/x",
              SLACK_SIGNING_SECRET: "s" };
const call = (body, method="POST") => worker.fetch(
  new Request("https://w.dev/share", { method,
    headers: {"Content-Type":"application/json"},
    body: method === "POST" ? JSON.stringify(body) : undefined }), env);

let fail = 0;
const ck = (l, c, x="") => { if(!c) fail++; console.log(`  ${c?"PASS":"FAIL"}  ${l}${x?"  "+x:""}`); };

const pre = await worker.fetch(new Request("https://w.dev/share", {method:"OPTIONS"}), env);
ck("CORS preflight -> 204", pre.status === 204,
   pre.headers.get("Access-Control-Allow-Origin") || "");

for (const kind of ["movers","new","chart"]) {
  posted = []; store.clear();
  const r = await call({kind});
  const j = await r.json();
  ck(`share ${kind}`.padEnd(16), r.status === 200 && posted.length === 1,
     `${j.message||j.error} · ${posted[0]?.blocks?.length ?? 0} blocks`);
}
store.clear();
ck("unknown kind -> 400", (await call({kind:"../etc/passwd"})).status === 400);
ck("no body -> 400", (await call(undefined)).status === 400);
ck("GET -> 405", (await call({kind:"movers"},"GET")).status === 405);

store.clear();
await call({kind:"movers"});
const second = await call({kind:"movers"});
ck("cooldown blocks repeat -> 429", second.status === 429,
   (await second.json()).error);

const noHook = await worker.fetch(new Request("https://w.dev/share",
  {method:"POST", body: JSON.stringify({kind:"movers"})}), {...env, SLACK_WEBHOOK_URL:""});
ck("missing webhook -> 500", noHook.status === 500);

console.log(fail ? `\n${fail} FAILURE(S)` : "\nALL SHARE TESTS PASSED");
process.exit(fail?1:0);
