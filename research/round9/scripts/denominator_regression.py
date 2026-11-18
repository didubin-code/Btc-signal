"""Independent arithmetic check of the PR11 exposure units on a chronological dump: recompute R from the engine's own recorded
geometry in the exposure table's units (bps of the CURRENT index, scaled by 60/remaining prints once a print has passed) and compare
with the engine's pr11.R and admission at every second where PR11 applies. Also reports how many admitted/withheld decisions would
flip between the strike and the index denominators. usage: python3 -I denominator_regression.py <chrono.ndjson> <rstar.json> <out.txt> [--engine-uses strike|index]"""
import sys, json, math, collections
f, rf, outp = sys.argv[1:4]; uses = 'index'
if '--engine-uses' in sys.argv: uses = sys.argv[sys.argv.index('--engine-uses') + 1]
RSTAR = {int(k): v for k, v in json.load(open(rf))['rstar'].items()}
c = collections.Counter(); ex = []; flips = []
for l in open(f):
    r = json.loads(l); pr = r.get('pr11') or {}; g = r.get('geo') or {}
    if not pr.get('applies') or g.get('gap') is None or not g.get('index'): continue
    tau = r['tau']; h = min(120, max(1, math.ceil(tau - 1e-9))); scale = 60.0 / h if (g.get('nLock', 0) >= 1 and tau <= 60) else 1.0
    Ri = abs(g['gap']) / g['index'] * 1e4 * scale; Rs = abs(g['gap']) / r['strike'] * 1e4 * scale; Reng = Ri if uses == 'index' else Rs
    c['rows'] += 1
    if pr.get('h') != h: c['h_mismatch'] += 1; ex.append(('h', r['ticker'], tau, pr.get('h'), h))
    if abs((pr.get('R') or 0) - Reng) > 0.0051: c['R_mismatch'] += 1; ex.append(('R', r['ticker'], tau, pr.get('R'), round(Reng, 4)))
    reasons = pr.get('reasons') or []
    floor_eng = pr.get('floorMet')
    if floor_eng is not None and floor_eng != (Reng >= RSTAR[h] - 1e-9): c['floor_mismatch'] += 1; ex.append(('floor', r['ticker'], tau, floor_eng, Reng, RSTAR[h]))
    if (Ri >= RSTAR[h] - 1e-9) != (Rs >= RSTAR[h] - 1e-9): flips.append((r['ticker'], tau, r['state'], round(Rs, 4), round(Ri, 4), RSTAR[h])); c['denominator_flips'] += 1
out = ['denominator regression on %s (engine declared to use the %s denominator): rows with PR11 applied %d | h mismatches %d | R mismatches (> 0.005) %d | floor-decision mismatches %d' % (f.split('/')[-1], uses, c['rows'], c['h_mismatch'], c['R_mismatch'], c['floor_mismatch'])]
out.append('decisions where the strike and index denominators disagree on the floor: %d' % c['denominator_flips'])
for x in flips[:20]: out.append('  flip: %s tau %.3f state %s R_strike %.4f R_index %.4f floor %d' % x)
for x in ex[:20]: out.append('  mismatch: ' + ' '.join(str(v) for v in x))
open(outp, 'w').write('\n'.join(out) + '\n'); print('\n'.join(out[:3]))
