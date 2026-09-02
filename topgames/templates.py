"""The dashboard's single HTML page."""

PAGE = r"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Top Games — App Store Tracker</title>
<style>
:root{
  --bg:#f6f7f9; --panel:#fff; --ink:#14171f; --muted:#697086; --line:#e4e7ee;
  --accent:#3b5bfd; --up:#0f9d58; --down:#d93025; --new:#7b3fe4; --chip:#eef1f8;
}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){
  --bg:#0e1117; --panel:#161a23; --ink:#e8eaf0; --muted:#98a0b5; --line:#252b38;
  --accent:#7f93ff; --up:#4ad07f; --down:#ff7369; --new:#b18cff; --chip:#1f2532;
}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
  font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
header{position:sticky;top:0;z-index:9;background:var(--panel);
  border-bottom:1px solid var(--line);padding:14px 22px;
  display:flex;gap:16px;align-items:center;flex-wrap:wrap}
h1{font-size:17px;margin:0;letter-spacing:-.01em}
.sub{color:var(--muted);font-size:12.5px}
.grow{flex:1}
button{font:inherit;font-size:13px;padding:7px 13px;border-radius:8px;cursor:pointer;
  border:1px solid var(--line);background:var(--panel);color:var(--ink)}
button:hover{border-color:var(--accent)}
button.primary{background:var(--accent);border-color:var(--accent);color:#fff}
button:disabled{opacity:.5;cursor:not-allowed}
nav{display:flex;gap:4px;padding:14px 22px 0}
nav button{border:none;background:none;padding:8px 14px;border-radius:8px;color:var(--muted)}
nav button.on{background:var(--chip);color:var(--ink);font-weight:600}
main{padding:14px 22px 60px;max-width:1180px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:18px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:11px;padding:13px 15px}
.card .k{color:var(--muted);font-size:11.5px;text-transform:uppercase;letter-spacing:.05em}
.card .v{font-size:23px;font-weight:650;margin-top:3px;letter-spacing:-.02em}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:11px;overflow:hidden}
table{width:100%;border-collapse:collapse}
th{text-align:left;font-size:11.5px;text-transform:uppercase;letter-spacing:.05em;
  color:var(--muted);padding:10px 12px;border-bottom:1px solid var(--line);
  position:sticky;top:0;background:var(--panel)}
td{padding:9px 12px;border-bottom:1px solid var(--line);vertical-align:middle}
tr:last-child td{border-bottom:none}
tr:hover td{background:var(--chip)}
.rank{font-variant-numeric:tabular-nums;font-weight:650;width:44px;color:var(--muted)}
.ico{width:38px;height:38px;border-radius:9px;display:block;background:var(--chip)}
.nm{font-weight:600;text-decoration:none;color:var(--ink)}
.nm:hover{color:var(--accent)}
.by{color:var(--muted);font-size:12.5px}
.d{font-variant-numeric:tabular-nums;font-weight:600;font-size:13px}
.up{color:var(--up)} .down{color:var(--down)} .flat{color:var(--muted)}
.tag{display:inline-block;font-size:10.5px;font-weight:700;padding:2px 7px;border-radius:20px;
  text-transform:uppercase;letter-spacing:.04em;margin-left:6px}
