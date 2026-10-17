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
   * Any order error or unknown outcome halts trading until a person resumes it; an unknown outcome is booked provisionally and
     reconciled with Kalshi by client_order_id. A loss halts trading (HALT_AFTER_LOSSES, default 1). The whole ledger is replayed
     at start (halts, positions, today's P&L), and live trading needs an explicit, writable TRADER_LEDGER_FILE.
   Start: node trader.js        Endpoints: /health /status /windows /trades /stats /ledger /ledger/verify /config /live
                                           /halt?on=1  /selftest  /engine/<engine GET route>
                                Admin (X-Admin-Token header): /livecheck   POST /halt?on=0 (resume)
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
const { mkKalshi, kalshiFeeUsd, normalisePem, keyUsable } = require('./lib/kalshi');
const KEY_ID = ENV.KALSHI_KEY_ID || '';
const PRIVATE_KEY = normalisePem(ENV.KALSHI_PRIVATE_KEY);          // same normalisation as the engine
const KEY_OK = keyUsable(PRIVATE_KEY);
const LIVE_REQUESTED = flag('LIVE', false);
/* live needs: LIVE=1, the arm phrase, a key that can sign, and an explicitly configured ledger file (halts and positions must
   survive a restart: point it at a persistent disk) */
const ARM_BLOCKS = [];
if (ENV.TRADER_LIVE_ARM !== ARM_PHRASE) ARM_BLOCKS.push('TRADER_LIVE_ARM is not ' + ARM_PHRASE);
if (!KEY_ID || !PRIVATE_KEY) ARM_BLOCKS.push('Kalshi credentials missing');
else if (!KEY_OK) ARM_BLOCKS.push('KALSHI_PRIVATE_KEY cannot sign (not a usable RSA private key)');
if (!ENV.TRADER_LEDGER_FILE) ARM_BLOCKS.push('TRADER_LEDGER_FILE not set (it must be on a persistent disk)');
const LIVE_ARMED = LIVE_REQUESTED && ARM_BLOCKS.length === 0;
CFG.live = LIVE_ARMED;
CFG.requireExchangeOpen = LIVE_ARMED || flag('REQUIRE_EXCHANGE_OPEN', false);
const MODE = LIVE_ARMED ? 'LIVE' : 'DRY-RUN';
const MODE_NOTE = LIVE_ARMED ? 'real orders, max $' + CFG.maxTradeUsd + ' each'
  : LIVE_REQUESTED ? ('LIVE=1 requested but NOT armed: ' + ARM_BLOCKS.join('; ') + ' -> dry run')
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

const { decide } = require('./lib/policy');
const { mkLedger } = require('./lib/ledger');
const kalshi = mkKalshi({ base: CFG.kalshiBase, keyId: KEY_ID, privateKey: PRIVATE_KEY, exchangeIndex: CFG.exchangeIndex,
  statusIndex: num('EXCHANGE_STATUS_INDEX', 2, 0, 64), timeoutMs: num('KALSHI_TIMEOUT_MS', 6000, 500, 30000) });
const KALSHI_TIMEOUT_MS = num('KALSHI_TIMEOUT_MS', 6000, 500, 30000);
const ledger = mkLedger(CFG.ledgerFile);

/* ------------------------------ state ------------------------------ */
const ST = {
  bootTs: Date.now(), ticks: 0, tickErrors: 0, lastErr: null, busy: false,
  halts: new Map(),                // reason -> {ts, latched}
  manualHalt: false,
  windows: new Map(),              // ticker -> {attempts, filledContracts, side, ...evaluation counters}
  positions: [],                   // open (unsettled) positions
  day: null, realizedTodayUsd: 0, tradesToday: 0, consecutiveLosses: 0,
  forward: { LIVE: { settled: 0, won: 0, lost: 0, void: 0, pnlUsd: 0 }, 'DRY-RUN': { settled: 0, won: 0, lost: 0, void: 0, pnlUsd: 0 } },   // per mode
  lastDecision: null, lastSnapshot: null, exchange: { tradingActive: null, ts: 0 }, inFlight: false,
  live: { orders: [], lastResult: null },
};
const today = (t = Date.now()) => new Date(t).toISOString().slice(0, 10);
function rollDay(now = Date.now()) { const d = today(now); if (ST.day !== d) { ST.day = d; ST.realizedTodayUsd = 0; ST.tradesToday = 0; } }
const fwd = mode => ST.forward[mode === 'LIVE' ? 'LIVE' : 'DRY-RUN'];
function haltReasons() {
  const r = [...ST.halts.keys()];
  if (ledger.state.err) r.push('ledger write failing (' + ledger.state.err.slice(0, 80) + '): halts and positions would not survive a restart');
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

/* restore the risk state from the WHOLE ledger after a restart (needs a persistent TRADER_LEDGER_FILE).
   Today's realised P&L and trade count, halts, open positions, per-window attempts and the forward record come back;
   an order whose result was never written (the process stopped mid-order) is treated as an unknown outcome: halt, book it
   provisionally, look it up on Kalshi. Paper positions are not restored into a LIVE trader; real ones always are. */
function restoreFromLedger(now = Date.now()) {
  const rows = ledger.all(); let restored = 0;
  ST.day = today(now); ST.realizedTodayUsd = 0; ST.tradesToday = 0;
  const pending = new Map(), summarized = new Set();
  for (const r of rows) {
    if (r.ev === 'HALT') ST.halts.set(r.reason, { ts: r.ts, restored: true });
    if (r.ev === 'RESUME') { ST.halts.clear(); ST.consecutiveLosses = 0; }
    if (r.ev === 'ORDER_ATTEMPT') { const w = windowRec(r.ticker, r.closeMs); w.attempts = Math.max(w.attempts, r.attempt); w.side = r.side; pending.set(r.clientOrderId, r); }
    if (r.ev === 'ORDER_RESULT') { pending.delete(r.clientOrderId); if (r.kind === 'unknown') { const w = ST.windows.get(r.ticker); if (w) w.attempts = Math.max(w.attempts, CFG.maxAttemptsPerWindow); } }
    if (r.ev === 'FILL' && r.filled > 0) {
      const w = windowRec(r.ticker, r.closeMs); w.filledContracts += r.filled; w.side = r.side;
      if (r.mode === MODE || r.mode === 'LIVE') ST.positions.push({ id: r.id, ticker: r.ticker, closeMs: r.closeMs, side: r.side, contracts: r.filled, priceCents: r.priceCents,
        feeUsd: r.feeUsd, costUsd: r.costUsd, mode: r.mode, strike: r.strike, provisional: !!r.provisional, clientOrderId: r.clientOrderId || r.id });
      if (r.mode === MODE && today(r.ts) === ST.day) ST.tradesToday++;
    }
    if (r.ev === 'RECONCILED') applyReconciled(r);
    if (r.ev === 'SETTLED') {
      ST.positions = ST.positions.filter(p => p.id !== r.id);
      const f = fwd(r.mode); f.settled++; f.pnlUsd = Math.round((f.pnlUsd + r.pnlUsd) * 100) / 100;
      if (r.won === true) f.won++; else if (r.won === false) f.lost++; else f.void++;
      if (r.mode === MODE) {
        if (r.won === true) ST.consecutiveLosses = 0; else if (r.won === false) ST.consecutiveLosses++;
        if (today(r.ts) === ST.day) ST.realizedTodayUsd = Math.round((ST.realizedTodayUsd + r.pnlUsd) * 100) / 100;
      }
    }
    if (r.ev === 'WINDOW') summarized.add(r.ticker);
    restored++;
  }
  for (const w of ST.windows.values()) if (summarized.has(w.ticker) || w.closeMs < now) w.summarized = true;   // no duplicate WINDOW records
  for (const r of pending.values()) {
    const w = windowRec(r.ticker, r.closeMs); w.attempts = Math.max(w.attempts, CFG.maxAttemptsPerWindow);
    ledger.append({ ev: 'ORDER_RESULT', ticker: r.ticker, clientOrderId: r.clientOrderId, kind: 'unknown', filled: 0, error: 'no result was recorded before the restart' });
    latchHalt('order outcome unknown after a restart (' + r.clientOrderId + '): check /livecheck, then resume', { ticker: r.ticker });
    if (r.mode === 'LIVE') { const id = bookProvisional(r); if (CFG.live) setTimeout(() => reconcile(r.ticker, r.clientOrderId, id).catch(() => { }), 5000); }
  }
  return restored;
}

/* an order whose outcome is unknown is booked as if it filled completely at the limit (worst case for every limit), until
   reconcile() finds it on Kalshi; settlement waits for that */
function bookProvisional(a) {
  const feeUsd = kalshiFeeUsd(a.limitCents, a.contracts);
  const costUsd = Math.round((a.contracts * a.limitCents / 100 + feeUsd) * 100) / 100;
  const w = windowRec(a.ticker, a.closeMs); w.filledContracts += a.contracts; w.side = a.side;
  if (!ST.positions.some(p => p.id === a.clientOrderId))
    ST.positions.push({ id: a.clientOrderId, ticker: a.ticker, closeMs: a.closeMs, side: a.side, contracts: a.contracts, priceCents: a.limitCents, feeUsd, costUsd,
      mode: a.mode, strike: a.strike, provisional: true, clientOrderId: a.clientOrderId });
  ledger.append({ ev: 'FILL', id: a.clientOrderId, clientOrderId: a.clientOrderId, ticker: a.ticker, closeMs: a.closeMs, strike: a.strike, side: a.side, filled: a.contracts,
    priceCents: a.limitCents, feeUsd, costUsd, mode: a.mode, provisional: true, note: 'PROVISIONAL: outcome unknown, booked as a full fill at the limit until reconciled' });
  return a.clientOrderId;
}
function applyReconciled(r) {
  const p = ST.positions.find(x => x.id === r.id);
  if (!p) return;
  if (!(r.filled > 0)) { ST.positions = ST.positions.filter(x => x !== p); const w = ST.windows.get(p.ticker); if (w) w.filledContracts = Math.max(0, w.filledContracts - p.contracts); return; }
  Object.assign(p, { contracts: r.filled, priceCents: r.priceCents, feeUsd: r.feeUsd, costUsd: r.costUsd, provisional: false });
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
/* Kalshi reports fill prices and costs in book (YES) terms or in the bought side's terms; the spec does not say which for a NO
   bought through an 'ask'. The trader only buys at >= 90 c, so on a DOWN order a per-contract figure below 50 c is the YES side
   (NO bought at q = YES sold at 1 - q). Anything implausible (not between 50 c and the limit) falls back to the limit. */
function boughtPriceCents(side, pCents, limitCents) {
  if (!(pCents > 0 && pCents < 100)) return limitCents;
  const p = side === 'DOWN' && pCents < 50 ? 100 - pCents : pCents;
  return p >= 50 && p <= limitCents + 1e-6 ? Math.round(p * 1e4) / 1e4 : limitCents;
}
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
    if (res.kind === 'unknown') {
      latchHalt('order outcome unknown for ' + ctx.ticker + ': check /livecheck, then resume', { ticker: ctx.ticker });
      w.attempts = Math.max(w.attempts, CFG.maxAttemptsPerWindow);                       // this window is used, whatever happened
      const id = bookProvisional(base);
      setTimeout(() => reconcile(ctx.ticker, clientOrderId, id).catch(() => { }), 5000);
      return res;
    }
    const filled = Math.min(Number(res.filled) || 0, plan.contracts);
    if (filled > 0) {
      /* live: Kalshi's reported average fill price and fee when present (never above the limit), else the limit (the most the
         IOC order could pay) and the computed fee; paper: at the walked book average (optimistic) */
      const avg = res.avgFillDollars != null ? boughtPriceCents(ctx.sig.side, res.avgFillDollars * 100, plan.limitCents) : null;
      const priceCents = CFG.live ? (avg != null ? avg : plan.limitCents) : plan.avgCents;
      const feeUsd = CFG.live && avg != null && res.avgFeeDollars != null && res.avgFeeDollars >= 0 ? Math.round(res.avgFeeDollars * filled * 100) / 100 : kalshiFeeUsd(priceCents, filled);
      const costUsd = Math.round((filled * priceCents / 100 + feeUsd) * 100) / 100;
      const id = clientOrderId;
      w.filledContracts += filled;
      ST.positions.push({ id, ticker: ctx.ticker, closeMs: ctx.closeMs, side: ctx.sig.side, contracts: filled, priceCents, feeUsd, costUsd, mode: MODE, strike: ctx.strike });
      ST.tradesToday++;
      ledger.append({ ev: 'FILL', id, clientOrderId, ticker: ctx.ticker, closeMs: ctx.closeMs, strike: ctx.strike, side: ctx.sig.side, filled, priceCents, feeUsd, costUsd, mode: MODE,
        note: CFG.live ? (avg != null ? 'booked at the average fill price Kalshi reported' : 'booked at the limit price') : 'PAPER: assumes the displayed offers were still there (optimistic)' });
    }
    return res;
  } finally { ST.inFlight = false; }
}
/* look the order up on Kalshi by its client_order_id and book what really happened (retries every 30 s, up to 20 times;
   until then the provisional full fill at the limit stays booked and the position does not settle) */
async function reconcile(ticker, clientOrderId, id, tries = 0) {
  if (!CFG.live) return;
  const p = ST.positions.find(x => x.id === id);
  if (!p || !p.provisional) return;
  const o = await kalshi.findOrder(ticker, clientOrderId);
  if (!o.ok) {
    ledger.append({ ev: 'RECONCILE_FAILED', ticker, clientOrderId, try: tries + 1, error: String(o.error).slice(0, 200) });
    if (tries + 1 < 20) setTimeout(() => reconcile(ticker, clientOrderId, id, tries + 1).catch(() => { }), 30000);
    return;
  }
  const filled = Math.min(o.found ? o.filled : 0, p.contracts);
  let priceCents = p.priceCents, feeUsd = 0, costUsd = 0;
  if (filled > 0) {
    feeUsd = o.feesDollars > 0 ? Math.round(o.feesDollars * 100) / 100 : kalshiFeeUsd(p.priceCents, filled);
    priceCents = o.costDollars > 0 ? boughtPriceCents(p.side, o.costDollars / filled * 100, p.priceCents) : p.priceCents;
    costUsd = Math.round((filled * priceCents / 100 + feeUsd) * 100) / 100;
  }
  const rec = ledger.append({ ev: 'RECONCILED', id, ticker, clientOrderId, found: !!o.found, filled, status: o.status || null, priceCents, feeUsd, costUsd });
  applyReconciled(rec);
}

/* ------------------------------ settlement ------------------------------ */
async function settleOpen(now = Date.now()) {
  for (const p of [...ST.positions]) {
    if (now < p.closeMs + 3000) continue;
    if (p.provisional) { if (now - p.closeMs > 3 * 3600 * 1000 && !p.flagged) { p.flagged = true; latchHalt('position ' + p.ticker + ' still unreconciled after 3 h'); } continue; }
    let res = null;
    const d = S && S.SETTLE && S.SETTLE.done.find(x => x.ticker === p.ticker && x.status === 'SETTLED');
    if (d) res = { result: d.result, official: d.official, source: 'engine' };
    else if (!p.nextPoll || now >= p.nextPoll) { p.nextPoll = now + 5000; const m = await kalshi.marketResult(p.ticker); if (m) res = { ...m, source: 'kalshi' }; }
    if (!res) { if (now - p.closeMs > 3 * 3600 * 1000 && !p.flagged) { p.flagged = true; latchHalt('position ' + p.ticker + ' unsettled after 3 h'); } continue; }
    /* a finalized market without a yes/no result (void): settled at P&L 0 (assumed refund), and a LIVE one halts for review */
    const won = res.nonBinary ? null : (p.side === 'UP') === (res.result === 'yes');
    const pnlUsd = won == null ? 0 : Math.round(((won ? p.contracts : 0) - p.costUsd) * 100) / 100;
    ST.positions = ST.positions.filter(x => x !== p);
    const f = fwd(p.mode); f.settled++; f.pnlUsd = Math.round((f.pnlUsd + pnlUsd) * 100) / 100; if (won === true) f.won++; else if (won === false) f.lost++; else f.void++;
    if (p.mode === MODE) {
      rollDay(now); ST.realizedTodayUsd = Math.round((ST.realizedTodayUsd + pnlUsd) * 100) / 100;
      if (won === true) ST.consecutiveLosses = 0; else if (won === false) ST.consecutiveLosses++;
    }
    ledger.append({ ev: 'SETTLED', id: p.id, ticker: p.ticker, side: p.side, contracts: p.contracts, costUsd: p.costUsd, result: res.result, official: res.official,
      strike: p.strike, won, pnlUsd, mode: p.mode, source: res.source, note: won == null ? 'non-binary result: P&L assumed 0 (refund); verify on Kalshi' : undefined });
    if (won == null && p.mode === 'LIVE') latchHalt('non-binary settlement (' + res.result + ') for ' + p.ticker + ': verify the refund on Kalshi, then resume');
    if (won === false && p.mode === MODE && ST.consecutiveLosses >= CFG.maxConsecutiveLosses) latchHalt(ST.consecutiveLosses + ' consecutive loss(es) (last ' + p.ticker + '): review before resuming');
    if (p.mode === MODE && ST.realizedTodayUsd <= -Math.abs(CFG.dailyLossLimitUsd)) latchHalt('daily loss limit $' + CFG.dailyLossLimitUsd + ' reached');
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
  if (ST.busy || ST.stopping) return; ST.busy = true;
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
async function pollExchange() { const s = await kalshi.exchangeStatus(); if (s.ok) ST.exchange = { tradingActive: s.tradingActive, exchangeActive: s.exchangeActive, index: s.index, note: s.note, ts: Date.now() }; }

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
  const one = (mode) => { const f = fwd(mode), n = f.won + f.lost;
    return { mode, settled: f.settled, won: f.won, lost: f.lost, void: f.void, pnlUsd: f.pnlUsd,
      lossRatePct: n ? Math.round(10000 * f.lost / n) / 100 : null, lossRateUpper95Pct: n ? Math.round(10000 * cpUpper(f.lost, n)) / 100 : null,
      note: 'observed by this trader; ' + (mode === 'LIVE' ? 'real fills' : 'paper fills (optimistic)') }; };
  return { ...EVIDENCE, forward: one(MODE), otherMode: one(MODE === 'LIVE' ? 'DRY-RUN' : 'LIVE') };
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
function send(res, code, obj, { cors = true } = {}) {
  res.statusCode = code; res.setHeader('Content-Type', 'application/json; charset=utf-8'); res.setHeader('Cache-Control', 'no-store');
  if (cors) res.setHeader('Access-Control-Allow-Origin', '*');
  res.end(JSON.stringify(obj, null, 1));
}
/* admin routes: the X-Admin-Token header must equal TRADER_ADMIN_TOKEN (constant-time); never a query parameter */
function adminOk(req) {
  if (!CFG.adminToken) return false;
  const tok = String(req.headers['x-admin-token'] || '');
  return crypto.timingSafeEqual(crypto.createHash('sha256').update(tok).digest(), crypto.createHash('sha256').update(CFG.adminToken).digest());
}
const intParam = (u, name, def, max) => { const v = Math.floor(Number(u.searchParams.get(name))); return Number.isFinite(v) && v >= 1 ? Math.min(max, v) : def; };
const ENGINE_ROUTE = /^\/[A-Za-z0-9._-]+(\/[A-Za-z0-9._-]+)*$/;
const server = http.createServer(async (req, res) => {
  let u; try { u = new URL(req.url, 'http://localhost'); } catch (_) { return send(res, 400, { error: 'bad url' }); }
  const p = u.pathname.replace(/\/+$/, '') || '/';
  try {
    if (p.startsWith('/engine/')) {   // read-only passthrough to the embedded engine's own endpoints (/engine/health, /engine/exec, /engine/dq ...)
      if (req.method !== 'GET') return send(res, 405, { error: 'GET only' });
      const sub = p.slice('/engine'.length);
      if (!ENGINE_ROUTE.test(sub)) return send(res, 404, { error: 'not found' });
      req.url = sub + u.search;
      for (const h of S.server.listeners('request')) Promise.resolve().then(() => h(req, res)).catch(e => { ST.lastErr = 'engine route: ' + String(e && e.message || e).slice(0, 200); if (!res.headersSent) send(res, 500, { error: 'engine route failed' }); });
      return;
    }
    if (p === '/' || p === '/health') return send(res, 200, { ok: true, version: VERSION, mode: MODE, modeNote: MODE_NOTE, uptimeSec: Math.round(process.uptime()),
      ticks: ST.ticks, tickErrors: ST.tickErrors, halted: haltReasons(), ledgerErr: ledger.state.err, lockMaxFlip: CFG.lockMaxFlip, maxTradeUsd: CFG.maxTradeUsd, engineSha256: ENGINE_SHA256.slice(0, 16),
      lastDecision: ST.lastDecision && { action: ST.lastDecision.action, ticker: ST.lastDecision.ticker, tau: ST.lastDecision.tau, why: (ST.lastDecision.why || []).slice(0, 2) } });
    if (p === '/status') return send(res, 200, { version: VERSION, mode: MODE, halted: haltReasons(), decision: ST.lastDecision, engine: ST.lastSnapshot,
      risk: { day: ST.day, realizedTodayUsd: ST.realizedTodayUsd, tradesToday: ST.tradesToday, consecutiveLosses: ST.consecutiveLosses, openExposureUsd: openExposureUsd(), positions: ST.positions },
      exchange: ST.exchange, lastErr: ST.lastErr });
    if (p === '/windows') { const n = intParam(u, 'n', 20, 200); return send(res, 200, [...ST.windows.values()].slice(-n)); }
    if (p === '/trades') { const n = intParam(u, 'n', 100, 2000); return send(res, 200, ledger.tail(2000).filter(r => /ORDER_|FILL|SETTLED|RECONCILE/.test(r.ev)).slice(-n)); }
    if (p === '/stats') return send(res, 200, stats());
    if (p === '/ledger') { const n = intParam(u, 'n', 200, 2000); return send(res, 200, { file: CFG.ledgerFile, lines: ledger.tail(n), err: ledger.state.err }); }
    if (p === '/ledger/verify') return send(res, 200, ledger.verify());
    if (p === '/config') return send(res, 200, publicConfig());
    if (p === '/live') return send(res, 200, { mode: MODE, modeNote: MODE_NOTE, credentials: kalshi.ready(), lastResult: ST.live.lastResult, orders: ST.live.orders.slice(-10) });
    if (p === '/livecheck') {   // account data: admin only, no CORS
      if (!CFG.adminToken) return send(res, 403, { error: 'disabled: set TRADER_ADMIN_TOKEN, then send it in the X-Admin-Token header' }, { cors: false });
      if (!adminOk(req)) return send(res, 403, { error: 'bad token' }, { cors: false });
      if (!kalshi.ready()) return send(res, 200, { ready: false, note: 'no KALSHI_KEY_ID / KALSHI_PRIVATE_KEY' }, { cors: false });
      const pos = await kalshi.positions();
      const mine = pos && Array.isArray(pos.market_positions) ? pos.market_positions.filter(x => /^KXBTC15M-/.test(String(x.ticker))) : pos && pos.error ? { error: 'positions unavailable' } : [];
      const bal = await kalshi.balance();
      return send(res, 200, { ready: true, balance: bal && bal.error ? { error: 'balance unavailable' } : bal, kxbtc15mPositions: mine,
        traderPositions: ST.positions }, { cors: false });
    }
    if (p === '/halt') {
      const on = u.searchParams.get('on');
      if (on === '1') { if (!ST.manualHalt) ledger.append({ ev: 'HALT', reason: 'manual halt (HTTP)' }); ST.manualHalt = true; return send(res, 200, { ok: true, halted: haltReasons() }); }
      if (on === '0') {
        if (req.method !== 'POST') return send(res, 405, { error: 'resume is POST only: curl -X POST -H "X-Admin-Token: <TRADER_ADMIN_TOKEN>" <url>/halt?on=0' }, { cors: false });
        if (!CFG.adminToken) return send(res, 403, { error: 'resume is disabled: set TRADER_ADMIN_TOKEN (restart to apply), then POST /halt?on=0 with the X-Admin-Token header. A restart alone does not clear halts.' }, { cors: false });
        if (!adminOk(req)) return send(res, 403, { error: 'bad token' }, { cors: false });
        ST.manualHalt = false; ST.halts.clear(); ST.consecutiveLosses = 0; ledger.append({ ev: 'RESUME', by: 'admin token' });
        return send(res, 200, { ok: true, halted: haltReasons() }, { cors: false });
      }
      return send(res, 200, { halted: haltReasons(), usage: 'GET /halt?on=1 halts (no token); POST /halt?on=0 with header X-Admin-Token resumes' });
    }
    if (p === '/selftest') return send(res, 200, selfTest());
    return send(res, 404, { error: 'not found', routes: ['/health', '/status', '/windows', '/trades', '/stats', '/ledger', '/ledger/verify', '/config', '/live', '/livecheck', '/halt', '/selftest', '/engine/<route>'] });
  } catch (e) { return send(res, 500, { error: String(e && e.message || e) }); }
});

/* ------------------------------ boot ------------------------------ */
function boot() {
  if (ENGINE_SHA256 !== ENGINE_SHA256_EXPECTED && !flag('ALLOW_ENGINE_MISMATCH', false)) throw new Error('engine file differs from the validated 2.8.1 build (' + ENGINE_SHA256 + ')');
  loadEngine();
  /* an engine or route promise that rejects must not take the process down (a crash mid-order loses its result) */
  process.on('unhandledRejection', e => { ST.lastErr = 'unhandled rejection: ' + String(e && e.stack || e).slice(0, 300); console.error('[' + VERSION + '] ' + ST.lastErr); });
  /* Render stops a service with SIGTERM: stop ticking, let an order in flight finish and be written, then exit */
  process.on('SIGTERM', () => {
    ST.stopping = true; const t0 = Date.now();
    const wait = () => { if (!ST.inFlight || Date.now() - t0 > KALSHI_TIMEOUT_MS + 2000) { ledger.append({ ev: 'STOP', signal: 'SIGTERM', inFlight: ST.inFlight }); process.exit(0); } setTimeout(wait, 100); };
    wait();
  });
  const restored = restoreFromLedger();
  ledger.append({ ev: 'BOOT', version: VERSION, mode: MODE, modeNote: MODE_NOTE, engineSha256: ENGINE_SHA256, lockMaxFlip: CFG.lockMaxFlip, maxTradeUsd: CFG.maxTradeUsd, restoredRecords: restored,
    haltsRestored: [...ST.halts.keys()] });
  S.ensureSentinel();          // start the engine's feeds and its own background classifier
  server.listen(CFG.port, () => console.log('[' + VERSION + '] ' + MODE + ' (' + MODE_NOTE + ') on :' + CFG.port + ' | engine ' + S.MODEL_VERSION + ' sha ' + ENGINE_SHA256.slice(0, 12) + ' | LOCK_MAX_FLIP ' + CFG.lockMaxFlip + ' | max $' + CFG.maxTradeUsd + '/trade'));
  setInterval(() => { tick().catch(() => { }); }, CFG.tickMs);
  pollExchange().catch(() => { }); setInterval(() => { pollExchange().catch(() => { }); }, 60000);
}
if (require.main === module) boot();

module.exports = { boughtPriceCents, CFG, ST, MODE, MODE_NOTE, VERSION, loadEngine, evaluate, execute, reconcile, settleOpen, summarizeWindows, tick, selfTest, stats, restoreFromLedger, latchHalt, haltReasons,
  server, ledger, kalshi, publicConfig, engine: () => S, ENGINE_SHA256, ENGINE_SHA256_EXPECTED, ARM_PHRASE };
