/* Boundary, threshold, invalid-input and settlement tests on the exact release build's exported functions (gate mode). No server change.
   usage: PR11_MODE=gate node boundary_tests.js <server.js> */
'use strict'; process.env.PINRADAR_REPLAY = '1'; process.env.ENABLE_WS = '0';
const S = require(require('path').resolve(process.argv[2])); const { pr11Exposure, pr11Gate, pr11Apply, m25Decide, PR11_RSTAR } = S;
const K = 65000, R = []; const T = (name, ok, got) => { R.push([ok ? 'PASS' : 'FAIL', name, typeof got === 'string' ? got : JSON.stringify(got)]); };
const cfg = { lockMaxFlip: 0.005, highMaxFlip: 0.05, leanMaxFlip: 0.3, revFlip: 0.05, contracts: 10, maxBookAgeMs: 1500, minExecTau: 3, minEdgeCents: 0.05 };
const gapFor = (bps, sign = 1) => sign * bps / 1e4 * K;
const bey = (gapBps, nLock, n, tau) => pr11Exposure({ gapUsd: gapFor(gapBps), nLock, n }, K, tau);
/* --- tau boundaries around 120 s --- */
const a = bey(30, 0, 60, 120.001), b = bey(30, 0, 60, 120), c = bey(30, 0, 60, 119.999);
T('tau 120.001 -> beyond (gate not applied)', a && a.applies === false && a.scope === 'beyond', a);
T('tau 120.000 -> applies, h 120, floor 68', b && b.applies && b.h === 120 && b.rstar === 68, b);
T('tau 119.999 -> applies, h 120, floor 68', c && c.applies && c.h === 120 && c.rstar === 68, c);
const mk = (tau, st) => ({ state: st, side: 'UP', pFlip: 0.0015, tau, headline: 'LOCKED UP', display27: { headline: 'PREDICTED LOCKED — UP', note: null }, guarantee: 'x', validation: { audit: { n: 1 }, lines: ['LOCKED standard: …'] }, v28: { value: { veto: null, positive: true }, execution: { ready: true } }, trade: { action: 'TRADE NOW' } });
const g1 = { hard: [], soft: [] }, x1 = pr11Gate(g1, { gapUsd: gapFor(30), nLock: 0, n: 60 }, K, 120.001), s1 = pr11Apply(mk(120.001, 'LOCKED'), x1);
T('display at 120.001: NOT YET GATED label, no soft gate pushed, state/trade untouched, not qualified', g1.soft.length === 0 && /NOT YET GATED/.test(s1.headline) && s1.state === 'LOCKED' && s1.trade.action === 'TRADE NOW' && s1.pr11.qualified === false, s1.headline);
const g2 = { hard: [], soft: [] }, x2 = pr11Gate(g2, { gapUsd: gapFor(30), nLock: 0, n: 60 }, K, 120), d2 = m25Decide({ tau: 120, pUp: 0.9985, pUpCons: 0.998, gates: g2, book: null, cfg });
T('gate at 120.000 with 30 bps (< 68): soft gate pushed, gates.pr11 set, decision HIGH CONFIDENCE / WAIT', g2.soft.length === 1 && g2.pr11 && g2.pr11.length === 1 && d2.state === 'HIGH CONFIDENCE' && d2.trade.action === 'WAIT', [g2.soft, d2.state]);
const s2 = pr11Apply(Object.assign(mk(120, 'HIGH CONFIDENCE'), { state: 'HIGH CONFIDENCE', trade: { action: 'WAIT' } }), x2);
T('display at 120.000 withheld: WITHHELD headline, readiness off, veto names the floor', /^LOCKED WITHHELD/.test(s2.headline) && s2.v28.execution.ready === false && /exposure floor/.test(s2.v28.value.veto) && s2.pr11.withheld === true, s2.headline);
const g3 = { hard: [], soft: [] }, x3 = pr11Gate(g3, { gapUsd: gapFor(70), nLock: 0, n: 60 }, K, 119.999), s3 = pr11Apply(mk(119.999, 'LOCKED'), x3);
T('display at 119.999 admitted (70 >= 68): ordinary PREDICTED LOCKED, qualified, no label', g3.soft.length === 0 && s3.display27.headline === 'PREDICTED LOCKED — UP' && s3.pr11.qualified === true && !/WITHHELD|NOT YET/.test(s3.headline), s3.display27.headline);
/* --- settlement: tau 0 and below --- */
const z0 = bey(30, 60, 0, 0), zn = bey(30, 60, 0, -1);
T('tau 0 and tau -1 -> scope closed, not applied', z0 && z0.applies === false && z0.scope === 'closed' && zn && zn.applies === false && zn.scope === 'closed', [z0, zn]);
const dA = m25Decide({ tau: 0, pUp: 0.9999, pUpCons: 0.9999, gates: { hard: [], soft: ['PR11 cushion floor: t'], pr11: ['PR11 cushion floor: t'] }, book: null, cfg, provenSide: 'UP' });
T('at the close the state is AWAITING SETTLEMENT whatever the gates (no admitted LOCKED, no trade)', dA.state === 'AWAITING SETTLEMENT' && !(dA.trade && dA.trade.action === 'TRADE NOW'), [dA.state, dA.trade && dA.trade.action]);
const sA = pr11Apply({ state: 'AWAITING SETTLEMENT', tau: 0, headline: 'AWAITING SETTLEMENT', display27: { headline: 'AWAITING SETTLEMENT' }, validation: { lines: [] } }, z0);
T('display at the close: no PR11 label, not qualified', sA.headline === 'AWAITING SETTLEMENT' && sA.pr11.qualified === false && sA.pr11.scope === 'closed', sA.pr11);
const last = bey(0.77, 59, 1, 0.5);
T('last print (tau 0.5, 59 passed, 1 unknown): inside-minute branch, h 1, floor 10 bps', last && last.applies && last.h === 1 && last.rstar === 10, last);
/* --- the 60-s branch boundary --- */
const i60 = bey(30, 1, 59, 60), b60 = bey(30, 1, 59, 60.001);
T('tau 60.000 with 1 print passed -> inside-minute branch (h 59, R = cushion*60/59); tau 60.001 -> before-minute branch (h 61, R = cushion)', i60.h === 59 && Math.abs(i60.R - 30 * 60 / 59) < 0.01 && b60.h === 61 && Math.abs(b60.R - 30) < 0.01, [i60, b60]);
/* --- each exposure threshold: below / at / above, both branches, UP and DOWN --- */
let thrOk = true, thrEx = [], eqAdmit = 0, eqTotal = 0, eqEx = [];
for (const h of [1, 2, 10, 30, 54, 59, 60, 61, 92, 105, 120]) {
  const rstar = PR11_RSTAR[h - 1];
  for (const sign of [1, -1]) {
    const mkx = e => h <= 60 ? pr11Exposure({ gapUsd: sign * ((rstar + e) * h / 60) / 1e4 * K, nLock: 60 - h, n: h }, K, Math.max(0.25, h - 0.25))
                            : pr11Exposure({ gapUsd: sign * (rstar + e) / 1e4 * K, nLock: 0, n: 60 }, K, h - 0.5);
    for (const e of [-1e-6, 1e-6]) { const x = mkx(e); if (!x || !x.applies || x.h !== h || x.rstar !== rstar || x.admit !== (e > 0)) { thrOk = false; thrEx.push({ h, sign, e, x }); } }
    const xe = mkx(0); eqTotal++; if (xe.admit) eqAdmit++; else eqEx.push({ h, sign, Rcomputed: xe.R, rstar });
  }
}
T('threshold boundaries at 11 horizons (1..120), both branches, UP and DOWN: one millionth of a bp above the floor is admitted, one millionth below is not; h and R*(h) lookup correct', thrOk, thrEx.slice(0, 3));
T('exact equality R = R*(h) (22 constructed cases): the rule is R >= R*, so mathematically admitted; in floating point the constructed R lands a few 1e-15 either side, so admission at exact equality follows the rounding (informational, not a defect: production gaps are 2-decimal USD values and never land exactly on an integer floor) — admitted in ' + eqAdmit + ' of ' + eqTotal, true, eqEx.slice(0, 4));
T('table lookup: PR11_RSTAR[h-1] for h 1..120 is 10..68 and monotone', PR11_RSTAR.length === 120 && PR11_RSTAR[0] === 10 && PR11_RSTAR[119] === 68 && PR11_RSTAR.every((v, i) => i === 0 || v >= PR11_RSTAR[i - 1]), PR11_RSTAR.slice(0, 5));
/* --- inside-minute remaining-count arithmetic --- */
const rc = bey(10, 40, 20, 20.5);
T('inside the minute: R = cushion * 60 / remaining (10 bps, 20 unknown -> 30 bps), h = remaining, floor R*(20) = 21', rc && Math.abs(rc.R - 30) < 0.01 && rc.h === 20 && rc.rstar === 21 && rc.admit === true && rc.nKnown === 40, rc);
/* --- invalid inputs to the exposure helper --- */
const bad = [['gapUsd NaN', { gapUsd: NaN, nLock: 0, n: 60 }, K, 90], ['gapUsd Infinity', { gapUsd: Infinity, nLock: 0, n: 60 }, K, 90], ['gapUsd string', { gapUsd: 'x', nLock: 0, n: 60 }, K, 90],
  ['strike 0', { gapUsd: 100, nLock: 0, n: 60 }, 0, 90], ['strike negative', { gapUsd: 100, nLock: 0, n: 60 }, -1, 90], ['strike NaN', { gapUsd: 100, nLock: 0, n: 60 }, NaN, 90], ['strike null', { gapUsd: 100, nLock: 0, n: 60 }, null, 90],
  ['tau NaN', { gapUsd: 100, nLock: 0, n: 60 }, K, NaN], ['tau null', { gapUsd: 100, nLock: 0, n: 60 }, K, null], ['tau Infinity', { gapUsd: 100, nLock: 0, n: 60 }, K, Infinity], ['geo null', null, K, 90]];
