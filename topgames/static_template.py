"""The dashboard's markup, styling and behaviour.

A market-terminal reading of the brief: dense tabular data, monospaced figures,
movement carried entirely by colour and a rank sparkline.
"""

STYLE = r"""
:root{
  --bg:#0a0c10; --surface:#0f131a; --row:#11161e; --row-hover:#151b25;
  --line:#1c222c; --line-soft:#161b24;
  --ink:#e6ebf2; --dim:#8b95a5; --faint:#5c6675;
  --up:#35d489; --down:#ff5f5f; --flat:#5c6675;
  --signal:#ffd23f; --mint:#3ddc84;
  --radius:8px;
  --mono:ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,monospace;
  --sans:-apple-system,BlinkMacSystemFont,"Segoe UI",Inter,Roboto,sans-serif;
}
*{box-sizing:border-box}
html,body{margin:0;padding:0}
body{background:var(--bg);color:var(--ink);font-family:var(--sans);
  font-size:14px;line-height:1.45;-webkit-font-smoothing:antialiased}
a{color:inherit;text-decoration:none}
:focus-visible{outline:2px solid var(--mint);outline-offset:2px;border-radius:4px}
@media (prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important}}

/* ---------- top bar ---------- */
.topbar{display:flex;align-items:center;gap:26px;padding:13px 22px;
  background:var(--surface);border-bottom:1px solid var(--line);
  position:sticky;top:0;z-index:20;flex-wrap:wrap}
.brand{font-weight:800;font-size:17px;letter-spacing:.02em;white-space:nowrap}
.brand i{color:var(--mint);font-style:normal}
.brand span{font-family:var(--mono);font-size:11px;font-weight:500;color:var(--faint);
  letter-spacing:.06em;margin-left:9px}
.tabs{display:flex;gap:3px;flex-wrap:wrap}
.tabs button{font:inherit;font-size:11.5px;font-weight:700;letter-spacing:.09em;
  text-transform:uppercase;color:var(--dim);background:none;border:none;
  padding:8px 15px;border-radius:20px;cursor:pointer;transition:color .12s,background .12s}
.tabs button:hover{color:var(--ink)}
.tabs button.on{background:var(--mint);color:#06210f}
.spacer{flex:1}
.dspick{font:inherit;font-size:12px;background:var(--bg);color:var(--ink);
  border:1px solid var(--line);border-radius:7px;padding:7px 10px;cursor:pointer;
  max-width:190px}
.dspick:hover{border-color:var(--faint)}
.sync{font-family:var(--mono);font-size:11.5px;color:var(--faint);
  letter-spacing:.03em;display:flex;align-items:center;gap:7px;white-space:nowrap}
.dot{width:7px;height:7px;border-radius:50%;background:var(--up);
  box-shadow:0 0 0 3px rgba(53,212,137,.16)}
.btn{font:inherit;font-size:11.5px;font-weight:700;letter-spacing:.08em;
  text-transform:uppercase;padding:9px 15px;border-radius:var(--radius);cursor:pointer;
  border:1px solid var(--line);background:transparent;color:var(--dim);
  transition:border-color .12s,color .12s}
.btn:hover{border-color:var(--faint);color:var(--ink)}
.btn.solid{background:#e6ebf2;border-color:#e6ebf2;color:#0a0c10}
.btn.solid:hover{background:#fff;border-color:#fff;color:#0a0c10}

/* ---------- movers ticker ---------- */
.ticker{display:flex;align-items:stretch;border-bottom:1px solid var(--line);
  background:var(--bg);overflow:hidden}
.ticker-tag{background:var(--signal);color:#241c00;font-size:11px;font-weight:800;
  letter-spacing:.11em;text-transform:uppercase;padding:12px 18px;white-space:nowrap;
  display:flex;align-items:center}
.ticker-rail{display:flex;overflow-x:auto;scrollbar-width:none}
.ticker-rail::-webkit-scrollbar{display:none}
.tick{display:flex;align-items:center;gap:9px;padding:12px 20px;white-space:nowrap;
  border-right:1px solid var(--line-soft);font-size:13px}
.tick b{font-weight:600}
.tick em{font-family:var(--mono);font-style:normal;font-size:12px;font-weight:700}
.tick .up{color:var(--up)} .tick .down{color:var(--down)} .tick .flat{color:var(--flat)}

/* ---------- hero ---------- */
main{padding:0 22px 70px}
.hero{display:flex;gap:40px;align-items:flex-end;justify-content:space-between;
  padding:34px 0 26px;flex-wrap:wrap}
h1{margin:0;font-size:clamp(28px,4.4vw,44px);font-weight:700;letter-spacing:-.028em;
  line-height:1.06}
h1 .thin{color:var(--dim);font-weight:400}
.lede{margin:11px 0 0;color:var(--dim);font-size:13.5px;max-width:62ch}
.figures{display:flex;gap:0;flex-shrink:0}
.fig{padding:0 26px;border-left:1px solid var(--line);text-align:right}
.fig:first-child{border-left:none}
.fig .n{font-family:var(--mono);font-size:31px;font-weight:600;letter-spacing:-.02em;
  line-height:1.1}
.fig .l{font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:var(--faint);
  margin-top:5px}
.fig.up .n{color:var(--up)} .fig.down .n{color:var(--down)}

/* ---------- controls ---------- */
.controls{display:flex;gap:9px;align-items:center;flex-wrap:wrap;margin-bottom:16px}
.ctl{display:flex;align-items:center;gap:8px;border:1px solid var(--line);
  border-radius:var(--radius);padding:8px 13px;background:var(--surface);font-size:12.5px;
  flex:0 0 auto}
.ctl label{color:var(--faint);font-size:11px;letter-spacing:.06em;text-transform:uppercase}
.ctl select{font:inherit;font-size:12.5px;background:none;border:none;color:var(--ink);
  cursor:pointer;padding-right:2px;max-width:150px;text-overflow:ellipsis}
.ctl select option{background:var(--surface);color:var(--ink)}
.ctl.active{border-color:var(--mint)}
.ctl.active select,.ctl.active label{color:var(--mint)}
.seg{display:flex;border:1px solid var(--line);border-radius:var(--radius);overflow:hidden}
.seg button{font:inherit;font-size:11px;font-weight:700;letter-spacing:.09em;
  text-transform:uppercase;padding:9px 15px;background:none;border:none;color:var(--faint);
  cursor:pointer}
.seg button.on{background:var(--row-hover);color:var(--ink)}
.search{flex:1 1 200px;min-width:170px}
.search input{width:100%;font:inherit;font-size:12.5px;padding:9px 13px;
  border:1px solid var(--line);border-radius:var(--radius);background:var(--surface);
  color:var(--ink)}
.search input::placeholder{color:var(--faint)}

/* ---------- table ---------- */
.panel{border:1px solid var(--line);border-radius:11px;overflow:hidden;background:var(--surface)}
.scroll{overflow-x:auto}
table{width:100%;border-collapse:collapse;min-width:960px}
thead th{text-align:left;font-size:10px;font-weight:700;letter-spacing:.12em;
  text-transform:uppercase;color:var(--faint);padding:13px 14px;
  border-bottom:1px solid var(--line);white-space:nowrap;user-select:none}
thead th.sortable{cursor:pointer}
thead th.sortable:hover{color:var(--ink)}
thead th .ar{opacity:.35;margin-left:5px;font-size:9px}
thead th.sorted{color:var(--mint)}
thead th.sorted .ar{opacity:1}
tbody td{padding:13px 14px;border-bottom:1px solid var(--line-soft);vertical-align:middle}
tbody tr:last-child td{border-bottom:none}
tbody tr{background:var(--row);transition:background .1s}
tbody tr:hover{background:var(--row-hover)}
.c-rank{font-family:var(--mono);font-size:14px;font-weight:600;color:var(--dim);width:52px}
.c-d{width:74px}
.d{font-family:var(--mono);font-size:12.5px;font-weight:700;white-space:nowrap}
.d.up{color:var(--up)} .d.down{color:var(--down)} .d.flat{color:var(--flat)}
.game{display:flex;align-items:center;gap:13px;min-width:230px}
.ico{width:40px;height:40px;border-radius:10px;flex-shrink:0;background:var(--row-hover);
  object-fit:cover}
.g-name{font-weight:600;font-size:14px;letter-spacing:-.005em}
.g-sub{font-family:var(--mono);font-size:11px;color:var(--faint);margin-top:2px}
.tag{display:inline-block;font-family:var(--mono);font-size:9.5px;font-weight:700;
  letter-spacing:.06em;padding:2px 6px;border-radius:4px;margin-left:7px;
  text-transform:uppercase;vertical-align:1px}
.tag.new{background:rgba(61,220,132,.14);color:var(--mint)}
.tag.fresh{background:rgba(255,210,63,.14);color:var(--signal)}
.tag.count{background:var(--row-hover);color:var(--dim);border:1px solid var(--line)}
.tag.top100{background:rgba(61,220,132,.16);color:var(--mint);
  border:1px solid rgba(61,220,132,.32)}
.co{font-size:13px;white-space:nowrap}
.rating{font-family:var(--mono);font-size:13.5px;font-weight:600;white-space:nowrap}
.rating .star{color:var(--signal);margin-right:4px}
.bar{height:3px;border-radius:2px;background:var(--line);margin-top:6px;width:112px;
  overflow:hidden}
.bar i{display:block;height:100%;background:var(--up);border-radius:2px}
.num{font-family:var(--mono);font-size:13px;text-align:right;white-space:nowrap}
.num.dim{color:var(--dim)}
.mono-dim{font-family:var(--mono);font-size:12.5px;color:var(--dim)}
.spark{display:flex;align-items:center;gap:7px;height:26px}
.spark svg{width:60px;height:24px;overflow:visible;flex-shrink:0}
.spark .lbl{font-family:var(--mono);font-size:11px;font-weight:700;white-space:nowrap}
.spark .lbl.up{color:var(--up)} .spark .lbl.down{color:var(--down)}
.spark .lbl.flat{color:var(--faint)}
.spark.none{color:var(--faint);font-family:var(--mono);font-size:11px}
.price{font-family:var(--mono);font-size:11px;color:var(--dim);border:1px solid var(--line);
  padding:3px 9px;border-radius:5px;white-space:nowrap}
a.g-name:hover,a.co-link:hover{color:var(--mint)}
.co-link{cursor:pointer}
/* Google Play is a search, not a resolved page, so it reads as a quiet
   affordance beside the title rather than a second primary link. */
.play{display:inline-flex;align-items:center;justify-content:center;
  width:16px;height:16px;margin-left:6px;border-radius:4px;vertical-align:-3px;
  color:var(--dim);border:1px solid var(--line);background:var(--row-hover)}
.play:hover{color:var(--mint);border-color:var(--mint)}
.play svg{fill:currentColor;display:block}
/* Publisher table: pin the figure columns so they cluster right instead of
   drifting apart across a wide screen. */
.pub th:nth-child(1),.pub td:nth-child(1){width:56px}
.pub th:nth-child(3),.pub td:nth-child(3){width:80px}
.pub th:nth-child(4),.pub td:nth-child(4){width:104px}
.pub th:nth-child(5),.pub td:nth-child(5){width:112px}
.pub th:nth-child(6),.pub td:nth-child(6){width:132px}
.pub th:nth-child(7),.pub td:nth-child(7){width:116px}
.pub tbody tr{cursor:pointer}
.sync-btn{background:none;border:1px solid var(--line);color:var(--dim);border-radius:6px;
  width:26px;height:26px;display:inline-flex;align-items:center;justify-content:center;
  cursor:pointer;font-size:13px;padding:0;margin-left:8px;line-height:1}
.sync-btn:hover{color:var(--ink);border-color:var(--faint)}
.copybar{display:flex;gap:9px;align-items:center;flex-wrap:wrap;margin-bottom:14px}
.toast{position:fixed;bottom:22px;left:50%;transform:translateX(-50%);z-index:60;
  background:var(--ink);color:var(--bg);padding:11px 18px;border-radius:8px;
  font-size:13px;font-weight:600;box-shadow:0 8px 26px rgba(0,0,0,.45)}
.pre{font-family:var(--mono);font-size:12px;color:var(--dim);background:var(--bg);
  border:1px solid var(--line);border-radius:8px;padding:13px 15px;white-space:pre-wrap;
  margin-top:12px;max-height:260px;overflow:auto}

/* ---------- grid view ---------- */
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(232px,1fr));gap:12px}
.card{border:1px solid var(--line);border-radius:11px;background:var(--surface);
  padding:15px;transition:border-color .12s}
.card:hover{border-color:var(--faint)}
.card-top{display:flex;gap:12px;align-items:flex-start;margin-bottom:13px;min-height:52px}
.card .g-name{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;
  overflow:hidden;line-height:1.3}
.card .rk{font-family:var(--mono);font-size:12px;color:var(--faint);font-weight:600}
.card-row{display:flex;justify-content:space-between;font-size:12px;padding:4px 0;
  color:var(--dim)}
.card-row b{font-family:var(--mono);color:var(--ink);font-weight:600}

/* ---------- timeline view ---------- */
.tl-row{display:flex;align-items:center;gap:15px;padding:11px 15px;
  border-bottom:1px solid var(--line-soft)}
.tl-row:last-child{border-bottom:none}
.tl-name{width:210px;flex-shrink:0;font-size:13px;font-weight:600;overflow:hidden;
  text-overflow:ellipsis;white-space:nowrap}
.tl-track{flex:1;height:30px;position:relative;min-width:150px}
.tl-track svg{width:100%;height:100%;overflow:visible}
.tl-end{font-family:var(--mono);font-size:12px;color:var(--dim);width:82px;text-align:right}

/* ---------- footer ---------- */
.tfoot{display:flex;justify-content:space-between;align-items:center;gap:16px;
  padding:15px 4px;font-size:12px;color:var(--faint);flex-wrap:wrap}
.rows{display:inline-flex;gap:2px;align-items:center;margin-left:4px}
.rows button{font:inherit;font-family:var(--mono);font-size:11.5px;padding:3px 8px;
  border:1px solid transparent;border-radius:5px;background:none;color:var(--dim);
  cursor:pointer}
.rows button:hover{color:var(--ink);border-color:var(--line)}
.rows button.on{background:var(--row-hover);color:var(--ink);border-color:var(--line)}
.pager{display:flex;gap:5px;align-items:center}
.pager button{font:inherit;font-family:var(--mono);font-size:12px;padding:5px 10px;
  border:1px solid transparent;border-radius:6px;background:none;color:var(--dim);
  cursor:pointer}
.pager button:hover:not(:disabled){border-color:var(--line);color:var(--ink)}
.pager button.on{background:var(--row-hover);color:var(--ink);border-color:var(--line)}
.pager button:disabled{opacity:.3;cursor:not-allowed}
.empty{padding:64px 20px;text-align:center;color:var(--faint)}
.note{border:1px solid var(--line);border-left:2px solid var(--signal);border-radius:8px;
  padding:13px 16px;margin-bottom:16px;color:var(--dim);font-size:12.5px;
  background:var(--surface)}
.note b{color:var(--ink);font-weight:600}
@media(max-width:760px){
  .figures{width:100%;justify-content:space-between}
  .fig{padding:0 12px}.fig .n{font-size:23px}
  .hero{padding-top:24px}
}
"""

