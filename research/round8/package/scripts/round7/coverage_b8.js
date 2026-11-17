/* Coverage and AVAILABLE QUOTED OFFERS (not fills), build 7 vs build 8 rule, on the recorded tapes (exact engine). Corrected 2026-11-17 20:2x UTC: the first version read the called side's own bids as asks. For every inside-120-s second: admitted
   under the served build (b8 file) and what b7 would have admitted (floor met, no official/missing requirement); executable = ask <= 99.9 c,
   size >= 10, book <= 3 s old (the ten_windows definition). usage: PR11_MODE=gate node coverage_b8.js <server.js> <RT> <tape>... */
'use strict'; process.env.PINRADAR_REPLAY = '1'; process.env.ENABLE_WS = '0';
const fs = require('fs'), path = require('path'); const S = require(path.resolve(process.argv[2])); const RT = require(path.resolve(process.argv[3]));
const tot = { secs120: 0, b8admit: 0, b7admit: 0, withheldMissing: 0, withheldOfficial: 0, withheldFloor: 0, officialAlsoFloor: 0 }; const win = {};
for (const tape of process.argv.slice(4)) {
  const lines = fs.readFileSync(tape, 'utf8').split('\n').filter(Boolean).map(l => JSON.parse(l)); const samples = [], recs = [], boots = [];
  for (const o of lines) { if (o.k === 's') samples.push([o.t, o.v]); else if (o.k === 'd') recs.push(o); else if (o.k === 'boot') boots.push(o.ts); }
  samples.sort((a, b) => a[0] - b[0]); for (let i = samples.length - 1; i > 0; i--) if (samples[i][0] === samples[i - 1][0]) samples.splice(i, 1);
  for (const rec of recs) {
    const tau = (rec.kal.closeMs - rec.ts) / 1000; if (!(tau > 0 && tau <= 120)) continue;
    const snap = RT.restoreAndDecide(S, rec, samples, boots); const sig = snap.signal, pr = sig.pr11 || {}; if (!pr.applies) continue;
    tot.secs120++; const tk = rec.kal.ticker; const w = win[tk] || (win[tk] = { b8: 0, b7: 0, b8exec: 0, b7exec: 0, firstB8: null, firstB7: null, side: null });
    const lockedState = sig.state === 'LOCKED' || sig.state === 'PROVEN LOCKED';
    const b8 = !!(pr.admit && lockedState);
    /* b7 would admit when the floor is met and the model's state would have been LOCKED: i.e. b8 admitted, or withheld only for official/missing */
    const b7 = b8 || (pr.floorMet && sig.state === 'HIGH CONFIDENCE' && sig.pFlip != null && sig.pFlip <= 0.005 && (pr.reason === 'official' || pr.reason === 'missing') && (snap.gates.soft || []).every(g => /^PR11/.test(g)));
    if (b8) tot.b8admit++; if (b7) tot.b7admit++;
    if (!pr.admit) { if (pr.reason === 'missing') tot.withheldMissing++; else if (pr.reason === 'official') { tot.withheldOfficial++; if (!pr.floorMet) tot.officialAlsoFloor++; } else if (pr.reason === 'floor') tot.withheldFloor++; }
    /* asks as the server derives them (bookFromKal): a YES ask is a NO bid seen from the other side (100 - p), and vice versa; a level without size is not an offer */
    const ob = rec.ob, side = sig.side, src = ob ? (side === 'UP' ? ob.no : ob.yes) : null; const fresh = rec.obTs != null && rec.ts - rec.obTs <= 3000;
    const lv = src ? src.filter(x => x[1] > 0).map(x => [Math.round((100 - x[0]) * 100) / 100, x[1]]).sort((a, b) => a[0] - b[0]) : null;
    let exec = false; if (lv && lv.length && fresh) { const best = lv[0]; exec = best[0] <= 99.9 && best[1] >= 10; }
    if (b8) { w.b8++; if (exec) { w.b8exec++; if (w.firstB8 == null) { w.firstB8 = +tau.toFixed(1); w.side = side; } } }
    if (b7) { w.b7++; if (exec) { w.b7exec++; if (w.firstB7 == null) w.firstB7 = +tau.toFixed(1); } }
  }
}
const ws = Object.entries(win); const n = ws.length, wb8 = ws.filter(([, w]) => w.b8).length, wb7 = ws.filter(([, w]) => w.b7).length, eb8 = ws.filter(([, w]) => w.b8exec).length, eb7 = ws.filter(([, w]) => w.b7exec).length;
console.log(JSON.stringify({ ...tot, windows: n, windowsAdmitted_b7: wb7, windowsAdmitted_b8: wb8, windowsExecutable_b7: eb7, windowsExecutable_b8: eb8 }));
for (const [tk, w] of ws) if (w.b7 !== w.b8 || w.b7exec !== w.b8exec || w.firstB7 !== w.firstB8) console.log('  changed:', tk, JSON.stringify(w));
console.log('  ten-window overlap:'); for (const [tk, w] of ws) if (/26NOV141900-00|26NOV142030-30|26NOV151915-15|26NOV152100-00/.test(tk)) console.log('   ', tk, JSON.stringify(w));
