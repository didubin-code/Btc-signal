/* Engine replay (regression): the REAL embedded Pin Radar 2.8.1 engine (LOCK_MAX_FLIP 0.002) and the trader's own main loop
   (tick(): evaluate -> decide -> execute -> settleOpen -> summarizeWindows), in DRY-RUN, driven second by second through real
   history the way the validation replays were run (validation/replay_chrono.js in btc-ai-backend):
     * prices: Binance BTCUSDC 1 Hz (the validation's substitute feed) driving the three index venues, venue quote age 50 ms;
     * markets: real Kalshi KXBTC15M strikes and official results (markets_usdc.ndjson); the official value reaches the engine's
       basis model 5 s after the close, and the trader's settlement 5 s after the close (no look-ahead);
     * one engine background tick (mutate:true, as bgTick does) then one trader tick per second, 750 ms into the second;
     * order book: SYNTHETIC. Kalshi keeps no order-book history; each second the book holds only the levels real Kalshi prints
       showed in the previous 15 s, sized by what printed there. Fills and P&L below are therefore NOT an execution estimate
       (the validation's print-based execution study is exec_thr02_usdc_full.json); they only exercise the order path.
   Checks:
     * every order the trader sent was LOCKED with modelled flip risk <= 0.2 %, >= 15 s left, priced 90-99 c, <= $5, DRY-RUN;
     * at most one fill per window, nothing sent while halted, the ledger chain verifies, no tick errors;
     * every eligible contract in the range was evaluated (one WINDOW record each);
     * regression: the trader's first LOCKED second and side per window equal the 0.2 % validation replay (replay/thr02_usdc.ndjson),
       i.e. the embedded engine and the read-only readings reproduce the validated verdicts.
   Data: PR_DATA (default /home/user/data_val, built by the btc-ai-backend validation pipeline). Absent -> SKIPPED (exit 0).
   Range: PR_REPLAY_FROM / PR_REPLAY_TO (default 2026-08-01 .. 2026-08-02 UTC, 96 windows), PR_REPLAY_WARM (default 86400 s, the
   validation chunks' warm-up; the August chunk started at 2026-08-01T00:00Z, so the default range is directly comparable). */
'use strict';
const fs = require('fs'), path = require('path'), os = require('os'), zlib = require('zlib');
const DATA = process.env.PR_DATA || '/home/user/data_val';
const SEC = path.join(DATA, 'sec'), MARKETS = path.join(DATA, 'kalshi', 'markets_usdc.ndjson'), TRADES = path.join(DATA, 'kalshi', 'trades');
const REF = path.join(DATA, 'replay', 'thr02_usdc.ndjson');
const FROM = process.env.PR_REPLAY_FROM || '2026-08-01T00:00:00Z', TO = process.env.PR_REPLAY_TO || '2026-08-02T00:00:00Z';
const WARM = Number(process.env.PR_REPLAY_WARM || 86400), HOR = 300, PHASE = 750, QA = 50, LAG = 5, BOOK_LOOKBACK_MS = 15000;
if (!fs.existsSync(path.join(SEC, 'usdc')) || !fs.existsSync(MARKETS) || !fs.existsSync(TRADES)) {
  console.log('engine_replay: SKIPPED (historical data not found under ' + DATA + '; set PR_DATA)'); process.exit(0);
}

/* the trader reads its configuration at require time: dry run, a throw-away ledger, shipped defaults otherwise */
const LEDGER = path.join(os.tmpdir(), 'pr5_replay_ledger_' + process.pid + '.jsonl');
Object.assign(process.env, { ENABLE_WS: '0', PINRADAR_REPLAY: '1', TRADER_LEDGER_FILE: LEDGER, LIVE: '0', TRADER_HALT: '' });
for (const k of ['KALSHI_KEY_ID', 'KALSHI_PRIVATE_KEY', 'TRADER_LIVE_ARM', 'LOCK_MAX_FLIP', 'MAX_TRADE_USD', 'TRADER_HALT_FILE']) delete process.env[k];
const realNow = Date.now; let NOW = Date.parse(FROM) - WARM * 1000; Date.now = () => NOW;
const T = require('../trader');
const S = T.loadEngine();

const t0 = Math.floor(Date.parse(FROM) / 1000), t1 = Math.floor(Date.parse(TO) / 1000);
const markets = fs.readFileSync(MARKETS, 'utf8').split('\n').filter(Boolean).map(l => JSON.parse(l))
  .filter(m => m.closeTs > t0 - WARM && m.closeTs <= t1 + 900).sort((a, b) => a.closeTs - b.closeTs);