BODY = r"""
<header class="topbar">
  <div class="brand">TOP<i>/</i>GAMES <span>__SCOPE__</span></div>
  <nav class="tabs" id="tabs">
    <button data-tab="top" class="on">Top 100</button>
    <button data-tab="new">New releases</button>
    <button data-tab="movers">Movers</button>
    <button data-tab="publishers">Publishers</button>
    <button data-tab="digest">Slack digest</button>
  </nav>
  <div class="spacer"></div>
  <div class="sync"><span class="dot"></span> synced <span id="synced">__SYNC__</span> · itunes rss
    <a class="sync-btn" id="sync" href="__ACTIONS__" target="_blank" rel="noopener"
       title="Run the refresh job now on GitHub">&#8635;</a></div>
  <button class="btn" id="csv">Export CSV</button>
  <a class="btn solid" href="__ACTIONS__" target="_blank" rel="noopener">Send digest</a>
</header>

<div class="ticker" id="ticker"></div>

<main>
  <section class="hero">
    <div>
      <h1 id="title"></h1>
      <p class="lede" id="lede"></p>
    </div>
    <div class="figures" id="figures"></div>
  </section>
  <div id="controls"></div>
  <div id="view"></div>
  <div class="tfoot" id="tfoot"></div>
</main>
"""

