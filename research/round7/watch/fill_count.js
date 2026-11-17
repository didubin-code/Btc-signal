'use strict'; process.env.PINRADAR_REPLAY = '1'; process.env.ENABLE_WS = '0';
const fs = require('fs'), path = require('path'); const S = require(path.resolve(process.argv[2])); const RT = require(path.resolve(process.argv[3]));
const c = { secs: 0, fill0: 0, fill1: 0, fill2plus: 0, fill2admittedB8: 0 };
for (const tape of process.argv.slice(4)) { const lines = fs.readFileSync(tape, 'utf8').split('\n').filter(Boolean).map(l => JSON.parse(l)); const samples = [], recs = [], boots = [];
  for (const o of lines) { if (o.k === 's') samples.push([o.t, o.v]); else if (o.k === 'd') recs.push(o); else if (o.k === 'boot') boots.push(o.ts); }
  samples.sort((a, b) => a[0] - b[0]); for (let i = samples.length - 1; i > 0; i--) if (samples[i][0] === samples[i - 1][0]) samples.splice(i, 1);
  for (const rec of recs) { const tau = (rec.kal.closeMs - rec.ts) / 1000; if (!(tau > 0 && tau <= 60)) continue; const snap = RT.restoreAndDecide(S, rec, samples, boots); const g = snap.geo; if (!g || !(g.nLock >= 1)) continue; c.secs++; const f = g.lockedFilledLive || 0; if (f === 0) c.fill0++; else if (f === 1) c.fill1++; else { c.fill2plus++; const pr = snap.signal.pr11 || {}; if (pr.floorMet && pr.reasons && pr.reasons.length === 1 && pr.reasons[0] === 'missing') c.fill2admittedB8++; } } }
console.log(JSON.stringify(c));
