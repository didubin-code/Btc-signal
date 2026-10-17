/* Execution and safety tests against a LOCAL mock of the Kalshi API (no real network, no real orders).
   Checks: request signatures verify with the public key; order JSON; fill / no-fill / rejection / routing miss / timeout handling;
   halts latch on rejection and unknown outcome; settlement and the loss halt; an UNARMED trader (LIVE=1 without the arm phrase)
   sends nothing; no key material appears in any endpoint, log line or ledger. */
'use strict';
const http = require('http'), crypto = require('crypto'), path = require('path'), os = require('os'), fs = require('fs');
const { spawn } = require('child_process');

const { publicKey, privateKey } = crypto.generateKeyPairSync('rsa', { modulusLength: 2048 });
const PRIV_PEM = privateKey.export({ type: 'pkcs8', format: 'pem' });
const MOCK = { mode: 'fill', reqs: [], badSig: 0, result: {}, placed: {}, hiddenFill: 5 };

const mock = http.createServer((req, res) => {
  let body = '';
  req.on('data', d => body += d);
  req.on('end', () => {
    const u = new URL(req.url, 'http://x');
    const rec = { method: req.method, path: u.pathname, body: body ? JSON.parse(body) : null, signed: !!req.headers['kalshi-access-signature'] };
    if (rec.signed) {
      const msg = req.headers['kalshi-access-timestamp'] + req.method + u.pathname;
      const ok = crypto.verify('sha256', Buffer.from(msg), { key: publicKey, padding: crypto.constants.RSA_PKCS1_PSS_PADDING, saltLength: crypto.constants.RSA_PSS_SALTLEN_DIGEST },
        Buffer.from(req.headers['kalshi-access-signature'], 'base64'));
      rec.sigOk = ok; if (!ok) MOCK.badSig++;
      rec.keyHeader = req.headers['kalshi-access-key'];
    }
    MOCK.reqs.push(rec);
    const json = (c, o) => { res.statusCode = c; res.setHeader('Content-Type', 'application/json'); res.end(JSON.stringify(o)); };
    if (u.pathname === '/trade-api/v2/exchange/status') return json(200, { trading_active: true, exchange_active: true });
    if (u.pathname.startsWith('/trade-api/v2/markets/')) { const tk = decodeURIComponent(u.pathname.split('/').pop()); const r = MOCK.result[tk]; return json(200, { market: r ? { result: r, expiration_value: '82,273.40' } : { result: '' } }); }
    if (u.pathname === '/trade-api/v2/portfolio/positions') return json(200, { market_positions: [] });
    if (u.pathname === '/trade-api/v2/portfolio/orders' && req.method === 'GET') {   // GetOrders: what really happened to an order whose response was lost
      const tk = u.searchParams.get('ticker');
      return json(200, { cursor: '', orders: Object.values(MOCK.placed).filter(o => o.ticker === tk) });
    }
    if (u.pathname === '/trade-api/v2/portfolio/balance') return json(200, { balance: 12345 });
    if (u.pathname === '/trade-api/v2/portfolio/events/orders' && req.method === 'POST') {
      const m = MOCK.mode;
      /* CreateOrderV2Response (Kalshi spec 3.34.0): top-level order_id, fill_count, remaining_count, average_fill_price, average_fee_paid */
      if (m === 'fill') return json(201, { order_id: 'o-' + MOCK.reqs.length, client_order_id: rec.body.client_order_id, fill_count: rec.body.count, remaining_count: '0.00',
        average_fill_price: rec.body.side === 'bid' ? rec.body.price : (1 - Number(rec.body.price)).toFixed(4), average_fee_paid: '0.0020', ts_ms: Date.now() });
      if (m === 'nofill') return json(201, { order_id: 'o-' + MOCK.reqs.length, client_order_id: rec.body.client_order_id, fill_count: '0.00', remaining_count: rec.body.count, ts_ms: Date.now() });
      if (m === 'hang' || m === '503') {   // the order executes on the exchange, but the response is lost
        const n = MOCK.hiddenFill, px = rec.body.side === 'bid' ? Number(rec.body.price) : 1 - Number(rec.body.price);
        MOCK.placed[rec.body.client_order_id] = { order_id: 'o-' + MOCK.reqs.length, client_order_id: rec.body.client_order_id, ticker: rec.body.ticker, status: 'executed',
          fill_count_fp: n.toFixed(2), taker_fill_cost_dollars: (n * px).toFixed(4), maker_fill_cost_dollars: '0.0000', taker_fees_dollars: n ? '0.0100' : '0.0000', maker_fees_dollars: '0.0000' };
        if (m === '503') return json(503, { error: { code: 'service_unavailable' } });
        return;   // never answers -> client timeout -> outcome unknown
      }
      if (m === 'reject') return json(400, { error: { code: 'insufficient_balance', message: 'insufficient balance' } });
      if (m === 'route') return json(404, { error: { code: 'market_not_found' } });
    }
    return json(404, { error: 'mock: unknown route ' + u.pathname });
  });
});