.tag.new{background:var(--new);color:#fff}
.tag.fresh{background:var(--accent);color:#fff}
.num{font-variant-numeric:tabular-nums;text-align:right;white-space:nowrap}
input[type=search]{font:inherit;font-size:13px;padding:7px 11px;border-radius:8px;
  border:1px solid var(--line);background:var(--bg);color:var(--ink);min-width:210px}
.empty{padding:44px;text-align:center;color:var(--muted)}
.toast{position:fixed;bottom:20px;left:50%;transform:translateX(-50%);z-index:99;
  background:var(--ink);color:var(--bg);padding:11px 18px;border-radius:9px;
  font-size:13.5px;box-shadow:0 6px 22px rgba(0,0,0,.25);max-width:80vw}
.toast.err{background:var(--down);color:#fff}
.spin{display:inline-block;width:12px;height:12px;border:2px solid currentColor;
  border-right-color:transparent;border-radius:50%;animation:s .7s linear infinite;
  vertical-align:-1px;margin-right:6px}
@keyframes s{to{transform:rotate(360deg)}}
.cfg{padding:16px 18px;line-height:1.85}
.cfg code{background:var(--chip);padding:2px 6px;border-radius:5px;font-size:12.5px}
.ev{font-size:12px;font-weight:700;padding:2px 8px;border-radius:20px;background:var(--chip)}
.wrap{overflow-x:auto}
</style></head><body>

<header>
  <div><h1>Top Games</h1><div class="sub" id="sub">loading…</div></div>
  <div class="grow"></div>
  <input type="search" id="q" placeholder="Filter by name or studio…">
  <button id="refresh" class="primary">Refresh data</button>
  <button id="slacktest">Test Slack</button>
</header>

<nav>
  <button data-t="chart" class="on">Chart</button>
  <button data-t="new">New releases</button>
  <button data-t="events">Signals</button>
  <button data-t="slack">Slack</button>
</nav>

<main>
  <div class="cards" id="cards"></div>
  <div class="panel" id="view"><div class="empty">Loading…</div></div>
</main>

<script>
const $=s=>document.querySelector(s);
let TAB='chart', DATA={}, STATS={};

function toast(msg,err){
  const t=document.createElement('div');
  t.className='toast'+(err?' err':''); t.textContent=msg;
  document.body.appendChild(t); setTimeout(()=>t.remove(),err?6500:3200);
}
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const num=n=>(n||0).toLocaleString();
const stars=r=>r?r.toFixed(2)+'★':'—';

async function api(path,opts){
  const r=await fetch(path,opts);
  const j=await r.json().catch(()=>({error:'bad response'}));
  if(!r.ok) throw new Error(j.error||('HTTP '+r.status));
  return j;
}

function delta(d,isNew){
  if(isNew) return '<span class="d up">NEW</span>';
  if(d===null||d===undefined) return '<span class="d flat">—</span>';
  if(d>0) return '<span class="d up">▲ '+d+'</span>';
  if(d<0) return '<span class="d down">▼ '+Math.abs(d)+'</span>';
  return '<span class="d flat">–</span>';
}

function filtered(rows){
  const q=$('#q').value.trim().toLowerCase();
  if(!q) return rows;
  return rows.filter(r=>((r.name||'')+' '+(r.artist||'')).toLowerCase().includes(q));
}

function renderCards(){
  const s=STATS, c=DATA.chart||{};
  const newEntries=(c.rows||[]).filter(r=>r.is_new_entry).length;
  const fresh=(c.rows||[]).filter(r=>r.is_new_release).length;
  $('#cards').innerHTML=[
    ['Tracked apps',num(s.apps)],
    ['New in chart',newEntries+(c.has_previous?'':' —')],
    ['Recent releases charting',fresh],
    ['Snapshots',num(s.snapshots)],
    ['Signals logged',num(s.events)],
  ].map(([k,v])=>`<div class="card"><div class="k">${k}</div><div class="v">${v}</div></div>`).join('');
}

function renderChart(){
  const c=DATA.chart||{rows:[]};
  if(!c.rows.length) return `<div class="empty">No chart data yet.<br><br>
    Click <b>Refresh data</b> to pull the current top ${STATS.chart_size||100}.</div>`;
  const rows=filtered(c.rows);
  if(!c.has_previous)
    var note=`<div class="cfg" style="border-bottom:1px solid var(--line);color:var(--muted)">
      This is the baseline snapshot — movement and new-entry signals appear after the next refresh.</div>`;
  return (note||'')+`<div class="wrap"><table><thead><tr>
    <th>#</th><th></th><th>Game</th><th>Move</th>
    <th class="num">Rating</th><th class="num">Ratings</th>
    <th class="num">Released</th><th class="num">Price</th></tr></thead><tbody>`+
    rows.map(r=>`<tr>
      <td class="rank">${r.rank}</td>
      <td><img class="ico" loading="lazy" src="${esc(r.icon)}" alt=""></td>
      <td><a class="nm" href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.name)}</a>
        ${r.is_new_entry?'<span class="tag new">new</span>':''}
        ${r.is_new_release?'<span class="tag fresh">fresh</span>':''}
        <div class="by">${esc(r.artist)}</div></td>
      <td>${delta(r.delta,r.is_new_entry)}</td>
      <td class="num">${stars(r.rating)}</td>
      <td class="num">${num(r.ratings)}</td>
      <td class="num by">${esc(r.release_date)}</td>
      <td class="num by">${esc(r.price||'—')}</td>
    </tr>`).join('')+'</tbody></table></div>';
}

function renderNew(){
  const rows=filtered((DATA.new||{}).rows||[]);
  if(!rows.length) return `<div class="empty">No recent releases stored yet. Hit <b>Refresh data</b>.</div>`;
  return `<div class="wrap"><table><thead><tr><th></th><th>Game</th>
    <th class="num">Released</th><th class="num">Rating</th>
    <th class="num">Ratings</th><th class="num">Price</th></tr></thead><tbody>`+
    rows.map(r=>`<tr>
      <td><img class="ico" loading="lazy" src="${esc(r.icon)}" alt=""></td>
      <td><a class="nm" href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.name)}</a>
        <div class="by">${esc(r.artist)}</div></td>
      <td class="num">${esc((r.release_date||'').slice(0,10))}</td>
      <td class="num">${stars(r.avg_rating)}</td>
      <td class="num">${num(r.rating_count)}</td>
      <td class="num by">${esc(r.formatted_price||'—')}</td>
    </tr>`).join('')+'</tbody></table></div>';
}

function renderEvents(){
  const rows=filtered((DATA.events||{}).rows||[]);
  if(!rows.length) return `<div class="empty">No signals yet. Signals appear once you have
    two or more snapshots to compare.</div>`;
  const label={new_entry:'new in chart',debut:'new release charted',exit:'dropped out',
    climb:'climbing',fall:'falling',new_release:'new release'};
  return `<div class="wrap"><table><thead><tr><th>When</th><th>Signal</th>
    <th>Game</th><th>Detail</th></tr></thead><tbody>`+
    rows.map(r=>`<tr>
      <td class="by">${esc((r.created_at||'').slice(0,16).replace('T',' '))}</td>
      <td><span class="ev">${esc(label[r.kind]||r.kind)}</span></td>
      <td><a class="nm" href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.name||r.app_id)}</a>
        <div class="by">${esc(r.artist||'')}</div></td>
      <td class="by">${esc(r.detail)}</td>
    </tr>`).join('')+'</tbody></table></div>';
}

function renderSlack(){
  const s=STATS, d=s.daily||{}, w=s.weekly||{};
  return `<div class="cfg">
  <b>Connection</b><br>
  Webhook: ${s.slack_configured
    ? '<span style="color:var(--up)">configured ✓</span>'
    : '<span style="color:var(--down)">not set</span> — add <code>slack.webhook_url</code> to <code>config.json</code>'}
  <br><br>
  <b>Daily digest</b> — ${d.enabled?'<span style="color:var(--up)">on</span>':'off'} · every day at <code>${esc(d.time)}</code><br>
  includes: ${(d.include||[]).map(k=>'<code>'+esc(k)+'</code>').join(' ')}<br><br>
  <b>Weekly digest</b> — ${w.enabled?'<span style="color:var(--up)">on</span>':'off'} · every <code>${esc(w.day)}</code> at <code>${esc(w.time)}</code><br>
  includes: ${(w.include||[]).map(k=>'<code>'+esc(k)+'</code>').join(' ')}<br><br>
  <button onclick="digest('daily',true)">Preview daily</button>
  <button onclick="digest('weekly',true)">Preview weekly</button>
  <button onclick="digest('daily',false)" class="primary">Send daily now</button>
  <button onclick="digest('weekly',false)" class="primary">Send weekly now</button>
  <pre id="preview" style="margin-top:16px;background:var(--chip);padding:13px;
    border-radius:9px;overflow:auto;max-height:420px;font-size:12px"></pre></div>`;
}

async function digest(period,dry){
  try{
    const j=await api(`/api/digest?period=${period}&dry=${dry?1:0}`,{method:'POST'});
    if(dry){ $('#preview').textContent=JSON.stringify(j.payload,null,2); toast('Preview built — not sent.'); }
    else toast(`Sent ${period} digest (${j.events} signals).`);
  }catch(e){ toast(e.message,true); }
}

function render(){
  renderCards();
  $('#view').innerHTML={chart:renderChart,new:renderNew,events:renderEvents,slack:renderSlack}[TAB]();
}

async function loadAll(){
  const [stats,chart,nw,ev]=await Promise.all([
    api('/api/stats'),api('/api/chart'),api('/api/new-releases'),api('/api/events?days=14')]);
  STATS=stats; DATA={chart,new:nw,events:ev};
  $('#sub').textContent=`${stats.genre} · ${stats.chart} · ${stats.country} · top ${stats.chart_size}`
    +` · last refresh ${stats.last_refresh==='never'?'never':stats.last_refresh.slice(0,16).replace('T',' ')}`;
  render();
}

$('#q').addEventListener('input',render);
document.querySelectorAll('nav button').forEach(b=>b.onclick=()=>{
  document.querySelectorAll('nav button').forEach(x=>x.classList.remove('on'));
  b.classList.add('on'); TAB=b.dataset.t; render();
});
$('#refresh').onclick=async()=>{
  const b=$('#refresh'); b.disabled=true; b.innerHTML='<span class="spin"></span>Refreshing…';
  try{
    const r=await api('/api/refresh',{method:'POST'});
    await loadAll();
    toast(r.baseline?'Baseline stored. Refresh again to see movement.'
      :`Done — ${r.new_entries} new in chart, ${r.new_releases} new releases, ${r.movers} movers.`);
  }catch(e){ toast(e.message,true); }
  finally{ b.disabled=false; b.textContent='Refresh data'; }
};
$('#slacktest').onclick=async()=>{
  try{ await api('/api/slack-test',{method:'POST'}); toast('Test message sent to Slack ✓'); }
  catch(e){ toast(e.message,true); }
};
loadAll().catch(e=>toast(e.message,true));
</script></body></html>
"""


import re as _re
# The static site reuses exactly this stylesheet so both surfaces look the same.
CSS = _re.search(r"<style>(.*?)</style>", PAGE, _re.S).group(1)