const byTicker = new Map(markets.map(m => [m.ticker, m]));
/* settlement through the trader's own code path; the result is released only after the close + LAG (no look-ahead) */
T.kalshi.marketResult = async ticker => { const m = byTicker.get(ticker); return m && Date.now() >= (m.closeTs + LAG) * 1000 && (m.result === 'yes' || m.result === 'no') ? { result: m.result, official: m.official } : null; };

/* ---- 1 Hz prices (as replay_chrono.js, proxy mode, proxy dir usdc) ---- */
const cache = new Map();
function dayArr(day) {
  if (cache.has(day)) return cache.get(day);
  const f = path.join(SEC, 'usdc', day + '.f64'); let a = null;
  if (fs.existsSync(f)) { const b = fs.readFileSync(f); a = new Float64Array(b.buffer, b.byteOffset, b.length / 8); }
  cache.set(day, a); if (cache.size > 4) cache.delete(cache.keys().next().value); return a;
}
function px(t) { const d = new Date(t * 1000).toISOString().slice(0, 10), a = dayArr(d); if (!a) return NaN; const v = a[t - Date.parse(d + 'T00:00:00Z') / 1000]; return v > 0 ? v : NaN; }
const VMAP = [['coinbase', 0.4], ['kraken', -0.4], ['bitstamp', 0]];
const lastSeen = {};
function setVenues(t, nowMs) {
  const v = px(t);
  for (const [name, off] of VMAP) {
    const V = S.VENUES[name]; if (!V) continue;
    if (Number.isFinite(v)) { Object.assign(V, { mid: v + off, bidDepth: 2, askDepth: 2, lastQuoteTs: nowMs - 40, lastMsgTs: nowMs }); lastSeen[name] = nowMs - 40; }
    else if (lastSeen[name]) V.lastMsgTs = nowMs;
  }
}

/* ---- synthetic Kalshi book from real prints at or before now (see the header) ---- */
const round2 = x => Math.round(x * 100) / 100;
function loadPrints(ticker) {
  const f = path.join(TRADES, ticker + '.json.gz'); if (!fs.existsSync(f)) return null;
  const j = JSON.parse(zlib.gunzipSync(fs.readFileSync(f)).toString('utf8'));
  return (j.trades || []).map(x => ({ ms: Date.parse(String(x.created_time).slice(0, 23) + 'Z'), y: round2(Number(x.yes_price_dollars) * 100), n: Number(x.count_fp), taker: x.taker_side }))
    .filter(p => Number.isFinite(p.ms) && p.y > 0 && p.y < 100 && p.n > 0).sort((a, b) => a.ms - b.ms);
}
function bookAt(ticker, prints, nowMs) {
  const yesBids = new Map(), noBids = new Map();
  for (const p of prints || []) {
    if (p.ms > nowMs) break;
    if (p.ms <= nowMs - BOOK_LOOKBACK_MS) continue;
    if (p.taker === 'yes') { const k = round2(100 - p.y); noBids.set(k, (noBids.get(k) || 0) + p.n); }   // YES bought at y: a YES ask at y = a NO bid at 100 - y
    else if (p.taker === 'no') yesBids.set(p.y, (yesBids.get(p.y) || 0) + p.n);                         // NO bought at 100 - y: a YES bid at y
  }
  if (!yesBids.size && !noBids.size) return null;
  return { ticker, yes: [...yesBids].sort((a, b) => b[0] - a[0]), no: [...noBids].sort((a, b) => b[0] - a[0]) };
}

