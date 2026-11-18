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
   The settlement is the simple average of the 60 official prints of the final minute. With nKnown print seconds passed AND sampled (the engine's own 1-Hz index samples, not the official prints; a passed
   second without a sample is missing information and WITHHOLDS the call, b8) and r = 60 - nKnown still unknown, the settlement reverses against the leader only if the MEAN of the r unknown prints ends at
   least R = 60 * |gap| / r below (UP) or above (DOWN) the current index; before the minute R = |gap| over the h seconds to close.
   PR11 admits a second only when R >= R*(h), the smallest move that occurred with a frequency of at most 0.05 % (two-sided) over
   every second of the 1-s BTC/USDC history 2023-10-02 .. 2026-09-01 at that horizon, in every volatility regime. It does not
   use the volatility estimate; it does not change any probability. In gate mode LOCKED is withheld through the existing
   soft-gate path (the state shows HIGH CONFIDENCE / WAIT with the reason). PROVEN LOCKED - a conditional price-only test on the
   engine's own index samples at the passed print seconds, not a settlement certainty - is subject to the same floor (b6) and, when
   shown, is labelled as conditional with its assumptions; REVERSAL WARNING, DATA UNRELIABLE and AWAITING SETTLEMENT are unaffected.
   b8: in the settlement minute the official settlement reference must be valid and current (an expected partial accumulator is fine;
   an invalid, stale or missing one withholds, because the divergence and official-risk checks cannot be performed). Outside 0 < tau <= 120 s PR11 does
   not apply. PR11_MODE: off | shadow | gate (default gate). An empirical frequency bound, not a guarantee. */
const PR11_MODE = (() => { const m = String(process.env.PR11_MODE || 'gate').toLowerCase(); return ['off', 'shadow', 'gate'].includes(m) ? m : 'gate'; })();
const PR11_RSTAR = Object.freeze(''' + table_json + r''');
const PR11_META = Object.freeze({ release: 'PR11-2026-11-18-b10', theta: 0.0005, horizons: 120, tableSha256: "''' + table_sha + r'''", sourceTableSha256: "''' + src_table_sha + r'''", declarationSha256: "''' + decl_sha + r'''", history: '2023-10-02..2026-09-01 1-s BTC/USDC' });
/* exposure of one decision: geo from lockGeometry25 (gapUsd = expected settlement - strike, the passed print seconds valued by the engine's
   own index samples; n = prints still unknown; nLock = prints passed); official = the settlement panel's reference state ({ ok, reasons }),
   required in the settlement minute (b8). Returns admit only when every requirement holds: no missing sample, official reference ok in the
   minute, floor met. */
function pr11Exposure(geo, strike, tau, official) {
  if (!geo || !Number.isFinite(geo.gapUsd) || !Number.isFinite(strike) || !(strike > 0) || !Number.isFinite(tau)) return null;
  if (!(tau > 0 && tau <= 120)) return { mode: PR11_MODE, applies: false, scope: tau > 120 ? 'beyond' : 'closed' };
  const nPassed = Number.isFinite(geo.nLock) ? geo.nLock : 0, nRem = Number.isFinite(geo.n) ? geo.n : 60;
  /* b8: a passed print second is KNOWN only when the engine holds an index sample for it (matched within 600 ms, or the live index for a
     print less than 1.1 s old: geo.lockedObserved). A passed second without a sample is missing information: the exposure cannot be
     assessed from observed data and the call is withheld. It is never valued at a mean and never treated as a future print. */
  /* b9: the live-index substitution is an approximation allowed for the single newest passed print only (a print less than 1.1 s old
     whose sample has not arrived). Within 100 ms after a print the engine can fill a second passed print the same way when that print's
     sample is missing; such an extra substitution is missing information and withholds (never admitted). */
  const extraFill = Math.max(0, (Number.isFinite(geo.lockedFilledLive) ? geo.lockedFilledLive : 0) - 1);
  const nObs = Number.isFinite(geo.lockedObserved) ? Math.max(0, Math.min(nPassed, geo.lockedObserved - extraFill)) : nPassed;
  const nMissing = nPassed - nObs;
  /* b10: exposure in the exposure table's units. The table measures |mean(remaining prints) - p[t]| / p[t], i.e. bps of the CURRENT
     price at the decision second, so the required adverse move is expressed relative to the current index (geo.index), not the strike.
     The two differ by the index-to-strike ratio (about 0.1-0.5 %), enough to flip a decision at the floor boundary in either direction
     (an UP leader above the strike read too large with the strike denominator, a DOWN leader below it too small). The strike is the
     denominator only when the geometry carries no finite index (never in production; keeps older fixtures meaningful). */
  const refPx = (Number.isFinite(geo.index) && geo.index > 0) ? geo.index : strike;
  const cushionBps = Math.abs(geo.gapUsd) / refPx * 1e4;
  let h, R;
  if (nPassed >= 1 && tau <= 60) { h = Math.max(1, Math.min(60, nRem)); R = cushionBps * 60 / h; }
  else { h = Math.min(120, Math.max(1, Math.ceil(tau - 1e-9))); R = cushionBps; }
  const rstar = PR11_RSTAR[h - 1], floorMet = R >= rstar;
  /* b8: in the settlement minute the official settlement reference must be valid and current, so that the divergence and official-risk
     checks are performable; an expected partial accumulator is valid; invalid, stale or missing withholds (fail closed) */
  const inMinute = tau <= 60, officialOk = !!(official && official.ok === true);
  const reasons = [];
  if (nMissing > 0) reasons.push('missing');
  if (inMinute && !officialOk) reasons.push('official');
  if (!floorMet) reasons.push('floor');
  const admit = reasons.length === 0, reason = reasons[0] || null;
  const why = reason === 'missing' ? nMissing + ' of the ' + nPassed + ' passed settlement seconds ' + (nMissing > 1 ? 'have' : 'has') + ' no index sample' + (extraFill > 0 ? ' (' + extraFill + ' valued at the live index beyond the newest print)' : '') + ', so the exposure cannot be assessed from observed information (floor for ' + h + ' s: ' + rstar + ' bps; proxy estimate ' + R.toFixed(1) + ' bps, diagnostic only)'
    : reason === 'official' ? 'the official settlement reference is unusable (' + ((official && official.reasons && official.reasons.length) ? official.reasons[0] : 'not available') + '), so the divergence and official-risk checks cannot be performed in the settlement minute (proxy estimate ' + R.toFixed(1) + ' bps vs floor ' + rstar + ' bps for ' + h + ' s, diagnostic only)'
    : 'the remaining ' + (60 - nPassed) + ' settlement prints would have to move ' + R.toFixed(1) + ' bps of the current index against the call; the historical floor for ' + h + ' s is ' + rstar + ' bps (0.05 % of seconds, 2023-2026)';
  return { mode: PR11_MODE, applies: true, h, R: round(R, 2), rstar, floorMet, admit, reason, reasons, officialOk: inMinute ? officialOk : null, nKnown: nObs, nMissing, cushionBps: round(cushionBps, 2), why };
}
/* gate mode only: withhold LOCKED and PROVEN LOCKED through the existing soft-gate path (gates.pr11 carries the same reason so that
   m25Decide applies it to PROVEN LOCKED as well). panel = the settlement panel (settlePanel27): reference OFFICIAL means the official
   settlement reference is valid and current (b8). */
