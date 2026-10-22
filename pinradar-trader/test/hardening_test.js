/* Hardening tests (the fixes from the safety review): restore after a restart, ledger durability, arming preconditions,
   admin-only routes, the engine passthrough, non-binary settlement. Each case runs the trader in its own child process with a
   prepared ledger; no network, no orders. */
'use strict';
const assert = require('assert');
const crypto = require('crypto'), path = require('path'), os = require('os'), fs = require('fs');
const { spawnSync, spawn } = require('child_process');
const { mkLedger } = require('../lib/ledger');
const ROOT = path.join(__dirname, '..');
const TMP = fs.mkdtempSync(path.join(os.tmpdir(), 'pr5_hard_'));
const results = [];
function t(name, fn) { try { fn(); results.push([true, name]); } catch (e) { results.push([false, name + ' :: ' + (e && e.message || e)]); } }
const baseEnv = () => { const e = { ...process.env, ENABLE_WS: '0' }; for (const k of ['LIVE', 'TRADER_LIVE_ARM', 'KALSHI_KEY_ID', 'KALSHI_PRIVATE_KEY', 'TRADER_ADMIN_TOKEN', 'TRADER_HALT', 'TRADER_HALT_FILE']) delete e[k]; return e; };
function child(env, body) {
  const script = `(async () => { const T = require('./trader.js'); T.loadEngine(); const out = {}; ${body}; console.log('@@' + JSON.stringify(out)); process.exit(0); })().catch(e => { console.log('@@' + JSON.stringify({ error: String(e.stack || e) })); process.exit(1); });`;
  const r = spawnSync(process.execPath, ['-e', script], { cwd: ROOT, env: { ...baseEnv(), ...env }, encoding: 'utf8', timeout: 120000 });
  const l = (r.stdout || '').split('\n').find(x => x.startsWith('@@'));
  const o = l ? JSON.parse(l.slice(2)) : { error: (r.stderr || r.stdout || '').slice(0, 800) };
  if (o.error) throw new Error('child: ' + o.error.slice(0, 600));
  return o;
}
const NOW = Date.now(), DAY = new Date(NOW).toISOString().slice(0, 10);
const fill = (id, mode, extra = {}) => ({ ev: 'FILL', id, clientOrderId: id, ticker: 'KXBTC15M-' + id, closeMs: NOW - 3600e3, strike: 82000, side: 'UP', filled: 5, priceCents: 99, feeUsd: 0.01, costUsd: 4.96, mode, ...extra });
const settled = (id, mode, won) => ({ ev: 'SETTLED', id, ticker: 'KXBTC15M-' + id, side: 'UP', contracts: 5, costUsd: 4.96, result: won ? 'yes' : 'no', won, pnlUsd: won ? 0.04 : -4.96, mode });

/* 1. today's realised P&L and trade count survive a restart (the -$10/day limit is not reset by a restart) */
t('restart keeps today\'s realised loss and trade count; the daily limit still blocks after a resume + restart', () => {
  const f = path.join(TMP, 'day.jsonl'), L = mkLedger(f);
  L.append(fill('a1', 'DRY-RUN')); L.append(settled('a1', 'DRY-RUN', false)); L.append({ ev: 'HALT', reason: '1 consecutive loss(es)' }); L.append({ ev: 'RESUME' });
  L.append(fill('a2', 'DRY-RUN')); L.append(settled('a2', 'DRY-RUN', false)); L.append({ ev: 'HALT', reason: 'daily loss limit $10 reached' }); L.append({ ev: 'RESUME' });
  L.append(fill('a3', 'DRY-RUN')); L.append(settled('a3', 'DRY-RUN', false)); L.append({ ev: 'RESUME' });
  const o = child({ TRADER_LEDGER_FILE: f }, `T.restoreFromLedger(); const { decide } = require('./lib/policy');
    out.realized = T.ST.realizedTodayUsd; out.trades = T.ST.tradesToday; out.halted = T.haltReasons();
    out.daily = decide({ now: Date.now(), ticker: 'KXBTC15M-X', strike: 82000, tau: 60, exchange: {}, book: { ok: true, ageMs: 100, yesAsks: [[99, 50]] },
      sig: { state: 'LOCKED', side: 'UP', pFlip: 0.001, pFlipCons: 0.003, gates: { hard: [] }, warmup: { lockedAvailable: true }, trade: { action: 'TRADE NOW' }, exec: { headline: 'TRADE NOW' } } },
      { halted: [], windows: new Map(), realizedTodayUsd: T.ST.realizedTodayUsd, consecutiveLosses: 0, tradesToday: T.ST.tradesToday, openExposureUsd: 0 }, T.CFG).why`);
  assert.strictEqual(o.realized, -14.88); assert.strictEqual(o.trades, 3); assert.ok(o.daily.some(w => /daily loss/.test(w)), JSON.stringify(o.daily));
});