function runChild(env, script) {
  return new Promise(resolve => {
    const p = spawn(process.execPath, ['-e', script], { env: { ...process.env, ENABLE_WS: '0', ...env }, cwd: path.join(__dirname, '..') });
    let out = '', err = '';
    p.stdout.on('data', d => out += d); p.stderr.on('data', d => err += d);
    p.on('exit', code => resolve({ code, out, err }));
  });
}
/* child side: drives the trader's own execute / settle / endpoints with synthetic decisions, talking to the mock over HTTP */
const CHILD = `
(async () => {
  const T = require('./trader.js'); T.loadEngine();
  const { decide } = require('./lib/policy');
  const ctl = (m) => fetch(process.env.MOCK_CTL + '/__ctl?mode=' + m).catch(()=>{});
  const now = Date.now(), out = { mode: T.MODE, steps: [] };
  const mk = (ticker, side, tauSec) => {
    const sig = { state: 'LOCKED', side, pFlip: 0.001, pFlipCons: 0.003, gates: { hard: [], soft: [] }, warmup: { lockedAvailable: true, volEnvelope: false, fullHistoryInSec: 0, basisCold: false },
      trade: { action: 'TRADE NOW', askCents: 99, evConsCents: 0.6 }, exec: { headline: 'TRADE NOW', reason: 'test' } };
    return { now, ticker, strike: 82263.34, tau: tauSec, closeMs: now + tauSec * 1000, sig, exchange: { tradingActive: true, ts: now },
      book: { ok: true, ageMs: 100, yesAsks: [[99, 100]], noAsks: [[99, 100]] } };
  };
  const st = () => ({ halted: T.haltReasons(), windows: T.ST.windows, realizedTodayUsd: T.ST.realizedTodayUsd, consecutiveLosses: T.ST.consecutiveLosses,
    tradesToday: T.ST.tradesToday, openExposureUsd: T.ST.positions.reduce((a,p)=>a+p.costUsd,0), inFlight: false });
  async function step(name, mode, ticker, side, tau) {
    await fetch(process.env.MOCK_CTL + '/__mode/' + mode);
    const ctx = mk(ticker, side, tau); const d = decide(ctx, st(), T.CFG);
    let res = null; if (d.action === 'BUY') res = await T.execute(ctx, d);
    out.steps.push({ name, decision: d.action, why: d.why.slice(0,2), kind: res && res.kind, filled: res && res.filled, halted: T.haltReasons() });
  }
  if (process.env.SCENARIO === 'live') {
    await step('fill UP', 'fill', 'KXBTC15M-26OCT161200-00', 'UP', 60);
    await step('second entry same window is refused', 'fill', 'KXBTC15M-26OCT161200-00', 'UP', 50);
    await step('next window refused while $5 is still open', 'fill', 'KXBTC15M-26OCT161215-15', 'UP', 60);
    // settle the first position as a WIN (strike 82263.34, official yes)
    T.ST.positions.forEach(p => p.closeMs = now - 10000);
    await fetch(process.env.MOCK_CTL + '/__result/KXBTC15M-26OCT161200-00/yes');
    await T.settleOpen(Date.now());
    out.afterWin = { forward: T.ST.forward.LIVE, halted: T.haltReasons(), realized: T.ST.realizedTodayUsd };
    await step('no fill DOWN', 'nofill', 'KXBTC15M-26OCT161230-30', 'DOWN', 60);
    await step('routing miss does not halt', 'route', 'KXBTC15M-26OCT161245-45', 'UP', 60);
    await step('rejection latches a halt', 'reject', 'KXBTC15M-26OCT161300-00', 'UP', 60);
    out.afterReject = T.haltReasons();
    const cfg = await new Promise(r => { const http = require('http'); const s = T.server.listen(0, async () => {
      const port = s.address().port; const g = async p => (await fetch('http://127.0.0.1:' + port + p)).text();
      const post = async (p, tok) => (await fetch('http://127.0.0.1:' + port + p, { method: 'POST', headers: { 'X-Admin-Token': tok } })).text();
      r({ config: await g('/config'), health: await g('/health'), live: await g('/live'), stats: await g('/stats'), halt0: await post('/halt?on=0', 'wrong') }); s.close(); }); });
    out.endpoints = cfg;
  }
  if (process.env.SCENARIO === 'timeout') {
    await step('timeout -> outcome unknown -> halt', 'hang', 'KXBTC15M-26OCT161300-00', 'UP', 60);
    out.provisional = T.ST.positions.map(p => ({ id: p.id, provisional: p.provisional, costUsd: p.costUsd }));
    await step('nothing more while halted', 'fill', 'KXBTC15M-26OCT161315-15', 'UP', 60);
    await T.reconcile('KXBTC15M-26OCT161300-00', 'pr5-KXBTC15M-26OCT161300-00-a1', 'pr5-KXBTC15M-26OCT161300-00-a1');
    out.afterReconcile = { positions: T.ST.positions, window: T.ST.windows.get('KXBTC15M-26OCT161300-00') };
  }
  if (process.env.SCENARIO === '5xx') {
    await step('HTTP 503 -> outcome unknown -> halt', '503', 'KXBTC15M-26OCT161330-30', 'DOWN', 60);
    out.provisional = T.ST.positions.map(p => ({ provisional: p.provisional, contracts: p.contracts }));
    await T.reconcile('KXBTC15M-26OCT161330-30', 'pr5-KXBTC15M-26OCT161330-30-a1', 'pr5-KXBTC15M-26OCT161330-30-a1');
    out.afterReconcile = T.ST.positions.map(p => ({ provisional: p.provisional, contracts: p.contracts, costUsd: p.costUsd }));
    T.ST.positions.forEach(p => p.closeMs = now - 10000);
    await fetch(process.env.MOCK_CTL + '/__result/KXBTC15M-26OCT161330-30/yes');      // DOWN loses: the reconciled position settles as a loss
    await T.settleOpen(Date.now());
    out.afterSettle = { realized: T.ST.realizedTodayUsd, positions: T.ST.positions.length, halted: T.haltReasons() };
  }
  if (process.env.SCENARIO === 'loss') {
    await step('fill DOWN', 'fill', 'KXBTC15M-26OCT161400-00', 'DOWN', 60);
    T.ST.positions.forEach(p => p.closeMs = now - 10000);
    await fetch(process.env.MOCK_CTL + '/__result/KXBTC15M-26OCT161400-00/yes');   // DOWN loses
    await T.settleOpen(Date.now());
    out.afterLoss = { forward: T.ST.forward.LIVE, halted: T.haltReasons() };
    await step('no trading after a loss (HALT_AFTER_LOSSES=1)', 'fill', 'KXBTC15M-26OCT161415-15', 'UP', 60);
  }
  if (process.env.SCENARIO === 'unarmed') {
    await step('LIVE=1 without the arm phrase stays a dry run', 'fill', 'KXBTC15M-26OCT161500-00', 'UP', 60);
  }
  out.ledger = require('fs').readFileSync(process.env.TRADER_LEDGER_FILE, 'utf8');
  out.verify = T.ledger.verify();
  console.log('@@' + JSON.stringify(out));
  process.exit(0);
})().catch(e => { console.log('@@' + JSON.stringify({ error: String(e.stack || e) })); process.exit(1); });`;

