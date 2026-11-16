"""Build the PR10 server file from the exact I2 file by exact-string replacement (every anchor must occur exactly once).
PR10 = settlement-history floor: displayed reversal risk floored at the real-settlement frequency of the (seconds-left, regime,
cushion) cell; SETTLE_FLOOR_MODE env: off | shadow (default: compute, record, score as shadow policy G, change no decision) |
gate (also withhold LOCKED when the floor exceeds LOCK_MAX_FLIP and raise the displayed risk to the floor).
usage: python3 -I make_PR10.py <base I2 pinradar_server.js> <floor_table_FIT.json> <out.js>"""
import sys, json, hashlib
base, table_f, outp = sys.argv[1:4]
src = open(base).read(); assert hashlib.sha256(src.encode()).hexdigest() == 'ca51a0c6f7cfd117f4db6f75ca1dec56e7c277674c97920fc82706b01548040f', 'base is not the live I2 file'
table = json.load(open(table_f)); table_json = json.dumps(table, separators=(',', ':'))
def X(old, new, count=1):
    global src
    assert src.count(old) == count, 'anchor count %d != %d for: %s' % (src.count(old), count, old[:90])
    src = src.replace(old, new)
# (a) constants, table and functions after INGEST_REV
X("const INGEST_REV = 'I2-2026-11-13';", "const INGEST_REV = 'I2-2026-11-13';\n" + r'''/* =====================================================================
   PR10 (2026-11-16): SETTLEMENT-HISTORY FLOOR
   The displayed reversal risk is never shown below the frequency with which a cushion of this size, with this many seconds
   left, in this volatility regime, was exhausted in real Kalshi settlements (28,541 windows of 2026; table from windows
   closing before 2026-09-01, as validated out of sample). The floor is a sigma-free, settlement-based bound: it does not
   condition on the volatility estimate, so it protects against the case where that conditioning fails.
   SETTLE_FLOOR_MODE: off | shadow (default: the floor is computed, carried on the signal, logged and scored as shadow
   policy G; no decision changes) | gate (LOCKED is also withheld, as a soft gate, when the floor exceeds LOCK_MAX_FLIP, and
   the displayed risk is raised to the floor while LOCKED or HIGH CONFIDENCE). PROVEN LOCKED, REVERSAL WARNING, DATA
   UNRELIABLE and AWAITING SETTLEMENT are never touched. Cells with fewer than 20 real settlements give no floor.
   Every number here is an empirical frequency, not a guarantee. */
const SETTLE_FLOOR_MODE = (() => { const m = String(process.env.SETTLE_FLOOR_MODE || 'shadow').toLowerCase(); return ['off', 'shadow', 'gate'].includes(m) ? m : 'shadow'; })();
const SETTLE_FLOOR29 = Object.freeze(''' + table_json + r''');
const SETTLE_FLOOR29_BINS = Object.freeze([[0, 2.5, '0-2.5'], [2.5, 5, '2.5-5'], [5, 7.5, '5-7.5'], [7.5, 10, '7.5-10'], [10, 12.5, '10-12.5'], [12.5, 15, '12.5-15'], [15, 17.5, '15-17.5'],
  [17.5, 20, '17.5-20'], [20, 22.5, '20-22.5'], [22.5, 25, '22.5-25'], [25, 27.5, '25-27.5'], [27.5, 30, '27.5-30'], [30, 32.5, '30-32.5'], [32.5, 35, '32.5-35'], [35, 37.5, '35-37.5'],
  [37.5, 40, '37.5-40'], [40, 50, '40-50'], [50, 75, '50-75'], [75, Infinity, '75-999']]);
function settleFloor29Bin(cBps) { for (const [lo, hi, label] of SETTLE_FLOOR29_BINS) if (cBps >= lo && cBps < hi) return label; return null; }
/* Floor for one decision. tau seconds left; gapUsd = expected settlement minus strike (the engine's gap); mu = the basis mean
   the engine used; bucket = volatility bucket 0-6. Horizon rounds UP to the next 10 s (20..120): the longer-horizon cell. */
function settleFloor29Lookup({ tau, gapUsd, mu, strike, bucket }) {
  if (!Number.isFinite(tau) || !Number.isFinite(gapUsd) || !Number.isFinite(strike) || !(strike > 0) || !Number.isFinite(bucket)) return null;
  const ce = gapUsd + (Number.isFinite(mu) ? mu : 0); const cBps = Math.abs(ce) / strike * 1e4;
  const h = Math.min(120, Math.max(20, 10 * Math.ceil(tau / 10 - 1e-9)));
  const group = bucket <= 1 ? 'quiet' : bucket <= 3 ? 'normal' : 'active';
  const label = settleFloor29Bin(cBps); const key = h + '|' + group + '|' + label; const cell = SETTLE_FLOOR29.cells[key];
  if (!cell) return { p: null, key, h, group, cBps: Math.round(cBps * 100) / 100, n: 0, k: 0 };
  const n = cell[0], k = cell[1]; return { p: (k + 0.5) / (n + 1), key, h, group, cBps: Math.round(cBps * 100) / 100, n, k };
}
/* gate mode only: withhold LOCKED through the existing soft-gate path when the floor exceeds LOCK_MAX_FLIP */
function settleFloor29Gate(gates, geo, tau, strike) {
  if (SETTLE_FLOOR_MODE === 'off' || !geo || !gates) return null;
  const f = settleFloor29Lookup({ tau, gapUsd: geo.gapUsd, mu: geo.basisMeanUsd, strike, bucket: geo.regime ? geo.regime.bucket : NaN });
  if (f && f.p != null && SETTLE_FLOOR_MODE === 'gate' && f.p > LOCK_MAX_FLIP)
    gates.soft.push('settlement history: a ' + f.cBps.toFixed(1) + ' bps cushion with ' + f.h + ' s left in a ' + f.group + ' regime was exhausted in ' + f.k + ' of ' + f.n + ' real settlements (' + (100 * f.p).toFixed(2) + ' %)');
  return f;
}
/* carried on every signal; in gate mode the displayed risk is raised to the floor while LOCKED or HIGH CONFIDENCE */
function settleFloor29Apply(sig, f) {
  if (!sig) return sig;
  if (!f) { sig.settleFloor = { mode: SETTLE_FLOOR_MODE, p: null }; return sig; }
  const binds = f.p != null && sig.pFlip != null && f.p > sig.pFlip && (sig.state === 'LOCKED' || sig.state === 'HIGH CONFIDENCE');
  sig.settleFloor = { mode: SETTLE_FLOOR_MODE, p: f.p == null ? null : Math.round(f.p * 1e6) / 1e6, cell: f.key, n: f.n, k: f.k, cushionBps: f.cBps, binds, applied: false };
  if (SETTLE_FLOOR_MODE === 'gate' && binds) {
    sig.pFlip = Math.round(f.p * 1e6) / 1e6; sig.pWin = Math.round((1 - f.p) * 1e6) / 1e6; sig.pFlipCons = Math.round(Math.max(sig.pFlipCons || 0, f.p) * 1e6) / 1e6;
    sig.pFlipLabel = fmtFlip(sig.pFlip); sig.pWinLabel = fmtWin(sig.pWin); sig.probabilityReference = 'SETTLEMENT-HISTORY FLOOR'; sig.settleFloor.applied = true;
    (sig.reasons || (sig.reasons = [])).push('displayed risk raised to the settlement-history floor ' + fmtFlip(f.p) + ' (' + f.k + ' of ' + f.n + ' real settlements in this cell)');
  }
  return sig;
}
''')
# (b) computeLockSnapshot: gate before classification, apply after enrichment
X("  brtiGate27(gates, settle, geo);                                              // v2.7: can only withhold LOCKED\n  const signal = brtiAfterClassify27(classify25(",
  "  brtiGate27(gates, settle, geo);                                              // v2.7: can only withhold LOCKED\n  const floor29 = settleFloor29Gate(gates, geo, tau, strike);                   // PR10: gate mode only withholds LOCKED\n  const signal = brtiAfterClassify27(classify25(")
