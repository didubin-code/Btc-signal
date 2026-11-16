"""Build the PR11 server file from the exact I2 file by exact-string replacement (every anchor must occur exactly once).
PR11 = settlement-exposure gate (round7/PR11_DECLARATION.md): LOCKED is withheld, through the existing soft-gate path, at any second in the
final 120 s where the adverse move of the still-unknown settlement prints needed to reverse the settlement is below the historical floor
R*(h) (round7/qtable/rstar_0.050.json: 0.05 % two-sided exceedance over 2023-10..2026-08). PR11_MODE env: off | shadow (compute, carry on
every signal and row, score as shadow policy H, change no decision) | gate (default: also withhold LOCKED). Probabilities are never changed.
usage: python3 -I make_PR11.py <base I2 pinradar_server.js> <rstar_0.050.json> <PR11_DECLARATION.md> <out.js>"""
import sys, json, hashlib
base, table_f, decl_f, outp = sys.argv[1:5]
src = open(base).read(); assert hashlib.sha256(src.encode()).hexdigest() == 'ca51a0c6f7cfd117f4db6f75ca1dec56e7c277674c97920fc82706b01548040f', 'base is not the live I2 file'
tab = json.load(open(table_f)); table = [tab['rstar'][str(h)] for h in range(1, 121)]
assert len(table) == 120 and all(table[i] <= table[i + 1] for i in range(119)) and table[0] == 10 and table[119] == 68
table_json = json.dumps(table, separators=(',', ':')); table_sha = hashlib.sha256(table_json.encode()).hexdigest()
decl_sha = hashlib.sha256(open(decl_f, 'rb').read()).hexdigest(); src_table_sha = hashlib.sha256(open(table_f, 'rb').read()).hexdigest()
def X(old, new, count=1):
    global src
    assert src.count(old) == count, 'anchor count %d != %d for: %s' % (src.count(old), count, old[:90])
    src = src.replace(old, new)
