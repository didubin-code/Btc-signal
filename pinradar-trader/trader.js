/* =====================================================================
   BTC PIN RADAR TRADER 5.0 — replacement for live-trader-4.17 (archived: ../trader-archive/live-trader-4.17/)
   ---------------------------------------------------------------------
   * Decision engine: Pin Radar 2.8.1 (engine/pinradar_server.js, byte-identical to btc-ai-backend
     pinradar-research/2.8.1/dist, SHA-256 55d0555c…), run IN-PROCESS with LOCK_MAX_FLIP = 0.002 (the 0.2 % LOCKED threshold,
     validated in btc-ai-backend pinradar-research/validation/VALIDATION_REPORT.md section G).
   * Every KXBTC15M window is evaluated every TRADER_TICK_MS. A buy happens only when the engine says TRADE NOW AND every trader
     check passes (lib/policy.js): reversal risk, expected value at the exact limit, liquidity, timing, data integrity, risk state.
   * At most one entry per window, at most MAX_TRADE_USD (default $5, fee included) per trade, IOC limit orders only, no exits.
   * DRY RUN by default. Real orders need LIVE=1 AND TRADER_LIVE_ARM=I-ACCEPT-REAL-MONEY-RISK AND Kalshi credentials.
   * Any order error or unknown outcome halts trading until a person resumes it. A loss halts trading (HALT_AFTER_LOSSES, default 1).
   Start: node trader.js        Endpoints: /health /status /windows /trades /stats /ledger /ledger/verify /config /live /livecheck
                                           /halt?on=1  /halt?on=0&token=…  /selftest  /engine/<engine GET route>
   ===================================================================== */
'use strict';
const http = require('http');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { URL } = require('url');

const VERSION = 'pinradar-trader-5.0';
const ENV = process.env;
const ARM_PHRASE = 'I-ACCEPT-REAL-MONEY-RISK';

/* ------------------------------ configuration ------------------------------ */
function num(name, def, lo, hi) {
  const raw = ENV[name];
  const n = raw === undefined || raw === '' ? def : Number(raw);
  if (!Number.isFinite(n)) return def;
  return Math.max(lo, Math.min(hi, n));
}
const flag = (name, def) => (ENV[name] === undefined || ENV[name] === '') ? def : /^(1|true|yes|on)$/i.test(ENV[name]);

/* the engine reads LOCK_MAX_FLIP when it loads: the trader's threshold must be in place before require() */
if (ENV.LOCK_MAX_FLIP === undefined || ENV.LOCK_MAX_FLIP === '') ENV.LOCK_MAX_FLIP = '0.002';
const ABSOLUTE_MAX_TRADE_USD = num('ABSOLUTE_MAX_TRADE_USD', 5, 1, 1e6);   // raising the cap above $5 needs BOTH variables changed
const CFG = {
  maxTradeUsd: Math.min(num('MAX_TRADE_USD', 5, 0.5, 1e6), ABSOLUTE_MAX_TRADE_USD),
  maxContracts: num('MAX_CONTRACTS', 1000, 1, 1e6),
  lockMaxFlip: Number(ENV.LOCK_MAX_FLIP),
  minAskCents: num('TRADER_MIN_ASK_CENTS', 90, 50, 99.9),
  maxAskCents: num('TRADER_MAX_ASK_CENTS', 99, 50, 99.9),
  minEdgeCents: num('TRADER_MIN_EDGE_CENTS', 0.5, 0, 50),
  minTauSec: num('TRADER_MIN_TAU_SEC', 15, 3, 300),
  maxBookAgeMs: num('TRADER_MAX_BOOK_AGE_MS', 1500, 100, 10000),
  maxAttemptsPerWindow: num('MAX_ATTEMPTS_PER_WINDOW', 2, 1, 10),
  dailyLossLimitUsd: num('DAILY_LOSS_LIMIT_USD', 10, 1, 1e6),
  maxConsecutiveLosses: num('HALT_AFTER_LOSSES', 1, 1, 100),
  maxTradesPerDay: num('MAX_TRADES_PER_DAY', 96, 1, 1000),
  maxOpenUsd: num('MAX_OPEN_USD', 5, 0.5, 1e6),
  requireWarmVol: flag('REQUIRE_WARM_VOL', true),
  requireWarmBasis: flag('REQUIRE_WARM_BASIS', true),
  strikeSaneMin: 1000,
  tickMs: num('TRADER_TICK_MS', 500, 200, 5000),
  execSec: num('EXEC_SEC', 12, 0, 120),
  ledgerFile: ENV.TRADER_LEDGER_FILE || '/tmp/pinradar_trader_ledger.jsonl',
  haltFile: ENV.TRADER_HALT_FILE || '',
  adminToken: ENV.TRADER_ADMIN_TOKEN || '',
  kalshiBase: (ENV.KALSHI_BASE || 'https://api.elections.kalshi.com/trade-api/v2').replace(/\/+$/, ''),
  exchangeIndex: num('EXCHANGE_INDEX', -1, -1, 64),
  port: num('PORT', 10000, 1, 65535),
};
const KEY_ID = ENV.KALSHI_KEY_ID || '';
const PRIVATE_KEY = (ENV.KALSHI_PRIVATE_KEY || '').replace(/\\n/g, '\n');
const LIVE_REQUESTED = flag('LIVE', false);
const LIVE_ARMED = LIVE_REQUESTED && ENV.TRADER_LIVE_ARM === ARM_PHRASE && !!(KEY_ID && PRIVATE_KEY);
CFG.live = LIVE_ARMED;
CFG.requireExchangeOpen = LIVE_ARMED || flag('REQUIRE_EXCHANGE_OPEN', false);
const MODE = LIVE_ARMED ? 'LIVE' : 'DRY-RUN';
const MODE_NOTE = LIVE_ARMED ? 'real orders, max $' + CFG.maxTradeUsd + ' each'
  : LIVE_REQUESTED ? ('LIVE=1 requested but NOT armed: ' + (ENV.TRADER_LIVE_ARM !== ARM_PHRASE ? 'TRADER_LIVE_ARM is not ' + ARM_PHRASE : 'Kalshi credentials missing') + ' -> dry run')
  : 'no orders are sent; paper fills at the displayed book (optimistic)';

