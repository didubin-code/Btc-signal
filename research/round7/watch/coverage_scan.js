/* Targeted measurement: at every recorded second inside the settlement minute (prints passed >= 1), how many passed print seconds lack a
   matched index sample (coverage < 1), and what the exposure would be if unmatched seconds were treated as unknown prints instead of being
   valued at the observed mean. usage: PR11_MODE=gate node coverage_scan.js <server.js> <RT> <tape.ndjson> ... */
'use strict'; process.env.PINRADAR_REPLAY = '1'; process.env.ENABLE_WS = '0';
const fs = require('fs'), path = require('path'); const S = require(path.resolve(process.argv[2])); const RT = require(path.resolve(process.argv[3]));
const tot = { secs: 0, cov1: 0, covLt1: 0, covLt09: 0, filled: 0, admitted: 0, admittedCovLt1: 0, flips: 0, maxMissing: 0, covHist: {}, ex: [] };
for (const tape of process.argv.slice(4)) {
  const lines = fs.readFileSync(tape, 'utf8').split('\n').filter(Boolean).map(l => JSON.parse(l));
  const samples = [], recs = [], boots = [];
  for (const o of lines) { if (o.k === 's') samples.push([o.t, o.v]); else if (o.k === 'd') recs.push(o); else if (o.k === 'boot') boots.push(o.ts); }
  samples.sort((a, b) => a[0] - b[0]); for (let i = samples.length - 1; i > 0; i--) if (samples[i][0] === samples[i - 1][0]) samples.splice(i, 1);
  for (const rec of recs) {
    const snap = RT.restoreAndDecide(S, rec, samples, boots); const g = snap.geo, sig = snap.signal; if (!g || !(g.nLock >= 1)) continue;
    const tau = (rec.kal.closeMs - rec.ts) / 1000; if (!(tau > 0 && tau <= 60)) continue;
    tot.secs++; const cov = g.lockedCoverage; const miss = g.nLock - g.lockedObserved; tot.maxMissing = Math.max(tot.maxMissing, miss);
    const key = cov >= 1 ? '1.0' : cov >= 0.9 ? '0.9-1' : '<0.9'; tot.covHist[key] = (tot.covHist[key] || 0) + 1;
    if (cov >= 1) tot.cov1++; else if (cov >= 0.9) tot.covLt1++; else tot.covLt09++;
    const pr = sig.pr11 || {}; const adm = pr.applies && pr.admit && (sig.state === 'LOCKED' || sig.state === 'PROVEN LOCKED');
    if (adm) tot.admitted++;
    if (g.lockedFilledLive > 0) tot.filled++;
    if (cov < 1) {
      if (adm) { tot.admittedCovLt1++; if (!tot.partial) tot.partial = []; if (tot.partial.length < 6) tot.partial.push({ tape: tape.split('/').pop(), tk: rec.kal.ticker, tau: +tau.toFixed(2), nLock: g.nLock, lobs: g.lockedObserved, cov, R: (sig.pr11 || {}).R, rstar: (sig.pr11 || {}).rstar }); }
      /* corrected rule: unmatched print seconds are unknown prints */
      const K = rec.kal.strike, lobs = g.lockedObserved, rPrime = 60 - lobs, gapPrime = (g.lockedMean * lobs + g.index * rPrime) / 60 - K;
      const Rp = Math.abs(gapPrime) / K * 1e4 * 60 / Math.max(1, Math.min(60, rPrime)), hP = Math.max(1, Math.min(60, rPrime)), rstarP = S.PR11_RSTAR[hP - 1];
      const admP = Rp >= rstarP; if (adm && !admP) { tot.flips++; if (tot.ex.length < 5) tot.ex.push({ tk: rec.kal.ticker, tau: tau.toFixed(1), nLock: g.nLock, lobs, R: pr.R, rstar: pr.rstar, Rp: +Rp.toFixed(2), rstarP }); }
    }
  }
}
console.log(JSON.stringify(tot));
