/* What the server would have served at given seconds of a recorded window under the PR11 build (exact tape restore-and-decide):
   state, action, why, first reason, pr11 field. usage: PR11_MODE=gate node show_display.js <server.js> <tape.ndjson> <RT> <ticker> <tau1,tau2,...> */
'use strict'; process.env.ENABLE_WS = '0'; process.env.PINRADAR_REPLAY = '1';
const fs = require('fs'), path = require('path');
const S = require(path.resolve(process.argv[2])); const RT = require(path.resolve(process.argv[4]));
const lines = fs.readFileSync(process.argv[3], 'utf8').split('\n').filter(Boolean).map(l => JSON.parse(l));
const samples = [], recs = [], boots = [];
for (const o of lines) { if (o.k === 's') samples.push([o.t, o.v]); else if (o.k === 'd') recs.push(o); else if (o.k === 'boot') boots.push(o.ts); }
samples.sort((a, b) => a[0] - b[0]); for (let i = samples.length - 1; i > 0; i--) if (samples[i][0] === samples[i - 1][0]) samples.splice(i, 1);
const tk = process.argv[5], taus = process.argv[6].split(',').map(Number);
console.log('mode', S.PR11_MODE, tk);
for (const rec of recs) {
  if (!rec.kal || rec.kal.ticker !== tk) continue;
  const tau = (rec.kal.closeMs - rec.ts) / 1000;
  if (!taus.some(t => Math.abs(t - tau) < 0.5)) continue;
  const s = RT.restoreAndDecide(S, rec, samples, boots).signal;
  console.log(`tau ${tau.toFixed(1)} | live: ${rec.out.state} ${rec.out.action} pFlip ${rec.out.pFlip} | PR11 build: ${s.state} | ${s.trade && s.trade.action} | pFlip ${s.pFlip} | why: ${s.trade && s.trade.why} | reason[0]: ${(s.reasons || [])[0]} | pr11: ${JSON.stringify(s.pr11)}`);
}