/* 2. the whole ledger is replayed: a halt older than the in-memory tail (2,000 lines) survives */
t('a halt 2,500 lines back is restored', () => {
  const f = path.join(TMP, 'old.jsonl'), L = mkLedger(f);
  L.append({ ev: 'HALT', reason: 'order rejected (HTTP 400): test' });
  for (let i = 0; i < 2500; i++) L.append({ ev: 'WINDOW', ticker: 'KXBTC15M-W' + i, closeMs: NOW - 1e9 + i });
  const o = child({ TRADER_LEDGER_FILE: f }, `T.restoreFromLedger(); out.halted = T.haltReasons();`);
  assert.ok(o.halted.some(h => /order rejected/.test(h)), JSON.stringify(o.halted));
});

/* 3. the process stopped mid-order (ORDER_ATTEMPT without ORDER_RESULT): halt, provisional position, window used; idempotent */
t('restart mid-order: halts, books the order provisionally, marks the window used; a second restart does not double it', () => {
  const f = path.join(TMP, 'mid.jsonl'), L = mkLedger(f);
  L.append({ ev: 'ORDER_ATTEMPT', ticker: 'KXBTC15M-26OCT170100-00', closeMs: NOW + 60e3, strike: 82000, side: 'DOWN', attempt: 1, clientOrderId: 'pr5-KXBTC15M-26OCT170100-00-a1',
    contracts: 5, limitCents: 98, maxCostUsd: 4.91, tau: 40, mode: 'LIVE', modeled: {} });
  const body = `T.restoreFromLedger(); out.halted = T.haltReasons(); out.pos = T.ST.positions; out.w = T.ST.windows.get('KXBTC15M-26OCT170100-00');`;
  const o1 = child({ TRADER_LEDGER_FILE: f }, body), o2 = child({ TRADER_LEDGER_FILE: f }, body);
  assert.ok(o1.halted.some(h => /outcome unknown after a restart/.test(h)), JSON.stringify(o1.halted));
  assert.strictEqual(o1.pos.length, 1); assert.strictEqual(o1.pos[0].provisional, true); assert.strictEqual(o1.pos[0].costUsd, 4.91);   // 5 x 0.98 + fee 0.01
  assert.ok(o1.w.attempts >= 2 && o1.w.filledContracts === 5);
  assert.strictEqual(o2.pos.length, 1); assert.ok(o2.halted.some(h => /outcome unknown/.test(h)));
  const fills = fs.readFileSync(f, 'utf8').split('\n').filter(l => /"ev":"FILL"/.test(l)).length;
  assert.strictEqual(fills, 1, 'provisional FILL written once, got ' + fills);
  assert.strictEqual(mkLedger(f).verify().ok, true);
});