# (a) constants, table and functions after INGEST_REV
X("const INGEST_REV = 'I2-2026-11-13';", "const INGEST_REV = 'I2-2026-11-13';\n" + r'''/* =====================================================================
   PR11 (2026-11-16): SETTLEMENT-EXPOSURE GATE  (round7/PR11_DECLARATION.md)
   The settlement is the simple average of the 60 official prints of the final minute. With nKnown prints recorded exactly and
   r = 60 - nKnown still unknown, the settlement reverses against the leader only if the MEAN of the r unknown prints ends at
   least R = 60 * |gap| / r below (UP) or above (DOWN) the current index; before the minute R = |gap| over the h seconds to close.
   PR11 admits a second only when R >= R*(h), the smallest move that occurred with a frequency of at most 0.05 % (two-sided) over
   every second of the 1-s BTC/USDC history 2023-10-02 .. 2026-09-01 at that horizon, in every volatility regime. It does not
   use the volatility estimate; it does not change any probability. In gate mode LOCKED is withheld through the existing
   soft-gate path (the state shows HIGH CONFIDENCE / WAIT with the reason); PROVEN LOCKED is decided before soft gates and is
   never touched; REVERSAL WARNING, DATA UNRELIABLE and AWAITING SETTLEMENT are unaffected. Outside 0 < tau <= 120 s PR11 does
   not apply. PR11_MODE: off | shadow | gate (default gate). An empirical frequency bound, not a guarantee. */
const PR11_MODE = (() => { const m = String(process.env.PR11_MODE || 'gate').toLowerCase(); return ['off', 'shadow', 'gate'].includes(m) ? m : 'gate'; })();
const PR11_RSTAR = Object.freeze(''' + table_json + r''');
const PR11_META = Object.freeze({ release: 'PR11-2026-11-16', theta: 0.0005, horizons: 120, tableSha256: "''' + table_sha + r'''", sourceTableSha256: "''' + src_table_sha + r'''", declarationSha256: "''' + decl_sha + r'''", history: '2023-10-02..2026-09-01 1-s BTC/USDC' });
/* exposure of one decision: geo from lockGeometry25 (gapUsd includes the recorded prints exactly; n = prints still unknown; nLock = prints passed) */
function pr11Exposure(geo, strike, tau) {
  if (!geo || !Number.isFinite(geo.gapUsd) || !Number.isFinite(strike) || !(strike > 0) || !Number.isFinite(tau)) return null;
  if (!(tau > 0 && tau <= 120)) return { mode: PR11_MODE, applies: false };
  const nKnown = Number.isFinite(geo.nLock) ? geo.nLock : 0, nRem = Number.isFinite(geo.n) ? geo.n : 60;
  const cushionBps = Math.abs(geo.gapUsd) / strike * 1e4;
  let h, R;
  if (nKnown >= 1 && tau <= 60) { h = Math.max(1, Math.min(60, nRem)); R = cushionBps * 60 / h; }
  else { h = Math.min(120, Math.max(1, Math.ceil(tau - 1e-9))); R = cushionBps; }
  const rstar = PR11_RSTAR[h - 1], admit = R >= rstar;
  return { mode: PR11_MODE, applies: true, h, R: round(R, 2), rstar, admit, nKnown, cushionBps: round(cushionBps, 2),
    why: 'the remaining ' + (60 - nKnown) + ' settlement prints would have to move ' + R.toFixed(1) + ' bps against the call; the historical floor for ' + h + ' s is ' + rstar + ' bps (0.05 % of seconds, 2023-2026)' };
}
/* gate mode only: withhold LOCKED through the existing soft-gate path */
function pr11Gate(gates, geo, strike, tau) {
  if (PR11_MODE === 'off') return { mode: PR11_MODE, applies: false };
  const x = pr11Exposure(geo, strike, tau);
  if (x && x.applies && !x.admit && PR11_MODE === 'gate' && gates && gates.soft) gates.soft.push('PR11 cushion floor: ' + x.why);
  return x;
}
/* carried on every signal in every mode; never changes a probability or a state. In gate mode, when PR11 is the reason LOCKED is
   withheld (state HIGH CONFIDENCE with the model's flip risk at or below the LOCKED limit), the display fields that would otherwise
   inherit LOCKED or HIGH CONFIDENCE wording are replaced: headline, display27 headline/note, guarantee (the call note), projection
   (no "LOCKED in ~N s" promise) and the validation lines (no HIGH CONFIDENCE audit statistics). */
function pr11Apply(sig, x) {
  if (!sig) return sig;
  sig.pr11 = x ? { mode: x.mode, applies: !!x.applies, h: x.h ?? null, R: x.R ?? null, rstar: x.rstar ?? null, admit: x.applies ? !!x.admit : null, nKnown: x.nKnown ?? null, cushionBps: x.cushionBps ?? null } : { mode: PR11_MODE, applies: false };
  const withheld = PR11_MODE === 'gate' && x && x.applies && !x.admit && sig.state === 'HIGH CONFIDENCE' && sig.pFlip != null && sig.pFlip <= LOCK_MAX_FLIP;
  sig.pr11.withheld = !!withheld;
  if (!withheld) return sig;
  const side = sig.side || '';
  sig.headline = 'LOCKED WITHHELD — EXPOSURE FLOOR NOT MET';
  if (sig.display27) { sig.display27.headline = 'LOCKED WITHHELD — ' + side + ' (exposure floor not met)'; sig.display27.note = 'the settlement-exposure gate withholds LOCKED: ' + x.why; }
  sig.guarantee = 'LOCKED withheld by the settlement-exposure gate (PR11): ' + x.why + '. The flip risk shown is the model\'s unchanged reading; it is not an entry signal while the floor is unmet.';
  sig.projection = { side, lockInSec: null, atTau: null, assumption: 'LOCKED stays withheld until the required adverse move of the remaining prints reaches the floor (' + x.R.toFixed(1) + ' bps now vs ' + x.rstar + ' bps for ' + x.h + ' s); the model\'s flip risk alone does not lift the gate' };
  if (sig.v28) {
    if (sig.v28.value) { sig.v28.value.veto = 'not LOCKED (exposure floor not met)'; sig.v28.value.positive = false; }
    if (sig.v28.execution) { sig.v28.execution.ready = false; sig.v28.execution.withheld = true; sig.v28.execution.reason = 'LOCKED withheld — exposure floor not met'; }
  }
  sig.validation = { audit: null, live: sig.validation ? sig.validation.live : null, lines: [
    'Settlement-exposure gate (PR11): ' + x.why + '.',
    'The gate uses the recorded official prints, the current index and a frozen table of historical frequencies (0.05 % of seconds, two-sided, 2023-10 to 2026-08); it does not alter the model\'s flip risk, which is shown unchanged above.',
    'A historical frequency is not a guarantee: a move larger than any in the record can still reverse the settlement.'] };
  return sig;
}
''')
# (b) computeLockSnapshot: gate before classification, carry after enrichment
X("  brtiGate27(gates, settle, geo);                                              // v2.7: can only withhold LOCKED\n  const signal = brtiAfterClassify27(classify25(",
  "  brtiGate27(gates, settle, geo);                                              // v2.7: can only withhold LOCKED\n  const pr11 = pr11Gate(gates, geo, strike, tau);                               // PR11: gate mode only withholds LOCKED\n  const signal = brtiAfterClassify27(classify25(")
