#!/usr/bin/env python3
"""Test the monitoring evaluator (monitor_rules.py) against build 6's own payloads and rendered page, then against deliberately invalid
behaviour (fault injections: mutated rows, mutated payloads, and renders produced by the superseded builds 3, 4 and 5).
Valid behaviour must produce no violation; every injected fault must be detected by the named check. usage: monitor_selftest.py <render dir>"""
import sys, json, os, copy
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from monitor_rules import row_violations, display_violations, row_from_signal
RD = sys.argv[1]
def load(name):
    p = json.load(open(os.path.join(RD, 'payload_%s.json' % name)))
    t = json.load(open(os.path.join(RD, 'render_%s.texts.json' % name)))
    v = json.load(open(os.path.join(RD, 'render_%s.v28.json' % name)))
    return p['signal'], t, v, p
VALID = [('admitted LOCKED inside 120 s (53.6 s, R 34.3 >= 33)', 'nov15_2100_admitted'), ('withheld LOCKED (Nov 14 entry second, 91.8 s, R 14.9 < 55)', 'nov14_withheld'),
         ('withheld at the 120-s transition (119.5 s, R 36.7 < 68)', 'nov15_1945_in120'), ('conditional PROVEN LOCKED (synthetic strike, 3.6 s)', 'proven_conditional'),
         ('LOCKED beyond 120 s, NOT YET GATED (121.5 s, DO NOT TRADE)', 'nov15_1945_beyond'), ('LOCKED beyond 120 s, NOT YET GATED with TRADE NOW (219.7 s, live decision)', 'beyond_tradenow'),
         ('warm-up: HIGH CONFIDENCE by the volatility warm-up gate, PR11 admits (53.6 s)', 'warmup'), ('stale input: DATA UNRELIABLE by the input-age hard gate (53.6 s)', 'stale')]
ok = True; print('== VALID BEHAVIOUR (build 6) — must pass'); 
for label, name in VALID:
    sig, t, v, p = load(name); row = row_from_signal(sig, p.get('ts'))
    rv = row_violations(row, 0); dv = display_violations(sig, t, v)
    status = 'PASS' if not rv and not dv else 'FAIL'
    if status == 'FAIL': ok = False
    print('%s  %-78s state %-16s pr11 admit=%s qualified=%s withheld=%s gates soft/hard %d/%d action %s%s' % (status, label, sig['state'], (sig.get('pr11') or {}).get('admit'), (sig.get('pr11') or {}).get('qualified'), (sig.get('pr11') or {}).get('withheld'), row['gatesSoft'], row['gatesHard'], row['action'], ('  -> ' + json.dumps(rv + dv)) if (rv or dv) else ''))
print('\n== FAULT INJECTIONS — each must be detected by the named check')
def expect(label, got_codes, want):
    global ok
    got = set(c for c, _ in got_codes); hit = all(any(g == w or g.startswith(w) for g in got) for w in want)
    if not hit: ok = False
    print('%s  %-78s detected %s (wanted %s)' % ('DETECTED' if hit else 'MISSED  ', label, sorted(got) or '-', want))
sigA, tA, vA, pA = load('nov15_2100_admitted'); sigW, tW, vW, pW = load('nov14_withheld'); sigU, tU, vU, pU = load('warmup')
r = row_from_signal(sigA, pA['ts']); r['pr11Admit'] = False; expect('I1 row: admitted LOCKED row with pr11Admit forced false', row_violations(r, 0), ['C1'])
r = row_from_signal(sigU, pU['ts']); r['gatesSoft'] = 0; r['gatesHard'] = 0; expect('I1 row: warm-up HIGH (0.5 %% limit met, admitted) with its soft gate removed', row_violations(r, 0), ['C1b'])
r = row_from_signal(sigU, pU['ts']); expect('I1 control: the real warm-up row (soft gate present) is NOT flagged', [('none', '')] if not row_violations(r, 0) else row_violations(r, 0), ['none'])
r = row_from_signal(sigA, pA['ts']); r['pr11Admit'] = None; expect('I3 row: admitted LOCKED row with the pr11Admit field removed (new build)', row_violations(r, 1), ['C2'])
r = row_from_signal(sigW, pW['ts']); r['action'] = 'TRADE NOW'; expect('I2 row: withheld HIGH row with action forced TRADE NOW', row_violations(r, 0), ['C3'])
r = row_from_signal(sigA, pA['ts']); r['tau'] = 125; r['pr11Admit'] = False; expect('scope control: LOCKED beyond 120 s with pr11Admit false is NOT a C1 (gate does not apply)', [('none', '')] if not row_violations(r, 0) else row_violations(r, 0), ['none'])
for label, name, want in [('I2 display: build 3 withheld render (v2.8 tiles before the build-4 fix)', 'fault_b3_withheld', ['D-withheld']),
                          ('I2 display: build 4 LOCKED beyond 120 s (no NOT YET GATED label)', 'fault_b4_beyond', ['D-scope-head']),
                          ('I2 display: build 5 PROVEN LOCKED (MATHEMATICALLY FINAL headline and tile)', 'fault_b5_proven', ['D-proven-head', 'D-proven-designation']),
                          ('I2 display: build 6 withheld payload with TRADE NOW injected', 'fault_b6_withheld_tradenow', ['D-trade', 'D-ring']),
                          ('I2 display: build 6 withheld payload with READY tile and positive value injected', 'fault_b6_withheld_ready', ['D-withheld-ready', 'D-withheld-value'])]:
    sig, t, v, p = load(name); expect(label, display_violations(sig, t, v), want)
sig = copy.deepcopy(sigW); sig['pr11']['withheld'] = False; expect('field consistency: declared pr11.withheld false while the call is withheld', display_violations(sig, tW, vW), ['D-field'])
sig = copy.deepcopy(sigA); sig['pr11']['qualified'] = False; expect('field consistency: declared pr11.qualified false on an admitted LOCKED', display_violations(sig, tA, vA), ['D-field'])
print('\nMONITOR SELFTEST', 'PASS' if ok else 'FAIL'); sys.exit(0 if ok else 1)