/* ------------------------------ engine ------------------------------ */
const ENGINE_FILE = path.join(__dirname, 'engine', 'pinradar_server.js');
const ENGINE_SHA256_EXPECTED = '55d0555c65e4f8a4e00355aaa2db7d1f0574918978f3749d6c8ff55d97522a0d';
const ENGINE_SHA256 = crypto.createHash('sha256').update(fs.readFileSync(ENGINE_FILE)).digest('hex');
let S = null;   // the engine module (loaded in boot() or by the tests)
function loadEngine() {
  if (S) return S;
  S = require(ENGINE_FILE);
  if (Math.abs(S.LOCK_MAX_FLIP - CFG.lockMaxFlip) > 1e-12) throw new Error('engine LOCK_MAX_FLIP ' + S.LOCK_MAX_FLIP + ' != trader ' + CFG.lockMaxFlip);
  return S;
}

const { mkKalshi, kalshiFeeUsd } = require('./lib/kalshi');
const { decide } = require('./lib/policy');
const { mkLedger } = require('./lib/ledger');
const kalshi = mkKalshi({ base: CFG.kalshiBase, keyId: KEY_ID, privateKey: PRIVATE_KEY, exchangeIndex: CFG.exchangeIndex, timeoutMs: num('KALSHI_TIMEOUT_MS', 6000, 500, 30000) });
const ledger = mkLedger(CFG.ledgerFile);

/* ------------------------------ state ------------------------------ */
const ST = {
  bootTs: Date.now(), ticks: 0, tickErrors: 0, lastErr: null, busy: false,
  halts: new Map(),                // reason -> {ts, latched}
  manualHalt: false,
  windows: new Map(),              // ticker -> {attempts, filledContracts, side, ...evaluation counters}
  positions: [],                   // open (unsettled) positions
  day: null, realizedTodayUsd: 0, tradesToday: 0, consecutiveLosses: 0,
  forward: { settled: 0, won: 0, lost: 0, pnlUsd: 0 },
  lastDecision: null, lastSnapshot: null, exchange: { tradingActive: null, ts: 0 }, inFlight: false,
  live: { orders: [], lastResult: null },
};
const today = (t = Date.now()) => new Date(t).toISOString().slice(0, 10);
function rollDay(now = Date.now()) { const d = today(now); if (ST.day !== d) { ST.day = d; ST.realizedTodayUsd = 0; ST.tradesToday = 0; } }
function haltReasons() {
  const r = [...ST.halts.keys()];
  if (ST.manualHalt) r.push('manual halt');
  if (flag('TRADER_HALT', false)) r.push('TRADER_HALT env');
  if (CFG.haltFile && fs.existsSync(CFG.haltFile)) r.push('halt file ' + CFG.haltFile);
  return r;
}
function latchHalt(reason, extra) {
  if (!ST.halts.has(reason)) { ST.halts.set(reason, { ts: Date.now() }); ledger.append({ ev: 'HALT', reason, ...(extra || {}) }); console.log('[' + VERSION + '] HALT: ' + reason); }
}
function openExposureUsd() { return ST.positions.reduce((a, p) => a + (p.costUsd || 0), 0); }
function windowRec(ticker, closeMs) {
  let w = ST.windows.get(ticker);
  if (!w) {
    w = { ticker, closeMs, attempts: 0, filledContracts: 0, side: null, evalTicks: 0, lockedTicks: 0, engineTradeNowTicks: 0, buyTicks: 0,
      firstLockedTau: null, firstEngineTradeNowTau: null, blockCounts: {}, summarized: false };
    ST.windows.set(ticker, w);
    if (ST.windows.size > 400) { const k = ST.windows.keys().next().value; ST.windows.delete(k); }
  }
  return w;
}

