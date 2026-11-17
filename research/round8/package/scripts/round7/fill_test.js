/* Newest-print live-index substitution: targeted checks on recorded seconds (exact engine).
   (1) phase scan: at inside-minute records, how old is the newest passed print at the decision time (now - tp0)? how often is it live-filled?
   (2) double fill: at a record with now - tp0 <= 100 ms, delete the PREVIOUS print's sample (tp0 - 1 s): does the engine fill two passed
       prints with the live index, and does PR11 then admit?  (3) no eligible substitute: newest print older than 1.1 s with its sample deleted.
   (4) the substituted value: equals the live index (finite), the print belongs to this window (off in 0..59, tp <= now).
   usage: PR11_MODE=gate node fill_test.js <server.js> <RT> <tape>... */
'use strict'; process.env.PINRADAR_REPLAY = '1'; process.env.ENABLE_WS = '0';
const fs = require('fs'), path = require('path'); const S = require(path.resolve(process.argv[2])); const RT = require(path.resolve(process.argv[3]));
const stats = { secs: 0, filled: 0, phaseLe100: 0, phaseHist: {} }; const cands = [];
for (const tape of process.argv.slice(4)) {
  const lines = fs.readFileSync(tape, 'utf8').split('\n').filter(Boolean).map(l => JSON.parse(l)); const samples = [], recs = [], boots = [];
  for (const o of lines) { if (o.k === 's') samples.push([o.t, o.v]); else if (o.k === 'd') recs.push(o); else if (o.k === 'boot') boots.push(o.ts); }
  samples.sort((a, b) => a[0] - b[0]); for (let i = samples.length - 1; i > 0; i--) if (samples[i][0] === samples[i - 1][0]) samples.splice(i, 1);
  for (const rec of recs) {
    const tau = (rec.kal.closeMs - rec.ts) / 1000; if (!(tau > 0 && tau <= 60)) continue;
    const close = rec.kal.closeMs, now = rec.ts; let off0 = null; for (let off = 0; off < 60; off++) { if (close - off * 1000 <= now) { off0 = off; break; } }
    if (off0 == null) continue; const phase = now - (close - off0 * 1000); stats.secs++; const b = phase < 100 ? '<100' : phase < 300 ? '100-300' : phase < 600 ? '300-600' : '>=600'; stats.phaseHist[b] = (stats.phaseHist[b] || 0) + 1;
    const snap = RT.restoreAndDecide(S, rec, samples, boots); const g = snap.geo; if (g && g.lockedFilledLive > 0) stats.filled++;
    if (phase <= 100 && g && g.nLock >= 2 && snap.signal.pr11 && snap.signal.pr11.admit && cands.length < 3) cands.push({ tape, rec, samples, boots, off0, phase });
    if (phase > 1100 - 1000 && phase >= 200 && g && g.nLock >= 2 && snap.signal.pr11 && snap.signal.pr11.admit && cands.length >= 3 && cands.length < 4) cands.push({ tape, rec, samples, boots, off0, phase, late: true });
  }
}
console.log('phase scan:', JSON.stringify(stats));
for (const c of cands) {
  const { rec, samples, boots, off0, phase } = c; const close = rec.kal.closeMs, now = rec.ts; const tp0 = close - off0 * 1000, tp1 = tp0 - 1000;
  const base = RT.restoreAndDecide(S, rec, samples, boots);
  const d1 = RT.restoreAndDecide(S, rec, samples.filter(s => Math.abs(s[0] - tp1) > 600), boots);   // previous print's sample deleted
  const d0 = RT.restoreAndDecide(S, rec, samples.filter(s => Math.abs(s[0] - tp0) > 600), boots);   // newest print's sample deleted (fill expected while phase <= 1100)
  const show = (sn, label) => { const g = sn.geo, pr = sn.signal.pr11 || {}; console.log('  %s | state %s | nLock %d sampled %d filledLive %d missing %s | pr11 admit %s reason %s | index %s lockedMean %s', label, sn.signal.state, g.nLock, g.lockedObserved, g.lockedFilledLive, pr.nMissing, pr.admit, pr.reason, g.index, g.lockedMean); };
  console.log(c.late ? 'LATE-PHASE CASE' : 'DOUBLE-FILL CASE', rec.kal.ticker, 'tau', ((close - now) / 1000).toFixed(2), 'newest print age', phase, 'ms');
  show(base, 'complete                       '); show(d0, 'newest print sample deleted    '); show(d1, 'previous print sample deleted  ');
  if (!c.late) { const d2 = RT.restoreAndDecide(S, rec, samples.filter(s => Math.abs(s[0] - tp1) > 600 && Math.abs(s[0] - tp0) > 600), boots); show(d2, 'both deleted                   '); }
}