X("  enrich28(signal, { geo, settle, kal, now, tau });             // v2.8: display-only enrichment\n  return { geo, gates, signal, settle };",
  "  enrich28(signal, { geo, settle, kal, now, tau });             // v2.8: display-only enrichment\n  settleFloor29Apply(signal, floor29);                            // PR10: carried on the signal; raises the displayed risk in gate mode\n  return { geo, gates, signal, settle };")
# (c) shadow policy G
X("  { id: 'F-market-pooled-value', model: 'F', desc: 'original: TRADE NOW only if the edge survives the adverse-selection prior (cheaper ask => weaker LOCKED), POOL28' }\n]);",
  "  { id: 'F-market-pooled-value', model: 'F', desc: 'original: TRADE NOW only if the edge survives the adverse-selection prior (cheaper ask => weaker LOCKED), POOL28' },\n  { id: 'G-settle-floor', model: 'G', desc: 'PR10: displayed risk floored at the real-settlement frequency of the (seconds left, regime, cushion) cell; LOCKED withheld when the floor exceeds 0.5 %' }\n]);")
X("    default: return base;\n  }\n}\n/* per-window, per-policy first events",
  "    case 'G-settle-floor': {\n      const d = base; if (!d) return d;\n      const f = settleFloor29Lookup({ tau, gapUsd: geo.gapUsd, mu: geo.basisMeanUsd, strike: snap.strike, bucket: geo.regime ? geo.regime.bucket : NaN });\n      if (!f || f.p == null) return d;\n      if (d.state === 'LOCKED' && f.p > cfg.lockMaxFlip) return Object.assign({}, d, { state: 'HIGH CONFIDENCE', pFlip: Math.max(d.pFlip, f.p), pFlipCons: Math.max(d.pFlipCons || 0, f.p), trade: Object.assign({}, d.trade || {}, { action: 'WAIT', why: 'settlement-history floor ' + fmtFlip(f.p) }) });\n      if ((d.state === 'LOCKED' || d.state === 'HIGH CONFIDENCE') && f.p > d.pFlip) return Object.assign({}, d, { pFlip: f.p, pFlipCons: Math.max(d.pFlipCons || 0, f.p) });\n      return d;\n    }\n    default: return base;\n  }\n}\n/* per-window, per-policy first events")