/* restore the risk state from the ledger after a restart (needs a persistent TRADER_LEDGER_FILE) */
function restoreFromLedger() {
  const rows = ledger.tail(2000); let restored = 0;
  for (const r of rows) {
    if (r.ev === 'HALT') ST.halts.set(r.reason, { ts: r.ts, restored: true });
    if (r.ev === 'RESUME') { ST.halts.clear(); ST.consecutiveLosses = 0; }
    if (r.ev === 'ORDER_ATTEMPT') { const w = windowRec(r.ticker, r.closeMs); w.attempts = Math.max(w.attempts, r.attempt); w.side = r.side; }
    if (r.ev === 'FILL' && r.filled > 0) {
      const w = windowRec(r.ticker, r.closeMs); w.filledContracts += r.filled; w.side = r.side;
      ST.positions.push({ id: r.id, ticker: r.ticker, closeMs: r.closeMs, side: r.side, contracts: r.filled, priceCents: r.priceCents, feeUsd: r.feeUsd, costUsd: r.costUsd, mode: r.mode, strike: r.strike });
      if (today(r.ts) === today()) ST.tradesToday++;
    }
    if (r.ev === 'SETTLED') {
      ST.positions = ST.positions.filter(p => p.id !== r.id);
      ST.forward.settled++; ST.forward.pnlUsd += r.pnlUsd; if (r.won) ST.forward.won++; else ST.forward.lost++;
      ST.consecutiveLosses = r.won ? 0 : ST.consecutiveLosses + 1;
      if (today(r.ts) === today()) ST.realizedTodayUsd += r.pnlUsd;
    }
    restored++;
  }
  rollDay();
  return restored;
}

/* ------------------------------ the engine reading ------------------------------ */
function engineReading(now, contracts) {
  const kal = S.getKalshiContext();
  if (!kal || !kal.ok || !Number.isFinite(kal.strike)) return { kal, snap: null };
  const liveIdx = S.computeIndex(now);
  const used = liveIdx ? Object.values(S.VENUES).filter(v => liveIdx.used.includes(v.name)) : [];
  const age = used.length ? Math.max(...used.map(v => now - v.lastQuoteTs)) : Infinity;
  const quality = S.assessQuality(now, kal);
  const strikeIssue = (liveIdx && Math.abs(kal.strike / liveIdx.value - 1) > 0.2) ? 'strike implausible vs index' : null;   // = engine STRIKE_MAX_DEV_FRAC default
  /* read-only: mutate:false, like a page request. The engine's own background tick keeps the sticky-side / reversal state. */
  const snap = S.computeLockSnapshot({ now, kal, strike: kal.strike, strikeIssue, overrides: [], quality, liveIdx, liveIndexAgeMs: age,
    side: null, mutate: false, contracts, execSec: CFG.execSec });
  return { kal, snap, book: S.bookFromKal(kal, now) };
}

