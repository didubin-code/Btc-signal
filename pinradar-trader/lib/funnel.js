/* Trade-frequency accountability: LOCKED SIGNAL -> EXECUTABLE OPPORTUNITY -> POSITIVE-EV TRADE -> ORDER ATTEMPT -> CONFIRMED FILL.
   classify() maps one decision's reasons to the first funnel stage that blocked it; summarize() aggregates the persistent WINDOW,
   OUTCOME and SETTLED ledger records. The directional record of LOCKED signals (OUTCOME) is kept apart from trading P&L (SETTLED). */
'use strict';

/* earliest blocking stage, in funnel order */
const ORDER = ['data', 'timing', 'liquidity', 'ev', 'risk', 'other'];
const RULES = [   // checked in this order for one reason string ("nobody is selling" beats the engine's TOO LATE label)
  ['data', /hard gate|data unreliable|volatility history|basis model cold|strike missing|no KXBTC15M|no engine signal|no side|window closed|order book missing|ledger write/],
  ['liquidity', /nobody is selling|not enough offered|market disagrees/],
  ['timing', /TOO LATE|less than \d+ s left|s left/],
  ['liquidity', /below \d+(\.\d+)? c|above \d+(\.\d+)? c|offered at/],
  ['ev', /edge|stressed value|does not survive|DO NOT TRADE|SIT OUT/],
  ['risk', /halted|in flight|daily loss|consecutive|trade count|open exposure|exchange status|already entered|already positioned|attempts for this window|retry spacing/],
];
function category(reason) {
  for (const [c, re] of RULES) if (re.test(reason)) return c;
  return 'other';
}
/* -> { stage reached: 'blocked'|'executable'|'positiveEv'|'buy', blockedBy: category|null, reason } */
function classify(dec) {
  if (dec.action === 'BUY') return { reached: 'buy', blockedBy: null, reason: null };
  const cats = dec.why.map(w => [category(w), w]);
  let best = null;
  for (const c of ORDER) { const hit = cats.find(x => x[0] === c); if (hit) { best = hit; break; } }
  const blockedBy = best ? best[0] : 'other';
  const reached = blockedBy === 'risk' ? 'positiveEv' : blockedBy === 'ev' ? 'executable' : 'blocked';
  return { reached, blockedBy, reason: best ? best[1] : null };
}
const norm = r => String(r || '').replace(/[0-9]+(\.[0-9]+)?/g, '#').slice(0, 90);

/* aggregate over ledger rows (optionally only windows closing at or after sinceMs) */
function summarize(rows, sinceMs = 0) {
  const W = rows.filter(r => r.ev === 'WINDOW' && r.closeMs >= sinceMs);
  const out = { windowsEvaluated: W.length, locked: 0, executable: 0, positiveEv: 0, attempted: 0, filled: 0,
    attemptedNotFilled: 0, firstLockedTauSec: { median: null, p10: null, p90: null },
    missedBy: { data: 0, timing: 0, liquidity: 0, ev: 0, risk: 0, unfilled: 0, other: 0 }, topMissedReasons: [],
    directional: { lockedWithOutcome: 0, lockedCorrect: 0, lockedWrong: 0, wrong: [] },
    trading: { LIVE: { settled: 0, won: 0, lost: 0, void: 0, pnlUsd: 0 }, 'DRY-RUN': { settled: 0, won: 0, lost: 0, void: 0, pnlUsd: 0 } },
    notes: ['locked = the engine showed LOCKED at <= the threshold in this window (a prediction, not a trade)',
      'executable = some LOCKED second passed data, timing and liquidity checks; positiveEv = it also passed the expected-value checks',
      'directional counts every LOCKED window with a settled result, traded or not; trading counts only filled orders (after fees)'] };
  const taus = [], reasons = {};
  for (const w of W) {
    const f = w.funnel || {};
    if (!(w.lockedTicks > 0)) continue;
    out.locked++; if (w.firstLockedTau != null) taus.push(w.firstLockedTau);
    if (f.executable) out.executable++;
    if (f.positiveEv) out.positiveEv++;
    if (w.attempts > 0) out.attempted++;
    if (w.filledContracts > 0) { out.filled++; continue; }
    if (w.attempts > 0) out.attemptedNotFilled++;
    const m = f.missedBy || 'other'; out.missedBy[m] = (out.missedBy[m] || 0) + 1;
    if (f.missedReason) reasons[f.missedReason] = (reasons[f.missedReason] || 0) + 1;
  }
  taus.sort((a, b) => a - b);
  const q = p => taus.length ? taus[Math.min(taus.length - 1, Math.floor(p * taus.length))] : null;
  out.firstLockedTauSec = { median: q(0.5), p10: q(0.1), p90: q(0.9), n: taus.length };
  out.topMissedReasons = Object.entries(reasons).sort((a, b) => b[1] - a[1]).slice(0, 10);
  const tickers = new Set(W.map(w => w.ticker));
  for (const r of rows) {
    if (r.ev === 'OUTCOME' && tickers.has(r.ticker) && r.lockedCorrect != null) {
      out.directional.lockedWithOutcome++;
      if (r.lockedCorrect) out.directional.lockedCorrect++; else { out.directional.lockedWrong++; out.directional.wrong.push({ ticker: r.ticker, side: r.lockedSide, result: r.result, firstLockedTau: r.firstLockedTau }); }
    }
    if (r.ev === 'SETTLED' && tickers.has(r.ticker)) {
      const t = out.trading[r.mode === 'LIVE' ? 'LIVE' : 'DRY-RUN'];
      t.settled++; t.pnlUsd = Math.round((t.pnlUsd + r.pnlUsd) * 100) / 100; if (r.won === true) t.won++; else if (r.won === false) t.lost++; else t.void++;
    }
  }
  out.directional.wrong = out.directional.wrong.slice(-20);
  return out;
}
module.exports = { classify, category, summarize, norm };