/* 4. a LIVE trader does not restore paper positions; the forward record is kept per mode */
const { privateKey } = crypto.generateKeyPairSync('rsa', { modulusLength: 2048 });
const PEM = privateKey.export({ type: 'pkcs8', format: 'pem' });
const ARMED = { LIVE: '1', TRADER_LIVE_ARM: 'I-ACCEPT-REAL-MONEY-RISK', KALSHI_KEY_ID: 'k', KALSHI_PRIVATE_KEY: PEM, KALSHI_BASE: 'http://127.0.0.1:9/trade-api/v2' };
t('LIVE restore: paper positions dropped, real ones kept; forward record per mode; paper losses do not count toward the live day', () => {
  const f = path.join(TMP, 'mode.jsonl'), L = mkLedger(f);
  L.append(fill('p1', 'DRY-RUN')); L.append(settled('p1', 'DRY-RUN', false)); L.append({ ev: 'RESUME' });
  L.append(fill('p2', 'DRY-RUN', { closeMs: NOW + 600e3 }));
  L.append(fill('l1', 'LIVE')); L.append(settled('l1', 'LIVE', true));
  L.append(fill('l2', 'LIVE', { closeMs: NOW + 600e3 }));
  const o = child({ ...ARMED, TRADER_LEDGER_FILE: f }, `T.restoreFromLedger(); out.mode = T.MODE; out.pos = T.ST.positions.map(p => p.id); out.stats = T.stats(); out.realized = T.ST.realizedTodayUsd; out.cl = T.ST.consecutiveLosses;`);
  assert.strictEqual(o.mode, 'LIVE'); assert.deepStrictEqual(o.pos, ['l2']);
  assert.strictEqual(o.stats.forward.mode, 'LIVE'); assert.strictEqual(o.stats.forward.won, 1); assert.strictEqual(o.stats.forward.lost, 0);
  assert.strictEqual(o.stats.otherMode.lost, 1); assert.strictEqual(o.realized, 0.04); assert.strictEqual(o.cl, 0);
});

/* 5. arming preconditions */
t('LIVE does not arm without an explicit TRADER_LEDGER_FILE', () => {
  const o = child({ ...ARMED, TRADER_LEDGER_FILE: '' }, `out.mode = T.MODE; out.note = T.MODE_NOTE;`);
  assert.strictEqual(o.mode, 'DRY-RUN'); assert.ok(/TRADER_LEDGER_FILE not set/.test(o.note), o.note);
});
t('LIVE does not arm with a private key that cannot sign', () => {
  const o = child({ ...ARMED, KALSHI_PRIVATE_KEY: 'not-a-key', TRADER_LEDGER_FILE: path.join(TMP, 'k.jsonl') }, `out.mode = T.MODE; out.note = T.MODE_NOTE;`);
  assert.strictEqual(o.mode, 'DRY-RUN'); assert.ok(/cannot sign/.test(o.note), o.note);
});
t('a key with its newlines collapsed (accepted by the engine) arms and signs', () => {
  const o = child({ ...ARMED, KALSHI_PRIVATE_KEY: PEM.replace(/\n/g, ' '), TRADER_LEDGER_FILE: path.join(TMP, 'k2.jsonl') }, `out.mode = T.MODE; out.sig = !!T.kalshi.signRequest('POST', '/x')['KALSHI-ACCESS-SIGNATURE'];`);
  assert.strictEqual(o.mode, 'LIVE'); assert.strictEqual(o.sig, true);
});
t('a failing ledger write is a halt reason', () => {
  const o = child({ TRADER_LEDGER_FILE: path.join(TMP, 'no-such-dir', 'x.jsonl') }, `T.ledger.append({ ev: 'BOOT' }); out.halted = T.haltReasons();`);
  assert.ok(o.halted.some(h => /ledger write failing/.test(h)), JSON.stringify(o.halted));
});

/* 6. restored windows are not summarised again */
t('restart does not write duplicate WINDOW records', () => {
  const f = path.join(TMP, 'win.jsonl'), L = mkLedger(f);
  L.append({ ev: 'ORDER_ATTEMPT', ticker: 'KXBTC15M-Z', closeMs: NOW - 600e3, side: 'UP', attempt: 1, clientOrderId: 'pr5-KXBTC15M-Z-a1', contracts: 5, limitCents: 99, mode: 'DRY-RUN', modeled: {} });
  L.append({ ev: 'ORDER_RESULT', ticker: 'KXBTC15M-Z', clientOrderId: 'pr5-KXBTC15M-Z-a1', kind: 'paper', filled: 5 });
  L.append({ ev: 'WINDOW', ticker: 'KXBTC15M-Z', closeMs: NOW - 600e3 });
  child({ TRADER_LEDGER_FILE: f }, `T.restoreFromLedger(); T.summarizeWindows(Date.now());`);
  assert.strictEqual(fs.readFileSync(f, 'utf8').split('\n').filter(l => /"ev":"WINDOW"/.test(l)).length, 1);
});

