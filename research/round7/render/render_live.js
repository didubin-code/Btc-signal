/* Render the published page H1.1 against the LIVE backend (read-only from our side: the page's own POST /radar). usage: node render_live.js <page.html> <backend url> <out prefix> */
const http = require('http'), fs = require('fs'); const { chromium } = require('playwright');
const page_html = fs.readFileSync(process.argv[2], 'utf8'), backend = process.argv[3], out = process.argv[4];
const srv = http.createServer((q, r) => { r.writeHead(200, { 'Content-Type': 'text/html' }); r.end(page_html); });
srv.listen(0, '127.0.0.1', async () => {
  const base = 'http://127.0.0.1:' + srv.address().port; const b = await chromium.launch(); const ctx = await b.newContext({ viewport: { width: 1280, height: 1800 }, deviceScaleFactor: 1 });
  const p = await ctx.newPage(); const errors = []; p.on('pageerror', e => errors.push('pageerror: ' + e.message)); p.on('console', m => { if (m.type() === 'error') errors.push('console: ' + m.text()); });
  await p.addInitScript(u => { localStorage.setItem('pinradar28', JSON.stringify({ u, lf: false, c: 10 })); }, backend);
  await p.goto(base + '/'); const btn = p.locator('#startBtn'); if (await btn.count()) await btn.first().click();
  try { await p.waitForFunction(() => { const h = document.getElementById('callHead'); return h && h.textContent && h.textContent.trim().length > 0 && !/waiting|connecting|—/.test(h.textContent.trim()) || (document.getElementById('callProb') && /%/.test(document.getElementById('callProb').textContent)); }, null, { timeout: 25000 }); } catch (_) {}
  await p.waitForTimeout(4000);
  const ids = ['callHead', 'callTag', 'callProb', 'callStatus', 'callNote', 'tradeAct', 'tradeWhy', 'proj', 'valid', 'kRegime', 'v28o', 'v28v', 'v28x'];
  const texts = await p.evaluate(ids => { const o = {}; for (const i of ids) { const e = document.getElementById(i); o[i] = e ? e.textContent.trim().replace(/\s+/g, ' ') : null; } const h = document.getElementById('callHead'); o.callHeadClass = h ? h.className : null; const c = document.getElementById('call'); o.callClass = c ? c.className : null; return o; }, ids);
  const health = await p.evaluate(async u => { try { const r = await fetch(u + '/health'); const j = await r.json(); return { codeSha256: j.codeSha256, pr11: j.pr11 || null, ingest: j.ingest, uptimeSec: j.uptimeSec }; } catch (e) { return { err: String(e) }; } }, backend);
  await p.screenshot({ path: out + '.png', fullPage: true });
  fs.writeFileSync(out + '.texts.json', JSON.stringify({ ts: new Date().toISOString(), backend, texts, health, errors }, null, 1));
  console.log(JSON.stringify({ ts: new Date().toISOString(), head: texts.callHead, tag: texts.callTag, act: texts.tradeAct, v28x: texts.v28x, health, errors: errors.length }));
  await b.close(); srv.close();
});
