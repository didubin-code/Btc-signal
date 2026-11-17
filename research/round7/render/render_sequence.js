/* Render the published page H1.1 through a SEQUENCE of /radar payloads in one browser session (the page polls /radar on its own clock),
   capturing the call panel and v2.8 tiles after each switch. usage: node render_sequence.js <page.html> <out prefix> <payload1.json> <payload2.json> ... */
const http = require('http'), fs = require('fs'); const { chromium } = require('playwright');
const page_html = fs.readFileSync(process.argv[2], 'utf8'), out = process.argv[3], payloads = process.argv.slice(4).map(p => fs.readFileSync(p, 'utf8'));
let cur = 0, served = 0;
const srv = http.createServer((q, r) => { r.setHeader('Access-Control-Allow-Origin', '*'); r.setHeader('Access-Control-Allow-Headers', 'Content-Type'); if (q.method === 'OPTIONS') { r.writeHead(204); return r.end(); }
  if (q.url.startsWith('/radar')) { served++; r.writeHead(200, { 'Content-Type': 'application/json' }); return r.end(payloads[cur]); } if (q.url.startsWith('/health')) { r.writeHead(200, { 'Content-Type': 'application/json' }); return r.end('{"ok":true}'); } r.writeHead(200, { 'Content-Type': 'text/html' }); r.end(page_html); });
srv.listen(0, '127.0.0.1', async () => {
  const base = 'http://127.0.0.1:' + srv.address().port; const b = await chromium.launch(); const ctx = await b.newContext({ viewport: { width: 1280, height: 1800 }, deviceScaleFactor: 1 }); const p = await ctx.newPage();
  const errors = []; p.on('pageerror', e => errors.push('pageerror: ' + e.message)); p.on('console', m => { if (m.type() === 'error') errors.push('console: ' + m.text()); });
  await p.addInitScript(u => { localStorage.setItem('pinradar28', JSON.stringify({ u, lf: false, c: 10 })); }, base);
  await p.goto(base + '/'); const btn = p.locator('#startBtn'); if (await btn.count()) await btn.first().click();
  const ids = ['callHead', 'callTag', 'callProb', 'callStatus', 'callNote', 'tradeAct', 'tradeWhy', 'proj', 'valid', 'kRegime'];
  const grab = async () => await p.evaluate(ids => { const o = {}; for (const i of ids) { const e = document.getElementById(i); o[i] = e ? e.textContent.trim().replace(/\s+/g, ' ') : null; } const h = document.getElementById('callHead'); o.callHeadClass = h ? h.className : null; const c = document.getElementById('call'); o.callClass = c ? c.className : null;
    const t = {}; for (const k of ['v28o', 'v28v', 'v28x', 'v28dz']) { const e = document.getElementById(k); t[k] = e ? e.textContent.trim().replace(/\s+/g, ' ') : null; } const vx = document.querySelector('#v28x b'); t.v28xClass = vx ? vx.className : null; const vv = document.querySelector('#v28v b'); t.v28vClass = vv ? vv.className : null; o.v28 = t; return o; }, ids);
  const states = [];
  for (let i = 0; i < payloads.length; i++) { cur = i; const before = served; await p.waitForFunction(n => true, null, { timeout: 100 }).catch(() => {}); const t0 = Date.now(); while (served < before + 2 && Date.now() - t0 < 15000) await p.waitForTimeout(250); await p.waitForTimeout(1500); const s = await grab(); s.step = i; s.servedPolls = served; states.push(s); await p.screenshot({ path: out + '_step' + i + '.png', fullPage: false }); }
  fs.writeFileSync(out + '.json', JSON.stringify({ states, errors }, null, 1)); console.log(JSON.stringify({ steps: states.length, errors: errors.length, polls: served }));
  await b.close(); srv.close();
});