/* ---- replay ---- */
S.SKEW.samples.length = 0; for (let i = 0; i < 10; i++) S.SKEW.samples.push(20); S.SKEW.estMs = 20;
S.IDX.ring.length = 0; if (S.BASIS) { S.BASIS.samples.length = 0; S.BASIS.byKey.clear(); }
let mi = 0, cur = null, prints = null, settleQ = [], evalSec = 0, bookSec = 0, buyTicks = 0;
const wall = realNow();
async function run() {
  for (let t = t0 - WARM; t < t1 + 60; t++) {
    NOW = t * 1000 + 100;
    setVenues(t, NOW);
    S.sampleIndex();
    while (mi < markets.length && markets[mi].closeTs < t) mi++;
    const m = markets[mi] && markets[mi].closeTs - 900 < t && t <= markets[mi].closeTs ? markets[mi] : null;
    if (m !== cur) { if (cur) settleQ.push({ m: cur, at: cur.closeTs + LAG }); cur = m; prints = m && m.closeTs >= t0 && m.closeTs < t1 ? loadPrints(m.ticker) : null; }
    while (settleQ.length && settleQ[0].at <= t) {                // the engine's basis model gets the official value after the close
      const { m: sm } = settleQ.shift();
      if (Number.isFinite(sm.official)) { const pa = S.proxyWindowAverage(sm.closeTs * 1000);
        if (pa.n >= 57) S.addBasisSample('close:' + sm.closeTs * 1000, pa.mean, sm.official, { ticker: sm.ticker, n: pa.n }); }
    }
    NOW = t * 1000 + PHASE;
    if (t >= t0) { await T.settleOpen(NOW); T.summarizeWindows(NOW); }
    if (!m || m.closeTs < t0 || m.closeTs >= t1) continue;
    S.KAL.market = { ticker: m.ticker, strike: m.strike, closeMs: m.closeTs * 1000, openMs: (m.closeTs - 900) * 1000, status: 'active', yesBid: 50, yesAsk: 51 };
    const tau = m.closeTs - t - PHASE / 1000;
    if (!(tau > 0 && tau <= HOR)) { S.KAL.ob = null; S.KAL.obTs = 0; continue; }
    S.KAL.ts = NOW - 120;
    for (const [name] of VMAP) { const V = S.VENUES[name]; if (V && V.lastQuoteTs > t * 1000) V.lastQuoteTs = NOW - QA; }
    const ob = bookAt(m.ticker, prints, NOW);
    S.KAL.ob = ob; S.KAL.obTs = ob ? NOW - 200 : 0; if (ob) bookSec++;
    /* the engine's own background classifier (bgTick: mutate:true), then the trader's tick (read-only engine readings) */
    const kal = S.getKalshiContext(), liveIdx = S.computeIndex(NOW);
    const used = liveIdx ? Object.values(S.VENUES).filter(v => liveIdx.used.includes(v.name)) : [];
    const age = used.length ? Math.max(...used.map(v => NOW - v.lastQuoteTs)) : Infinity;
    S.computeLockSnapshot({ now: NOW, kal, strike: kal.strike, strikeIssue: null, overrides: [], quality: S.assessQuality(NOW, kal), liveIdx, liveIndexAgeMs: age, side: null, mutate: true });
    await T.tick(); evalSec++;
    if (T.ST.lastDecision && T.ST.lastDecision.action === 'BUY') buyTicks++;
  }
}