X("  enrich28(signal, { geo, settle, kal, now, tau });             // v2.8: display-only enrichment\n  return { geo, gates, signal, settle };",
  "  enrich28(signal, { geo, settle, kal, now, tau });             // v2.8: display-only enrichment\n  pr11Apply(signal, pr11);                                        // PR11: carried on the signal in every mode\n  return { geo, gates, signal, settle };")
# (c) shadow policy H
X("  { id: 'F-market-pooled-value', model: 'F', desc: 'original: TRADE NOW only if the edge survives the adverse-selection prior (cheaper ask => weaker LOCKED), POOL28' }\n]);",
  "  { id: 'F-market-pooled-value', model: 'F', desc: 'original: TRADE NOW only if the edge survives the adverse-selection prior (cheaper ask => weaker LOCKED), POOL28' },\n  { id: 'H-pr11-exposure', model: 'H', desc: 'PR11: LOCKED withheld when the required adverse move of the remaining settlement prints is below the 0.05 % historical floor R*(h)' }\n]);")
X("    default: return base;\n  }\n}\n/* per-window, per-policy first events",
  "    case 'H-pr11-exposure': {\n      const d = base; if (!d) return d;\n      const x = pr11Exposure(geo, snap.strike, tau);\n      if (!x || !x.applies || x.admit || d.state !== 'LOCKED') return d;\n      return Object.assign({}, d, { state: 'HIGH CONFIDENCE', reasons: ['LOCKED withheld: PR11 cushion floor: ' + x.why].concat(d.reasons || []), trade: Object.assign({}, d.trade || {}, { action: 'WAIT', why: 'PR11 cushion floor: ' + x.why }) });\n    }\n    default: return base;\n  }\n}\n/* per-window, per-policy first events")
X("    const view = { geo: snap.geo, gates: s.gates || snap.gates, book, decision: base, panel: snap.settle };",
  "    const view = { geo: snap.geo, gates: s.gates || snap.gates, book, decision: base, panel: snap.settle, strike: s.strike };")
# (d) rows: tape 'd' rows, their out key, and the /predictions rows
X("    inputAgeMs: sig.geometry && sig.geometry.inputAgeMs, hard: sig.gates.hard, soft: sig.gates.soft, model: sig.modelVersion,",
  "    inputAgeMs: sig.geometry && sig.geometry.inputAgeMs, pr11H: sig.pr11 ? sig.pr11.h : null, pr11R: sig.pr11 ? sig.pr11.R : null, pr11Rstar: sig.pr11 ? sig.pr11.rstar : null, pr11Admit: sig.pr11 ? sig.pr11.admit : null, hard: sig.gates.hard, soft: sig.gates.soft, model: sig.modelVersion,")
