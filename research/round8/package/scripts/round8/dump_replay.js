/* Per-second exact replay dump: runs ONE engine file on ONE capture tape with the recorded-state restore of
   tools/replay_tape28.js (restoreAndDecide) and writes one NDJSON row per recorded decision with the engine's own
   geometry, settlement panel, gates, signal and (build 9) pr11 fields, next to the state the server served live (rec.out).
   usage: node dump_replay.js <server.js> <tape.ndjson> <out.ndjson> <replay_tape28.js>   (PR11_MODE from env; unset = gate) */
'use strict'; process.env.ENABLE_WS = '0'; process.env.PINRADAR_REPLAY = '1';
const fs = require('fs'), path = require('path');
const RT = require(path.resolve(process.argv[5]));
const S = require(path.resolve(process.argv[2]));
const lines = fs.readFileSync(process.argv[3], 'utf8').split('\n').filter(Boolean).map(l => JSON.parse(l));
const samples = [], recs = [], boots = [];
for (const o of lines) { if (o.k === 's') samples.push([o.t, o.v]); else if (o.k === 'd') recs.push(o); else if (o.k === 'boot') boots.push(o.ts); }
samples.sort((a, b) => a[0] - b[0]); boots.sort((a, b) => a - b);
for (let i = samples.length - 1; i > 0; i--) if (samples[i][0] === samples[i - 1][0]) samples.splice(i, 1);
const out = fs.openSync(process.argv[4], 'w'); let n = 0; const times = [];
for (const rec of recs) {
  const t0 = process.hrtime.bigint(); const snap = RT.restoreAndDecide(S, rec, samples, boots); const ms = Number(process.hrtime.bigint() - t0) / 1e6; times.push(ms);
  const g = snap.geo || {}, sg = snap.signal || {}, st = snap.settle || {}, gates = snap.gates || { soft: [], hard: [] };
  const row = { ts: rec.ts, ticker: rec.kal && rec.kal.ticker, closeMs: rec.kal && rec.kal.closeMs, tau: rec.kal ? +((rec.kal.closeMs - rec.ts) / 1000).toFixed(3) : null, strike: rec.kal && rec.kal.strike,
    liveIdx: rec.liveIdx ? rec.liveIdx.value : null, ageMs: rec.ageMs, quality: rec.quality && rec.quality.grade, obTs: rec.obTs,
    live: rec.out || null,
    state: sg.state, side: sg.side, pWin: sg.pWin, pFlip: sg.pFlip, pFlipCons: sg.pFlipCons, action: sg.trade ? sg.trade.action : null, askCents: sg.trade ? sg.trade.askCents : null, lockedSide: sg.lockedSide,
    geo: { n: g.n, nLock: g.nLock, lobs: g.lockedObserved, filledLive: g.lockedFilledLive == null ? null : g.lockedFilledLive, cov: g.lockedCoverage, gap: g.gapUsd, exp: g.expectedSettle, sigma: g.sigmaBps, regime: g.regime ? g.regime.bucket : null, index: g.index },
    ref: st.reference, offReasons: st.officialReasons || null, recorded: st.recorded, recordedAvg: st.recordedAvg, brtiAgeMs: st.brtiAgeMs, divergenceUsd: st.divergenceUsd == null ? null : st.divergenceUsd, officialPUp: st.officialPUp == null ? null : st.officialPUp,
    gatesSoft: (gates.soft || []).length, gatesHard: (gates.hard || []).length, soft: gates.soft || [], hard: gates.hard || [], pr11: sg.pr11 || null, ms: +ms.toFixed(3) };
  fs.writeSync(out, JSON.stringify(row) + '\n'); n++;
}
fs.closeSync(out); times.sort((a, b) => a - b);
console.log(JSON.stringify({ server: path.basename(process.argv[2]), tape: path.basename(process.argv[3]), mode: S.PR11_MODE || 'n/a(base)', rows: n, samples: samples.length, boots: boots.length, msMean: +(times.reduce((a, b) => a + b, 0) / Math.max(1, n)).toFixed(3), msP50: +(times[Math.floor(n * .5)] || 0).toFixed(3), msP99: +(times[Math.floor(n * .99)] || 0).toFixed(3), msMax: +(times[n - 1] || 0).toFixed(3) }));
process.exit(0);