/* 7. non-binary settlement */
t('a finalized market without a yes/no result settles at P&L 0 and frees the exposure', () => {
  const f = path.join(TMP, 'void.jsonl'), L = mkLedger(f);
  L.append(fill('v1', 'DRY-RUN', { closeMs: NOW - 60e3 }));
  const o = child({ TRADER_LEDGER_FILE: f }, `T.restoreFromLedger(); T.kalshi.marketResult = async () => ({ result: 'void', official: null, nonBinary: true });
    await T.settleOpen(Date.now()); out.pos = T.ST.positions.length; out.stats = T.stats().forward; out.cl = T.ST.consecutiveLosses;`);
  assert.strictEqual(o.pos, 0); assert.strictEqual(o.stats.void, 1); assert.strictEqual(o.stats.lost, 0); assert.strictEqual(o.cl, 0);
});

/* 7b. trade count: a provisional order that reconcile found unfilled is not a trade, in-process or after a restart */
t('tradesToday: provisional order later reconciled as unfilled counts 0 after a restart', () => {
  const f = path.join(TMP, 'tc.jsonl'), L = mkLedger(f), id = 'pr5-KXBTC15M-T-a1';
  L.append({ ev: 'ORDER_ATTEMPT', ticker: 'KXBTC15M-T', closeMs: NOW - 60e3, side: 'UP', attempt: 1, clientOrderId: id, contracts: 5, limitCents: 99, mode: 'DRY-RUN', modeled: {} });
  L.append({ ev: 'ORDER_RESULT', ticker: 'KXBTC15M-T', clientOrderId: id, kind: 'unknown', filled: 0 });
  L.append(fill(id, 'DRY-RUN', { ticker: 'KXBTC15M-T', provisional: true }));
  L.append({ ev: 'RECONCILED', id, ticker: 'KXBTC15M-T', clientOrderId: id, found: false, filled: 0 });
  const o = child({ TRADER_LEDGER_FILE: f }, `T.restoreFromLedger(); out.trades = T.ST.tradesToday; out.pos = T.ST.positions.length;`);
  assert.strictEqual(o.trades, 0); assert.strictEqual(o.pos, 0);
});

/* 7c. ledger: a failed write is queued and written, in order, once the disk is back; the error then clears */
t('ledger: failed writes are retried in order and the error clears when they land', () => {
  const dir = path.join(TMP, 'later'), f = path.join(dir, 'l.jsonl'), L = mkLedger(f);
  L.append({ ev: 'A' }); assert.ok(L.state.err && L.state.lastOk === false);
  fs.mkdirSync(dir); L.append({ ev: 'B' });
  assert.strictEqual(L.state.err, null); assert.strictEqual(L.state.lastOk, true);
  const v = mkLedger(f).verify(); assert.strictEqual(v.ok, true); assert.strictEqual(v.lines, 2);
  assert.deepStrictEqual(mkLedger(f).all().map(r => r.ev), ['A', 'B']);
});