function pr11Gate(gates, geo, strike, tau, panel) {
  if (PR11_MODE === 'off') return { mode: PR11_MODE, applies: false };
  const official = panel ? { ok: panel.reference === 'OFFICIAL', reasons: panel.officialReasons || [] } : { ok: false, reasons: ['no settlement panel'] };
  const x = pr11Exposure(geo, strike, tau, official);
  if (x && x.applies && !x.admit && PR11_MODE === 'gate' && gates && gates.soft) {
    const tag = x.reason === 'missing' ? 'PR11 settlement samples missing: ' : x.reason === 'official' ? 'PR11 official reference unavailable: ' : 'PR11 cushion floor: ';
    gates.soft.push(tag + x.why); gates.pr11 = (gates.pr11 || []).concat([tag + x.why]);
  }
  return x;
}
/* carried on every signal in every mode; never changes a probability or a state. In gate mode, when PR11 is the reason LOCKED is
   withheld (state HIGH CONFIDENCE with the model's flip risk at or below the LOCKED limit), the display fields that would otherwise
   inherit LOCKED or HIGH CONFIDENCE wording are replaced: headline, display27 headline/note, guarantee (the call note), projection
   (no "LOCKED in ~N s" promise) and the validation lines (no HIGH CONFIDENCE audit statistics). PROVEN LOCKED (gate mode, b6) is shown
   as a conditional assessment with its assumptions; pr11.qualified marks a served LOCKED/PROVEN LOCKED that meets the floor. */
