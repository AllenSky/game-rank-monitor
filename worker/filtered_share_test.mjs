import worker from "./worker.js";
const env = { PAGES_BASE:"http://127.0.0.1:8766", SLACK_WEBHOOK_URL:"https://hooks.slack.test/x",
              SLACK_SIGNING_SECRET:"s", DATASETS:"us/puzzle,tr/puzzle,de/puzzle,gb/word,br/casino" };
const store=new Map();
globalThis.caches={default:{async match(r){return store.get(r.url);},async put(r,v){store.set(r.url,v);}}};
let posted=[]; const real=globalThis.fetch;
globalThis.fetch=async(u,o)=>{ if(String(u).includes("hooks.slack.test")){posted.push(JSON.parse(o.body));return new Response("ok");} return real(u,o); };
const share=(body)=>worker.fetch(new Request("https://w.dev/share",{method:"POST",
  headers:{"Content-Type":"application/json"},body:JSON.stringify(body)}),env);
let fail=0; const ck=(l,c,x="")=>{if(!c)fail++;console.log(`  ${c?"PASS":"FAIL"}  ${l}${x?"  "+x:""}`);};

for (const f of [{store:"us",genre:"Puzzle",age:"30"},{store:"tr",genre:"Puzzle",age:"30"},
                 {store:"us",genre:"all",age:"30"},{store:"us",genre:"Puzzle",age:"all"}]) {
  store.clear(); posted=[];
  const r=await share({kind:"new",filters:f});
  const p=posted[0];
  const head=p?.blocks?.[0]?.text?.text?.split("\n")[1] ?? "";
  ck(`${f.store}/${f.genre}/${f.age}`.padEnd(22), r.status===200 && !!p, `${p?.text ?? ""}`);
}
store.clear();
ck("bad store -> 400", (await share({kind:"new",filters:{store:"zz",genre:"Puzzle",age:"30"}})).status===400);
ck("traversal store -> 400", (await share({kind:"new",filters:{store:"../x",genre:"a",age:"1"}})).status===400);
store.clear();
await share({kind:"new",filters:{store:"us",genre:"Puzzle",age:"30"}});
ck("same filters -> 429", (await share({kind:"new",filters:{store:"us",genre:"Puzzle",age:"30"}})).status===429);
ck("different filters allowed", (await share({kind:"new",filters:{store:"tr",genre:"Puzzle",age:"30"}})).status===200);
console.log(fail?`\n${fail} FAILURE(S)`:"\nALL FILTERED-SHARE TESTS PASSED");
process.exit(fail?1:0);
