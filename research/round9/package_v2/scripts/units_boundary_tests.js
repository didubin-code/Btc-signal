/* Independent units/boundary regressions for the PR11 exposure (build 10): the harness computes the expected values with its own
   arithmetic (table units: bps of the current index, scaled by 60/remaining prints once a print has passed) and compares with the
   exported pr11Exposure. usage: PR11_MODE=gate node units_boundary_tests.js <server.js> */
'use strict'; process.env.PINRADAR_REPLAY = '1'; process.env.ENABLE_WS = '0';
const S = require(require('path').resolve(process.argv[2])); const { pr11Exposure, PR11_RSTAR } = S;
const R = []; const T = (name, ok, got) => R.push([ok ? 'PASS' : 'FAIL', name, typeof got === 'string' ? got : JSON.stringify(got)]);
const OK = { ok: true, reasons: [] };
const expectR = (gap, index, tau, nLock) => { const h = Math.min(120, Math.max(1, Math.ceil(tau - 1e-9))); const scale = (nLock >= 1 && tau <= 60) ? 60 / h : 1; return { h, R: Math.abs(gap) / index * 1e4 * scale, rstar: PR11_RSTAR[h - 1] }; };
const near = (a, b, t) => Math.abs(a - b) <= t;
/* 1. the recorded second from the independent audit */
{ const gap = 32.01734179955969 * 64707.58 * 51 / (1e4 * 60); const e = expectR(gap, 64883.71, 50.906, 9); const x = pr11Exposure({ gapUsd: gap, nLock: 9, n: 51, lockedObserved: 9, lockedFilledLive: 1, index: 64883.71 }, 64707.58, 50.906, OK);
  T('recorded KXBTC15M-26NOV152000-00 @ 50.906 s: engine R equals the index-unit value 31.93 (strike-unit value was 32.02), floor 32 -> withheld', x && x.h === e.h && near(x.R, e.R, 0.0051) && near(e.R, 31.9304, 0.001) && x.admit === false && x.reason === 'floor', [x.R, e.R, x.admit, x.reason]); }
/* 2. direction: index above / below the strike, before the minute */
for (const [gap, index, label] of [[200, 65200, 'UP leader, index above strike'], [-200, 64800, 'DOWN leader, index below strike'], [200, 65000, 'index equal to strike']]) {
  const e = expectR(gap, index, 90.5, 0); const x = pr11Exposure({ gapUsd: gap, nLock: 0, n: 60, lockedObserved: 0, index }, 65000, 90.5, OK);
  T('before the minute, ' + label + ': R = |gap|/index x 1e4, h 91', x && x.h === 91 && near(x.R, e.R, 0.0051), [x.R, e.R]); }
/* 3. inside the minute: scaling by 60/remaining prints with the index denominator; boundaries 60.000 / 59.999 */
{ const a = pr11Exposure({ gapUsd: 30, nLock: 0, n: 60, lockedObserved: 0, index: 65100 }, 65000, 60.0, OK), b = pr11Exposure({ gapUsd: 30, nLock: 0, n: 60, lockedObserved: 0, index: 65100 }, 65000, 59.999, OK);
  T('tau 60.000 and 59.999 with no passed print yet (geometry n 60): h 60, R = |gap|/index x 1e4 unscaled', a && a.h === 60 && near(a.R, 30 / 65100 * 1e4, 0.0051) && b && b.h === 60 && near(b.R, 30 / 65100 * 1e4, 0.0051), [a.h, a.R, b.h, b.R]);
  const c = pr11Exposure({ gapUsd: 30, nLock: 1, n: 59, lockedObserved: 1, index: 65100 }, 65000, 59.0, OK), e = expectR(30, 65100, 59.0, 1);
  T('tau 59.0 with one passed print: h 59, R scaled by 60/59 in index units', c && c.h === 59 && near(c.R, e.R, 0.0051), [c.h, c.R, e.R]); }
/* 4. exact floor equality in index units admits; one unit below withholds */
{ const h = 51, gapEq = 32 / 1e4 * 65100 * h / 60; const eq = pr11Exposure({ gapUsd: gapEq, nLock: 9, n: 51, lockedObserved: 9, index: 65100 }, 65000, 50.9, OK), below = pr11Exposure({ gapUsd: gapEq * (1 - 1e-6), nLock: 9, n: 51, lockedObserved: 9, index: 65100 }, 65000, 50.9, OK);
  T('R exactly R* (32 @ h 51) admits; R one millionth below withholds (floor)', eq && eq.floorMet === true && eq.admit === true && below && below.admit === false && below.reason === 'floor', [eq.R, eq.admit, below.R, below.admit]); }
/* 5. the strike-denominated reading would differ: at the recorded index/strike ratio an admitted call in strike units is withheld in index units and vice versa for a DOWN leader */
{ const strike = 65000, index = 65200, h = 51, gap = 32 / 1e4 * strike * h / 60 * 1.001; const x = pr11Exposure({ gapUsd: gap, nLock: 9, n: 51, lockedObserved: 9, index }, strike, 50.9, OK);
  const Rs = Math.abs(gap) / strike * 1e4 * 60 / h, Ri = Math.abs(gap) / index * 1e4 * 60 / h;
  T('UP leader: strike-unit R 32.03 would admit, index-unit R 31.93 withholds — engine follows the index units', Rs >= 32 && Ri < 32 && x && x.admit === false, [Rs, Ri, x.admit]);
  const gap2 = -32 / 1e4 * strike * h / 60 * 0.999, x2 = pr11Exposure({ gapUsd: gap2, nLock: 9, n: 51, lockedObserved: 9, index: 64800 }, strike, 50.9, OK);
  const Rs2 = Math.abs(gap2) / strike * 1e4 * 60 / h, Ri2 = Math.abs(gap2) / 64800 * 1e4 * 60 / h;
  T('DOWN leader: strike-unit R 31.97 would withhold, index-unit R 32.07 admits — engine follows the index units', Rs2 < 32 && Ri2 >= 32 && x2 && x2.admit === true, [Rs2, Ri2, x2.admit]); }
/* 6. missing and official requirements are unchanged by the units change */
{ const m = pr11Exposure({ gapUsd: 300, nLock: 9, n: 51, lockedObserved: 8, index: 65100 }, 65000, 50.9, OK), o = pr11Exposure({ gapUsd: 300, nLock: 9, n: 51, lockedObserved: 9, index: 65100 }, 65000, 50.9, { ok: false, reasons: ['stale'] });
  T('missing sample still withholds (reason missing); unusable official reference in the minute still withholds (reason official)', m && m.admit === false && m.reason === 'missing' && o && o.admit === false && o.reason === 'official', [m.reason, o.reason]); }
/* 7. displayed text names the units */
{ const w = pr11Exposure({ gapUsd: 20, nLock: 0, n: 60, lockedObserved: 0, index: 65100 }, 65000, 90.5, OK); T('withheld text says "bps of the current index"', w && /bps of the current index/.test(w.why), w && w.why); }
const fails = R.filter(r => r[0] === 'FAIL'); for (const r of R) console.log(r[0] + '  ' + r[1] + '  => ' + r[2]); console.log('UNITS BOUNDARY TESTS', R.length, 'checks; failed', fails.length); process.exit(fails.length ? 1 : 0);