SCRIPT = r"""
let D = __DATA__;

/* Resolved once at load: switching datasets rewrites the address bar, which
   would otherwise re-base every later relative fetch onto the new path. */
const SITE_ROOT = new URL(D.root || './', location.href).href;
const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"]/g,
  c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const num = n => (n || 0).toLocaleString('en-US');
const PAGE_SIZES = [10, 50, 100];

const S = { tab:'top', view:'table', sort:'rank', dir:1, page:1, perPage:10,
            q:'', publisher:'all', minRating:0, released:'any', relGenre:null, relCountry:null, relAge:null, relPage:1 };

/* The delta column can only describe the span the database actually covers. */
/* Chart-only datasets carry no rank history, so every movement affordance is
   suppressed rather than rendered as a column of dashes. Read through a call,
   not a const: the active dataset changes without a page load. */
function spanLabelNow(){
  return D.span_days >= 7 ? 'Δ 7D'
       : D.span_days >= 1 ? `Δ ${D.span_days}D`
       : 'Δ TODAY';
}

function playLink(r){
  // Resolves directly when the publisher reused the reverse-domain string;
  // pools published before bundle ids were stored fall back to a title search.
  const q = r.play_url ||
    (r.name ? 'https://play.google.com/store/search?c=apps&q=' +
              encodeURIComponent(r.name) : '');
  if (!q) return '';
  return `<a class="play" href="${esc(q)}" target="_blank" rel="noopener"
     title="Search Google Play for ${esc(r.name)}" aria-label="Search Google Play">
     <svg viewBox="0 0 24 24" width="11" height="11" aria-hidden="true"><path
       d="M3 2.2v19.6c0 .6.7 1 1.2.6l14.3-9.8c.4-.3.4-1 0-1.3L4.2 1.6C3.7 1.2 3 1.6 3 2.2z"
     /></svg></a>`;
}

function companyLink(r){
  return r.artist_url
    ? `<a class="co-link" href="${esc(r.artist_url)}" target="_blank"
         rel="noopener">${esc(r.artist)}</a>`
    : esc(r.artist);
}

/* Slack has no way in from a static page, so the page composes the message and
   hands it to the clipboard. Embedding the webhook here would let any visitor
   post into the channel. */
function slackText(kind, rows){
  const scope = `${D.genre} · ${D.country}`;
  if (kind === 'movers'){
    const up = rows.filter(r => r.delta > 0), down = rows.filter(r => r.delta < 0);
    const line = r => `${r.delta > 0 ? '▲' : '▼'} *${r.name}* ${
      r.delta > 0 ? 'up' : 'down'} ${Math.abs(r.delta)} — now #${r.rank}`;
    return [`*Movers — ${scope}*`,
            `${up.length} up · ${down.length} down over ${
              D.span_days >= 1 ? D.span_days + ' day(s)' : 'today'}`,
            '', ...up.map(line), ...down.map(line)].join('\n');
  }
  if (kind === 'new'){
    const charted = rows.filter(r => r.rank).length;
    return [`*New releases — ${scope}*`,
            `${rows.length} in the last ${D.new_days} days · ${charted} in the top 100`,
            '',
            ...rows.map(r => `• *${r.name}* — ${r.artist} · ${
              r.rating ? r.rating.toFixed(2) + '★' : 'no ratings yet'} · ${r.released}${
              r.rank ? `  \`TOP 100 #${r.rank}\`` : ''}`)].join('\n');
  }
  return [`*Top ${rows.length} — ${scope}*`, '',
          ...rows.map(r => `#${String(r.rank).padStart(2,'0')} *${r.name}* — ${
            r.artist} · ${r.rating.toFixed(2)}★`)].join('\n');
}

function toast(msg){
  const t = document.createElement('div');
  t.className = 'toast'; t.textContent = msg;
  document.body.appendChild(t); setTimeout(() => t.remove(), 2600);
}

/* Posting to Slack goes through the Worker, which holds the webhook. The page
   sends only a message kind -- never text -- so the endpoint cannot be used to
   push arbitrary content into the channel. */
async function shareToSlack(kind, btn){
  if (!D.worker_url){
    toast('Share needs the Worker deployed — see DEPLOY.md');
    return;
  }
  const label = btn.textContent;
  btn.disabled = true; btn.textContent = 'Sending…';
  try {
    const payload = {kind};
    if (kind === 'new') {
      // Post what is on screen, not a prebuilt list: the Worker rebuilds the
      // message from these three values against the published pool.
      payload.filters = {store: S.relCountry, genre: S.relGenre || 'all',
                      age: S.relAge || String(D.new_days)};
    }
    const res = await fetch(D.worker_url.replace(/\/$/, '') + '/share', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify(payload),
    });
    const reply = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(reply.error || `HTTP ${res.status}`);
    toast(reply.message || 'Sent to Slack');
  } catch (err) {
    toast(`Could not send: ${err.message}`);
  } finally {
    btn.disabled = false; btn.textContent = label;
  }
}

async function copyText(text, label){
  try { await navigator.clipboard.writeText(text); toast(label); }
  catch { 
    const ta = document.createElement('textarea');
    ta.value = text; document.body.appendChild(ta); ta.select();
    document.execCommand('copy'); ta.remove(); toast(label);
  }
}

function deltaCell(d, isNew){
  if (isNew) return '<span class="d up">NEW</span>';
  if (d === null || d === undefined) return '<span class="d flat">–</span>';
  if (d > 0) return `<span class="d up">▲ ${d}</span>`;
  if (d < 0) return `<span class="d down">▼ ${Math.abs(d)}</span>`;
  return '<span class="d flat">— 0</span>';
}

/* Rank over time.
   Rank 1 is the best rank, so the y axis is inverted: climbing draws upward,
   which is the direction people expect. Each step is coloured by its own
   direction rather than the net change, so a game that slid and recovered
   still reads as movement instead of a flat grey line. A minimum vertical span
   keeps a one-place wobble from filling the whole box. */
const SPARK_MIN_SPAN = 4;

function spark(raw){
  if (!raw || raw.length < 2)
    return '<div class="spark none">no history yet</div>';

  /* Collapse runs of an unchanged rank. Snapshots are taken far more often than
     the chart actually moves, so plotting them one-per-x-step buries a real
     jump inside a long flat run. One x-step per distinct position gives every
     move equal width; the tooltip keeps the true snapshot count. */
  const history = raw.filter((r, i) => i === 0 || r !== raw[i - 1]);
  if (history.length < 2)
    return `<div class="spark none" title="held #${raw[0]} across `
         + `${raw.length} snapshots">held #${raw[0]}</div>`;

  const W = 60, H = 24, pad = 3;
  const lo = Math.min(...history), hi = Math.max(...history);
  const mid = (lo + hi) / 2;
  const span = Math.max(hi - lo, SPARK_MIN_SPAN);
  const top = mid - span / 2, bottom = mid + span / 2;

  const x = i => pad + i * (W - 2 * pad) / (history.length - 1);
  const y = r => pad + ((r - top) / (bottom - top)) * (H - 2 * pad);

  const UP = 'var(--up)', DOWN = 'var(--down)', FLAT = 'var(--flat)';
  const segs = [];
  for (let i = 1; i < history.length; i++){
    const step = history[i - 1] - history[i];        // + means it climbed
    const colour = step > 0 ? UP : step < 0 ? DOWN : FLAT;
    segs.push(`<line x1="${x(i-1).toFixed(1)}" y1="${y(history[i-1]).toFixed(1)}"
      x2="${x(i).toFixed(1)}" y2="${y(history[i]).toFixed(1)}" stroke="${colour}"
      stroke-width="1.75" stroke-linecap="round" vector-effect="non-scaling-stroke"/>`);
  }
  // A vertex dot at each snapshot, so direction changes are countable.
  const dots = history.map((r, i) =>
    `<circle cx="${x(i).toFixed(1)}" cy="${y(r).toFixed(1)}" r="1.3"
       fill="var(--bg)" stroke="${FLAT}" stroke-width="1"
       vector-effect="non-scaling-stroke"/>`).join('');

  const net = history[0] - history[history.length - 1];
  const cls = net > 0 ? 'up' : net < 0 ? 'down' : 'flat';
  const endColour = net > 0 ? UP : net < 0 ? DOWN : FLAT;
  const lastX = x(history.length - 1), lastY = y(history[history.length - 1]);

  // Total distance travelled, which a net figure of zero would hide entirely.
  let swing = 0;
  for (let i = 1; i < history.length; i++) swing += Math.abs(history[i] - history[i-1]);
  const label = net > 0 ? `+${net}` : net < 0 ? `${net}` : (swing ? '±' : '0');
  const moves = history.length - 1;
  const title = `#${history[0]} → #${history[history.length - 1]} · `
    + `${moves} move${moves === 1 ? '' : 's'} across ${raw.length} snapshots`
    + (swing > Math.abs(net) ? ` · ${swing} places moved in total` : '');

  return `<div class="spark" title="${esc(title)}">
    <svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" aria-label="${esc(title)}">
      <line x1="0" y1="${(H/2).toFixed(1)}" x2="${W}" y2="${(H/2).toFixed(1)}"
        stroke="var(--line)" stroke-width="1" vector-effect="non-scaling-stroke"/>
      ${segs.join('')}${dots}
      <circle cx="${lastX.toFixed(1)}" cy="${lastY.toFixed(1)}" r="2.2" fill="${endColour}"/>
    </svg>
    <span class="lbl ${cls}">${label}</span>
  </div>`;
}

function filtered(){
  let rows = D.items.slice();
  if (S.q){
    const q = S.q.toLowerCase();
    rows = rows.filter(r => (r.name + ' ' + r.artist).toLowerCase().includes(q));
  }
  if (S.publisher !== 'all') rows = rows.filter(r => r.artist === S.publisher);
  if (S.minRating) rows = rows.filter(r => r.rating >= S.minRating);
  if (S.released !== 'any'){
    const days = Number(S.released);
    const cutoff = Date.now() - days*864e5;
    rows = rows.filter(r => r.released && new Date(r.released).getTime() >= cutoff);
  }
  const key = S.sort;
  rows.sort((a,b) => {
    let x = a[key], y = b[key];
    if (key === 'delta'){ x = a.delta ?? -999; y = b.delta ?? -999; }
    if (typeof x === 'string') return x.localeCompare(y) * S.dir;
    return ((x ?? 0) - (y ?? 0)) * S.dir;
  });
  return rows;
}

function renderTicker(){
  const moving = D.movers.length > 0;
  const items = moving ? D.movers : D.items.slice(0, 12);
  $('#ticker').innerHTML =
    `<div class="ticker-tag">${moving ? "Today's movers" : 'Leading now'}</div>
     <div class="ticker-rail">` +
    items.map(m => {
      const d = m.delta;
      // Before any movement exists, showing "— 0" twelve times says nothing;
      // the current rank is the useful figure instead.
      if (!moving)
        return `<a class="tick" href="${esc(m.url)}" target="_blank" rel="noopener">
          <em class="flat">#${String(m.rank).padStart(2,'0')}</em><b>${esc(m.name)}</b></a>`;
      const cls = d > 0 ? 'up' : d < 0 ? 'down' : 'flat';
      const gl = d > 0 ? '▲' : d < 0 ? '▼' : '—';
      return `<a class="tick" href="${esc(m.url)}" target="_blank" rel="noopener">
        <b>${esc(m.name)}</b><em class="${cls}">${gl} ${Math.abs(d || 0)}</em></a>`;
    }).join('') + '</div>';
}

function renderHero(){
  const t = { top:['Top 100 free', D.stats.tracked + ' titles · ' + D.stats.publishers + ' publishers'],
              new:['New releases', S.relAge === 'all'
                     ? ((RELEASES[S.relCountry] || []).length + ' games tracked in this store')
                     : ('Released in the last ' + (S.relAge || D.new_days) + ' days')],
              movers:['Biggest movers', 'Ranked by size of rank change'],
              publishers:['Publishers', 'Grouped by company across the chart'],
              digest:['Slack digest', 'What lands in your channel'] }[S.tab];
  // The releases tab has its own store selector, so the heading follows that
  // rather than the chart's country, which is a different thing entirely.
  const showing = S.tab === 'new' && S.relCountry
    ? countryLabel(S.relCountry) : D.country_name;
  $('#title').innerHTML =
    `${esc(D.genre)}, ${esc(showing)} <span class="thin">— ${t[0]}</span>`;
  $('#lede').textContent = S.tab === 'new'
    ? `Discovered by sweeping the Search API. ${t[1]}.`
    : `Ranked from the iTunes RSS chart, enriched with the Lookup API. ${t[1]}.`;
  const f = D.stats;
  $('#figures').innerHTML = [
    ['', f.tracked, 'Tracked'],
    ['up', f.climbing, 'Climbing'],
    ['down', f.falling, 'Falling'],
    ['', f.median_rating.toFixed(2), 'Median rating'],
  ].map(([c,n,l]) =>
    `<div class="fig ${c}"><div class="n">${n}</div><div class="l">${l}</div></div>`).join('');
}


/* Country and genre behave like the other filters: they change what is shown
   without leaving the page. Each dataset is a separate published file, so the
   change is a fetch and re-render rather than a client-side predicate. */
/** "role_playing" -> "Role Playing" */
function titleCase(v){
  return String(v).replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

/** "jp" -> "Japan", falling back to the uppercased code. */
function countryLabel(code){
  const named = (D.datasets || []).find(d => d.country === code);
  return (named && named.country_name) || String(code).toUpperCase();
}

function datasetMap(){
  const m = new Map();
  for (const d of (D.datasets || [])){
    if (!m.has(d.country)) m.set(d.country, []);
    m.get(d.country).push(d);
  }
  return m;
}

function datasetControls(){
  const list = D.datasets || [];
  if (list.length < 2) return '';
  const m = datasetMap();
  const here = list.find(d => d.slug === D.slug) || list[0];
  const countries = [...m.keys()].sort();
  // Only genres actually published for the selected country, so the control
  // can never offer a combination that does not exist.
  const genres = (m.get(here.country) || []).map(d => d.genre).sort();
  return `
    <div class="ctl ${countries.length > 1 ? '' : ''}" ${loadingAttr()}><label>Country</label>
      <select id="f-country">${countries.map(c =>
        `<option value="${esc(c)}" ${c === here.country ? 'selected' : ''}
          >${esc(c.toUpperCase())}</option>`).join('')}</select></div>
    <div class="ctl" ${loadingAttr()}><label>Genre</label>
      <select id="f-genre">${genres.map(g =>
        `<option value="${esc(g)}" ${g === here.genre ? 'selected' : ''}
          >${esc(titleCase(g))}</option>`).join('')}</select></div>`;
}

function loadingAttr(){ return SWITCHING ? 'data-loading="1"' : ''; }

let SWITCHING = false;

async function switchDataset(country, genre){
  const list = D.datasets || [];
  let target = list.find(d => d.country === country && d.genre === genre);
  // Changing country can strand the current genre; fall back to that country's
  // first published chart rather than failing.
  if (!target) target = list.find(d => d.country === country);
  if (!target || target.slug === D.slug) return;

  SWITCHING = true; renderControls();
  try {
    const res = await fetch(new URL(`${target.path}/data/chart.json`, SITE_ROOT),
                            {cache: 'no-cache'});
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const next = await res.json();
    // The fetched file carries the other page's relative depth; keep ours.
    next.root = D.root;
    next.datasets = D.datasets;
    D = next;
    S.page = 1; S.publisher = 'all'; S.q = ''; S.relGenre = null; S.relCountry = null; CHART_INDEX = null;
    if (!HAS_HISTORY_NOW() && S.tab === 'movers') S.tab = 'top';
    if (!HAS_HISTORY_NOW() && S.view === 'timeline') S.view = 'table';
    syncTabs();
    renderTicker();
    render();
    localiseSync();
    history.replaceState(null, '', new URL(`${target.path}/`, SITE_ROOT));
    toast(`Showing ${target.title}`);
  } catch (err) {
    toast(`Could not load that chart: ${err.message}`);
  } finally {
    SWITCHING = false; renderControls();
  }
}

function HAS_HISTORY_NOW(){ return D.history !== false; }

function syncTabs(){
  const movers = document.querySelector('#tabs button[data-tab="movers"]');
  if (movers) movers.style.display = HAS_HISTORY_NOW() ? '' : 'none';
  document.querySelectorAll('#tabs button').forEach(b =>
    b.classList.toggle('on', b.dataset.tab === S.tab));
}

function renderControls(){
  // New Releases carries its own Store and Genre controls, so the chart's
  // filters are suppressed there rather than shown twice.
  if (S.tab === 'digest' || S.tab === 'publishers' || S.tab === 'new'){
    $('#controls').innerHTML = ''; return;
  }
  const pubs = [...new Set(D.items.map(i => i.artist))].sort();
  const sortActive = S.sort !== 'rank' || S.dir !== 1;
  $('#controls').innerHTML = `
   <div class="controls">
    ${datasetControls()}
    <div class="ctl ${sortActive?'active':''}"><label>Sort</label>
      <select id="f-sort">
        <option value="rank|1">Rank, best first</option>
        <option value="delta|-1">Rank change, high → low</option>
        <option value="delta|1">Rank change, low → high</option>
        <option value="rating|-1">Rating, high → low</option>
        <option value="ratings|-1">Ratings count, high → low</option>
        <option value="released|-1">Newest release first</option>
        <option value="name|1">Title, A → Z</option>
      </select></div>
    <div class="ctl ${S.publisher!=='all'?'active':''}"><label>Publisher</label>
      <select id="f-pub"><option value="all">All</option>
      ${pubs.map(p=>`<option ${S.publisher===p?'selected':''}>${esc(p)}</option>`).join('')}
      </select></div>
    <div class="ctl ${S.minRating?'active':''}"><label>Rating</label>
      <select id="f-rating">
        <option value="0">Any</option><option value="4">4.0+</option>
        <option value="4.5">4.5+</option><option value="4.8">4.8+</option>
      </select></div>
    <div class="ctl ${S.released!=='any'?'active':''}"><label>Released</label>
      <select id="f-rel">
        <option value="any">Any time</option><option value="30">Last 30 days</option>
        <option value="90">Last 90 days</option><option value="365">Last year</option>
      </select></div>
    <div class="seg">
      ${(HAS_HISTORY_NOW() ? ['table','grid','timeline'] : ['table','grid']).map(v =>
        `<button data-view="${v}" class="${S.view===v?'on':''}">${v}</button>`).join('')}
    </div>
    <div class="search"><input id="f-q" type="search" value="${esc(S.q)}"
      placeholder="Search title or company…"></div>
   </div>`;
  $('#f-sort').value = `${S.sort}|${S.dir}`;
  $('#f-rating').value = String(S.minRating);
  $('#f-rel').value = S.released;
  const fc = $('#f-country'), fg = $('#f-genre');
  if (fc) fc.onchange = e => switchDataset(e.target.value, $('#f-genre').value);
  if (fg) fg.onchange = e => switchDataset($('#f-country').value, e.target.value);
  $('#f-sort').onchange = e => { const [k,d] = e.target.value.split('|');
    S.sort = k; S.dir = Number(d); S.page = 1; render(); };
  $('#f-pub').onchange = e => { S.publisher = e.target.value; S.page = 1; render(); };
  $('#f-rating').onchange = e => { S.minRating = Number(e.target.value); S.page=1; render(); };
  $('#f-rel').onchange = e => { S.released = e.target.value; S.page = 1; render(); };
  $('#f-q').oninput = e => { S.q = e.target.value; S.page = 1; renderBody(); };
  document.querySelectorAll('[data-view]').forEach(b =>
    b.onclick = () => { S.view = b.dataset.view; render(); });
}

const TH = (key,label,extra='') => {
  const on = S.sort === key;
  return `<th class="sortable ${on?'sorted':''}" data-sort="${key}" ${extra}>${label}
    <span class="ar">${on ? (S.dir===1?'▲':'▼') : '▲▼'}</span></th>`;
};

function tableFor(rows){
  return `<div class="panel"><div class="scroll"><table>
    <thead><tr>
      ${TH('rank','#')}${HAS_HISTORY_NOW() ? TH('delta',spanLabelNow()) : ''}${TH('name','Game')}
      ${TH('artist','Company')}${TH('rating','Rating')}${TH('ratings','Ratings')}
      ${TH('released','Released')}${HAS_HISTORY_NOW() ? '<th>Rank trend</th>' : ''}
    </tr></thead><tbody>
    ${rows.map(r => `<tr>
      <td class="c-rank">${String(r.rank).padStart(2,'0')}</td>
      ${HAS_HISTORY_NOW() ? `<td class="c-d">${deltaCell(r.delta, r.is_new_entry)}</td>` : ''}
      <td><div class="game">
        <a href="${esc(r.url)}" target="_blank" rel="noopener">
          <img class="ico" loading="lazy" src="${esc(r.icon)}" alt=""></a>
        <div><a class="g-name" href="${esc(r.url)}" target="_blank"
             rel="noopener">${esc(r.name)}</a>${playLink(r)}${
            r.is_new_release ? '<span class="tag fresh">fresh</span>' : ''}
          <div class="g-sub">${esc(r.genre)}</div></div></div></td>
      <td><div class="co">${companyLink(r)}${
          r.titles_charting > 1
            ? `<span class="tag count" data-studio="${esc(r.artist)}"
                 title="Show this studio's games">×${r.titles_charting}</span>` : ''
        }</div></td>
      <td><div class="rating"><span class="star">★</span>${r.rating.toFixed(2)}</div>
        <div class="bar"><i style="width:${(r.rating/5*100).toFixed(1)}%"></i></div></td>
      <td class="num">${num(r.ratings)}</td>
      <td class="num dim">${esc(r.released)}</td>
      ${HAS_HISTORY_NOW() ? `<td>${spark(r.history)}</td>` : ''}
    </tr>`).join('')}
    </tbody></table></div></div>`;
}

function gridFor(rows){
  return `<div class="grid">${rows.map(r => `
    <a class="card" href="${esc(r.url)}" target="_blank" rel="noopener">
      <div class="card-top">
        <img class="ico" loading="lazy" src="${esc(r.icon)}" alt="">
        <div><div class="g-name">${esc(r.name)}</div>
          <div class="g-sub">${esc(r.artist)}</div></div>
      </div>
      <div class="card-row"><span class="rk">#${String(r.rank).padStart(2,'0')}</span>
        ${deltaCell(r.delta, r.is_new_entry)}</div>
      <div class="card-row"><span>Rating</span><b>${r.rating.toFixed(2)}</b></div>
      <div class="card-row"><span>Ratings</span><b>${num(r.ratings)}</b></div>
      <div class="card-row"><span>Released</span><b>${esc(r.released)}</b></div>
    </a>`).join('')}</div>`;
}

function timelineFor(rows){
  const usable = rows.filter(r => r.history.length >= 2);
  if (!usable.length)
    return `<div class="panel"><div class="empty">
      Rank history needs at least two snapshots on different days.<br>
      The timeline fills in as the scheduled job runs.</div></div>`;
  return `<div class="panel">${usable.map(r => {
    const h = r.history, lo = Math.min(...h), hi = Math.max(...h);
    const range = Math.max(hi - lo, 1);
    const pts = h.map((v,i) =>
      `${(i/(h.length-1)*100).toFixed(1)},${((v-lo)/range*100).toFixed(1)}`).join(' ');
    const dir = h[h.length-1] < h[0] ? 'var(--up)'
              : h[h.length-1] > h[0] ? 'var(--down)' : 'var(--flat)';
    return `<div class="tl-row">
      <div class="tl-name">${esc(r.name)}</div>
      <div class="tl-track"><svg viewBox="0 0 100 100" preserveAspectRatio="none">
        <polyline points="${pts}" fill="none" stroke="${dir}" stroke-width="2.5"
          vector-effect="non-scaling-stroke" stroke-linejoin="round"/></svg></div>
      <div class="tl-end">#${h[0]} → #${h[h.length-1]}</div>
    </div>`; }).join('')}</div>`;
}

function publishersView(){
  const rows = D.publishers;
  return `<div class="note">Select a company to see its games in the top
    ${D.stats.tracked}. The name links to its App Store developer page.</div>
    <div class="panel"><div class="scroll"><table class="pub">
    <thead><tr><th>#</th><th>Company</th><th>Titles</th><th>Best rank</th>
      <th>Avg rating</th><th>Total ratings</th><th>Net change</th></tr></thead><tbody>
    ${rows.map((p,i) => `<tr data-studio="${esc(p.artist)}">
      <td class="c-rank">${String(i+1).padStart(2,'0')}</td>
      <td>${p.artist_url
            ? `<a class="g-name co-link" href="${esc(p.artist_url)}" target="_blank"
                 rel="noopener">${esc(p.artist)}</a>`
            : `<span class="g-name">${esc(p.artist)}</span>`}</td>
      <td class="num">${p.titles}</td>
      <td class="num">#${p.best_rank}</td>
      <td class="num">${p.avg_rating.toFixed(2)}</td>
      <td class="num">${num(p.ratings_total)}</td>
      <td>${deltaCell(p.net_delta, false)}</td>
    </tr>`).join('')}</tbody></table></div></div>`;
}

function releasePager(total, pages, first){
  const last = Math.min(first + S.perPage, total);
  const sizes = PAGE_SIZES.map(n =>
    `<button class="${S.perPage === n ? 'on' : ''}" data-relsize="${n}">${n}</button>`).join('');
  const nums = Array.from({length: pages}, (_, i) => i + 1)
    .filter(p => p === 1 || p === pages || Math.abs(p - S.relPage) <= 1)
    .map((p, i, a) => (i && p - a[i-1] > 1 ? '<span>…</span>' : '') +
      `<button class="${p === S.relPage ? 'on' : ''}" data-relp="${p}">${p}</button>`).join('');
  return `<div class="tfoot">
    <div>Showing ${first + 1}–${last} of ${total}
      <span class="rows">Rows ${sizes}</span></div>
    <div class="pager">
      <button ${S.relPage === 1 ? 'disabled' : ''} data-relp="${S.relPage - 1}">← prev</button>
      ${nums}
      <button ${S.relPage === pages ? 'disabled' : ''} data-relp="${S.relPage + 1}">next →</button>
    </div></div>`;
}


const RELEASES = {};
let RELEASES_LOADING = false;

/** Rank of a release in the chart currently on screen, if it is in it. */
function chartRank(r){
  if (!CHART_INDEX) CHART_INDEX = new Map(
    (D.items || []).map(i => [i.app_id, i.rank]));
  return CHART_INDEX.get(r.app_id) || null;
}
let CHART_INDEX = null;

async function loadReleases(country){
  if (RELEASES[country]) { renderBody(); renderHero(); return; }
  RELEASES_LOADING = true; renderBody();
  try {
    const res = await fetch(new URL(`releases/${country}.json`, SITE_ROOT),
                            {cache: 'no-cache'});
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    RELEASES[country] = await res.json();
  } catch (err) {
    RELEASES[country] = [];
    toast(`No release data for ${country.toUpperCase()}: ${err.message}`);
  } finally {
    RELEASES_LOADING = false;
    // Only the genre default is re-derived: clearing the country here
    // would bounce the view straight back to the chart's own store.
    S.relGenre = null;
      renderBody();
      renderHero();
  }
}

function releaseGenres(){
  const counts = new Map();
  for (const r of agedPool())
    for (const g of (r.genres || []))
      counts.set(g, (counts.get(g) || 0) + 1);
  return [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
}

/** The Store and Genre controls, rendered during loading as well as after. */
/** The pool for the selected store, narrowed to the selected age. */
function agedPool(){
  const pool = RELEASES[S.relCountry] || [];
  if (S.relAge === 'all') return pool;
  const max = Number(S.relAge);
  return pool.filter(r => (r.days_old ?? 1e9) <= max);
}

/** How many releases the current filters actually leave on screen. */
function shownCount(){
  let rows = agedPool();
  if (S.relGenre && S.relGenre !== 'all')
    rows = rows.filter(r => (r.genres || []).includes(S.relGenre));
  return rows.length;
}

function releasePicker(loading){
  const uniqCountries = [...new Set((D.datasets || []).map(d => d.country))].sort();
  const total = agedPool().length;
  return `<div class="controls">
    ${uniqCountries.length > 1 ? `
    <div class="ctl ${S.relCountry !== D.country.toLowerCase() ? 'active' : ''}">
      <label>Store</label>
      <select id="f-relcountry" ${loading ? 'disabled' : ''}>${uniqCountries.map(c =>
        `<option value="${esc(c)}" ${c === S.relCountry ? 'selected' : ''}
          >${esc(c.toUpperCase())}</option>`).join('')}</select></div>` : ''}
    <div class="ctl ${S.relAge !== String(D.new_days) ? 'active' : ''}">
      <label>Released</label>
      <select id="f-relage" ${loading ? 'disabled' : ''}>
        <option value="${D.new_days}" ${S.relAge === String(D.new_days) ? 'selected' : ''}
          >Last ${D.new_days} days</option>
        <option value="90"   ${S.relAge === '90'   ? 'selected' : ''}>Last 90 days</option>
        <option value="365"  ${S.relAge === '365'  ? 'selected' : ''}>Last year</option>
        <option value="all"  ${S.relAge === 'all'  ? 'selected' : ''}>Any time</option>
      </select></div>
    <div class="ctl ${S.relGenre && S.relGenre !== 'all' ? 'active' : ''}"><label>Genre</label>
      <select id="f-relgenre" ${loading ? 'disabled' : ''}>
        <option value="all" ${S.relGenre === 'all' ? 'selected' : ''}
          >All genres (${total})</option>
        ${releaseGenres().map(([g, n]) =>
          `<option value="${esc(g)}" ${S.relGenre === g ? 'selected' : ''}
            >${esc(g)} (${n})</option>`).join('')}
      </select></div>
    <div class="search"><input id="f-relq" type="search" value="${esc(S.q)}"
      ${loading ? 'disabled' : ''} placeholder="Search title or company…"></div>
    </div>`;
}

function newReleasesView(){
  if (RELEASES_LOADING)
    return releasePicker(true) + `<div class="panel"><div class="empty">
      <span class="spin"></span>Loading releases…</div></div>`;
  // Releases are storefront-specific, so the pool is fetched per country rather
  // than inlined for every chart.
  let rows = agedPool();
  const total = rows.length;
  // The sweep collects every genre it turns up; this narrows the view without
  // narrowing the data, so the tracked genre is a default rather than a cage.
  if (S.relGenre !== 'all')
    rows = rows.filter(r => (r.genres || []).includes(S.relGenre));
  const shown = rows.length;
  if (S.q){
    const q = S.q.toLowerCase();
    rows = rows.filter(r => (r.name + ' ' + r.artist).toLowerCase().includes(q));
  }
  const picker = releasePicker(false);
  if (!rows.length)
    return picker + `<div class="panel"><div class="empty">
      Nothing matches that filter.</div></div>`;

  const pages = Math.max(1, Math.ceil(rows.length / S.perPage));
  S.relPage = Math.min(Math.max(1, S.relPage), pages);
  const first = (S.relPage - 1) * S.perPage;
  const page = rows.slice(first, first + S.perPage);
  return picker + `<div class="note">${
      S.relGenre === 'all'
        ? (S.relAge === 'all'
            ? 'Every game the sweep has found in this store'
            : `Every release the sweep found in the last ${S.relAge} days`)
        : `<b>${esc(S.relGenre)}</b> ${S.relAge === 'all'
             ? 'games in this store' : `from the last ${S.relAge} days`}`
    } — <b>${shown}</b> games${(() => {
      const c = rows.filter(r => chartRank(r)).length;
      return c ? `, of which <b>${c}</b> ${c === 1 ? 'has' : 'have'} reached the top ${D.stats.tracked}` : '';
    })()}.</div>
    <div class="panel"><div class="scroll"><table>
    <thead><tr><th>Age</th><th>Game</th><th>Company</th><th>Genre</th>
      <th>Rating</th><th>Ratings</th><th>Released</th><th>Chart</th></tr></thead><tbody>
    ${page.map(r => `<tr>
      <td class="c-rank">${r.days_old ?? '—'}d</td>
      <td><div class="game">
        <a href="${esc(r.url)}" target="_blank" rel="noopener">
          <img class="ico" loading="lazy" src="${esc(r.icon)}" alt=""></a>
        <div><a class="g-name" href="${esc(r.url)}" target="_blank"
             rel="noopener">${esc(r.name)}</a>${playLink(r)}${
             chartRank(r) ? `<span class="tag top100">top 100</span>` : ''}
          <div class="g-sub">${esc(r.genre)}</div></div></div></td>
      <td><div class="co">${companyLink(r)}</div></td>
      <td class="g-sub">${esc((r.genres || []).slice(0, 2).join(' / ') || '—')}</td>
      <td class="rating"><span class="star">★</span>${r.rating ? r.rating.toFixed(2) : '—'}</td>
      <td class="num">${num(r.ratings)}</td>
      <td class="num dim">${esc(r.released)}</td>
      <td>${chartRank(r) ? `<span class="d up">#${chartRank(r)}</span>`
                   : '<span class="d flat">—</span>'}</td>
    </tr>`).join('')}</tbody></table></div></div>`
    + releasePager(rows.length, pages, first);
}

function digestView(){
  const d = D.digest;
  return `<div class="note">The dashboard cannot post to Slack on its own — it is a
    static page. <b>Send digest</b> opens the scheduled job on GitHub, where you can run it
    by hand.</div>
    <div class="panel"><div class="scroll"><table>
    <thead><tr><th>Digest</th><th>When</th><th>Includes</th></tr></thead><tbody>
    <tr><td class="g-name">Daily</td><td class="mono-dim">${esc(d.daily_time)} UTC</td>
      <td class="co">${d.daily.map(k=>`<span class="tag count">${esc(k)}</span>`).join(' ')}</td></tr>
    <tr><td class="g-name">Weekly</td>
      <td class="mono-dim">${esc(d.weekly_day)} ${esc(d.weekly_time)} UTC</td>
      <td class="co">${d.weekly.map(k=>`<span class="tag count">${esc(k)}</span>`).join(' ')}</td></tr>
    </tbody></table></div></div>`;
}

function renderBody(){
  const el = $('#view'), foot = $('#tfoot');
  if (S.tab === 'digest'){ el.innerHTML = digestView(); foot.innerHTML=''; return; }
  if (S.tab === 'publishers'){
    el.innerHTML = publishersView();
    foot.innerHTML = `<div>${D.publishers.length} companies in the top ${D.stats.tracked}</div>`;
    el.querySelectorAll('tr[data-studio]').forEach(tr => tr.onclick = ev => {
      if (ev.target.closest('a')) return;   // let the developer-page link through
      showStudio(tr.dataset.studio);
    });
    return;
  }
  if (S.tab === 'new'){
    if (S.relAge === null) S.relAge = String(D.new_days);
    if (S.relCountry === null){
      S.relCountry = D.country.toLowerCase();
      loadReleases(S.relCountry);
      return;
    }
    if (S.relGenre === null){
      // Default to the chart's own genre; the pool itself stays unfiltered.
      const g = titleCase(D.genre);
      S.relGenre = releaseGenres().some(([n]) => n === g) ? g : 'all';
    }
    el.innerHTML = `<div class="copybar">
        <button class="btn solid" id="shareslack">Share to Slack</button>
        <span style="color:var(--faint);font-size:12px" id="sharenote"></span>
      </div>` + newReleasesView();
    foot.innerHTML = `<div>${D.new_releases.length} releases in the last ${D.new_days} days</div>`;
    const sb = el.querySelector('#shareslack');
    sb.onclick = () => shareToSlack('new', sb);
    const note = el.querySelector('#sharenote');
    if (note) {
      const n = shownCount();
      note.textContent = `Posts these ${n} ${
        S.relGenre && S.relGenre !== 'all' ? S.relGenre + ' ' : ''}release${
        n === 1 ? '' : 's'} for ${(S.relCountry || D.country).toUpperCase()}`
        + (S.relAge === 'all' ? '.' : ` from the last ${S.relAge} days.`);
    }
    const rc = el.querySelector('#f-relcountry');
    if (rc) rc.onchange = e => { S.relCountry = e.target.value; S.relPage = 1;
                                 loadReleases(S.relCountry); };
    el.querySelectorAll('[data-relp]').forEach(b => b.onclick = () => {
      S.relPage = Number(b.dataset.relp); renderBody();
      window.scrollTo({top: 0, behavior: 'smooth'});
    });
    el.querySelectorAll('[data-relsize]').forEach(b => b.onclick = () => {
      const anchor = (S.relPage - 1) * S.perPage;
      S.perPage = Number(b.dataset.relsize);
      S.relPage = Math.floor(anchor / S.perPage) + 1;
      renderBody();
    });
    const ra = el.querySelector('#f-relage');
    if (ra) ra.onchange = e => { S.relAge = e.target.value; S.relGenre = null;
                                 S.relPage = 1; renderBody(); renderHero(); };
    const rg = el.querySelector('#f-relgenre');
    if (rg) rg.onchange = e => { S.relGenre = e.target.value; S.relPage = 1;
                                 renderBody(); };
    const rq = el.querySelector('#f-relq');
    if (rq) rq.oninput = e => { S.q = e.target.value; S.relPage = 1; renderBody(); };
    return;
  }

  let rows = filtered();
  if (S.tab === 'movers') rows = rows.filter(r => r.delta);

  if (!rows.length){
    el.innerHTML = `<div class="panel"><div class="empty">${
      S.tab === 'movers'
        ? 'No rank movement recorded yet. Movement appears once two snapshots exist.'
        : S.tab === 'new'
        ? 'No games in this chart were released in the last ' + D.new_days + ' days.'
        : 'Nothing matches those filters.'}</div></div>`;
    foot.innerHTML = ''; return;
  }

  // The timeline is a trend overview, so it always plots the whole set.
  const paged = S.view === 'table' || S.view === 'grid';
  const pages = paged ? Math.max(1, Math.ceil(rows.length / S.perPage)) : 1;
  S.page = Math.min(S.page, pages);
  const show = paged ? rows.slice((S.page-1)*S.perPage, S.page*S.perPage) : rows;

  const kind = S.tab === 'movers' ? 'movers' : 'chart';
  const copyRows = S.tab === 'movers' ? rows : show;
  const bar = `<div class="copybar">
      <button class="btn solid" id="shareslack">Share to Slack</button>
      <span style="color:var(--faint);font-size:12px">${
        S.tab === 'movers'
          ? 'Posts every mover as “up/down N — now #rank”.'
          : `Posts the current top ${Math.min(copyRows.length, 25)} with live ranks.`
      }</span></div>`;

  el.innerHTML = bar + (S.view === 'grid' ? gridFor(show)
               : S.view === 'timeline' ? timelineFor(rows)
               : tableFor(show));

  const cp = el.querySelector('#shareslack');
  if (cp) cp.onclick = () => shareToSlack(kind, cp);

  el.querySelectorAll('[data-studio]').forEach(t => t.onclick = ev => {
    ev.preventDefault(); ev.stopPropagation(); showStudio(t.dataset.studio);
  });

  el.querySelectorAll('th[data-sort]').forEach(th => th.onclick = () => {
    const k = th.dataset.sort;
    if (S.sort === k) S.dir *= -1; else { S.sort = k; S.dir = k === 'rank' ? 1 : -1; }
    S.page = 1; render();
  });

  const sizeSwitch = `<span class="rows">Rows ${PAGE_SIZES.map(n =>
    `<button class="${S.perPage===n?'on':''}" data-size="${n}">${n}</button>`).join('')}</span>`;

  if (!paged){
    foot.innerHTML = `<div>Showing all ${rows.length} · refreshed daily</div>`;
  } else {
    const first = (S.page-1)*S.perPage + 1;
    const last = Math.min(S.page*S.perPage, rows.length);
    foot.innerHTML =
      `<div>Showing ${first}–${last} of ${rows.length} · refreshed daily ${sizeSwitch}</div>
       <div class="pager">
        <button ${S.page===1?'disabled':''} data-p="${S.page-1}">← prev</button>
        ${Array.from({length:pages},(_,i)=>i+1)
          .filter(p => p===1 || p===pages || Math.abs(p-S.page)<=1)
          .map((p,i,a) => (i && p - a[i-1] > 1 ? '<span>…</span>' : '') +
            `<button class="${p===S.page?'on':''}" data-p="${p}">${p}</button>`).join('')}
        <button ${S.page===pages?'disabled':''} data-p="${S.page+1}">next →</button>
       </div>`;
  }
  foot.querySelectorAll('[data-p]').forEach(b =>
    b.onclick = () => { S.page = Number(b.dataset.p); renderBody();
      window.scrollTo({top:0, behavior:'smooth'}); });
  foot.querySelectorAll('[data-size]').forEach(b =>
    b.onclick = () => {
      // Keep the first visible row in view instead of jumping back to page 1.
      const anchor = (S.page - 1) * S.perPage;
      S.perPage = Number(b.dataset.size);
      S.page = Math.floor(anchor / S.perPage) + 1;
      renderBody();
    });
}

/** Show one studio's games in the main chart view. */
function showStudio(name){
  S.tab = 'top'; S.publisher = name; S.page = 1; S.view = 'table'; S.q = '';
  document.querySelectorAll('#tabs button').forEach(b =>
    b.classList.toggle('on', b.dataset.tab === 'top'));
  render();
  toast(`Showing ${name}`);
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function render(){ renderHero(); renderControls(); renderBody(); }

document.querySelectorAll('#tabs button').forEach(b => b.onclick = () => {
  document.querySelectorAll('#tabs button').forEach(x => x.classList.remove('on'));
  b.classList.add('on'); S.tab = b.dataset.tab; S.page = 1; render();
});

$('#csv').onclick = () => {
  const rows = filtered();
  const head = ['rank','delta','name','company','genre','rating','ratings','released','price','url'];
  const body = rows.map(r => [r.rank, r.delta ?? '', r.name, r.artist, r.genre,
    r.rating, r.ratings, r.released, r.price, r.url]
    .map(v => `"${String(v).replace(/"/g,'""')}"`).join(','));
  const blob = new Blob([[head.join(','), ...body].join('\n')], {type:'text/csv'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `top-games-${D.captured_at.slice(0,10)}.csv`;
  a.click(); URL.revokeObjectURL(a.href);
};

/* The job runs in UTC; showing that raw reads as the wrong time for everyone
   outside it. Render the instant in whatever zone the viewer is actually in. */
function localiseSync(){
  const el = document.getElementById('synced');
  const t = new Date(D.captured_at);
  if (isNaN(t)) return;
  const hhmm = t.toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'});
  const zone = Intl.DateTimeFormat().resolvedOptions().timeZone || 'local';
  const mins = Math.round((Date.now() - t.getTime()) / 60000);
  const ago = mins < 1 ? 'just now'
            : mins < 60 ? `${mins}m ago`
            : mins < 1440 ? `${Math.floor(mins/60)}h ago`
            : `${Math.floor(mins/1440)}d ago`;
  el.textContent = `${hhmm} (${ago})`;
  el.title = `${t.toLocaleString()} · ${zone}\nUTC: ${D.captured_at}`;
}

localiseSync();
syncTabs();
renderTicker();
render();
"""
