/* Deletion experiment on COMPLETE recorded windows (build 7 rule: an unsampled passed print second is an unknown print at the current index with
   an enlarged horizon). Delete the ring sample(s) of chosen passed print seconds and compare the exposure and admission with the complete-data
   result. Also synthetic extremes: move one past sample far from the current index (adverse or favorable), then delete it.
   usage: PR11_MODE=gate node deletion_test.js <server.js> <RT> <tape> <ticker> <tau> [strikeMul] */
'use strict'; process.env.PINRADAR_REPLAY = '1'; process.env.ENABLE_WS = '0';
const fs = require('fs'), path = require('path'); const S = require(path.resolve(process.argv[2])); const RT = require(path.resolve(process.argv[3]));
const lines = fs.readFileSync(process.argv[4], 'utf8').split('\n').filter(Boolean).map(l => JSON.parse(l));
const samples0 = [], recs = [], boots = [];
for (const o of lines) { if (o.k === 's') samples0.push([o.t, o.v]); else if (o.k === 'd') recs.push(o); else if (o.k === 'boot') boots.push(o.ts); }
samples0.sort((a, b) => a[0] - b[0]); for (let i = samples0.length - 1; i > 0; i--) if (samples0[i][0] === samples0[i - 1][0]) samples0.splice(i, 1);
const tk = process.argv[5], want = Number(process.argv[6]), mul = process.argv[7] ? Number(process.argv[7]) : null;
let best = null; for (const rec of recs) { if (!rec.kal || rec.kal.ticker !== tk) continue; const tau = (rec.kal.closeMs - rec.ts) / 1000; if (!best || Math.abs(tau - want) < Math.abs(best.tau - want)) best = { rec: JSON.parse(JSON.stringify(rec)), tau }; }
const rec = best.rec; if (mul) { rec.kal.strike = Math.round(mul * rec.liveIdx.value * 100) / 100; if (rec.prevSettled) rec.prevSettled.official = rec.kal.strike; if (rec.lock25) { rec.lock25.lockedSide = null; rec.lock25.lockedAtTau = null; rec.lock25.hist = []; } }
const close = rec.kal.closeMs, now = rec.ts, K = rec.kal.strike;
function decide(samples) { const snap = RT.restoreAndDecide(S, rec, samples, boots); const g = snap.geo, sig = snap.signal, pr = sig.pr11 || {}; return { state: sig.state, side: sig.side, nLock: g && g.nLock, lobs: g && g.lockedObserved, cov: g && g.lockedCoverage, gap: g && g.gapUsd, idx: g && g.index, h: pr.h, R: pr.R, rstar: pr.rstar, admit: pr.admit, nMissing: pr.nMissing, hard: snap.gates.hard.length, soft: snap.gates.soft }; }
const base = decide(samples0);
console.log('BASE', tk, 'tau', best.tau.toFixed(2), JSON.stringify(base));
if (!(base.nLock >= 1)) { console.log('not inside the minute'); process.exit(0); }
/* passed print seconds and their matched samples */
const prints = []; for (let off = 0; off < 60; off++) { const tp = close - off * 1000; if (tp > now) continue; let hit = null; for (const p of samples0) { const d = Math.abs(p[0] - tp); if (d <= 600 && Math.round((close - p[0]) / 1000) === off && (!hit || d < hit.d)) hit = { t: p[0], v: p[1], d }; } prints.push({ off, tp, hit }); }
const matched = prints.filter(p => p.hit); const sideSign = base.side === 'UP' ? 1 : -1;
const dev = p => sideSign * (p.hit.v - base.idx) / K * 1e4;   // >0: the past print was on the favourable side of the current index
matched.sort((a, b) => dev(a) - dev(b)); const mostAdverse = matched[0], mostFav = matched[matched.length - 1];
const byOff = [...matched].sort((a, b) => b.off - a.off); const oldest = byOff[0], newest = byOff[byOff.length - 1], middle = byOff[Math.floor(byOff.length / 2)];
const without = (ps) => samples0.filter(s => !ps.some(p => p.hit && s[0] === p.hit.t));
const rows = [];
function test(label, ps) { const d = decide(without(ps)); rows.push([label, ps.map(p => p.off + 's@' + dev(p).toFixed(1) + 'bps').join(','), d]); }
test('delete oldest passed print', [oldest]); test('delete middle passed print', [middle]); test('delete newest matched print', [newest]);
test('delete most ADVERSE past print', [mostAdverse]); test('delete most FAVOURABLE past print', [mostFav]);
test('delete 3 most adverse', matched.slice(0, Math.min(3, matched.length))); test('delete 3 most favourable', matched.slice(-3));
if (matched.length >= 6) test('delete 6 (10 % of 60) most adverse', matched.slice(0, 6));
for (const [label, deleted, d] of rows) console.log('%-34s %-28s nLock %s lobs %s miss %s h %s R %s rstar %s admit %s state %s%s', label, deleted, d.nLock, d.lobs, d.nMissing, d.h, d.R, d.rstar, d.admit, d.state, (d.admit && !base.admit) ? '  <-- NEWLY ADMITTED BY DELETING INFORMATION' : (!d.admit && base.admit ? '  (withheld)' : ''));
/* synthetic extremes: move one past sample far from the current index, then delete it */
console.log('SYNTHETIC: a past print at +/- X bps from the current index (adverse = against the call); complete-data vs deleted');
for (const X of [20, 40, 80, 150]) for (const sgn of [-1, 1]) {
  const target = middle; const v2 = base.idx * (1 + sgn * sideSign * X / 1e4);   // sgn -1: adverse
  const mod = samples0.map(s => s[0] === target.hit.t ? [s[0], v2] : s); const full = decide(mod); const del = decide(mod.filter(s => s[0] !== target.hit.t));
  console.log('  past print %s bps %s  complete: R %s h %s admit %s | deleted: R %s h %s admit %s%s', X, sgn < 0 ? 'ADVERSE   ' : 'FAVOURABLE', full.R, full.h, full.admit, del.R, del.h, del.admit, (del.admit && !full.admit) ? '  <-- NEWLY ADMITTED BY DELETING THE ADVERSE PRINT' : '');
}
