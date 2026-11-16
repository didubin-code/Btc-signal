/* Render the published page H1.1 (sha 8bf43b57, the page production serves) against a /radar payload produced by the PR11 engine, offline.
   Serves the page and answers POST /radar with the payload; sets the page's backend URL in localStorage; waits for the call panel; records
   the visible texts and a screenshot. usage: node render_page.js <page.html> <payload.json> <out prefix> */
const http = require('http'), fs = require('fs'), path = require('path');
const { chromium } = require('playwright');
const page_html = fs.readFileSync(process.argv[2], 'utf8'), payload = fs.readFileSync(process.argv[3], 'utf8'), out = process.argv[4];
const srv = http.createServer((req, res) => {
  res.setHeader('Access-Control-Allow-Origin', '*'); res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  if (req.method === 'OPTIONS') { res.writeHead(204); return res.end(); }
  if (req.url.startsWith('/radar')) { res.writeHead(200, { 'Content-Type': 'application/json' }); return res.end(payload); }
  if (req.url.startsWith('/health')) { res.writeHead(200, { 'Content-Type': 'application/json' }); return res.end('{"ok":true}'); }
  res.writeHead(200, { 'Content-Type': 'text/html' }); res.end(page_html);
});
srv.listen(0, '127.0.0.1', async () => {
  const port = srv.address().port, base = 'http://127.0.0.1:' + port;
  const browser = await chromium.launch(); const ctx = await browser.newContext({ viewport: { width: 1180, height: 1500 }, deviceScaleFactor: 2 });
  const page = await ctx.newPage(); const errors = [];
  page.on('pageerror', e => errors.push(String(e))); page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
  await page.addInitScript(b => { try { localStorage.setItem('pinradar28', JSON.stringify({ u: b, lf: false, c: 10 })); } catch (e) {} }, base);
  await page.goto(base + '/', { waitUntil: 'load' });
  try { const btn = page.locator('button', { hasText: /^start/i }).first(); if (await btn.count()) await btn.click(); } catch (e) { errors.push('start click: ' + e.message); }
  try { await page.waitForFunction(() => { const h = document.getElementById('callHead'); return h && h.textContent.trim() && h.textContent.trim() !== 'NO CALL'; }, null, { timeout: 15000 }); } catch (e) { errors.push('callHead did not render: ' + e.message); }
  await page.waitForTimeout(1500);
  const texts = await page.evaluate(() => {
    const g = id => { const e = document.getElementById(id); return e ? e.textContent.trim().replace(/\s+/g, ' ') : null; };
    const cls = id => { const e = document.getElementById(id); return e ? e.className : null; };
    return { callHead: g('callHead'), callHeadClass: cls('callHead'), callClass: cls('call'), callTag: g('callTag'), callProb: g('callProb'), callStatus: g('callStatus'), callNote: g('callNote'),
      tradeAct: g('tradeAct'), tradeWhy: g('tradeWhy'), tradeBoxClass: cls('tradeBox'), proj: g('proj'), valid: g('valid'), kRegime: g('kRegime'), kNeed: g('kNeed'), kPrints: g('kPrints'), kLockAt: g('kLockAt'), kAsk: g('kAsk'), d27: g('d27'), lead: g('lead'), verdict: g('verdict') };
  });
  fs.writeFileSync(out + '.texts.json', JSON.stringify({ texts, errors }, null, 1));
  await page.screenshot({ path: out + '.png', fullPage: true });
  try { await page.locator('#call').screenshot({ path: out + '_call.png' }); } catch (e) { errors.push('call screenshot: ' + e.message); }
  console.log(JSON.stringify({ texts, errors }, null, 1)); await browser.close(); srv.close();
});