run().then(() => {
  Date.now = realNow;
  const rows = T.ledger.tail(1e6);
  const results = [];
  const ok = (name, pass, detail) => results.push([!!pass, name + (detail != null ? ' :: ' + detail : '')]);
  const attempts = rows.filter(r => r.ev === 'ORDER_ATTEMPT'), fills = rows.filter(r => r.ev === 'FILL'), settled = rows.filter(r => r.ev === 'SETTLED');
  const halts = rows.filter(r => r.ev === 'HALT'), windows = rows.filter(r => r.ev === 'WINDOW');
  const bad = attempts.filter(a => !((a.modeled.state === 'LOCKED' || a.modeled.state === 'PROVEN LOCKED') && a.modeled.pFlip != null && a.modeled.pFlip <= 0.002 + 1e-12
    && a.tau >= 15 && a.limitCents >= 90 && a.limitCents <= 99 && a.maxCostUsd <= 5 + 1e-9 && a.mode === 'DRY-RUN' && a.modeled.lockMaxFlip === 0.002));
  ok('every order sent: LOCKED, flip risk <= 0.2 %, >= 15 s left, 90-99 c, <= $5, DRY-RUN', bad.length === 0, attempts.length + ' orders, ' + bad.length + ' violating' + (bad[0] ? ' e.g. ' + JSON.stringify(bad[0]).slice(0, 200) : ''));
  const perWin = new Map(); for (const f of fills) perWin.set(f.ticker, (perWin.get(f.ticker) || 0) + 1);
  ok('at most one fill per window', [...perWin.values()].every(n => n === 1), fills.length + ' fills in ' + perWin.size + ' windows');
  const firstHalt = halts.length ? halts[0].seq : Infinity;
  ok('nothing sent after a halt', !attempts.some(a => a.seq > firstHalt), halts.length ? 'halt: ' + halts[0].reason : 'no halt');
  ok('ledger hash chain verifies', T.ledger.verify().ok === true, JSON.stringify(T.ledger.verify()));
  ok('no tick errors', T.ST.tickErrors === 0, T.ST.tickErrors + (T.ST.lastErr ? ' ' + T.ST.lastErr.slice(0, 200) : ''));
  const eligible = markets.filter(m => m.closeTs >= t0 && m.closeTs < t1);
  const seen = new Set(windows.filter(w => w.evalTicks > 0).map(w => w.ticker));
  ok('every eligible contract evaluated (one WINDOW record each)', eligible.every(m => seen.has(m.ticker)), seen.size + ' / ' + eligible.length);
  ok('every fill settled with the official Kalshi result', settled.length === fills.length, settled.length + ' / ' + fills.length);
  /* regression against the validation's 0.2 % replay */
  let cmp = null;
  if (fs.existsSync(REF)) {
    const ref = new Map(fs.readFileSync(REF, 'utf8').split('\n').filter(Boolean).map(l => JSON.parse(l)).filter(r => r.closeTs >= t0 && r.closeTs < t1).map(r => [r.ticker, r]));
    let n = 0, same = 0; const diff = [];
    for (const w of windows) {
      const r = ref.get(w.ticker); if (!r) continue; n++;
      const a = w.firstLockedTau != null ? { tau: w.firstLockedTau, side: w.lockedSide } : null, b = r.firstLocked ? { tau: r.firstLocked.tau, side: r.firstLocked.side } : null;
      if ((!a && !b) || (a && b && a.side === b.side && Math.abs(a.tau - b.tau) < 0.06)) same++; else diff.push(w.ticker + ' trader ' + JSON.stringify(a) + ' validation ' + JSON.stringify(b));
    }
    cmp = { windows: n, identical: same, differences: diff.slice(0, 5) };
    ok('first LOCKED (second and side) identical to the 0.2 % validation replay', n > 0 && same === n, same + ' / ' + n + (diff.length ? ' first diff: ' + diff[0] : ''));
  } else console.log('note: ' + REF + ' absent: regression comparison skipped');

  const won = settled.filter(s => s.won).length;
  const summary = { range: FROM + ' .. ' + TO, warmSec: WARM, engineSha256: T.ENGINE_SHA256.slice(0, 16), lockMaxFlip: S.LOCK_MAX_FLIP,
    windows: eligible.length, evaluatedSeconds: evalSec, secondsWithSyntheticBook: bookSec,
    windowsLocked: windows.filter(w => w.lockedTicks > 0).length, windowsEngineTradeNow: windows.filter(w => w.firstEngineTradeNowTau != null).length,
    buyTicks, orders: attempts.length, fills: fills.length, settled: settled.length, won, lost: settled.length - won,
    paperPnlUsd: Math.round(settled.reduce((a, s) => a + s.pnlUsd, 0) * 100) / 100, halts: halts.map(h => h.reason),
    topBlocksWhileLocked: Object.entries(windows.reduce((acc, w) => { for (const [k, v] of w.topBlocks || []) acc[k] = (acc[k] || 0) + v; return acc; }, {})).sort((a, b) => b[1] - a[1]).slice(0, 6),
    regression: cmp, wallSec: Math.round((realNow() - wall) / 100) / 10,
    note: 'SYNTHETIC book from real Kalshi prints (15 s look-back); fills/P&L exercise the order path only and are not an execution estimate' };
  console.log(JSON.stringify(summary, null, 1));
  for (const f of fills) { const s = settled.find(x => x.id === f.id); console.log('  fill ' + f.ticker + ' ' + f.side + ' ' + f.filled + ' @ ' + f.priceCents + ' c, cost $' + f.costUsd + (s ? ' -> ' + (s.won ? 'WON' : 'LOST') + ' ' + s.pnlUsd : ' (unsettled)')); }
  let n = 0; for (const [p, s] of results) { console.log((p ? 'ok   ' : 'FAIL ') + s); if (p) n++; }
  console.log(`engine_replay: ${n}/${results.length} passed`);
  try { fs.unlinkSync(LEDGER); } catch (_) { }
  process.exit(n === results.length ? 0 : 1);
}).catch(e => { Date.now = realNow; console.error(e); process.exit(1); });