function evaluate(now = Date.now()) {
  /* first pass at 1 contract finds the side and the ask; the second pass asks the engine about the actual size */
  const r1 = engineReading(now, 1);
  if (!r1.snap) return { ctx: null, dec: { action: 'SKIP', why: ['no Kalshi market / strike yet'] }, r: r1 };
  const sig1 = r1.snap.signal;
  const lv = sig1 && sig1.side === 'UP' ? r1.book.yesAsks : sig1 && sig1.side === 'DOWN' ? r1.book.noAsks : null;
  let contracts = 1;
  if (lv && lv.length) {
    const { sizeForBudget } = require('./lib/policy');
    contracts = Math.max(1, sizeForBudget(lv[0][0], CFG.maxTradeUsd, CFG.maxContracts).contracts);
  }
  const r = contracts === 1 ? r1 : engineReading(now, contracts);
  const sig = r.snap.signal;
  const ctx = { now, sig, book: r.book, ticker: r.kal.ticker, strike: r.kal.strike, closeMs: r.kal.closeMs, tau: (r.kal.closeMs - now) / 1000,
    exchange: ST.exchange };
  const w = windowRec(ctx.ticker, ctx.closeMs);
  const dec = decide(ctx, { halted: haltReasons(), windows: ST.windows, realizedTodayUsd: ST.realizedTodayUsd, consecutiveLosses: ST.consecutiveLosses,
    tradesToday: ST.tradesToday, openExposureUsd: openExposureUsd(), inFlight: ST.inFlight }, CFG);
  /* per-window evaluation record: every window is evaluated; the reasons it was not traded are counted */
  w.evalTicks++;
  const locked = sig && (sig.state === 'LOCKED' || sig.state === 'PROVEN LOCKED');
  if (locked) { w.lockedTicks++; if (w.firstLockedTau == null) { w.firstLockedTau = Math.round(ctx.tau * 10) / 10; w.lockedSide = sig.side; } }
  if (sig && sig.exec && sig.exec.headline === 'TRADE NOW') { w.engineTradeNowTicks++; if (w.firstEngineTradeNowTau == null) w.firstEngineTradeNowTau = Math.round(ctx.tau * 10) / 10; }
  if (dec.action === 'BUY') w.buyTicks++;
  else if (locked && dec.why.length) { const k = dec.why[0].replace(/[0-9.]+/g, '#').slice(0, 80); w.blockCounts[k] = (w.blockCounts[k] || 0) + 1; }
  return { ctx, dec, r, contracts };
}

/* ------------------------------ execution ------------------------------ */
async function execute(ctx, dec) {
  const w = windowRec(ctx.ticker, ctx.closeMs);
  const plan = dec.plan;
  w.attempts++; w.side = ctx.sig.side; ST.inFlight = true;
  const clientOrderId = 'pr5-' + ctx.ticker + '-a' + w.attempts;
  const base = { ticker: ctx.ticker, closeMs: ctx.closeMs, strike: ctx.strike, side: ctx.sig.side, attempt: w.attempts, clientOrderId,
    contracts: plan.contracts, limitCents: plan.limitCents, maxCostUsd: plan.maxCostUsd, tau: Math.round(ctx.tau * 100) / 100, mode: MODE,
    modeled: { state: ctx.sig.state, pFlip: ctx.sig.pFlip, pFlipCons: ctx.sig.pFlipCons, evConsCentsAtLimit: plan.evConsCentsAtLimit,
      engineEvConsCents: ctx.sig.trade && ctx.sig.trade.evConsCents, engineReason: ctx.sig.exec && ctx.sig.exec.reason, lockMaxFlip: CFG.lockMaxFlip } };
  ledger.append({ ev: 'ORDER_ATTEMPT', ...base });
  try {
    let res;
    if (!CFG.live) {
      res = { kind: 'paper', filled: plan.contracts, order: kalshi.buildBuyOrder({ ticker: ctx.ticker, side: ctx.sig.side, count: plan.contracts, limitCents: plan.limitCents, clientOrderId }) };
    } else {
      res = await kalshi.placeBuy({ ticker: ctx.ticker, side: ctx.sig.side, count: plan.contracts, limitCents: plan.limitCents, clientOrderId });
    }
    ST.live.lastResult = { ts: Date.now(), kind: res.kind, filled: res.filled || 0, ticker: ctx.ticker, error: res.error || null };
    ST.live.orders.push({ ts: Date.now(), ticker: ctx.ticker, kind: res.kind, filled: res.filled || 0, order: res.order }); if (ST.live.orders.length > 50) ST.live.orders.shift();
    ledger.append({ ev: 'ORDER_RESULT', ticker: ctx.ticker, clientOrderId, kind: res.kind, filled: res.filled || 0, remaining: res.remaining || 0, orderId: res.orderId || null,
      status: res.status || null, error: res.error || null, order: res.order });
    if (res.kind === 'rejected') latchHalt('order rejected (HTTP ' + res.status + '): ' + String(res.error).slice(0, 120), { ticker: ctx.ticker });
    if (res.kind === 'unknown') { latchHalt('order outcome unknown for ' + ctx.ticker + ': check /livecheck, then resume', { ticker: ctx.ticker }); setTimeout(() => reconcile(ctx.ticker).catch(() => { }), 5000); }
    const filled = Math.min(Number(res.filled) || 0, plan.contracts);
    if (filled > 0) {
      /* live: booked at the limit (the most the IOC order could pay); paper: at the walked book average (optimistic) */
      const priceCents = CFG.live ? plan.limitCents : plan.avgCents;
      const feeUsd = kalshiFeeUsd(priceCents, filled);
      const costUsd = Math.round((filled * priceCents / 100 + feeUsd) * 100) / 100;
      const id = clientOrderId;
      w.filledContracts += filled;
      ST.positions.push({ id, ticker: ctx.ticker, closeMs: ctx.closeMs, side: ctx.sig.side, contracts: filled, priceCents, feeUsd, costUsd, mode: MODE, strike: ctx.strike });
      ST.tradesToday++;
      ledger.append({ ev: 'FILL', id, ticker: ctx.ticker, closeMs: ctx.closeMs, strike: ctx.strike, side: ctx.sig.side, filled, priceCents, feeUsd, costUsd, mode: MODE,
        note: CFG.live ? 'booked at the limit price' : 'PAPER: assumes the displayed offers were still there (optimistic)' });
    }
    return res;
  } finally { ST.inFlight = false; }
}
async function reconcile(ticker) {
  if (!CFG.live) return;
  const pos = await kalshi.positions();
  ledger.append({ ev: 'RECONCILE', ticker, positions: pos && pos.market_positions ? pos.market_positions.filter(p => p.ticker === ticker) : pos });
}

