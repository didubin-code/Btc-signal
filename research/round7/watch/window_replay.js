'use strict'; process.env.PINRADAR_REPLAY = '1'; process.env.ENABLE_WS = '0';
const fs = require('fs'), path = require('path'); const S = require(path.resolve(process.argv[2])); const RT = require(path.resolve(process.argv[3]));
const lines = fs.readFileSync(process.argv[4], 'utf8').split('\n').filter(Boolean).map(l => JSON.parse(l)); const tk = process.argv[5];
const samples = [], recs = [], boots = []; for (const o of lines) { if (o.k === 's') samples.push([o.t, o.v]); else if (o.k === 'd') recs.push(o); else if (o.k === 'boot') boots.push(o.ts); }
samples.sort((a, b) => a[0] - b[0]); for (let i = samples.length - 1; i > 0; i--) if (samples[i][0] === samples[i - 1][0]) samples.splice(i, 1);
const c = { rows: 0, in120: 0, admitted: 0, locked: 0, reasons: {}, states: {}, firstAdmit: null, maxR: 0 };
for (const rec of recs) { if (rec.kal.ticker !== tk) continue; c.rows++; const tau = (rec.kal.closeMs - rec.ts) / 1000; const snap = RT.restoreAndDecide(S, rec, samples, boots); const sig = snap.signal, pr = sig.pr11 || {}; c.states[sig.state] = (c.states[sig.state] || 0) + 1;
  if (!(tau > 0 && tau <= 120)) continue; c.in120++; if (sig.state === 'LOCKED' || sig.state === 'PROVEN LOCKED') c.locked++; if (pr.applies && pr.admit && (sig.state === 'LOCKED' || sig.state === 'PROVEN LOCKED')) { c.admitted++; if (c.firstAdmit == null) c.firstAdmit = tau; } if (pr.applies && !pr.admit) c.reasons[pr.reason] = (c.reasons[pr.reason] || 0) + 1; if (pr.R > c.maxR) c.maxR = pr.R; }
console.log(tk, JSON.stringify(c));