function pr11Apply(sig, x) {
  if (!sig) return sig;
  sig.pr11 = x ? { mode: x.mode, applies: !!x.applies, h: x.h ?? null, R: x.R ?? null, rstar: x.rstar ?? null, admit: x.applies ? !!x.admit : null, reason: x.reason ?? null, reasons: x.reasons ?? null, floorMet: x.floorMet ?? null, officialOk: x.officialOk ?? null, nKnown: x.nKnown ?? null, nMissing: x.nMissing ?? null, cushionBps: x.cushionBps ?? null } : { mode: PR11_MODE, applies: false };
  const withheld = PR11_MODE === 'gate' && x && x.applies && !x.admit && sig.state === 'HIGH CONFIDENCE' && sig.pFlip != null && sig.pFlip <= LOCK_MAX_FLIP;
  sig.pr11.withheld = !!withheld;
  sig.pr11.scope = x && x.applies ? 'final120' : (x && x.scope) || null;
  sig.pr11.qualified = !!(x && x.applies && x.admit && (sig.state === 'LOCKED' || sig.state === 'PROVEN LOCKED'));   // b6: a served LOCKED/PROVEN that meets PR11
  sig.pr11.proven = sig.state === 'PROVEN LOCKED' ? { conditional: true, marginFrac: PROVEN_MARGIN_FRAC, basis: 'engine index samples at the passed print seconds, not the official prints',
    assumptions: ['official prints for the passed seconds within ' + (100 * PROVEN_MARGIN_FRAC).toFixed(2) + ' % of the engine\'s index samples', 'no print or settlement revision', 'settlement = plain average of the 60 prints'] } : null;
  /* beyond 120 s to close the gate has not assessed the call: a LOCKED shown there is labelled as not yet gated (presentation only;
     state, probabilities, trade decision, rows and the observer's view unchanged; PROVEN LOCKED cannot occur there) */
  if (PR11_MODE === 'gate' && x && !x.applies && x.scope === 'beyond' && sig.state === 'LOCKED') {
    const side = sig.side || '';
    sig.headline = 'LOCKED — NOT YET GATED (over 120 s to close)';
    if (sig.display27) { sig.display27.headline = 'PREDICTED LOCKED — ' + side + ' · NOT YET GATED (over 120 s to close)'; sig.display27.note = 'the settlement-exposure gate (PR11) assesses this call from 120 s to close; until then LOCKED is the model\'s prediction alone'; }
    sig.guarantee = 'More than 120 s to close: the settlement-exposure gate (PR11) has not assessed this call; it is assessed from 120 s. Until then LOCKED is the model\'s prediction alone, not a guarantee.';
    const lines = (sig.validation && sig.validation.lines) || [];
    sig.validation = Object.assign({}, sig.validation || {}, { lines: ['Settlement-exposure gate (PR11): not applied beyond 120 s to close; this call is assessed when the final 120 s begin.'].concat(lines) });
    return sig;
  }
  /* PROVEN LOCKED (gate mode, b6): a conditional price-only test on the engine's own index samples, not a settlement certainty. It reaches
     this point only when it also meets the exposure floor (otherwise m25Decide withheld it above); it is shown as a separate conditional
     assessment with its assumptions. State, probabilities, trade decision and v2.8 tiles are untouched. */
  if (PR11_MODE === 'gate' && sig.state === 'PROVEN LOCKED') {
    const side = sig.side || '', m = (100 * PROVEN_MARGIN_FRAC).toFixed(2);
    const floor = x && x.applies ? (x.admit ? 'met: ' + x.why : 'NOT met: ' + x.why) : 'not applied';
    sig.headline = 'PROVEN LOCKED (CONDITIONAL) — ' + side;
    if (sig.display27) { sig.display27.headline = 'PROVEN LOCKED — ' + side + ' · CONDITIONAL (price-only test on recorded index samples)'; sig.display27.note = 'conditional, not a settlement certainty: holds if the official prints for the passed seconds are within ' + m + ' % of the engine\'s index samples and nothing is revised'; }
    sig.guarantee = 'PROVEN LOCKED is a conditional price-only test, not a settlement certainty: the engine\'s own index samples for the passed print seconds, discounted by ' + m + ' %, keep the 60-print average above the strike even if every remaining print were $0. It holds only if the official prints for those seconds are within ' + m + ' % of the samples, no print or settlement is revised, and the settlement is the plain 60-print average. Settlement-exposure gate (PR11) ' + floor + '.';
    const lines = ((sig.validation && sig.validation.lines) || []).map(l => /^PROVEN:/.test(l) ? 'PROVEN LOCKED (conditional): the engine\'s index samples at the passed print seconds, discounted by ' + m + ' %, keep the 60-print average above the strike with every remaining print at $0. Assumptions: official prints within ' + m + ' % of those samples; no revision; plain 60-print average. The LOCKED record above is the LOCKED standard\'s; PROVEN LOCKED has no separate validated record.' : l);
    sig.validation = Object.assign({}, sig.validation || {}, { lines: ['Settlement-exposure gate (PR11): ' + floor + '.'].concat(lines) });
    if (sig.v28 && sig.v28.designation) sig.v28.designation = { code: 'PROVEN_CONDITIONAL', label: 'PROVEN LOCKED (conditional price-only test) — not a settlement certainty',
      basis: 'the engine\'s index samples at the passed print seconds, discounted by ' + m + ' %, keep the 60-print average above the strike with every remaining print at $0; assumes official prints within ' + m + ' % of those samples, no revision and a plain 60-print average; settlement-exposure gate (PR11) ' + floor.split(':')[0] };
    return sig;
  }
  if (!withheld) return sig;
  const side = sig.side || '', reason = x.reason || 'floor';
  const H = reason === 'missing' ? { head: 'LOCKED WITHHELD — SETTLEMENT SAMPLES MISSING', d27: 'LOCKED WITHHELD — ' + side + ' (' + x.nMissing + ' passed settlement second' + (x.nMissing > 1 ? 's' : '') + ' unsampled)', veto: 'not LOCKED (settlement samples missing)', ready: 'LOCKED withheld — settlement samples missing', until: 'every passed settlement second has an index sample' }
    : reason === 'official' ? { head: 'LOCKED WITHHELD — OFFICIAL REFERENCE UNAVAILABLE', d27: 'LOCKED WITHHELD — ' + side + ' (official settlement reference not verifiable)', veto: 'not LOCKED (official reference unavailable)', ready: 'LOCKED withheld — official reference unavailable', until: 'the official settlement reference is valid and current' }
    : { head: 'LOCKED WITHHELD — EXPOSURE FLOOR NOT MET', d27: 'LOCKED WITHHELD — ' + side + ' (exposure floor not met)', veto: 'not LOCKED (exposure floor not met)', ready: 'LOCKED withheld — exposure floor not met', until: 'the required adverse move of the remaining prints reaches the floor (' + x.R.toFixed(1) + ' bps now vs ' + x.rstar + ' bps for ' + x.h + ' s); the model\'s flip risk alone does not lift the gate' };
  sig.headline = H.head;
  if (sig.display27) { sig.display27.headline = H.d27; sig.display27.note = 'the settlement-exposure gate withholds LOCKED: ' + x.why; }
  sig.guarantee = 'LOCKED withheld by the settlement-exposure gate (PR11): ' + x.why + '. The flip risk shown is the model\'s unchanged reading; it is not an entry signal while the gate withholds.';
  sig.projection = { side, lockInSec: null, atTau: null, assumption: 'LOCKED stays withheld until ' + H.until };
  if (sig.v28) {
    if (sig.v28.value) { sig.v28.value.veto = H.veto; sig.v28.value.positive = false; }
    if (sig.v28.execution) { sig.v28.execution.ready = false; sig.v28.execution.withheld = true; sig.v28.execution.reason = H.ready; }
  }
  sig.validation = { audit: null, live: sig.validation ? sig.validation.live : null, lines: [
    'Settlement-exposure gate (PR11): ' + x.why + '.',
    'The gate uses the number of settlement prints already passed (valued by the engine\'s own index samples, every one of which must be present), the official settlement reference (which must be valid and current in the settlement minute), the current index and a frozen table of historical frequencies (0.05 % of seconds, two-sided, 2023-10 to 2026-08); it does not alter the model\'s flip risk, which is shown unchanged above.',
    'A historical frequency is not a guarantee: a move larger than any in the record can still reverse the settlement.'] };
  return sig;
}
''')
# (a1) classify25 copies the gates object for m25Decide: carry the PR11 list too (b8; builds 6-7 dropped it here, so the PROVEN branch never saw the gate in the full path)
X("  const g = { hard: [...gates.hard], soft: [...gates.soft], official: [...(gates.official || [])], budgetMs: gates.budgetMs };",
  "  const g = { hard: [...gates.hard], soft: [...gates.soft], official: [...(gates.official || [])], pr11: [...(gates.pr11 || [])], budgetMs: gates.budgetMs };   // PR11 b8: the PR11 gate reaches m25Decide's PROVEN branch")
# (a2) m25Decide: the floor applies to PROVEN LOCKED too (b6)
X("  else if (provenSide && provenSide === side && !(gates.official && gates.official.length)) out.state = 'PROVEN LOCKED';   // v2.8 D4",
  "  else if (provenSide && provenSide === side && !(gates.official && gates.official.length) && !(gates.pr11 && gates.pr11.length)) out.state = 'PROVEN LOCKED';   // v2.8 D4; PR11 b6: the exposure floor applies to PROVEN LOCKED too")
# (b) computeLockSnapshot: gate before classification, carry after enrichment
X("  brtiGate27(gates, settle, geo);                                              // v2.7: can only withhold LOCKED\n  const signal = brtiAfterClassify27(classify25(",
  "  brtiGate27(gates, settle, geo);                                              // v2.7: can only withhold LOCKED\n  const pr11 = pr11Gate(gates, geo, strike, tau, settle);                       // PR11: gate mode only withholds LOCKED\n  const signal = brtiAfterClassify27(classify25(")
X("  enrich28(signal, { geo, settle, kal, now, tau });             // v2.8: display-only enrichment\n  return { geo, gates, signal, settle };",
  "  enrich28(signal, { geo, settle, kal, now, tau });             // v2.8: display-only enrichment\n  pr11Apply(signal, pr11);                                        // PR11: carried on the signal in every mode\n  return { geo, gates, signal, settle };")
# (c) shadow policy H
X("  { id: 'F-market-pooled-value', model: 'F', desc: 'original: TRADE NOW only if the edge survives the adverse-selection prior (cheaper ask => weaker LOCKED), POOL28' }\n]);",
  "  { id: 'F-market-pooled-value', model: 'F', desc: 'original: TRADE NOW only if the edge survives the adverse-selection prior (cheaper ask => weaker LOCKED), POOL28' },\n  { id: 'H-pr11-exposure', model: 'H', desc: 'PR11: LOCKED withheld when the required adverse move of the remaining settlement prints is below the 0.05 % historical floor R*(h)' }\n]);")
X("    default: return base;\n  }\n}\n/* per-window, per-policy first events",
  "    case 'H-pr11-exposure': {\n      const d = base; if (!d) return d;\n      const pn = snap.panel; const x = pr11Exposure(geo, snap.strike, tau, pn ? { ok: pn.reference === 'OFFICIAL', reasons: pn.officialReasons || [] } : { ok: false, reasons: ['no settlement panel'] });\n      if (!x || !x.applies || x.admit || !(d.state === 'LOCKED' || d.state === 'PROVEN LOCKED')) return d;\n      return Object.assign({}, d, { state: 'HIGH CONFIDENCE', reasons: ['LOCKED withheld: PR11 (' + x.reason + '): ' + x.why].concat(d.reasons || []), trade: Object.assign({}, d.trade || {}, { action: 'WAIT', why: 'PR11 (' + x.reason + '): ' + x.why }) });\n    }\n    default: return base;\n  }\n}\n/* per-window, per-policy first events")
X("    const view = { geo: snap.geo, gates: s.gates || snap.gates, book, decision: base, panel: snap.settle };",
  "    const view = { geo: snap.geo, gates: s.gates || snap.gates, book, decision: base, panel: snap.settle, strike: s.strike };")
# (d) rows: tape 'd' rows, their out key, and the /predictions rows
X("    inputAgeMs: sig.geometry && sig.geometry.inputAgeMs, hard: sig.gates.hard, soft: sig.gates.soft, model: sig.modelVersion,",
  "    inputAgeMs: sig.geometry && sig.geometry.inputAgeMs, pr11H: sig.pr11 ? sig.pr11.h : null, pr11R: sig.pr11 ? sig.pr11.R : null, pr11Rstar: sig.pr11 ? sig.pr11.rstar : null, pr11Admit: sig.pr11 ? sig.pr11.admit : null, pr11Missing: sig.pr11 ? sig.pr11.nMissing : null, pr11Reason: sig.pr11 ? sig.pr11.reason : null, hard: sig.gates.hard, soft: sig.gates.soft, model: sig.modelVersion,")
X("    out: s ? { state: s.state, side: s.side, pWin: s.pWin, pFlip: s.pFlip, pFlipCons: s.pFlipCons, action: s.trade ? s.trade.action : null, ev: s.trade ? s.trade.evConsCents : null } : null };",
  "    out: s ? { state: s.state, side: s.side, pWin: s.pWin, pFlip: s.pFlip, pFlipCons: s.pFlipCons, action: s.trade ? s.trade.action : null, ev: s.trade ? s.trade.evConsCents : null, pr11Admit: s.pr11 ? s.pr11.admit : null } : null };")
X("    pWin: sig.pWin, pFlip: sig.pFlip, pFlipCons: sig.pFlipCons, action: sig.trade ? sig.trade.action : null, ask: sig.trade ? sig.trade.askCents : null,\n    lockedSide: sig.lockedSide,",
  "    pWin: sig.pWin, pFlip: sig.pFlip, pFlipCons: sig.pFlipCons, action: sig.trade ? sig.trade.action : null, ask: sig.trade ? sig.trade.askCents : null,\n    pr11H: sig.pr11 ? sig.pr11.h : null, pr11R: sig.pr11 ? sig.pr11.R : null, pr11Rstar: sig.pr11 ? sig.pr11.rstar : null, pr11Admit: sig.pr11 ? sig.pr11.admit : null, pr11Missing: sig.pr11 ? sig.pr11.nMissing : null, pr11Reason: sig.pr11 ? sig.pr11.reason : null,\n    lockedSide: sig.lockedSide,")
# (e) self-tests
X("    push('2.6 recalibration ratios loaded (quiet > 1 > active)',",
  r'''    { const tsha = require('crypto').createHash('sha256').update(JSON.stringify(PR11_RSTAR)).digest('hex'); const OK = { ok: true, reasons: [] }, PANEL_OK = { reference: 'OFFICIAL', officialReasons: [] };
      push('PR11 table loaded: 120 thresholds, monotone, h=1 10 bps .. h=120 68 bps, sha256 as built', PR11_RSTAR.length === 120 && PR11_RSTAR.every((v, i) => i === 0 || v >= PR11_RSTAR[i - 1]) && PR11_RSTAR[0] === 10 && PR11_RSTAR[119] === 68 && tsha === PR11_META.tableSha256, tsha.slice(0, 16) + ' mode ' + PR11_MODE);
      const a = pr11Exposure({ gapUsd: 101.69, nLock: 0, n: 60 }, 68245.46, 91.8);
      push('PR11 exposure: the Nov 14 00:15 UTC entry (91.8 s, 14.9 bps, no prints yet) -> h 92, R* 55, not admitted', !!a && a.applies && a.h === 92 && a.rstar === 55 && near(a.R, 14.9, 0.1) && a.admit === false, JSON.stringify(a));
      const b = pr11Exposure({ gapUsd: 118.23, nLock: 0, n: 60 }, 64510.2, 101.6);
      push('PR11 exposure: the Nov 15 18:30 UTC entry (101.6 s, 18.3 bps) -> h 102, R* 60, not admitted', !!b && b.h === 102 && b.rstar === 60 && near(b.R, 18.3, 0.1) && b.admit === false, JSON.stringify(b));
      const c = pr11Exposure({ gapUsd: 50, nLock: 40, n: 20 }, 65000, 20.5, OK), c2 = pr11Exposure({ gapUsd: 10, nLock: 40, n: 20 }, 65000, 20.5, OK);
      push('PR11 exposure inside the minute: 40 prints recorded, 20 unknown: 7.7 bps cushion -> R 23.1 >= R*(20) 21 admitted; 1.5 bps -> R 4.6 not', !!c && c.h === 20 && near(c.R, 23.08, 0.05) && c.admit === true && !!c2 && near(c2.R, 4.62, 0.05) && c2.admit === false, JSON.stringify([c, c2]));
      const d = pr11Exposure({ gapUsd: 5, nLock: 59, n: 1 }, 65000, 0.5, OK);
      push('PR11 exposure at the last print: 0.77 bps cushion with 1 print unknown -> R 46 >= R*(1) 10, admitted (the last print would have to move 46 bps)', !!d && d.h === 1 && near(d.R, 46.2, 0.2) && d.admit === true, JSON.stringify(d));
      const e = pr11Exposure({ gapUsd: 101.69, nLock: 0, n: 60 }, 68245.46, 125);
      push('PR11 does not apply beyond 120 s (scope beyond) or at/after the close (scope closed)', !!e && e.applies === false && e.scope === 'beyond' && pr11Exposure({ gapUsd: 10, nLock: 60, n: 0 }, 65000, 0).scope === 'closed' && pr11Exposure({ gapUsd: 101.69, nLock: 0, n: 60 }, 68245.46, 120).applies === true, JSON.stringify(e));
      const mkL = (tau) => ({ state: 'LOCKED', side: 'UP', pFlip: 0.0015, pWin: 0.9985, headline: 'LOCKED UP', display27: { headline: 'PREDICTED LOCKED — UP', note: 'predictive classification (validated flip risk), not a guarantee of the settlement' }, guarantee: 'prediction, not a guarantee: the flip risk shown is a calibrated model estimate', projection: null, validation: { audit: { n: 3484 }, live: null, lines: ['LOCKED standard: …'] }, v28: { value: { veto: null, positive: true }, execution: { ready: true } }, trade: { action: 'TRADE NOW' } });
      const bey = pr11Apply(mkL(121), pr11Gate({ hard: [], soft: [] }, { gapUsd: 30, nLock: 0, n: 60 }, 65000, 121));
      push('PR11 scope (gate mode): a LOCKED beyond 120 s is labelled NOT YET GATED in the headline, display and note, the evidence is prefixed, and state, probabilities, trade decision and v2.8 tiles are untouched; shadow/off leave it alone',
        PR11_MODE === 'gate' ? (bey.pr11.scope === 'beyond' && /NOT YET GATED/.test(bey.headline) && /NOT YET GATED/.test(bey.display27.headline) && /120 s/.test(bey.guarantee) && /not applied beyond 120 s/.test(bey.validation.lines[0]) && bey.validation.lines.length === 2 && bey.validation.audit.n === 3484 && bey.state === 'LOCKED' && bey.pFlip === 0.0015 && bey.trade.action === 'TRADE NOW' && bey.v28.execution.ready === true)
          : (bey.headline === 'LOCKED UP' && bey.display27.headline === 'PREDICTED LOCKED — UP' && bey.validation.lines.length === 1), JSON.stringify({ headline: bey.headline, d27: bey.display27.headline, scope: bey.pr11.scope }));
      const in120 = pr11Apply(mkL(120), pr11Gate({ hard: [], soft: [] }, { gapUsd: 30 * 65000 / 1e4 * 3, nLock: 0, n: 60 }, 65000, 120));
      push('PR11 transition: at 120 s the gate applies; an admitted LOCKED keeps its ordinary labels (PREDICTED LOCKED); off mode carries no exposure', (PR11_MODE === 'off' ? in120.pr11.applies === false : (in120.pr11.scope === 'final120' && in120.pr11.applies === true && in120.pr11.admit === true)) && in120.headline === 'LOCKED UP' && in120.display27.headline === 'PREDICTED LOCKED — UP' && in120.validation.lines.length === 1, JSON.stringify(in120.pr11));
      const pvs = pr11Apply({ state: 'PROVEN LOCKED', side: 'UP', pFlip: 0, pWin: 1, headline: 'PROVEN UP', display27: { headline: 'MATHEMATICALLY FINAL (price-only) — UP', note: null }, guarantee: 'price-only bound (the remaining prints cannot overturn it); still subject to CF Benchmarks data', validation: { audit: null, lines: ['PROVEN: …'] }, trade: { action: 'TRADE NOW' }, v28: { execution: { ready: true }, designation: { code: 'MATHEMATICALLY_FINAL', label: 'MATHEMATICALLY FINAL (price-only bound)' } } }, pr11Gate({ hard: [], soft: [] }, { gapUsd: 300, nLock: 50, n: 10 }, 65000, 10.5, PANEL_OK));
      push('PR11 b6 PROVEN LOCKED (gate mode): shown only as a CONDITIONAL assessment — headline, display, note, call note and evidence state the price-only basis and the assumptions, the floor is reported met, state/trade/readiness untouched, pr11.qualified and pr11.proven.conditional set; shadow/off leave the labels alone',
        PR11_MODE === 'gate' ? (pvs.pr11.admit === true && pvs.pr11.qualified === true && !!pvs.pr11.proven && pvs.pr11.proven.conditional === true && pvs.headline === 'PROVEN LOCKED (CONDITIONAL) — UP' && /CONDITIONAL/.test(pvs.display27.headline) && /not a settlement certainty/.test(pvs.display27.note) && /not a settlement certainty/.test(pvs.guarantee) && /0\.25 %/.test(pvs.guarantee) && /\(PR11\) met/.test(pvs.guarantee) && /^Settlement-exposure gate \(PR11\): met/.test(pvs.validation.lines[0]) && /Assumptions:/.test(pvs.validation.lines[1]) && !pvs.validation.lines.includes('PROVEN: …') && pvs.state === 'PROVEN LOCKED' && pvs.trade.action === 'TRADE NOW' && pvs.v28.execution.ready === true && pvs.v28.designation.code === 'PROVEN_CONDITIONAL' && /not a settlement certainty/.test(pvs.v28.designation.label))
          : (pvs.headline === 'PROVEN UP' && pvs.display27.headline === 'MATHEMATICALLY FINAL (price-only) — UP' && pvs.validation.lines[0] === 'PROVEN: …' && pvs.v28.designation.code === 'MATHEMATICALLY_FINAL' && (PR11_MODE === 'off' ? (pvs.pr11.applies === false && pvs.pr11.qualified === false) : (pvs.pr11.admit === true && pvs.pr11.qualified === true))), JSON.stringify({ headline: pvs.headline, d27: pvs.display27.headline, lines: pvs.validation.lines.length, pr11: pvs.pr11 }));
      const gT = { hard: [], soft: [] }; const gx = pr11Gate(gT, { gapUsd: 118.23, nLock: 0, n: 60 }, 64510.2, 101.6);
      push('PR11 gate: a soft gate is pushed only in gate mode and only when PR11 applies and does not admit', PR11_MODE === 'gate' ? (gT.soft.length === 1 && /^PR11 cushion floor/.test(gT.soft[0])) : gT.soft.length === 0, JSON.stringify(gT.soft));
      const gA = { hard: [], soft: [] }; pr11Gate(gA, { gapUsd: 50, nLock: 40, n: 20 }, 65000, 20.5, PANEL_OK); const gO = { hard: [], soft: [] }; pr11Gate(gO, { gapUsd: 118.23, nLock: 0, n: 60 }, 64510.2, 125);
      push('PR11 gate: nothing is pushed when admitted or when PR11 does not apply', gA.soft.length === 0 && gO.soft.length === 0, JSON.stringify([gA.soft, gO.soft]));
      const cfgT = m25Cfg(10); const dec = m25Decide({ tau: 101.6, pUp: 0.998, pUpCons: 0.996, gates: { hard: [], soft: ['PR11 cushion floor: test'] }, book: null, cfg: cfgT });
      push('PR11 withheld LOCKED reads HIGH CONFIDENCE with the reason, action WAIT, probabilities unchanged', dec.state === 'HIGH CONFIDENCE' && /LOCKED withheld: PR11/.test(dec.reasons.join(' ')) && dec.trade && dec.trade.action === 'WAIT' && near(dec.pFlip, 0.002, 1e-9), JSON.stringify({ state: dec.state, action: dec.trade && dec.trade.action, pFlip: dec.pFlip }));
      const pv = m25Decide({ tau: 10, pUp: 0.9999, pUpCons: 0.9999, gates: { hard: [], soft: ['PR11 cushion floor: test'], pr11: ['PR11 cushion floor: test'] }, book: null, cfg: cfgT, provenSide: 'UP' });
      const pvI2 = m25Decide({ tau: 10, pUp: 0.9999, pUpCons: 0.9999, gates: { hard: [], soft: ['volatility estimate warming up'] }, book: null, cfg: cfgT, provenSide: 'UP' });
      push('PR11 b6: the exposure floor withholds PROVEN LOCKED too (HIGH CONFIDENCE, reason, WAIT); other soft gates still do not (I2 behaviour kept)', pv.state === 'HIGH CONFIDENCE' && /LOCKED withheld: PR11/.test(pv.reasons.join(' ')) && pv.trade && pv.trade.action === 'WAIT' && pvI2.state === 'PROVEN LOCKED', JSON.stringify([pv.state, pvI2.state]));
      { const full = pr11Exposure({ gapUsd: 66.67, nLock: 40, n: 20, lockedObserved: 40, lockedMean: 65075, index: 65050 }, 65000, 20.5, OK);
        const m4 = pr11Exposure({ gapUsd: 66.67, nLock: 40, n: 20, lockedObserved: 36, lockedMean: 65075, index: 65050 }, 65000, 20.5, OK);
        const m8 = pr11Exposure({ gapUsd: 66.67, nLock: 40, n: 20, lockedObserved: 32, lockedMean: 65075, index: 65050 }, 65000, 20.5, OK);
        push('PR11 b8: with every passed print second sampled the exposure is the b6 value (40 passed, 20 unknown: h 20, R 30.8 >= 21, admitted, 0 missing, reason null)', !!full && full.h === 20 && near(full.R, 30.77, 0.05) && full.admit === true && full.nMissing === 0 && full.nKnown === 40 && full.reason === null, JSON.stringify(full));
        push('PR11 b8: 4 passed seconds without a sample WITHHOLD the call (reason missing) although the floor is met — missing information is never valued at a mean nor treated as a future print', !!m4 && m4.admit === false && m4.reason === 'missing' && m4.nMissing === 4 && m4.nKnown === 36 && m4.floorMet === true && /4 of the 40 passed settlement seconds have no index sample/.test(m4.why), JSON.stringify(m4));
        push('PR11 b8: 8 missing seconds withhold too (reason missing)', !!m8 && m8.admit === false && m8.reason === 'missing' && m8.nMissing === 8, JSON.stringify(m8));
        const m0 = pr11Exposure({ gapUsd: 66.67, nLock: 40, n: 20, lockedObserved: 0, lockedMean: null, index: 65050 }, 65000, 20.5, OK);
        push('PR11 b8: no sampled passed second at all withholds (reason missing)', !!m0 && m0.admit === false && m0.reason === 'missing' && m0.nMissing === 40, JSON.stringify(m0));
        const f1 = pr11Exposure({ gapUsd: 66.67, nLock: 40, n: 20, lockedObserved: 40, lockedFilledLive: 1, lockedMean: 65075, index: 65050 }, 65000, 20.5, OK);
        const f2 = pr11Exposure({ gapUsd: 66.67, nLock: 40, n: 20, lockedObserved: 40, lockedFilledLive: 2, lockedMean: 65075, index: 65050 }, 65000, 20.5, OK);
        push('PR11 b9 newest-print substitution: one live-filled print (the newest) is allowed; a second live-filled passed print is missing information and withholds (reason missing, named in the text)', !!f1 && f1.admit === true && f1.nMissing === 0 && !!f2 && f2.admit === false && f2.reason === 'missing' && f2.nMissing === 1 && /valued at the live index beyond the newest print/.test(f2.why), JSON.stringify([f1.admit, f2.reason, f2.nMissing]));
        /* b10: units regression — the exposure is in bps of the CURRENT index (the table's p[t]), never of the strike */
        { const rec = pr11Exposure({ gapUsd: 176.091, nLock: 9, n: 51, lockedObserved: 9, lockedFilledLive: 1, lockedMean: 64880, index: 64883.71 }, 64707.58, 50.906, OK);
          push('PR11 b10 units: the recorded KXBTC15M-26NOV152000-00 second (50.906 s, strike 64707.58, index 64883.71, gap 176.09): R 31.93 bps of the current index < floor 32 -> withheld (the strike denominator read 32.02 and admitted)', !!rec && rec.h === 51 && rec.rstar === 32 && near(rec.R, 31.93, 0.011) && rec.admit === false && rec.reason === 'floor', JSON.stringify([rec.h, rec.R, rec.rstar, rec.admit, rec.reason]));
          const up = pr11Exposure({ gapUsd: 200, nLock: 0, n: 60, lockedObserved: 0, index: 65200 }, 65000, 90.5, OK), dn = pr11Exposure({ gapUsd: -200, nLock: 0, n: 60, lockedObserved: 0, index: 64800 }, 65000, 90.5, OK);
          push('PR11 b10 units: before the minute R = |gap| / index x 1e4 (UP leader above the strike reads below |gap|/strike, DOWN leader below it reads above)', !!up && !!dn && near(up.R, 200 / 65200 * 1e4, 0.0051) && near(dn.R, 200 / 64800 * 1e4, 0.0051) && up.R < 200 / 65000 * 1e4 && dn.R > 200 / 65000 * 1e4 && up.h === 91 && dn.h === 91, JSON.stringify([up.R, dn.R]));
          const in1 = pr11Exposure({ gapUsd: 30, nLock: 1, n: 59, lockedObserved: 1, index: 65100 }, 65000, 59.5, OK), b60 = pr11Exposure({ gapUsd: 30, nLock: 0, n: 60, lockedObserved: 0, index: 65100 }, 65000, 60.0, OK);
          push('PR11 b10 units: inside the minute the index-denominated cushion is scaled by 60/remaining prints (59.5 s: h 59); at exactly 60.0 s no print has passed, h 60, no scaling', !!in1 && in1.h === 59 && near(in1.R, 30 / 65100 * 1e4 * 60 / 59, 0.0051) && !!b60 && b60.h === 60 && near(b60.R, 30 / 65100 * 1e4, 0.0051), JSON.stringify([in1.R, b60.R]));
          const eq = pr11Exposure({ gapUsd: 32 / 1e4 * 65100 * 51 / 60, nLock: 9, n: 51, lockedObserved: 9, index: 65100 }, 65000, 50.9, OK);
          push('PR11 b10 units: exactly at the floor (R = R* = 32 in index units) the call is admitted (floorMet uses >=)', !!eq && eq.h === 51 && near(eq.R, 32, 0.0051) && eq.floorMet === true && eq.admit === true, JSON.stringify([eq.R, eq.floorMet, eq.admit]));
          const nf = pr11Exposure({ gapUsd: 200, nLock: 0, n: 60, lockedObserved: 0, index: NaN }, 65000, 90.5, OK);
          push('PR11 b10 units: with no finite index in the geometry the strike is the fallback denominator (never unit-less)', !!nf && near(nf.R, 200 / 65000 * 1e4, 0.0051), JSON.stringify(nf && nf.R));
          let bad10 = null, cnt10 = 0; const K10 = 65000;
          for (const im of [0.5, 0.9, 1, 1.1, 2]) for (let nl = 1; nl <= 59; nl++) { const n = 60 - nl, lsum = 60 * K10 / (1 - PROVEN_MARGIN_FRAC) * (1 + 1e-9), gap = (lsum + K10 * im * n) / 60 - K10; const ex = pr11Exposure({ gapUsd: gap, nLock: nl, n, lockedObserved: nl, index: K10 * im }, K10, n + 0.25, OK); cnt10++; if (!ex || !ex.floorMet) { bad10 = { im, nl, ex }; break; } }
          push('PR11 b10 units: the PROVEN-margin property holds in index units too — every (prints passed, index 0.5-2x strike) pair at the PROVEN margin meets the floor', bad10 === null && cnt10 === 295, JSON.stringify(bad10)); }
        const big = pr11Exposure({ gapUsd: 2000, nLock: 40, n: 20, lockedObserved: 39, lockedMean: 65075, index: 65050 }, 65000, 20.5, OK);
        push('PR11 b8 deletion property: one unsampled passed second withholds even at R 923 bps (deleting information can never admit)', !!big && big.admit === false && big.reason === 'missing' && big.R > 900, JSON.stringify(big));
        const oNo = pr11Exposure({ gapUsd: 66.67, nLock: 40, n: 20, lockedObserved: 40 }, 65000, 20.5, { ok: false, reasons: ['official BRTI 3000 ms old (limit 2500 ms)'] });
        const oUndef = pr11Exposure({ gapUsd: 66.67, nLock: 40, n: 20, lockedObserved: 40 }, 65000, 20.5);
        const oBefore = pr11Exposure({ gapUsd: 101.69 * 6, nLock: 0, n: 60 }, 68245.46, 91.8, { ok: false, reasons: ['official BRTI feed disabled (BRTI_ENABLE=0)'] });
        push('PR11 b8 official reference: in the settlement minute a stale/invalid/missing official reference withholds (reason official, the panel reason named); an unevaluated reference fails closed; before the minute the reference is not required', !!oNo && oNo.admit === false && oNo.reason === 'official' && /3000 ms old/.test(oNo.why) && oNo.floorMet === true && !!oUndef && oUndef.admit === false && oUndef.reason === 'official' && !!oBefore && oBefore.admit === true && oBefore.officialOk === null, JSON.stringify([oNo.reason, oUndef.reason, oBefore.admit]));
        const gP = { hard: [], soft: [] }; const xP = pr11Gate(gP, { gapUsd: 300, nLock: 3, n: 57, lockedObserved: 3 }, 65000, 56.5, { reference: 'OFFICIAL', officialReasons: [] });
        const gX = { hard: [], soft: [] }; const xX = pr11Gate(gX, { gapUsd: 300, nLock: 3, n: 57, lockedObserved: 3 }, 65000, 56.5, { reference: 'PROXY', officialReasons: ['official settlement accumulator not received for this window'] });
        push('PR11 b8 gate: an expected partial accumulator (panel OFFICIAL, 3 of 60) is fine — with the floor met (46 bps, R 48.6 >= 34) the call is admitted; a PROXY panel in the minute pushes the official-reference gate', PR11_MODE === 'gate' ? (gP.soft.length === 0 && xP.admit === true && gX.soft.length === 1 && /^PR11 official reference unavailable/.test(gX.soft[0]) && xX.reason === 'official') : (gP.soft.length === 0 && gX.soft.length === 0), JSON.stringify([gP.soft, gX.soft]));
        const ordered = pr11Exposure({ gapUsd: 5, nLock: 40, n: 20, lockedObserved: 38 }, 65000, 20.5, { ok: false, reasons: ['x'] });
        push('PR11 b8: every failing requirement is listed (missing, official, floor) and the first is the headline reason', !!ordered && ordered.reasons.join(',') === 'missing,official,floor' && ordered.reason === 'missing', JSON.stringify(ordered.reasons));
        const wm = pr11Apply({ state: 'HIGH CONFIDENCE', side: 'UP', pFlip: 0.0015, pWin: 0.9985, headline: 'HIGH CONFIDENCE', display27: { headline: 'HIGH CONFIDENCE — UP (not locked)', note: null }, projection: { side: 'UP', lockInSec: 2 }, validation: { audit: { n: 366 }, lines: ['x'] }, v28: { value: { veto: 'not LOCKED (HIGH CONFIDENCE)', positive: true }, execution: { ready: true } } }, m4);
        const wo = pr11Apply({ state: 'HIGH CONFIDENCE', side: 'DOWN', pFlip: 0.0015, pWin: 0.9985, headline: 'HIGH CONFIDENCE', display27: { headline: 'HIGH CONFIDENCE — DOWN (not locked)', note: null }, projection: { side: 'DOWN', lockInSec: 2 }, validation: { audit: { n: 366 }, lines: ['x'] }, v28: { value: { veto: null, positive: true }, execution: { ready: true } } }, oNo);
        push('PR11 b8 display (gate mode): the withheld reason is consistent across headline, note, readiness tile, trade-value veto, projection and evidence — samples missing', PR11_MODE === 'gate' ? (wm.pr11.withheld === true && wm.headline === 'LOCKED WITHHELD — SETTLEMENT SAMPLES MISSING' && /4 passed settlement seconds unsampled/.test(wm.display27.headline) && wm.v28.execution.ready === false && /samples missing/.test(wm.v28.execution.reason) && wm.v28.value.veto === 'not LOCKED (settlement samples missing)' && wm.v28.value.positive === false && /every passed settlement second has an index sample/.test(wm.projection.assumption) && /^Settlement-exposure gate \(PR11\): 4 of the 40/.test(wm.validation.lines[0]) && wm.validation.audit === null) : (wm.headline === 'HIGH CONFIDENCE' && wm.v28.execution.ready === true), JSON.stringify({ h: wm.headline, d27: wm.display27.headline, veto: wm.v28.value.veto }));
        push('PR11 b8 display (gate mode): the withheld reason is consistent — official reference unavailable', PR11_MODE === 'gate' ? (wo.pr11.withheld === true && wo.headline === 'LOCKED WITHHELD — OFFICIAL REFERENCE UNAVAILABLE' && /official settlement reference not verifiable/.test(wo.display27.headline) && wo.v28.execution.ready === false && wo.v28.value.veto === 'not LOCKED (official reference unavailable)' && /official settlement reference is valid and current/.test(wo.projection.assumption) && /3000 ms old/.test(wo.validation.lines[0])) : (wo.headline === 'HIGH CONFIDENCE'), JSON.stringify({ h: wo.headline, d27: wo.display27.headline }));
        const pvO = m25Decide({ tau: 10, pUp: 0.9999, pUpCons: 0.9999, gates: { hard: [], soft: ['PR11 official reference unavailable: t'], pr11: ['PR11 official reference unavailable: t'] }, book: null, cfg: m25Cfg(10), provenSide: 'UP' });
        push('PR11 b8: PROVEN LOCKED is withheld by the official-reference and missing-sample requirements too (same path as the floor)', pvO.state === 'HIGH CONFIDENCE' && /LOCKED withheld: PR11 official/.test(pvO.reasons.join(' ')), pvO.state);
        const bf = pr11Exposure({ gapUsd: 101.69, nLock: 0, n: 60, lockedObserved: 0 }, 68245.46, 91.8);
        push('PR11 b8: before the minute (no passed prints) nothing changes (Nov 14 entry: h 92, R 14.9, floor 55)', !!bf && bf.h === 92 && near(bf.R, 14.9, 0.1) && bf.admit === false && bf.nMissing === 0, JSON.stringify(bf)); }
      { let bad = null, cnt = 0; const K = 65000;
        for (const im of [0.5, 0.9, 1, 1.1, 2]) for (let nl = 1; nl <= 59; nl++) { const n = 60 - nl, lsum = 60 * K / (1 - PROVEN_MARGIN_FRAC) * (1 + 1e-9), gap = (lsum + K * im * n) / 60 - K; const ex = pr11Exposure({ gapUsd: gap, nLock: nl, n }, K, n + 0.25, OK); cnt++; if (!ex || !ex.applies || !ex.admit) bad = bad || { im, nl, ex }; }
        const path = pr11Exposure({ gapUsd: 65000 * 0.0025 / (1 - 0.0025), nLock: 1, n: 59 }, 65000, 59.25, OK);
        push('PR11 b6 ⊇ PROVEN: at the PROVEN margin with the live index at or above half the strike, every (prints passed, index) pair meets the floor (R >= 1504/r + 10000·index/strike bps) — the gate changes no realistic PROVEN call; it withholds only the index-near-zero case', bad === null && cnt === 295 && !!path && path.applies === true && path.admit === false, JSON.stringify({ bad, pathological: path && { R: path.R, rstar: path.rstar, admit: path.admit } }));
      }
      const wh = pr11Apply({ state: 'HIGH CONFIDENCE', side: 'UP', pFlip: 0.0019, pWin: 0.9981, headline: 'HIGH CONFIDENCE', display27: { headline: 'HIGH CONFIDENCE — UP (not locked)', note: null }, projection: { side: 'UP', lockInSec: 1.5, assumption: 'index holds at its current level' }, validation: { audit: { n: 366, losses: 5 }, live: null, lines: ['HIGH CONFIDENCE = flip risk ≤ 2% (not LOCKED). Out of sample: 5 of 366 first calls at this level lost (1.37%).'] }, v28: { value: { veto: 'not LOCKED (HIGH CONFIDENCE)', positive: false }, execution: { ready: true, bookFresh: true, depth: 10 } } }, gx);
      push('PR11 display (gate mode): the v2.8 readiness tile is NOT READY and the trade-value veto names the exposure floor while withheld; untouched otherwise',
        PR11_MODE === 'gate' ? (wh.v28.execution.ready === false && wh.v28.execution.withheld === true && wh.v28.value.veto === 'not LOCKED (exposure floor not met)') : (wh.v28.execution.ready === true && wh.v28.value.veto === 'not LOCKED (HIGH CONFIDENCE)'), JSON.stringify(wh.v28));
      push('PR11 display (gate mode): a LOCKED withheld by the floor shows the failed requirement in the headline, note, projection and evidence, with no inherited HIGH CONFIDENCE statistics and no "LOCKED in ~N s" promise; shadow/off leave the display untouched',
        PR11_MODE === 'gate' ? (wh.pr11.withheld === true && /^LOCKED WITHHELD/.test(wh.headline) && /exposure floor not met/.test(wh.display27.headline) && /settlement-exposure gate/.test(wh.guarantee) && wh.projection.lockInSec === null && /stays withheld/.test(wh.projection.assumption) && wh.validation.audit === null && wh.validation.lines.length === 3 && !wh.validation.lines.join(' ').includes('first calls at this level') && wh.pFlip === 0.0019 && wh.state === 'HIGH CONFIDENCE')
          : (wh.pr11.withheld === false && wh.headline === 'HIGH CONFIDENCE' && wh.display27.headline === 'HIGH CONFIDENCE — UP (not locked)' && wh.guarantee === undefined && wh.projection.lockInSec === 1.5 && wh.validation.audit.n === 366), JSON.stringify({ headline: wh.headline, d27: wh.display27.headline, proj: wh.projection, lines: wh.validation.lines.length }));
      const nw = pr11Apply({ state: 'HIGH CONFIDENCE', side: 'UP', pFlip: 0.012, headline: 'HIGH CONFIDENCE', display27: { headline: 'H' }, projection: { side: 'UP', lockInSec: 20 }, validation: { audit: { n: 1 }, lines: ['x'] } }, gx);
      push('PR11 display: a HIGH CONFIDENCE for the model\'s own reason (flip risk above the LOCKED limit) is not rewritten', nw.pr11.withheld === false && nw.headline === 'HIGH CONFIDENCE' && nw.projection.lockInSec === 20 && nw.validation.lines[0] === 'x', JSON.stringify(nw.pr11));
      push('PR11 b6 qualified flag: true only for a served LOCKED/PROVEN LOCKED inside 120 s that meets the floor (false when withheld, beyond 120 s, or in off mode)', in120.pr11.qualified === (PR11_MODE !== 'off') && bey.pr11.qualified === false && wh.pr11.qualified === false && nw.pr11.qualified === false && pvs.pr11.qualified === (PR11_MODE !== 'off'), JSON.stringify([in120.pr11.qualified, bey.pr11.qualified, wh.pr11.qualified, pvs.pr11.qualified]));
      const ap = pr11Apply({ state: 'LOCKED', pFlip: 0.0019, pWin: 0.9981 }, gx);
      push('PR11 apply: the field is carried (off mode: applies false) with the missing-sample count and no probability or state changes', ap.pr11 && (PR11_MODE === 'off' ? ap.pr11.applies === false : (ap.pr11.admit === false && ap.pr11.rstar === 60 && ap.pr11.nMissing === 0)) && ap.pFlip === 0.0019 && ap.state === 'LOCKED' && pr11Apply({ state: 'LOCKED', pFlip: 0.001 }, null).pr11.applies === false, JSON.stringify(ap.pr11));
    }
    push('2.6 recalibration ratios loaded (quiet > 1 > active)',''')
# (e2) full-path self-test: the PR11 gate reaches the PROVEN branch through classify25
X("    const sig = classify25({ now: Date.now(), tau: 30, ticker: 'SELFTEST', closeMs: Date.now() + 30000, strike: 80000, geo, gates: { hard: [], soft: [] }, kal: kalT, contracts: 10, mutate: false });",
  r'''    const sig = classify25({ now: Date.now(), tau: 30, ticker: 'SELFTEST', closeMs: Date.now() + 30000, strike: 80000, geo, gates: { hard: [], soft: [] }, kal: kalT, contracts: 10, mutate: false });
    { const geoP = Object.assign({}, geo, { provenUp: true, pUp: 0.9999, pUpCons: 0.9999 });
      const sP = classify25({ now: Date.now(), tau: 30, ticker: 'SELFTEST', closeMs: Date.now() + 30000, strike: 80000, geo: geoP, gates: { hard: [], soft: ['PR11 settlement samples missing: t'], pr11: ['PR11 settlement samples missing: t'] }, kal: kalT, contracts: 10, mutate: false });
      const sI = classify25({ now: Date.now(), tau: 30, ticker: 'SELFTEST', closeMs: Date.now() + 30000, strike: 80000, geo: geoP, gates: { hard: [], soft: ['volatility estimate warming up'] }, kal: kalT, contracts: 10, mutate: false });
      push('PR11 b8 full path: the PR11 gate reaches the PROVEN branch through classify25 (PROVEN withheld -> HIGH CONFIDENCE / WAIT); another soft gate alone leaves PROVEN LOCKED (I2 behaviour)', sP.state === 'HIGH CONFIDENCE' && sP.trade && sP.trade.action === 'WAIT' && /LOCKED withheld: PR11/.test((sP.reasons || []).join(' ')) && sI.state === 'PROVEN LOCKED', [sP.state, sI.state]); }''')
# (f) exports
X("getKalshiContext: kalshiContext, radar, runSelfTest,", "getKalshiContext: kalshiContext, radar, runSelfTest, pr11Exposure, pr11Gate, pr11Apply, PR11_RSTAR, PR11_MODE, PR11_META,")
# (g) health identity
X("        build: BUILD_ID, fixes: BUILD_FIXES, ingest: INGEST_REV, codeSha256: CODE_SHA256_32,",
  "        build: BUILD_ID, fixes: BUILD_FIXES, ingest: INGEST_REV, codeSha256: CODE_SHA256_32,\n        pr11: { mode: PR11_MODE, tableSha256: PR11_META.tableSha256, declarationSha256: PR11_META.declarationSha256, release: PR11_META.release },")
# (h) configuration hash covers the mode
X('"PORT", "PRED_LOG_FILE",', '"PORT", "PR11_MODE", "PRED_LOG_FILE",')
open(outp, 'w').write(src)
print('written', outp, 'sha256', hashlib.sha256(src.encode()).hexdigest(), 'lines', src.count('\n'), 'table sha', table_sha[:16], 'declaration sha', decl_sha[:16])