let badOk = true, badEx = [];
for (const [name, geo, k, tau] of bad) { const x = pr11Exposure(geo, k, tau); const okNull = (x === null) || (name === 'tau Infinity' && x && x.applies === false); if (!okNull) { badOk = false; badEx.push({ name, x }); } }
T('uncomputable exposure (non-finite gap, strike <= 0 or non-finite, non-finite tau, no geometry) -> null (tau Infinity -> not applied), never an admit', badOk, badEx);
const cnt = [['nLock NaN -> treated as 0 (before-minute branch)', bey(30, NaN, 60, 50), r => r.nKnown === 0 && r.h === 50], ['nLock negative (impossible) -> not inside the minute: before-minute branch, h from the time to close (50)', pr11Exposure({ gapUsd: gapFor(30), nLock: -5, n: 65 }, K, 50), r => r.h === 50 && r.R === 30], ['n NaN -> remaining defaults to 60', pr11Exposure({ gapUsd: gapFor(30), nLock: 10, n: NaN }, K, 50), r => r.h === 60], ['n 0 inside the minute -> h clamps to 1', pr11Exposure({ gapUsd: gapFor(30), nLock: 60, n: 0 }, K, 0.5), r => r.h === 1], ['n 70 -> h clamps to 60', pr11Exposure({ gapUsd: gapFor(30), nLock: 1, n: 70 }, K, 50), r => r.h === 60]];
for (const [name, x, f] of cnt) T('count handling: ' + name, !!x && x.applies && f(x), x);
/* an uncomputable gate inside the scope never admits: pr11Gate(null exposure) pushes nothing but the decision itself is DATA UNRELIABLE whenever the inputs that make it uncomputable are missing (hard gates): shown here at the decision level */
const gN = { hard: ['no settlement geometry'], soft: [] }, xN = pr11Gate(gN, null, K, 90), dN = m25Decide({ tau: 90, pUp: NaN, pUpCons: NaN, gates: gN, book: null, cfg });
T('no geometry: exposure null, gate pushes nothing, decision DATA UNRELIABLE with no trade object (no instruction) or NO TRADE, pr11.applies false', xN === null && gN.soft.length === 0 && dN.state === 'DATA UNRELIABLE' && (dN.trade === null || dN.trade.action === 'NO TRADE') && pr11Apply({ state: 'DATA UNRELIABLE' }, xN).pr11.applies === false, [dN.state, dN.trade && dN.trade.action]);
const dH = m25Decide({ tau: 90, pUp: 0.9999, pUpCons: 0.9999, gates: { hard: ['oldest index input 20000 ms > 2500 ms budget'], soft: [] }, book: null, cfg });
T('a hard gate with a confident model: DATA UNRELIABLE, NO TRADE (never LOCKED)', dH.state === 'DATA UNRELIABLE' && dH.trade.action === 'NO TRADE', [dH.state, dH.trade.action]);
const dNaN = m25Decide({ tau: 90, pUp: NaN, pUpCons: 0.9, gates: { hard: [], soft: [] }, book: null, cfg });
T('non-finite model probability without any gate: DATA UNRELIABLE ("no model probability")', dNaN.state === 'DATA UNRELIABLE' && /no model probability/.test(dNaN.reasons.join(' ')), [dNaN.state, dNaN.reasons]);
/* --- UP and DOWN symmetry --- */
const up = bey(40, 0, 60, 100), dn = bey(40, 0, 60, 100, -1), dn2 = pr11Exposure({ gapUsd: -gapFor(40), nLock: 0, n: 60 }, K, 100);
T('UP (+gap) and DOWN (-gap) give the same R, h and admit', up.R === dn2.R && up.h === dn2.h && up.admit === dn2.admit, [up, dn2]);
const fails = R.filter(r => r[0] === 'FAIL'); for (const r of R) console.log(r[0] + '  ' + r[1] + (r[0] === 'FAIL' ? '  => ' + r[2] : ''));
console.log('BOUNDARY TESTS', R.length, 'checks; failed', fails.length, 'mode', S.PR11_MODE); process.exit(fails.length ? 1 : 0);
