/* Pin Radar Trader 5.0 — the entry decision, as a pure function (no I/O, fully testable).

   The direction, the reversal risk, the expected value after fees, the book, the timing and the data checks all come from the
   Pin Radar 2.8.1 engine (embedded, byte-identical; run with LOCK_MAX_FLIP = 0.002). The engine's own action line must say
   TRADE NOW, which already requires:
     LOCKED at the configured flip threshold (0.2 %), no REVERSAL WARNING, no DATA UNRELIABLE / hard gate,
     a fresh Kalshi book with enough offers for the order, the cautious edge after the fee >= MIN_EDGE_CENTS,
     the edge surviving an adverse 1.645 sigma move during the order time, the called side offered at >= 90 c (market-disagreement guard),
     and at least order time + 3 s before the close.
   The trader then adds its own, stricter checks (each one listed in the returned reasons when it blocks):
     warm engine (validated configuration), price band, sizing within the dollar cap including the fee, the edge recomputed at the
     exact limit and size, one entry per window and never the other side, and the risk state (halts, loss limits, open exposure). */
'use strict';
const { kalshiFeeUsd } = require('./kalshi');

/* the most contracts whose cost (contracts x limit + Kalshi fee for the order) fits within maxUsd */
function sizeForBudget(limitCents, maxUsd, maxContracts = 1e6) {
  if (!(limitCents > 0 && limitCents < 100) || !(maxUsd > 0)) return { contracts: 0, costUsd: 0, feeUsd: 0 };
  let n = Math.min(maxContracts, Math.floor((maxUsd * 100) / limitCents));
  while (n >= 1) {
    const fee = kalshiFeeUsd(limitCents, n), cost = Math.round(n * limitCents) / 100 + fee;
    if (cost <= maxUsd + 1e-9) return { contracts: n, costUsd: Math.round(cost * 100) / 100, feeUsd: fee };
    n--;
  }
  return { contracts: 0, costUsd: 0, feeUsd: 0 };
}

/* walk the asks of the called side: the limit (worst level) needed to buy n contracts, and the average */
function walkAsks(levels, n) {
  let need = n, cost = 0, worst = null;
  for (const [p, s] of levels || []) {
    if (!(p > 0 && p < 100 && s > 0)) continue;
    const take = Math.min(need, s); cost += take * p; need -= take; worst = p;
    if (need <= 1e-9) break;
  }
  return need > 1e-9 ? null : { limitCents: worst, avgCents: cost / n };
}

/* ctx: { now, sig (engine signal), book: {ok, ageMs, yesAsks, noAsks}, ticker, strike, tau, exchange: {tradingActive, ts} }
   st:  { halted: [reasons], windows: Map(ticker -> {attempts, filledContracts, side}), realizedTodayUsd, consecutiveLosses,
          tradesToday, openExposureUsd, inFlight }
   cfg: see trader.js CFG                                                                                                  */
