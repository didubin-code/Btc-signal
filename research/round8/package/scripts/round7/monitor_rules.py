#!/usr/bin/env python3
"""PR11 monitoring evaluator — the one code path used by window_check.sh (live rows), monitor_selftest.py (fixtures and fault injections)
and the attended reviews (rendered page). Rules are the release plan's I1–I3 evidence, written as code.
ROW RULES (a row = /predictions or /tape decision row: ts, ticker, tau, state, side, pFlip, action, pr11Admit, gatesSoft, gatesHard):
  C1  served LOCKED/PROVEN LOCKED, 0 < tau <= 120, pr11Admit false                          -> I1 gate violation
  C1b served HIGH CONFIDENCE, flip risk <= LOCK_MAX_FLIP (0.5 %), 0 < tau <= 120, pr11Admit true, gatesSoft == 0 AND gatesHard == 0
      -> I1: LOCKED withheld with no reason at all. Legitimate reasons for a HIGH CONFIDENCE at or below the LOCKED limit are exactly the
      soft gates (volatility warm-up, >300 s, volatility range, dispersion, quality degraded, official divergence, official flip risk,
      PR11 floor); hard gates give DATA UNRELIABLE, an official reversal gives REVERSAL WARNING, tau <= 0 gives AWAITING SETTLEMENT; a flip
      risk above 0.5 % is HIGH legitimately. The rule needs the gate counts (present in /predictions rows); rows without them are not judged.
  C2  served LOCKED/PROVEN LOCKED, 0 < tau <= 120, no pr11Admit field, row from the new build        -> I3 row/field defect
  C3  action TRADE NOW while the state is not LOCKED/PROVEN LOCKED                                     -> I2 contradictory instruction
DISPLAY RULES (sig = the served signal, texts = the rendered page's call panel, v28 = the v2.8 tiles):
  withheld (gate mode, state HIGH CONFIDENCE, PR11 applies and does not admit, flip risk <= 0.5 %): headline must say LOCKED WITHHELD; no
      green ring or pulse, no TRADE NOW, no READY tile, no positive trade value, no inherited statistics, no "LOCKED in ~N s" projection,
      evidence must start with the failed requirement.
  beyond 120 s (gate mode, state LOCKED, tau > 120): headline must say NOT YET GATED, note must say the gate has not assessed the call,
      evidence must say so. ALLOWED there: the green ring, the READY tile and TRADE NOW — they follow I2's policy, which PR11 leaves
      unchanged beyond 120 s by the owner's decision (smallest presentation correction, no extension of the table). This is stated, not hidden.
  admitted (gate mode, state LOCKED, 0 < tau <= 120): PR11 must admit and mark qualified; no WITHHELD or NOT YET GATED label.
  PROVEN LOCKED (gate mode): headline CONDITIONAL, note and designation "not a settlement certainty", no MATHEMATICALLY FINAL, qualified.
  DATA UNRELIABLE: headline DATA UNRELIABLE; HIGH CONFIDENCE not withheld by PR11: no WITHHELD label.
  always: TRADE NOW and the green/pulse panel only with state LOCKED/PROVEN LOCKED; declared pr11.withheld/qualified must equal the derived values.
  The READY tile is I2's execution-conditions indicator (shown for any state when the book is fresh and deep enough); it is forbidden only
  beside a PR11-withheld call, where the build forces it off."""
import sys, json, os, argparse
LOCK_MAX_FLIP = 0.005
LOCKED_STATES = ('LOCKED', 'PROVEN LOCKED')
def row_violations(r, build_from_ms=0):
    v = []
    st, tau, pf, act = r.get('state'), r.get('tau'), r.get('pFlip'), r.get('action')
    adm = r.get('pr11Admit', None); soft = r.get('gatesSoft'); hard = r.get('gatesHard'); ts = r.get('ts') or 0
    locked = st in LOCKED_STATES
    if act == 'TRADE NOW' and not locked: v.append(('C3', 'TRADE NOW while the state is %s' % st))
    if tau is not None and 0 < tau <= 120:
        if locked:
            if adm is False: v.append(('C1', 'served %s inside 120 s with pr11Admit false' % st))
            elif adm is None and ts >= build_from_ms: v.append(('C2', 'served %s inside 120 s without the pr11Admit field' % st))
        if st == 'HIGH CONFIDENCE' and pf is not None and pf <= LOCK_MAX_FLIP and adm is True and soft == 0 and hard == 0 and ts >= build_from_ms:
            v.append(('C1b', 'HIGH CONFIDENCE at flip risk %.4f with pr11Admit true and no soft or hard gate: LOCKED withheld without a reason' % pf))
    return v