/* ------------------------------ settlement ------------------------------ */
async function settleOpen(now = Date.now()) {
  for (const p of [...ST.positions]) {
    if (now < p.closeMs + 3000) continue;
    let res = null;
    const d = S && S.SETTLE && S.SETTLE.done.find(x => x.ticker === p.ticker && x.status === 'SETTLED');
    if (d) res = { result: d.result, official: d.official, source: 'engine' };
    else if (!p.nextPoll || now >= p.nextPoll) { p.nextPoll = now + 5000; const m = await kalshi.marketResult(p.ticker); if (m) res = { ...m, source: 'kalshi' }; }
    if (!res) { if (now - p.closeMs > 3 * 3600 * 1000 && !p.flagged) { p.flagged = true; latchHalt('position ' + p.ticker + ' unsettled after 3 h'); } continue; }
    const won = (p.side === 'UP') === (res.result === 'yes');
    const pnlUsd = Math.round(((won ? p.contracts : 0) - p.costUsd) * 100) / 100;
    ST.positions = ST.positions.filter(x => x !== p);
    rollDay(now); ST.realizedTodayUsd += pnlUsd;
    ST.forward.settled++; ST.forward.pnlUsd = Math.round((ST.forward.pnlUsd + pnlUsd) * 100) / 100; if (won) ST.forward.won++; else ST.forward.lost++;
    ST.consecutiveLosses = won ? 0 : ST.consecutiveLosses + 1;
    ledger.append({ ev: 'SETTLED', id: p.id, ticker: p.ticker, side: p.side, contracts: p.contracts, costUsd: p.costUsd, result: res.result, official: res.official,
      strike: p.strike, won, pnlUsd, mode: p.mode, source: res.source });
    if (!won && ST.consecutiveLosses >= CFG.maxConsecutiveLosses) latchHalt(ST.consecutiveLosses + ' consecutive loss(es) (last ' + p.ticker + '): review before resuming');
    if (ST.realizedTodayUsd <= -Math.abs(CFG.dailyLossLimitUsd)) latchHalt('daily loss limit $' + CFG.dailyLossLimitUsd + ' reached');
  }
}
function summarizeWindows(now = Date.now()) {
  for (const w of ST.windows.values()) {
    if (w.summarized || !(now > w.closeMs + 1000)) continue;
    w.summarized = true;
    ledger.append({ ev: 'WINDOW', ticker: w.ticker, closeMs: w.closeMs, evalTicks: w.evalTicks, lockedTicks: w.lockedTicks, lockedSide: w.lockedSide || null,
      firstLockedTau: w.firstLockedTau, firstEngineTradeNowTau: w.firstEngineTradeNowTau, buyTicks: w.buyTicks, attempts: w.attempts, filledContracts: w.filledContracts,
      topBlocks: Object.entries(w.blockCounts).sort((a, b) => b[1] - a[1]).slice(0, 3) });
  }
}

/* ------------------------------ main loop ------------------------------ */
async function tick() {
  if (ST.busy) return; ST.busy = true;
  try {
    ST.ticks++; rollDay();
    const now = Date.now();
    const { ctx, dec } = evaluate(now);
    ST.lastDecision = { ts: now, action: dec.action, why: dec.why, plan: dec.plan || null, ticker: ctx && ctx.ticker, tau: ctx && Math.round(ctx.tau * 10) / 10 };
    if (ctx && ctx.sig) ST.lastSnapshot = { state: ctx.sig.state, side: ctx.sig.side, pFlip: ctx.sig.pFlip, pFlipCons: ctx.sig.pFlipCons, exec: ctx.sig.exec && { headline: ctx.sig.exec.headline, reason: ctx.sig.exec.reason },
      trade: ctx.sig.trade && { action: ctx.sig.trade.action, askCents: ctx.sig.trade.askCents, evConsCents: ctx.sig.trade.evConsCents, depth: ctx.sig.trade.depth },
      warmup: ctx.sig.warmup && ctx.sig.warmup.label, hard: ctx.sig.gates && ctx.sig.gates.hard };
    if (dec.action === 'BUY') await execute(ctx, dec);
    await settleOpen(now);
    summarizeWindows(now);
  } catch (e) {
    ST.tickErrors++; ST.lastErr = String(e && e.stack || e).slice(0, 500);
  } finally { ST.busy = false; }
}
async function pollExchange() { const s = await kalshi.exchangeStatus(); if (s.ok) ST.exchange = { tradingActive: s.tradingActive, exchangeActive: s.exchangeActive, ts: Date.now() }; }