function decide(ctx, st, cfg) {
  const why = [];
  const sig = ctx.sig;
  const out = { action: 'SKIP', why, ticker: ctx.ticker || null, side: sig && sig.side || null, tau: ctx.tau };

  /* 1. market */
  if (!ctx.ticker || !/^KXBTC15M-/.test(ctx.ticker)) why.push('no KXBTC15M market');
  if (!(ctx.strike > cfg.strikeSaneMin)) why.push('strike missing or implausible');
  if (!Number.isFinite(ctx.tau) || ctx.tau <= 0) why.push('window closed or no countdown');
  if (!sig) { why.push('no engine signal'); return out; }

  /* 2. reversal risk (engine, 0.2 % threshold) */
  const locked = sig.state === 'LOCKED' || sig.state === 'PROVEN LOCKED';
  if (!locked) why.push('not LOCKED (' + sig.state + ')');
  if (locked && !(sig.pFlip != null && sig.pFlip <= cfg.lockMaxFlip + 1e-12)) why.push('flip risk ' + sig.pFlip + ' above the trader threshold ' + cfg.lockMaxFlip);
  if (sig.side !== 'UP' && sig.side !== 'DOWN') why.push('no side');

  /* 3. data integrity */
  const hard = (sig.gates && sig.gates.hard) || [];
  if (hard.length) why.push('hard gate: ' + hard[0]);
  if (sig.state === 'DATA UNRELIABLE') why.push('data unreliable');
  const wu = sig.warmup || {};
  if (cfg.requireWarmVol && (wu.volEnvelope || wu.lockedAvailable === false || (wu.fullHistoryInSec || 0) > 0)) why.push('engine volatility history not full yet (' + (wu.indexHistorySec != null ? Math.floor(wu.indexHistorySec) : '?') + ' s)');
  if (cfg.requireWarmBasis && wu.basisCold) why.push('engine basis model cold (' + wu.basisLiveN + ' settled windows)');

  /* 4. the engine's execution decision (EV, stress, book, timing, 90 c guard) */
  const tr = sig.trade || {};
  const head = sig.exec && sig.exec.headline;
  if (tr.action !== 'TRADE NOW' || head !== 'TRADE NOW') why.push('engine says ' + (head || '?') + ' / ' + (tr.action || '?') + (sig.exec && sig.exec.reason ? ': ' + sig.exec.reason : ''));
  if (!(ctx.tau >= cfg.minTauSec)) why.push('less than ' + cfg.minTauSec + ' s left');

  /* 5. book, price band, size, edge at the exact limit */
  const book = ctx.book || {};
  if (!book.ok || !(book.ageMs != null && book.ageMs <= cfg.maxBookAgeMs)) why.push('order book missing or older than ' + cfg.maxBookAgeMs + ' ms');
  const levels = sig.side === 'UP' ? book.yesAsks : book.noAsks;
  const best = levels && levels.length ? levels[0][0] : null;
  let plan = null;
  if (best != null) {
    const sz = sizeForBudget(best, cfg.maxTradeUsd, cfg.maxContracts);
    const w = sz.contracts >= 1 ? walkAsks(levels, sz.contracts) : null;
    if (!w) why.push('not enough offered to fill ' + sz.contracts + ' contracts');
    else {
      const sz2 = sizeForBudget(w.limitCents, cfg.maxTradeUsd, cfg.maxContracts);          // re-size at the worst level actually needed
      const w2 = sz2.contracts >= 1 ? walkAsks(levels, sz2.contracts) : null;
      if (!w2) why.push('not enough offered within the budget');
      else {
        const fee = kalshiFeeUsd(w2.limitCents, sz2.contracts);
        const pCautious = sig.pFlipCons != null ? 1 - sig.pFlipCons : null;
        const evConsCents = pCautious == null ? null : 100 * pCautious - w2.limitCents - (100 * fee) / sz2.contracts;   // at the LIMIT (worst case of the fill)
        plan = { contracts: sz2.contracts, limitCents: w2.limitCents, avgCents: Math.round(w2.avgCents * 1000) / 1000, feeUsd: fee,
          maxCostUsd: Math.round((sz2.contracts * w2.limitCents / 100 + fee) * 100) / 100, evConsCentsAtLimit: evConsCents == null ? null : Math.round(evConsCents * 1000) / 1000 };
        if (w2.limitCents < cfg.minAskCents) why.push('price ' + w2.limitCents + ' c below ' + cfg.minAskCents + ' c (the market disagrees)');
        if (w2.limitCents > cfg.maxAskCents) why.push('price ' + w2.limitCents + ' c above ' + cfg.maxAskCents + ' c');
        if (plan.maxCostUsd > cfg.maxTradeUsd + 1e-9) why.push('cost ' + plan.maxCostUsd + ' above the $' + cfg.maxTradeUsd + ' cap');
        if (!(evConsCents != null && evConsCents >= cfg.minEdgeCents)) why.push('cautious edge at the limit ' + (evConsCents == null ? '?' : evConsCents.toFixed(3)) + ' c < ' + cfg.minEdgeCents + ' c');
      }
    }
  } else why.push('nobody is selling ' + (sig.side || 'the called side'));
  out.plan = plan;

  /* 6. one entry per window, never the other side */
  const w = st.windows && ctx.ticker ? st.windows.get(ctx.ticker) : null;
  if (w && w.side && w.side !== sig.side) why.push('already positioned on ' + w.side + ' in this window');
  if (w && w.filledContracts > 0) why.push('already entered this window');
  if (w && w.attempts >= cfg.maxAttemptsPerWindow) why.push('order attempts for this window used up');

  /* 7. risk state */
  if (st.halted && st.halted.length) why.push('halted: ' + st.halted.join('; '));
  if (st.inFlight) why.push('an order is in flight');
  if (st.realizedTodayUsd <= -Math.abs(cfg.dailyLossLimitUsd)) why.push('daily loss limit reached');
  if (st.consecutiveLosses >= cfg.maxConsecutiveLosses) why.push(st.consecutiveLosses + ' consecutive losses');
  if (st.tradesToday >= cfg.maxTradesPerDay) why.push('daily trade count reached');
  if (plan && st.openExposureUsd + plan.maxCostUsd > cfg.maxOpenUsd + 1e-9) why.push('open exposure would exceed $' + cfg.maxOpenUsd);
  if (cfg.requireExchangeOpen && !(ctx.exchange && ctx.exchange.tradingActive && ctx.now - ctx.exchange.ts <= 300000)) why.push('Kalshi exchange status not confirmed active');

  if (!why.length) out.action = 'BUY';
  return out;
}

module.exports = { decide, sizeForBudget, walkAsks };