def row_counts(rows, build_from_ms=0):
    c = {'rows': len(rows), 'locked120': 0, 'proven120': 0, 'qualified120': 0, 'withheld120': 0, 'withheld120_le02': 0, 'dataUnreliable': 0, 'tradeNow': 0, 'C1': 0, 'C1b': 0, 'C2': 0, 'C3': 0}
    ex = []
    for r in rows:
        st, tau, adm, pf, act = r.get('state'), r.get('tau'), r.get('pr11Admit', None), r.get('pFlip'), r.get('action')
        if st == 'DATA UNRELIABLE': c['dataUnreliable'] += 1
        if act == 'TRADE NOW': c['tradeNow'] += 1
        if tau is not None and 0 < tau <= 120:
            if st in LOCKED_STATES:
                c['locked120'] += 1
                if st == 'PROVEN LOCKED': c['proven120'] += 1
                if adm is True: c['qualified120'] += 1
            if st == 'HIGH CONFIDENCE' and pf is not None and pf <= LOCK_MAX_FLIP and adm is False:
                c['withheld120'] += 1
                if pf <= 0.002: c['withheld120_le02'] += 1
        for code, why in row_violations(r, build_from_ms):
            c[code] += 1
            if len(ex) < 10: ex.append({'code': code, 'ticker': r.get('ticker'), 'tau': tau, 'state': st, 'why': why})
    return c, ex
def row_from_signal(sig, ts=None):
    pr = sig.get('pr11') or {}; g = sig.get('gates') or {}
    return {'ts': ts or sig.get('ts'), 'ticker': sig.get('ticker'), 'tau': sig.get('tau'), 'state': sig.get('state'), 'side': sig.get('side'), 'pFlip': sig.get('pFlip'),
            'action': (sig.get('trade') or {}).get('action'), 'pr11Admit': pr.get('admit') if pr.get('applies') else None,
            'gatesSoft': len(g.get('soft') or []), 'gatesHard': len(g.get('hard') or [])}
def display_violations(sig, texts, v28):
    texts = texts.get('texts', texts) if isinstance(texts, dict) else {}; v28 = v28 or {}
    st = sig.get('state'); pr = sig.get('pr11') or {}; tau = sig.get('tau'); pf = sig.get('pFlip')
    head = texts.get('callHead') or ''; cls = texts.get('callClass') or ''; tact = texts.get('tradeAct') or ''; note = texts.get('callNote') or ''
    valid = texts.get('valid') or ''; proj = texts.get('proj') or ''; dz = v28.get('v28dz') or ''; xcls = v28.get('v28xClass'); vcls = v28.get('v28vClass')
    gate = pr.get('mode') == 'gate'; locked = st in LOCKED_STATES
    derived_withheld = bool(gate and st == 'HIGH CONFIDENCE' and pr.get('applies') and pr.get('admit') is False and pf is not None and pf <= LOCK_MAX_FLIP)
    derived_qualified = bool(pr.get('applies') and pr.get('admit') and locked)
    v = []
    if tact == 'TRADE NOW' and not locked: v.append(('D-trade', 'TRADE NOW shown while the state is %s' % st))
    if cls in ('call locked', 'call trade') and not locked: v.append(('D-ring', 'green or pulsing call panel while the state is %s' % st))
    if 'withheld' in pr and bool(pr.get('withheld')) != derived_withheld: v.append(('D-field', 'pr11.withheld %s but derived %s' % (pr.get('withheld'), derived_withheld)))
    if 'qualified' in pr and bool(pr.get('qualified')) != derived_qualified: v.append(('D-field', 'pr11.qualified %s but derived %s' % (pr.get('qualified'), derived_qualified)))
    if derived_withheld:
        if 'LOCKED WITHHELD' not in head: v.append(('D-withheld-head', 'PR11-withheld call without the LOCKED WITHHELD headline: %r' % head))
        if xcls == 'g': v.append(('D-withheld-ready', 'READY tile beside a withheld call'))
        if vcls == 'g': v.append(('D-withheld-value', 'positive trade value beside a withheld call'))
        if 'first calls at this level' in valid or 'Backtest record' in valid or 'first LOCKED calls lost' in valid: v.append(('D-withheld-stats', 'inherited statistics beside a withheld call'))
        if 'LOCKED' in proj and 'in ~' in proj: v.append(('D-withheld-proj', '"LOCKED in ~N s" projection beside a withheld call'))
        if not valid.startswith('Settlement-exposure gate (PR11)'): v.append(('D-withheld-evidence', 'withheld call whose evidence does not start with the failed requirement'))
    if gate and st == 'LOCKED' and tau is not None and tau > 120:
        if 'NOT YET GATED' not in head: v.append(('D-scope-head', 'LOCKED beyond 120 s without the NOT YET GATED headline: %r' % head))
        if 'has not assessed' not in note: v.append(('D-scope-note', 'LOCKED beyond 120 s without the scope note'))
        if 'not applied beyond 120 s' not in valid: v.append(('D-scope-evidence', 'LOCKED beyond 120 s without the scope evidence line'))
    if gate and st == 'LOCKED' and tau is not None and 0 < tau <= 120:
        if pr.get('applies') and not pr.get('admit'): v.append(('D-served-unadmitted', 'LOCKED served inside 120 s that PR11 does not admit'))
        if 'NOT YET GATED' in head or 'WITHHELD' in head: v.append(('D-label', 'scope or withheld label on an admitted LOCKED'))
        if 'PREDICTED LOCKED' not in head: v.append(('D-admitted-head', 'admitted LOCKED without the PREDICTED LOCKED headline: %r' % head))
    if gate and st == 'PROVEN LOCKED':
        if 'CONDITIONAL' not in head: v.append(('D-proven-head', 'PROVEN LOCKED without CONDITIONAL in the headline: %r' % head))
        if 'not a settlement certainty' not in note: v.append(('D-proven-note', 'PROVEN LOCKED call note without "not a settlement certainty"'))
        if 'MATHEMATICALLY FINAL' in dz or 'not a settlement certainty' not in dz: v.append(('D-proven-designation', 'PROVEN LOCKED designation tile: %r' % dz[:80]))
        if 'PROVEN LOCKED (conditional)' not in valid: v.append(('D-proven-evidence', 'PROVEN LOCKED without the conditional evidence line'))
        if not derived_qualified: v.append(('D-proven-unqualified', 'PROVEN LOCKED served without meeting the floor'))
    if st == 'DATA UNRELIABLE' and 'DATA UNRELIABLE' not in head: v.append(('D-data-head', 'DATA UNRELIABLE without its headline: %r' % head))
    if st == 'HIGH CONFIDENCE' and not derived_withheld:
        if 'LOCKED WITHHELD' in head: v.append(('D-high-mislabel', 'WITHHELD label on a HIGH CONFIDENCE that PR11 did not withhold'))
        if 'HIGH CONFIDENCE' not in head: v.append(('D-high-head', 'HIGH CONFIDENCE without its headline: %r' % head))
    return v