/* ------------------------------ reporting ------------------------------ */
function cpUpper(k, n, a = 0.05) {   // one-sided Clopper-Pearson upper bound
  if (n === 0) return 1;
  let lo = k / n, hi = 1;
  const cdf = p => { let s = 0, t = Math.pow(1 - p, n); for (let i = 0; i <= k; i++) { s += t; t = t * (n - i) / (i + 1) * p / (1 - p); } return s; };
  for (let i = 0; i < 80; i++) { const m = (lo + hi) / 2; if (cdf(m) > a) lo = m; else hi = m; }
  return hi;
}
const EVIDENCE = {
  modeled: 'pFlip / pFlipCons in every decision are the engine\'s modelled flip risk (a model output, not an observed rate).',
  backtestObserved: {
    source: 'btc-ai-backend pinradar-research/validation/VALIDATION_REPORT.md, section G (0.2 % threshold replayed with this engine over 25,982 Kalshi contracts)',
    firstLockedWrongUnseen: '15 / 16,700 = 0.090 % (95 % CI 0.050-0.148 %)',
    lockedAtT20WrongUnseen: '1 / 15,601 (one-sided 95 % bound 0.030 %)',
    smallSizeUnseenJanJul: '100 contracts, 15 s buffer, 12 s order time: +0.22 c/contract (CI +0.14 to +0.29), 5,158 trades, 2 lost',
    caveats: ['backtest on a substitute price feed (Binance BTCUSDC), not the live 3-venue index; the last ~20 s are feed-dependent',
      'fills modelled from other traders\' prints (upper bound); the small-size edge decayed to about zero by September 2026',
      'NOT YET VALIDATED for real money: this forward record is the first independent evidence'],
  },
};
function stats() {
  const f = ST.forward;
  return { ...EVIDENCE, forward: { mode: MODE, settled: f.settled, won: f.won, lost: f.lost, pnlUsd: f.pnlUsd,
    lossRatePct: f.settled ? Math.round(10000 * f.lost / f.settled) / 100 : null, lossRateUpper95Pct: f.settled ? Math.round(10000 * cpUpper(f.lost, f.settled)) / 100 : null,
    note: 'observed by this trader; ' + (MODE === 'LIVE' ? 'real fills' : 'paper fills (optimistic)') } };
}
function publicConfig() {
  const c = { ...CFG }; delete c.adminToken;
  return { version: VERSION, mode: MODE, modeNote: MODE_NOTE, engine: { file: 'engine/pinradar_server.js', sha256: ENGINE_SHA256, expected: ENGINE_SHA256_EXPECTED, version: S && S.MODEL_VERSION,
    lockMaxFlip: S && S.LOCK_MAX_FLIP, minTradeAskCents: S && S.MIN_TRADE_ASK_CENTS, execSec: S && S.EXEC_SEC },
    config: c, credentials: { keyIdSet: !!KEY_ID, privateKeySet: !!PRIVATE_KEY }, adminTokenSet: !!CFG.adminToken };
}