/* 7d. a provisional LIVE position restored from the ledger is looked up on Kalshi after the restart, armed or disarmed */
function childAsync(env, body) {
  return new Promise(resolve => {
    const script = `(async () => { const T = require('./trader.js'); T.loadEngine(); const out = {}; ${body}; console.log('@@' + JSON.stringify(out)); process.exit(0); })().catch(e => { console.log('@@' + JSON.stringify({ error: String(e.stack || e) })); process.exit(1); });`;
    const p = spawn(process.execPath, ['-e', script], { cwd: ROOT, env: { ...baseEnv(), ...env } });
    let out = ''; p.stdout.on('data', d => out += d); p.stderr.on('data', d => out += d);
    p.on('exit', () => { const l = out.split('\n').find(x => x.startsWith('@@')); resolve(l ? JSON.parse(l.slice(2)) : { error: out.slice(0, 800) }); });
  });
}
async function reconcileAfterRestart() {
  const http = require('http'); let gets = 0;
  const srv = http.createServer((req, res) => {
    const u = new URL(req.url, 'http://x');
    if (u.pathname === '/trade-api/v2/portfolio/orders') { gets++; res.setHeader('Content-Type', 'application/json');
      return res.end(JSON.stringify({ cursor: '', orders: [{ client_order_id: 'pr5-KXBTC15M-R-a1', ticker: 'KXBTC15M-R', status: 'executed', fill_count_fp: '5.00',
        taker_fill_cost_dollars: '4.9500', maker_fill_cost_dollars: '0', taker_fees_dollars: '0.0100', maker_fees_dollars: '0' }] })); }
    res.statusCode = 404; res.end('{}');
  });
  await new Promise(r => srv.listen(0, '127.0.0.1', r));
  const base = 'http://127.0.0.1:' + srv.address().port + '/trade-api/v2';
  const mkL = n => { const f = path.join(TMP, n), L = mkLedger(f), id = 'pr5-KXBTC15M-R-a1';
    L.append({ ev: 'ORDER_ATTEMPT', ticker: 'KXBTC15M-R', closeMs: NOW - 60e3, strike: 82000, side: 'UP', attempt: 1, clientOrderId: id, contracts: 5, limitCents: 99, maxCostUsd: 4.96, mode: 'LIVE', modeled: {} });
    L.append({ ev: 'ORDER_RESULT', ticker: 'KXBTC15M-R', clientOrderId: id, kind: 'unknown', filled: 0 });
    L.append(fill(id, 'LIVE', { ticker: 'KXBTC15M-R', provisional: true }));
    return f; };
  const body = `T.restoreFromLedger(); await new Promise(r => setTimeout(r, 6500)); out.pos = T.ST.positions.map(p => ({ provisional: p.provisional, contracts: p.contracts, costUsd: p.costUsd }));
    out.reconciled = T.ledger.all().filter(r => r.ev === 'RECONCILED').length;`;
  const armed = await childAsync({ ...ARMED, KALSHI_BASE: base, TRADER_LEDGER_FILE: mkL('rec_armed.jsonl') }, body);
  const disarmed = await childAsync({ KALSHI_KEY_ID: 'k', KALSHI_PRIVATE_KEY: PEM, KALSHI_BASE: base, TRADER_LEDGER_FILE: mkL('rec_dry.jsonl') }, body);
  srv.close();
  return { armed, disarmed, gets };
}

/* 8. HTTP: admin-only routes, POST-only resume, malformed engine routes do not crash the process */
async function httpCases() {
  const f = path.join(TMP, 'http.jsonl');
  const script = `const T = require('./trader.js'); T.loadEngine(); process.on('unhandledRejection', e => { console.log('UNHANDLED ' + e); });
    T.server.listen(0, '127.0.0.1', () => console.log('PORT ' + T.server.address().port));`;
  const p = spawn(process.execPath, ['-e', script], { cwd: ROOT, env: { ...baseEnv(), TRADER_LEDGER_FILE: f, TRADER_ADMIN_TOKEN: 'tok-123', TRADER_VIEW_TOKEN: 'view-9' } });
  let buf = ''; p.stdout.on('data', d => buf += d); p.stderr.on('data', d => buf += d);
  const port = await new Promise((res, rej) => { const iv = setInterval(() => { const m = buf.match(/PORT (\d+)/); if (m) { clearInterval(iv); res(+m[1]); } }, 50); setTimeout(() => { clearInterval(iv); rej(new Error('no port: ' + buf)); }, 30000); });
  const base = 'http://127.0.0.1:' + port;
  const req = (pth, o = {}) => fetch(base + pth, o).then(async r => ({ status: r.status, cors: r.headers.get('access-control-allow-origin'), text: await r.text() }));
  const out = {};
  out.lcNoTok = await req('/livecheck'); out.lcBad = await req('/livecheck', { headers: { 'X-Admin-Token': 'nope' } }); out.lcOk = await req('/livecheck', { headers: { 'X-Admin-Token': 'tok-123' } });
  out.halt1 = await req('/halt?on=1'); out.halt1b = await req('/halt?on=1');
  out.resumeGet = await req('/halt?on=0&token=tok-123'); out.resumeBad = await req('/halt?on=0', { method: 'POST', headers: { 'X-Admin-Token': 'x' } });
  out.resumeQuery = await req('/halt?on=0&token=tok-123', { method: 'POST' }); out.resumeOk = await req('/halt?on=0', { method: 'POST', headers: { 'X-Admin-Token': 'tok-123' } });
  out.eng1 = await fetch(base + '/engine//x:99999?token=view-9').then(r => r.status).catch(e => 'ERR ' + e.message);
  out.eng2 = await req('/engine/health?token=view-9');
  out.badN = await req('/ledger?n=abc&token=view-9');
  out.statsNoTok = await req('/stats'); out.statsTok = await req('/stats', { headers: { 'X-View-Token': 'view-9' } }); out.funnel = await req('/funnel?token=view-9');
  out.healthOpen = await req('/health');
  out.alive = await req('/health').then(r => r.status).catch(e => 'ERR ' + e.message);
  p.kill('SIGKILL');
  return { out, log: buf, ledger: fs.readFileSync(f, 'utf8') };
}