X("    const view = { geo: snap.geo, gates: s.gates || snap.gates, book, decision: base, panel: snap.settle };",
  "    const view = { geo: snap.geo, gates: s.gates || snap.gates, book, decision: base, panel: snap.settle, strike: s.strike };")
# (d) rows and tape
X("    inputAgeMs: sig.geometry && sig.geometry.inputAgeMs, hard: sig.gates.hard, soft: sig.gates.soft, model: sig.modelVersion,",
  "    inputAgeMs: sig.geometry && sig.geometry.inputAgeMs, floorP: sig.settleFloor ? sig.settleFloor.p : null, floorCell: sig.settleFloor ? (sig.settleFloor.cell || null) : null, hard: sig.gates.hard, soft: sig.gates.soft, model: sig.modelVersion,")
X("    out: s ? { state: s.state, side: s.side, pWin: s.pWin, pFlip: s.pFlip, pFlipCons: s.pFlipCons, action: s.trade ? s.trade.action : null, ev: s.trade ? s.trade.evConsCents : null } : null };",
  "    out: s ? { state: s.state, side: s.side, pWin: s.pWin, pFlip: s.pFlip, pFlipCons: s.pFlipCons, action: s.trade ? s.trade.action : null, ev: s.trade ? s.trade.evConsCents : null, floorP: s.settleFloor ? s.settleFloor.p : null } : null };")