/* ------------------------------ self-test (no network, no orders) ------------------------------ */
function selfTest() {
  const checks = [];
  const push = (name, pass, got) => checks.push({ name, pass: !!pass, got });
  const { sizeForBudget, walkAsks } = require('./lib/policy');
  const s99 = sizeForBudget(99, 5);
  push('sizing: $5 at 99 c buys 5 contracts for <= $5 incl. fee', s99.contracts === 5 && s99.costUsd <= 5, s99);
  const s90 = sizeForBudget(90, 5);
  push('sizing: $5 at 90 c buys 5 contracts (5 x 0.90 + fee 0.04 = 4.54; 6 would cost 5.44)', s90.contracts === 5 && s90.costUsd === 4.54, s90);
  push('walk: limit is the worst level needed', JSON.stringify(walkAsks([[98, 2], [99, 10]], 5)) === JSON.stringify({ limitCents: 99, avgCents: 98.6 }), walkAsks([[98, 2], [99, 10]], 5));
  const oY = kalshi.buildBuyOrder({ ticker: 'KXBTC15M-26OCT161200-00', side: 'UP', count: 5, limitCents: 99, clientOrderId: 'x' });
  const oN = kalshi.buildBuyOrder({ ticker: 'KXBTC15M-26OCT161200-00', side: 'DOWN', count: 5, limitCents: 97, clientOrderId: 'x' });
  push('order: UP = bid YES at the limit', oY.side === 'bid' && oY.price === '0.9900' && oY.count === '5.00' && oY.time_in_force === 'immediate_or_cancel', oY);
  push('order: DOWN at 97 c = ask YES at 0.03', oN.side === 'ask' && oN.price === '0.0300', oN);
  let threw = false; try { kalshi.buildBuyOrder({ ticker: 'KXETH-1', side: 'UP', count: 1, limitCents: 99, clientOrderId: 'x' }); } catch (_) { threw = true; }
  push('order: refuses a non-KXBTC15M ticker', threw, threw);
  push('engine: byte-identical to the validated 2.8.1 build', ENGINE_SHA256 === ENGINE_SHA256_EXPECTED, ENGINE_SHA256.slice(0, 16));
  push('engine: LOCKED threshold is the trader threshold', S && Math.abs(S.LOCK_MAX_FLIP - CFG.lockMaxFlip) < 1e-12, S && S.LOCK_MAX_FLIP);
  push('cap: max trade <= absolute cap', CFG.maxTradeUsd <= ABSOLUTE_MAX_TRADE_USD, CFG.maxTradeUsd);
  if (S) {
    const r = S.runSelfTest();
    const fails = r.checks.filter(c => !c.pass).map(c => c.name);
    const expected = CFG.lockMaxFlip < 0.0047 ? fails.filter(n => /2\.6 quiet tape: a 99\.6% model call is NOT locked; active tape: a 99\.1% model call IS locked/.test(n)) : [];
    push('engine self-test (' + r.passed + '/' + r.total + '; at LOCK_MAX_FLIP=' + CFG.lockMaxFlip + ' the 0.5 %-threshold check that a 0.468 % flip IS locked is expected to fail)',
      fails.length === expected.length, { fails });
  }
  return { version: VERSION, ok: checks.every(c => c.pass), passed: checks.filter(c => c.pass).length, total: checks.length, checks };
}