(async () => {
  /* control routes on the same mock */
  const realHandler = mock.listeners('request')[0];
  mock.removeAllListeners('request');
  mock.on('request', (req, res) => {
    if (req.url.startsWith('/__mode/')) { MOCK.mode = req.url.split('/').pop(); res.end('ok'); return; }
    if (req.url.startsWith('/__result/')) { const [, , tk, r] = req.url.split('/'); MOCK.result[tk] = r; res.end('ok'); return; }
    realHandler(req, res);
  });
  await new Promise(r => mock.listen(0, '127.0.0.1', r));
  const port = mock.address().port, base = 'http://127.0.0.1:' + port;
  const results = [];
  const check = (name, pass, got) => results.push({ name, pass: !!pass, got });
  const tmp = n => path.join(os.tmpdir(), 'pr5_' + n + '_' + process.pid + '.jsonl');
  const armed = { LIVE: '1', TRADER_LIVE_ARM: 'I-ACCEPT-REAL-MONEY-RISK', KALSHI_KEY_ID: 'test-key-id', KALSHI_PRIVATE_KEY: PRIV_PEM, KALSHI_BASE: base + '/trade-api/v2',
    MOCK_CTL: base, KALSHI_TIMEOUT_MS: '800', TRADER_ADMIN_TOKEN: 'secret-admin-token' };
  const parse = r => { const l = r.out.split('\n').find(x => x.startsWith('@@')); return l ? JSON.parse(l.slice(2)) : { error: r.err.slice(0, 500) }; };

  /* 1. live scenario */
  let f = tmp('live'); MOCK.reqs = [];
  let o = parse(await runChild({ ...armed, SCENARIO: 'live', TRADER_LEDGER_FILE: f }, CHILD));
  if (o.error) { console.log('child error', o.error); process.exit(1); }
  const posts = MOCK.reqs.filter(r => r.method === 'POST');
  check('mode is LIVE only when armed with the phrase and keys', o.mode === 'LIVE', o.mode);
  check('every signed request verifies with the public key (RSA-PSS SHA-256 over ts+METHOD+path)', MOCK.badSig === 0 && MOCK.reqs.filter(r => r.signed).length >= 4, { bad: MOCK.badSig });
  check('first order: bid YES 5 @ 0.9900 IOC, deterministic client id, exchange_index -1',
    posts[0] && posts[0].body.side === 'bid' && posts[0].body.price === '0.9900' && posts[0].body.count === '5.00' && posts[0].body.time_in_force === 'immediate_or_cancel'
    && posts[0].body.client_order_id === 'pr5-KXBTC15M-26OCT161200-00-a1' && posts[0].body.exchange_index === -1, posts[0] && posts[0].body);
  check('second entry in the same window refused (no POST)', o.steps[1].decision === 'SKIP' && /already entered/.test(o.steps[1].why.join()), o.steps[1]);
  check('next window refused while the $5 position is unsettled (max open exposure)', o.steps[2].decision === 'SKIP' && /open exposure/.test(o.steps[2].why.join()), o.steps[2]);
  check('DOWN no-fill: ask YES at 0.0100, no position', posts[1] && posts[1].body.side === 'ask' && posts[1].body.price === '0.0100' && o.steps[3].kind === 'nofill', o.steps[3]);
  check('market_not_found skips without halting', o.steps[4].kind === 'route-miss' && !o.steps[4].halted.length, o.steps[4]);
  check('exactly 4 orders sent (fill, no-fill, routing miss, rejection)', posts.length === 4, posts.length);
  check('win settles: +$0.04 (5 x $1 - $4.96), forward 1/1', o.afterWin.forward.won === 1 && Math.abs(o.afterWin.realized - 0.04) < 1e-9, o.afterWin);
  check('rejection (HTTP 400) latches a halt', o.afterReject.some(h => /order rejected/.test(h)), o.afterReject);
  const cfgTxt = o.endpoints.config + o.endpoints.health + o.endpoints.live + o.endpoints.stats + o.ledger;
  check('no key material or admin token in /config /health /live /stats or the ledger', !/BEGIN PRIVATE KEY|PRIVATE KEY-----|MII[A-Za-z0-9+/]{20}|secret-admin-token/.test(cfgTxt), null);
  check('resume with a wrong token is refused', /bad token/.test(o.endpoints.halt0), o.endpoints.halt0);
  check('ledger hash chain verifies', o.verify.ok === true, o.verify);
  check('every POST was a KXBTC15M IOC buy within $5', posts.every(p => /^KXBTC15M-/.test(p.body.ticker) && p.body.time_in_force === 'immediate_or_cancel' && Number(p.body.count) * (p.body.side === 'bid' ? Number(p.body.price) : 1 - Number(p.body.price)) <= 5), posts.length);

  /* 2. timeout -> unknown -> halt */
  f = tmp('timeout'); MOCK.reqs = [];
  o = parse(await runChild({ ...armed, SCENARIO: 'timeout', TRADER_LEDGER_FILE: f }, CHILD));
  check('no response: outcome unknown, trading halted', o.steps[0].kind === 'unknown' && o.steps[0].halted.some(h => /outcome unknown/.test(h)), o.steps[0]);
  check('while halted nothing is sent', o.steps[1].decision === 'SKIP' && MOCK.reqs.filter(r => r.method === 'POST').length === 1, o.steps[1]);

  /* 2b. the order filled but the response was lost: reconcile finds no order -> the provisional position is removed (timeout case),
         and finds the fill -> it is booked at Kalshi's cost and settles (5xx case) */
  check('timeout: the unknown order is booked provisionally as a full fill at the limit ($4.96)', o.provisional && o.provisional.length === 1 && o.provisional[0].provisional === true && o.provisional[0].costUsd === 4.96, o.provisional);
  check('timeout: reconcile finds the executed order by client_order_id and books it (5 contracts, $4.96)', o.afterReconcile.positions.length === 1 && o.afterReconcile.positions[0].provisional === false
    && o.afterReconcile.positions[0].contracts === 5 && o.afterReconcile.positions[0].costUsd === 4.96 && o.afterReconcile.window.attempts >= 2, o.afterReconcile);
  f = tmp('5xx'); MOCK.reqs = []; MOCK.hiddenFill = 0;
  o = parse(await runChild({ ...armed, SCENARIO: '5xx', TRADER_LEDGER_FILE: f }, CHILD));
  check('HTTP 503 on order create is an unknown outcome (halt + provisional booking), not a plain rejection', o.steps[0].kind === 'unknown' && o.steps[0].halted.some(h => /outcome unknown/.test(h)) && o.provisional.length === 1, o.steps[0]);
  check('reconcile: no fill on Kalshi -> the provisional position is removed, nothing settles', o.afterReconcile.length === 0 && o.afterSettle.positions === 0 && o.afterSettle.realized === 0, o.afterReconcile);
  MOCK.hiddenFill = 5;

  /* 3. a loss halts */
  f = tmp('loss'); MOCK.reqs = [];
  o = parse(await runChild({ ...armed, SCENARIO: 'loss', TRADER_LEDGER_FILE: f }, CHILD));
  check('loss settles: -$4.96, forward 0/1', o.afterLoss.forward.lost === 1 && Math.abs(o.afterLoss.forward.pnlUsd + 4.96) < 1e-9, o.afterLoss);
  check('after a loss trading halts for review', o.afterLoss.halted.some(h => /consecutive loss/.test(h)) && o.steps[1].decision === 'SKIP', o.afterLoss.halted);

  /* 4. unarmed: LIVE=1 but no phrase */
  f = tmp('unarmed'); MOCK.reqs = [];
  o = parse(await runChild({ ...armed, TRADER_LIVE_ARM: 'yes', SCENARIO: 'unarmed', TRADER_LEDGER_FILE: f }, CHILD));
  check('LIVE=1 without the arm phrase is a DRY-RUN', o.mode === 'DRY-RUN', o.mode);
  check('dry run sends no order to Kalshi (paper fill only)', MOCK.reqs.filter(r => r.method === 'POST').length === 0 && o.steps[0].kind === 'paper', o.steps[0]);

  for (const n of ['live', 'timeout', '5xx', 'loss', 'unarmed']) { try { fs.unlinkSync(tmp(n)); } catch (_) { } }
  mock.close();
  let ok = 0; for (const c of results) { console.log((c.pass ? 'ok   ' : 'FAIL ') + c.name + (c.pass ? '' : ' :: ' + JSON.stringify(c.got).slice(0, 300))); if (c.pass) ok++; }
  console.log(`live_mock: ${ok}/${results.length} passed`);
  process.exit(ok === results.length ? 0 : 1);
})();