(async () => {
  let rr = null; try { rr = await reconcileAfterRestart(); } catch (e) { results.push([false, 'reconcile harness :: ' + e.message]); }
  if (rr) t('a restored provisional LIVE position is reconciled after a restart (armed, and disarmed with credentials)', () => {
    for (const o of [rr.armed, rr.disarmed]) { assert.ok(!o.error, o.error); assert.strictEqual(o.reconciled, 1, JSON.stringify(o)); assert.deepStrictEqual(o.pos, [{ provisional: false, contracts: 5, costUsd: 4.96 }]); }
    assert.strictEqual(rr.gets, 2);
  });
  let h = null; try { h = await httpCases(); } catch (e) { results.push([false, 'http harness :: ' + e.message]); }
  if (h) {
    const o = h.out;
    t('/livecheck needs the admin token (403 without or with a wrong one) and sends no CORS header', () => {
      assert.strictEqual(o.lcNoTok.status, 403); assert.strictEqual(o.lcBad.status, 403); assert.strictEqual(o.lcOk.status, 200);
      assert.strictEqual(o.lcNoTok.cors, null); assert.strictEqual(o.lcOk.cors, null);
    });
    t('resume is POST-only with the X-Admin-Token header (GET and a query token are refused); a repeated halt is written once', () => {
      assert.strictEqual(o.resumeGet.status, 405); assert.strictEqual(o.resumeBad.status, 403); assert.strictEqual(o.resumeQuery.status, 403); assert.strictEqual(o.resumeOk.status, 200);
      assert.strictEqual(h.ledger.split('\n').filter(l => /manual halt/.test(l)).length, 1); assert.strictEqual(h.ledger.split('\n').filter(l => /"ev":"RESUME"/.test(l)).length, 1);
    });
    t('a malformed /engine/ route is refused and the process stays up; a valid one still works', () => {
      assert.strictEqual(o.eng1, 404); assert.strictEqual(o.eng2.status, 200); assert.strictEqual(o.alive, 200); assert.ok(!/UNHANDLED|Invalid URL/.test(h.log), h.log.slice(0, 300));
    });
    t('TRADER_VIEW_TOKEN protects the data routes (/stats, /funnel, /ledger); /health stays open', () => {
      assert.strictEqual(o.statsNoTok.status, 403); assert.strictEqual(o.statsTok.status, 200); assert.strictEqual(o.healthOpen.status, 200);
      assert.strictEqual(o.funnel.status, 200); const fj = JSON.parse(o.funnel.text); assert.ok('locked' in fj && 'directional' in fj && 'missedBy' in fj, o.funnel.text.slice(0, 200));
    });
    t('?n= that is not a number falls back to the default', () => { assert.strictEqual(o.badN.status, 200); assert.ok(JSON.parse(o.badN.text).lines.length <= 200); });
  }
  try { fs.rmSync(TMP, { recursive: true, force: true }); } catch (_) { }
  let ok = 0; for (const [pass, n] of results) { console.log((pass ? 'ok   ' : 'FAIL ') + n); if (pass) ok++; }
  console.log(`hardening: ${ok}/${results.length} passed`);
  process.exit(ok === results.length ? 0 : 1);
})();