X("    out: s ? { state: s.state, side: s.side, pWin: s.pWin, pFlip: s.pFlip, pFlipCons: s.pFlipCons, action: s.trade ? s.trade.action : null, ev: s.trade ? s.trade.evConsCents : null } : null };",
  "    out: s ? { state: s.state, side: s.side, pWin: s.pWin, pFlip: s.pFlip, pFlipCons: s.pFlipCons, action: s.trade ? s.trade.action : null, ev: s.trade ? s.trade.evConsCents : null, pr11Admit: s.pr11 ? s.pr11.admit : null } : null };")
X("    pWin: sig.pWin, pFlip: sig.pFlip, pFlipCons: sig.pFlipCons, action: sig.trade ? sig.trade.action : null, ask: sig.trade ? sig.trade.askCents : null,\n    lockedSide: sig.lockedSide,",
  "    pWin: sig.pWin, pFlip: sig.pFlip, pFlipCons: sig.pFlipCons, action: sig.trade ? sig.trade.action : null, ask: sig.trade ? sig.trade.askCents : null,\n    pr11H: sig.pr11 ? sig.pr11.h : null, pr11R: sig.pr11 ? sig.pr11.R : null, pr11Rstar: sig.pr11 ? sig.pr11.rstar : null, pr11Admit: sig.pr11 ? sig.pr11.admit : null,\n    lockedSide: sig.lockedSide,")