/* ------------------------------ HTTP ------------------------------ */
function send(res, code, obj) {
  res.statusCode = code; res.setHeader('Content-Type', 'application/json; charset=utf-8'); res.setHeader('Cache-Control', 'no-store');
  res.setHeader('Access-Control-Allow-Origin', '*'); res.end(JSON.stringify(obj, null, 1));
}
const server = http.createServer(async (req, res) => {
  let u; try { u = new URL(req.url, 'http://localhost'); } catch (_) { return send(res, 400, { error: 'bad url' }); }
  const p = u.pathname.replace(/\/+$/, '') || '/';
  try {
    if (p.startsWith('/engine/')) {   // read-only passthrough to the embedded engine's own endpoints (/engine/health, /engine/exec, /engine/dq ...)
      if (req.method !== 'GET') return send(res, 405, { error: 'GET only' });
      req.url = p.slice('/engine'.length) + u.search; return S.server.emit('request', req, res);
    }
    if (p === '/' || p === '/health') return send(res, 200, { ok: true, version: VERSION, mode: MODE, modeNote: MODE_NOTE, uptimeSec: Math.round(process.uptime()),
      ticks: ST.ticks, tickErrors: ST.tickErrors, halted: haltReasons(), lockMaxFlip: CFG.lockMaxFlip, maxTradeUsd: CFG.maxTradeUsd, engineSha256: ENGINE_SHA256.slice(0, 16),
      lastDecision: ST.lastDecision && { action: ST.lastDecision.action, ticker: ST.lastDecision.ticker, tau: ST.lastDecision.tau, why: (ST.lastDecision.why || []).slice(0, 2) } });
    if (p === '/status') return send(res, 200, { version: VERSION, mode: MODE, halted: haltReasons(), decision: ST.lastDecision, engine: ST.lastSnapshot,
      risk: { day: ST.day, realizedTodayUsd: ST.realizedTodayUsd, tradesToday: ST.tradesToday, consecutiveLosses: ST.consecutiveLosses, openExposureUsd: openExposureUsd(), positions: ST.positions },
      exchange: ST.exchange, lastErr: ST.lastErr });
    if (p === '/windows') { const n = Math.min(200, Number(u.searchParams.get('n') || 20)); return send(res, 200, [...ST.windows.values()].slice(-n)); }
    if (p === '/trades') { const n = Math.min(2000, Number(u.searchParams.get('n') || 100)); return send(res, 200, ledger.tail(2000).filter(r => /ORDER_|FILL|SETTLED/.test(r.ev)).slice(-n)); }
    if (p === '/stats') return send(res, 200, stats());
    if (p === '/ledger') { const n = Math.min(2000, Number(u.searchParams.get('n') || 200)); return send(res, 200, { file: CFG.ledgerFile, lines: ledger.tail(n), err: ledger.state.err }); }
    if (p === '/ledger/verify') return send(res, 200, ledger.verify());
    if (p === '/config') return send(res, 200, publicConfig());
    if (p === '/live') return send(res, 200, { mode: MODE, modeNote: MODE_NOTE, credentials: kalshi.ready(), lastResult: ST.live.lastResult, orders: ST.live.orders.slice(-10) });
    if (p === '/livecheck') { if (!kalshi.ready()) return send(res, 200, { ready: false, note: 'no KALSHI_KEY_ID / KALSHI_PRIVATE_KEY' }); return send(res, 200, { ready: true, balance: await kalshi.balance(), positions: await kalshi.positions() }); }
    if (p === '/halt') {
      const on = u.searchParams.get('on');
      if (on === '1') { ST.manualHalt = true; ledger.append({ ev: 'HALT', reason: 'manual halt (HTTP)' }); return send(res, 200, { ok: true, halted: haltReasons() }); }
      if (on === '0') {
        if (!CFG.adminToken) return send(res, 403, { error: 'resume over HTTP is disabled: set TRADER_ADMIN_TOKEN, or restart the service after review' });
        const tok = u.searchParams.get('token') || req.headers['x-admin-token'] || '';
        if (!crypto.timingSafeEqual(Buffer.from(crypto.createHash('sha256').update(String(tok)).digest()), Buffer.from(crypto.createHash('sha256').update(CFG.adminToken).digest())))
          return send(res, 403, { error: 'bad token' });
        ST.manualHalt = false; ST.halts.clear(); ST.consecutiveLosses = 0; ledger.append({ ev: 'RESUME', by: 'admin token' });
        return send(res, 200, { ok: true, halted: haltReasons() });
      }
      return send(res, 200, { halted: haltReasons(), usage: '/halt?on=1 halts (no token); /halt?on=0&token=… resumes (TRADER_ADMIN_TOKEN)' });
    }
    if (p === '/selftest') return send(res, 200, selfTest());
    return send(res, 404, { error: 'not found', routes: ['/health', '/status', '/windows', '/trades', '/stats', '/ledger', '/ledger/verify', '/config', '/live', '/livecheck', '/halt', '/selftest', '/engine/<route>'] });
  } catch (e) { return send(res, 500, { error: String(e && e.message || e) }); }
});

/* ------------------------------ boot ------------------------------ */
function boot() {
  if (ENGINE_SHA256 !== ENGINE_SHA256_EXPECTED && !flag('ALLOW_ENGINE_MISMATCH', false)) throw new Error('engine file differs from the validated 2.8.1 build (' + ENGINE_SHA256 + ')');
  loadEngine();
  const restored = restoreFromLedger();
  ledger.append({ ev: 'BOOT', version: VERSION, mode: MODE, modeNote: MODE_NOTE, engineSha256: ENGINE_SHA256, lockMaxFlip: CFG.lockMaxFlip, maxTradeUsd: CFG.maxTradeUsd, restoredRecords: restored,
    haltsRestored: [...ST.halts.keys()] });
  S.ensureSentinel();          // start the engine's feeds and its own background classifier
  server.listen(CFG.port, () => console.log('[' + VERSION + '] ' + MODE + ' (' + MODE_NOTE + ') on :' + CFG.port + ' | engine ' + S.MODEL_VERSION + ' sha ' + ENGINE_SHA256.slice(0, 12) + ' | LOCK_MAX_FLIP ' + CFG.lockMaxFlip + ' | max $' + CFG.maxTradeUsd + '/trade'));
  setInterval(() => { tick().catch(() => { }); }, CFG.tickMs);
  pollExchange().catch(() => { }); setInterval(() => { pollExchange().catch(() => { }); }, 60000);
}
if (require.main === module) boot();

module.exports = { CFG, ST, MODE, VERSION, loadEngine, evaluate, execute, settleOpen, summarizeWindows, tick, selfTest, stats, restoreFromLedger, latchHalt, haltReasons,
  server, ledger, kalshi, publicConfig, engine: () => S, ENGINE_SHA256, ENGINE_SHA256_EXPECTED, ARM_PHRASE };
