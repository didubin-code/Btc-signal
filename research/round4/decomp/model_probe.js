/* Load the I2 server as a module (replay mode: no listener, no timers) and expose its probability model for decomposition. */
'use strict';
process.env.PINRADAR_REPLAY = '1'; process.env.ENABLE_WS = '0';
const path = process.argv[2];
const S = require(path);
const M = S.M25_MODEL;
console.log(JSON.stringify({ regime: M.regime ? { kind: M.regime.kind, edges: M.regime.edges, L: M.regime.L } : null, basisQ_n: (M.basisQ || []).length, basisQ_mean: (M.basisQ || []).reduce((a, b) => a + b, 0) / ((M.basisQ || []).length || 1),
  LIVE_VOL_SCALE: S.LIVE_VOL_SCALE, RECAL: [S.RECAL_QUIET, S.RECAL_NORMAL, S.RECAL_ACTIVE], exportsHave: ['m25PUp', 'recalPUp26', 'recalRatio26', 'm25Bucket', 'm25VarUnits', 'recalFlip26'].map(k => k + ':' + (typeof S[k])) }));
// pf for one input set: live path = m25PUp (with sigEff = sigma_row, which already includes LIVE_VOL_SCALE and staleness inflation) -> recal
function pf(inp) {
  const pUp = S.m25PUp(M, { tau: inp.tau, gap: inp.gap, sigBps: inp.sigma, S: inp.S, mu: inp.mu, bucket: inp.bucket });
  const r = S.recalRatio26(M.regime && M.regime.kind === 'sig' ? inp.bucket : -1);
  const p = S.recalPUp26(pUp, r);
  const side = p >= 0.5 ? 'UP' : 'DOWN';
  return { pUp, pf: side === 'UP' ? 1 - p : p, side, ratio: r, pfModel: side === 'UP' ? 1 - pUp : pUp };
}
if (process.argv[3]) {
  const rows = JSON.parse(require('fs').readFileSync(process.argv[3], 'utf8'));
  const out = rows.map(inp => ({ ...inp, model: pf(inp) }));
  console.log(JSON.stringify(out));
}
setTimeout(() => process.exit(0), 50);