# (e) self-tests
X("    push('2.6 recalibration ratios loaded (quiet > 1 > active)',",
  r'''    push('PR10 settlement-history floor table loaded (>= 400 cells, FIT period)', Object.keys(SETTLE_FLOOR29.cells).length >= 400 && !!SETTLE_FLOOR29.meta, Object.keys(SETTLE_FLOOR29.cells).length + ' cells, mode ' + SETTLE_FLOOR_MODE);
    { const f = settleFloor29Lookup({ tau: 101.6, gapUsd: 118.2, mu: -1.67, strike: 64510.2, bucket: 4 });
      push('PR10 lookup: the Nov 15 18:30 UTC entry maps to cell 110|active|17.5-20 with a rate above 0.5 %', !!f && f.key === '110|active|17.5-20' && f.p > 0.005, f ? JSON.stringify(f) : 'null');
      const g = settleFloor29Lookup({ tau: 91.8, gapUsd: 101.7, mu: 1.21, strike: 68245.46, bucket: 3 });
      push('PR10 lookup: the Nov 14 00:15 UTC entry maps to cell 100|normal|15-17.5 with a rate below 0.5 %', !!g && g.key === '100|normal|15-17.5' && g.p < 0.005, g ? JSON.stringify(g) : 'null');
      const h = settleFloor29Lookup({ tau: 119.25, gapUsd: 10, mu: 0, strike: 65000, bucket: 5 });
      push('PR10 horizon rounds up: 119.25 s -> 120, 15 s -> 20, 101.6 s -> 110', !!h && h.h === 120 && settleFloor29Lookup({ tau: 15, gapUsd: 10, mu: 0, strike: 65000, bucket: 5 }).h === 20 && f.h === 110, h ? h.key : 'null');
      push('PR10 unknown cell gives no floor', settleFloor29Lookup({ tau: 60, gapUsd: 9e9, mu: 0, strike: 65000, bucket: 2 }).p === null, 'ok');
      const sigL = { state: 'LOCKED', side: 'UP', pWin: 0.998, pFlip: 0.002, pFlipCons: 0.004, reasons: [] };
      const fl = { p: 0.0072, key: '110|active|17.5-20', n: 762, k: 5, cBps: 18.1, h: 110, group: 'active' };   // the table's own cell: (5 + 0.5) / (762 + 1)
      const a = settleFloor29Apply({ ...sigL }, fl);
      push('PR10 apply: shadow mode leaves the displayed risk unchanged and records the floor; gate mode raises it to the floor', SETTLE_FLOOR_MODE === 'gate' ? (a.pFlip === 0.0072 && a.settleFloor.applied === true) : (a.pFlip === 0.002 && a.settleFloor.binds === true && a.settleFloor.applied === false), JSON.stringify(a.settleFloor));
      const gatesT = { hard: [], soft: [] }; settleFloor29Gate(gatesT, { gapUsd: 118.2, basisMeanUsd: -1.67, regime: { bucket: 4 } }, 101.6, 64510.2);
      push('PR10 gate: a soft gate is pushed only in gate mode', SETTLE_FLOOR_MODE === 'gate' ? gatesT.soft.length === 1 : gatesT.soft.length === 0, JSON.stringify(gatesT.soft));
      const gatesN = { hard: [], soft: [] }; settleFloor29Gate(gatesN, { gapUsd: 101.7, basisMeanUsd: 1.21, regime: { bucket: 3 } }, 91.8, 68245.46);
      push('PR10 gate: no soft gate when the floor is below 0.5 % (Nov 14 cell)', gatesN.soft.length === 0, JSON.stringify(gatesN.soft));
      const pv = settleFloor29Apply({ state: 'PROVEN LOCKED', side: 'UP', pWin: 1, pFlip: 0, pFlipCons: 0, reasons: [] }, fl);
      push('PR10 never touches PROVEN LOCKED, REVERSAL WARNING or DATA UNRELIABLE', pv.pFlip === 0 && pv.settleFloor.applied === false && settleFloor29Apply({ state: 'REVERSAL WARNING', pFlip: 0.3, pFlipCons: 0.3, reasons: [] }, fl).pFlip === 0.3 && settleFloor29Apply({ state: 'DATA UNRELIABLE', pFlip: null, reasons: [] }, fl).pFlip === null, pv.state); }
    push('2.6 recalibration ratios loaded (quiet > 1 > active)',''')
# (f) exports
X("getKalshiContext: kalshiContext, radar, runSelfTest,", "getKalshiContext: kalshiContext, radar, runSelfTest, settleFloor29Lookup, settleFloor29Gate, settleFloor29Apply, SETTLE_FLOOR29, SETTLE_FLOOR_MODE,")
# (g) health identity
X("        build: BUILD_ID, fixes: BUILD_FIXES, ingest: INGEST_REV, codeSha256: CODE_SHA256_32,",
  "        build: BUILD_ID, fixes: BUILD_FIXES, ingest: INGEST_REV, codeSha256: CODE_SHA256_32,\n        settleFloor: { mode: SETTLE_FLOOR_MODE, cells: Object.keys(SETTLE_FLOOR29.cells).length, tableSha256: SETTLE_FLOOR29.meta.cellsJsonSha256, release: 'PR10-2026-11-16' },")
# (h) configuration hash covers the mode
X('"SETTLE_ALIGN", "SETTLE_POLL_MS",', '"SETTLE_ALIGN", "SETTLE_FLOOR_MODE", "SETTLE_POLL_MS",')
open(outp, 'w').write(src)
print('written', outp, 'sha256', hashlib.sha256(src.encode()).hexdigest(), 'lines', src.count('\n'))