def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--rows'); ap.add_argument('--build-from', type=int, default=0); ap.add_argument('--out'); ap.add_argument('--verify-line', default=''); ap.add_argument('--http', default='200'); ap.add_argument('--stamp', default=''); ap.add_argument('--in-window', default='0')
    a = ap.parse_args(); rows = []
    if a.rows and os.path.exists(a.rows) and a.http == '200':
        for l in open(a.rows):
            l = l.strip()
            if not l: continue
            try: rows.append(json.loads(l))
            except Exception: pass
    rows.sort(key=lambda r: r.get('ts', 0))
    c, ex = row_counts(rows, a.build_from)
    if rows and a.out: open(os.path.join(a.out, 'pred_cursor'), 'w').write(str(rows[-1]['ts'] + 1))
    flags = [k for k in ('C1', 'C1b', 'C2', 'C3') if c[k]]
    vp = a.verify_line.split(' VERIFY ')
    if len(vp) < 2 or not vp[1].startswith('PASS'): flags.append('MONITORING UNAVAILABLE: identity check ' + (vp[1][:60] if len(vp) > 1 else 'failed'))
    if a.http != '200': flags.append('MONITORING UNAVAILABLE: rows HTTP ' + a.http)
    elif a.in_window == '1' and not rows: flags.append('MONITORING UNAVAILABLE: no rows inside a window\'s final 300 s')
    line = '%s WINDOW CHECK | %s | rows %d (locked120 %d, proven120 %d, qualified120 %d, withheld120 %d [<=0.2%%: %d], data-unreliable %d, trade-now %d) | C1 %d C1b %d C2 %d C3 %d | %s' % (
        a.stamp, a.verify_line.split(' | ')[0], c['rows'], c['locked120'], c['proven120'], c['qualified120'], c['withheld120'], c['withheld120_le02'], c['dataUnreliable'], c['tradeNow'], c['C1'], c['C1b'], c['C2'], c['C3'], ('FLAGS ' + ','.join(flags)) if flags else ('clean' if rows else 'no rows this interval (outside a window\'s final 300 s): nothing judged'))
    if a.out: open(os.path.join(a.out, 'STATUS_WINDOW.txt'), 'a').write(line + '\n')
    print(line)
    if ex: print('EXAMPLES', json.dumps(ex[:5]))
    if flags:
        if a.out: open(os.path.join(a.out, 'FLAG'), 'a').write(line + '\n' + json.dumps(ex[:10]) + '\n')
        sys.exit(3)
if __name__ == '__main__': main()