# (e) self-tests
X("    push('2.6 recalibration ratios loaded (quiet > 1 > active)',",
  r'''    { const tsha = require('crypto').createHash('sha256').update(JSON.stringify(PR11_RSTAR)).digest('hex');
      push('PR11 table loaded: 120 thresholds, monotone, h=1 10 bps .. h=120 68 bps, sha256 as built', PR11_RSTAR.length === 120 && PR11_RSTAR.every((v, i) => i === 0 || v >= PR11_RSTAR[i - 1]) && PR11_RSTAR[0] === 10 && PR11_RSTAR[119] === 68 && tsha === PR11_META.tableSha256, tsha.slice(0, 16) + ' mode ' + PR11_MODE);
      const a = pr11Exposure({ gapUsd: 101.69, nLock: 0, n: 60 }, 68245.46, 91.8);
      push('PR11 exposure: the Nov 14 00:15 UTC entry (91.8 s, 14.9 bps, no prints yet) -> h 92, R* 55, not admitted', !!a && a.applies && a.h === 92 && a.rstar === 55 && near(a.R, 14.9, 0.1) && a.admit === false, JSON.stringify(a));
      const b = pr11Exposure({ gapUsd: 118.23, nLock: 0, n: 60 }, 64510.2, 101.6);
      push('PR11 exposure: the Nov 15 18:30 UTC entry (101.6 s, 18.3 bps) -> h 102, R* 60, not admitted', !!b && b.h === 102 && b.rstar === 60 && near(b.R, 18.3, 0.1) && b.admit === false, JSON.stringify(b));
      const c = pr11Exposure({ gapUsd: 50, nLock: 40, n: 20 }, 65000, 20.5), c2 = pr11Exposure({ gapUsd: 10, nLock: 40, n: 20 }, 65000, 20.5);
      push('PR11 exposure inside the minute: 40 prints recorded, 20 unknown: 7.7 bps cushion -> R 23.1 >= R*(20) 21 admitted; 1.5 bps -> R 4.6 not', !!c && c.h === 20 && near(c.R, 23.08, 0.05) && c.admit === true && !!c2 && near(c2.R, 4.62, 0.05) && c2.admit === false, JSON.stringify([c, c2]));
      const d = pr11Exposure({ gapUsd: 5, nLock: 59, n: 1 }, 65000, 0.5);
      push('PR11 exposure at the last print: 0.77 bps cushion with 1 print unknown -> R 46 >= R*(1) 10, admitted (the last print would have to move 46 bps)', !!d && d.h === 1 && near(d.R, 46.2, 0.2) && d.admit === true, JSON.stringify(d));
      const e = pr11Exposure({ gapUsd: 101.69, nLock: 0, n: 60 }, 68245.46, 125);
      push('PR11 does not apply beyond 120 s or at/after the close', !!e && e.applies === false && pr11Exposure({ gapUsd: 10, nLock: 60, n: 0 }, 65000, 0).applies === false, JSON.stringify(e));
      const gT = { hard: [], soft: [] }; const gx = pr11Gate(gT, { gapUsd: 118.23, nLock: 0, n: 60 }, 64510.2, 101.6);
      push('PR11 gate: a soft gate is pushed only in gate mode and only when PR11 applies and does not admit', PR11_MODE === 'gate' ? (gT.soft.length === 1 && /^PR11 cushion floor/.test(gT.soft[0])) : gT.soft.length === 0, JSON.stringify(gT.soft));
      const gA = { hard: [], soft: [] }; pr11Gate(gA, { gapUsd: 50, nLock: 40, n: 20 }, 65000, 20.5); const gO = { hard: [], soft: [] }; pr11Gate(gO, { gapUsd: 118.23, nLock: 0, n: 60 }, 64510.2, 125);
      push('PR11 gate: nothing is pushed when admitted or when PR11 does not apply', gA.soft.length === 0 && gO.soft.length === 0, JSON.stringify([gA.soft, gO.soft]));
      const cfgT = m25Cfg(10); const dec = m25Decide({ tau: 101.6, pUp: 0.998, pUpCons: 0.996, gates: { hard: [], soft: ['PR11 cushion floor: test'] }, book: null, cfg: cfgT });
      push('PR11 withheld LOCKED reads HIGH CONFIDENCE with the reason, action WAIT, probabilities unchanged', dec.state === 'HIGH CONFIDENCE' && /LOCKED withheld: PR11/.test(dec.reasons.join(' ')) && dec.trade && dec.trade.action === 'WAIT' && near(dec.pFlip, 0.002, 1e-9), JSON.stringify({ state: dec.state, action: dec.trade && dec.trade.action, pFlip: dec.pFlip }));
      const pv = m25Decide({ tau: 10, pUp: 0.9999, pUpCons: 0.9999, gates: { hard: [], soft: ['PR11 cushion floor: test'] }, book: null, cfg: cfgT, provenSide: 'UP' });
      push('PR11 never withholds PROVEN LOCKED (decided before soft gates)', pv.state === 'PROVEN LOCKED', pv.state);
      const wh = pr11Apply({ state: 'HIGH CONFIDENCE', side: 'UP', pFlip: 0.0019, pWin: 0.9981, headline: 'HIGH CONFIDENCE', display27: { headline: 'HIGH CONFIDENCE — UP (not locked)', note: null }, projection: { side: 'UP', lockInSec: 1.5, assumption: 'index holds at its current level' }, validation: { audit: { n: 366, losses: 5 }, live: null, lines: ['HIGH CONFIDENCE = flip risk ≤ 2% (not LOCKED). Out of sample: 5 of 366 first calls at this level lost (1.37%).'] }, v28: { value: { veto: 'not LOCKED (HIGH CONFIDENCE)', positive: false }, execution: { ready: true, bookFresh: true, depth: 10 } } }, gx);
      push('PR11 display (gate mode): the v2.8 readiness tile is NOT READY and the trade-value veto names the exposure floor while withheld; untouched otherwise',
        PR11_MODE === 'gate' ? (wh.v28.execution.ready === false && wh.v28.execution.withheld === true && wh.v28.value.veto === 'not LOCKED (exposure floor not met)') : (wh.v28.execution.ready === true && wh.v28.value.veto === 'not LOCKED (HIGH CONFIDENCE)'), JSON.stringify(wh.v28));
      push('PR11 display (gate mode): a LOCKED withheld by the floor shows the failed requirement in the headline, note, projection and evidence, with no inherited HIGH CONFIDENCE statistics and no "LOCKED in ~N s" promise; shadow/off leave the display untouched',
        PR11_MODE === 'gate' ? (wh.pr11.withheld === true && /^LOCKED WITHHELD/.test(wh.headline) && /exposure floor not met/.test(wh.display27.headline) && /settlement-exposure gate/.test(wh.guarantee) && wh.projection.lockInSec === null && /stays withheld/.test(wh.projection.assumption) && wh.validation.audit === null && wh.validation.lines.length === 3 && !wh.validation.lines.join(' ').includes('first calls at this level') && wh.pFlip === 0.0019 && wh.state === 'HIGH CONFIDENCE')
          : (wh.pr11.withheld === false && wh.headline === 'HIGH CONFIDENCE' && wh.display27.headline === 'HIGH CONFIDENCE — UP (not locked)' && wh.guarantee === undefined && wh.projection.lockInSec === 1.5 && wh.validation.audit.n === 366), JSON.stringify({ headline: wh.headline, d27: wh.display27.headline, proj: wh.projection, lines: wh.validation.lines.length }));
      const nw = pr11Apply({ state: 'HIGH CONFIDENCE', side: 'UP', pFlip: 0.012, headline: 'HIGH CONFIDENCE', display27: { headline: 'H' }, projection: { side: 'UP', lockInSec: 20 }, validation: { audit: { n: 1 }, lines: ['x'] } }, gx);
      push('PR11 display: a HIGH CONFIDENCE for the model\'s own reason (flip risk above the LOCKED limit) is not rewritten', nw.pr11.withheld === false && nw.headline === 'HIGH CONFIDENCE' && nw.projection.lockInSec === 20 && nw.validation.lines[0] === 'x', JSON.stringify(nw.pr11));
      const ap = pr11Apply({ state: 'LOCKED', pFlip: 0.0019, pWin: 0.9981 }, gx);
      push('PR11 apply: the field is carried (off mode: applies false) and no probability or state changes', ap.pr11 && (PR11_MODE === 'off' ? ap.pr11.applies === false : (ap.pr11.admit === false && ap.pr11.rstar === 60)) && ap.pFlip === 0.0019 && ap.state === 'LOCKED' && pr11Apply({ state: 'LOCKED', pFlip: 0.001 }, null).pr11.applies === false, JSON.stringify(ap.pr11));
    }
    push('2.6 recalibration ratios loaded (quiet > 1 > active)',''')
# (f) exports
X("getKalshiContext: kalshiContext, radar, runSelfTest,", "getKalshiContext: kalshiContext, radar, runSelfTest, pr11Exposure, pr11Gate, pr11Apply, PR11_RSTAR, PR11_MODE, PR11_META,")
# (g) health identity
X("        build: BUILD_ID, fixes: BUILD_FIXES, ingest: INGEST_REV, codeSha256: CODE_SHA256_32,",
  "        build: BUILD_ID, fixes: BUILD_FIXES, ingest: INGEST_REV, codeSha256: CODE_SHA256_32,\n        pr11: { mode: PR11_MODE, tableSha256: PR11_META.tableSha256, declarationSha256: PR11_META.declarationSha256, release: PR11_META.release },")
# (h) configuration hash covers the mode
X('"PORT", "PRED_LOG_FILE",', '"PORT", "PR11_MODE", "PRED_LOG_FILE",')
open(outp, 'w').write(src)
print('written', outp, 'sha256', hashlib.sha256(src.encode()).hexdigest(), 'lines', src.count('\n'), 'table sha', table_sha[:16], 'declaration sha', decl_sha[:16])
