import worker from "./worker.js";
import crypto from "node:crypto";
const SECRET = "test-signing-secret";
const env = { PAGES_BASE: "http://127.0.0.1:8766", SLACK_SIGNING_SECRET: SECRET,
              SLACK_WEBHOOK_URL: "https://hooks.slack.test/x",
              DATASETS: "us/puzzle,tr/puzzle,us/strategy,gb/word" };
const store = new Map();
globalThis.caches = { default: {
  async match(r){ return store.get(r.url); }, async put(r,v){ store.set(r.url,v); } } };
let posted = [], fetched = [];
const real = globalThis.fetch;
globalThis.fetch = async (u, o) => {
  fetched.push(String(u));
  if (String(u).includes("hooks.slack.test")) { posted.push(String(u)); return new Response("ok"); }
  return real(u, o);
};
const sign = (ts, body) => "v0=" + crypto.createHmac("sha256", SECRET)
  .update(`v0:${ts}:${body}`).digest("hex");
async function slash(text) {
  const body = new URLSearchParams({command:"/top100", text, response_url:"https://x"}).toString();
  const ts = String(Math.floor(Date.now()/1000));
  const r = await worker.fetch(new Request("https://w.dev/slack/command", {
    method:"POST", headers:{"Content-Type":"application/x-www-form-urlencoded",
      "X-Slack-Request-Timestamp":ts,"X-Slack-Signature":sign(ts,body)}, body}), env);
  return { status:r.status, json: await r.json().catch(()=>({})) };
}
let fail=0;
const ck=(l,c,x="")=>{ if(!c) fail++; console.log(`  ${c?"PASS":"FAIL"}  ${l}${x?"  "+x:""}`); };
const first = j => j.blocks?.[1]?.text?.text?.split("\n")[0] ?? j.blocks?.[0]?.text?.text?.slice(0,60) ?? "";

console.log("=== dataset routing ===");
for (const [text, expect] of [["", "/us/"], ["tr puzzle", "/tr/"], ["puzzle tr", "/tr/"],
                              ["gb word 50", "/gb/"], ["us strategy new", "/us/"]]) {
  const {status, json} = await slash(text);
  ck(`/top100 ${text || "(none)"}`.padEnd(26), status===200 && first(json).includes(expect),
     `${status} ${first(json).slice(0,54)}`);
}

console.log("\n=== rejection / injection ===");
for (const [text, why] of [
  ["de racing", "unpublished but well-formed"],
  ["../../etc puzzle", "path traversal"],
  ["%2e%2e puzzle", "encoded traversal"],
  ["https://evil.com puzzle", "absolute url"],
  ["x".repeat(200), "overlong token"],
]) {
  fetched = [];
  const {status, json} = await slash(text);
  // What matters is the URL we fetched, not the text echoed back to the user.
  const bad = fetched.filter(u => !u.startsWith(env.PAGES_BASE + "/"));
  const traversed = fetched.some(u => u.includes("..") || u.includes("%2e"));
  ck(why.padEnd(28), status===200 && bad.length===0 && !traversed,
     `${status} fetched=${fetched.map(u=>u.replace(env.PAGES_BASE,"")).join(",")||"none"}`);
}

console.log("\n=== share is dataset-scoped ===");
async function share(kind, dataset) {
  const r = await worker.fetch(new Request("https://w.dev/share", {method:"POST",
    headers:{"Content-Type":"application/json"}, body: JSON.stringify({kind, dataset})}), env);
  return { status:r.status, json: await r.json().catch(()=>({})) };
}
store.clear(); posted=[];
ck("share tr/puzzle", (await share("chart","tr/puzzle")).status===200);
ck("share us/strategy not blocked by tr cooldown", (await share("chart","us/strategy")).status===200);
ck("repeat tr/puzzle -> 429", (await share("chart","tr/puzzle")).status===429);
ck("share unknown dataset -> 400", (await share("chart","de/racing")).status===400);
ck("share traversal -> 400", (await share("chart","../../x")).status===400);

console.log(fail ? `\n${fail} FAILURE(S)` : "\nALL DATASET TESTS PASSED");
process.exit(fail?1:0);
