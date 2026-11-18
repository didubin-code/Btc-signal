/* Exact tape replay (same restore as tools/replay_tape28.js) with PR11 accounting:
   every mismatch between the live recorded decision and the replayed one must be explained by the PR11 soft gate
   (gate mode); in off/shadow mode there must be none beyond the baseline file's own mismatches.
   usage: node run_replay.js <server.js> <tape.ndjson> <out.json>   (PR11_MODE from env) */
'use strict'; process.env.ENABLE_WS = '0'; process.env.PINRADAR_REPLAY = '1';
const fs = require('fs'), path = require('path');
const RT = require(path.resolve(process.argv[5] || (process.env.RT || '')));
const S = require(path.resolve(process.argv[2]));
const lines = fs.readFileSync(process.argv[3], 'utf8').split('\n').filter(Boolean).map(l => JSON.parse(l));
const samples = [], recs = [], boots = [];
for (const o of lines) { if (o.k === 's') samples.push([o.t, o.v]); else if (o.k === 'd') recs.push(o); else if (o.k === 'boot') boots.push(o.ts); }
samples.sort((a, b) => a[0] - b[0]); boots.sort((a, b) => a - b);
for (let i = samples.length - 1; i > 0; i--) if (samples[i][0] === samples[i - 1][0]) samples.splice(i, 1);
const res = { mode: S.PR11_MODE || 'n/a(base)', records: recs.length, samples: samples.length, boots: boots.length, mismatches: 0, mismatchExplainedByPR11: 0, mismatchUnexplained: 0,
  pr11Applies: 0, pr11NotAdmitted: 0, softGated: 0, lockedLive: 0, lockedReplay: 0, unexplainedExamples: [], explainedExamples: [], perWindow: {} };
for (const rec of recs) {
  const snap = RT.restoreAndDecide(S, rec, samples, boots); const s = snap.signal;
  const got = { state: s.state, side: s.side, pWin: s.pWin, pFlip: s.pFlip, pFlipCons: s.pFlipCons, action: s.trade ? s.trade.action : null, ev: s.trade ? s.trade.evConsCents : null };
  const tk = rec.kal && rec.kal.ticker; const w = res.perWindow[tk] || (res.perWindow[tk] = { rows: 0, liveExactEntryTau: null, replayExactEntryTau: null, liveDispEntryTau: null, replayDispEntryTau: null, softGatedRows: 0, appliedRows: 0, result: null });
  w.rows++; const tau = (rec.kal.closeMs - rec.ts) / 1000;
  const live = rec.out || {}; if (live.state === 'LOCKED' || live.state === 'PROVEN LOCKED') res.lockedLive++; if (got.state === 'LOCKED' || got.state === 'PROVEN LOCKED') res.lockedReplay++;
  if (tau > 0 && tau <= 120) {
    if ((live.state === 'LOCKED' || live.state === 'PROVEN LOCKED') && live.pFlip <= 0.002 && w.liveExactEntryTau == null) w.liveExactEntryTau = +tau.toFixed(2);
    if ((got.state === 'LOCKED' || got.state === 'PROVEN LOCKED') && got.pFlip <= 0.002 && w.replayExactEntryTau == null) w.replayExactEntryTau = +tau.toFixed(2);
    if ((live.state === 'LOCKED' || live.state === 'PROVEN LOCKED') && live.pFlip < 0.0025 && w.liveDispEntryTau == null) w.liveDispEntryTau = +tau.toFixed(2);
    if ((got.state === 'LOCKED' || got.state === 'PROVEN LOCKED') && got.pFlip < 0.0025 && w.replayDispEntryTau == null) w.replayDispEntryTau = +tau.toFixed(2);
  }
  const fl = s.pr11 || null; const soft = (snap.gates && snap.gates.soft || []).some(x => /^PR11 (cushion floor|settlement samples missing|official reference unavailable)/.test(x));
  if (fl && fl.applies) res.pr11Applies++; if (fl && fl.applies && fl.admit === false) { res.pr11NotAdmitted++; w.appliedRows++; } if (soft) { res.softGated++; w.softGatedRows++; }
  if (RT.outKey(got) !== RT.outKey(live)) {
    res.mismatches++; const ex = { ts: rec.ts, utc: new Date(rec.ts).toISOString(), ticker: tk, tau: +tau.toFixed(2), live: RT.outKey(live), replay: RT.outKey(got), pr11: fl, soft };
    if (soft) { res.mismatchExplainedByPR11++; if (res.explainedExamples.length < 12) res.explainedExamples.push(ex); }
    else { res.mismatchUnexplained++; if (res.unexplainedExamples.length < 12) res.unexplainedExamples.push(ex); }
  }
}
fs.writeFileSync(process.argv[4], JSON.stringify(res, null, 1));
const { perWindow, unexplainedExamples, explainedExamples, ...head } = res; console.log(JSON.stringify(head));
for (const [tk, w] of Object.entries(perWindow)) if (w.softGatedRows || w.appliedRows || w.liveExactEntryTau !== w.replayExactEntryTau) console.log('  ' + tk, JSON.stringify(w));
