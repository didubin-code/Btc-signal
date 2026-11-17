"""D3 validation: (a) the I2 file replayed by the recorded-state restore reproduces what the server served;
(b) the build-9 engine differs from the served state only at PR11-withheld LOCKED seconds; (c) the offline rule
on recorded fields (gap, tau, reference) agrees with the build-9 engine's own admission, and where not, why.
usage: python3 -I validate_d3.py <I2 dumps comma> <B9 dumps comma> <rstar.json> <out.txt>"""
import sys, json, math, collections
I2F, B9F, RF, OUTP = sys.argv[1].split(','), sys.argv[2].split(','), sys.argv[3], sys.argv[4]
RSTAR = {int(k): v for k, v in json.load(open(RF))['rstar'].items()}
out = []; P = out.append
def key(o): return (o.get('state'), o.get('side'), round(o.get('pFlip') or 0, 6)) if o else None
tot = collections.Counter(); reasons = collections.Counter(); dis = []; perwin = collections.defaultdict(lambda: collections.Counter())
for fi, fb in zip(I2F, B9F):
    I = [json.loads(l) for l in open(fi)]; B = [json.loads(l) for l in open(fb)]
    assert len(I) == len(B)
    for a, b in zip(I, B):
        assert a['ts'] == b['ts'] and a['ticker'] == b['ticker']
        tot['rows'] += 1; live = a['live'] or {}
        if key(live) == key(a): tot['i2_parity'] += 1
        else: tot['i2_mismatch'] += 1
        tau = a['tau']; lockedLive = live.get('state') in ('LOCKED', 'PROVEN LOCKED'); lockedB = b['state'] in ('LOCKED', 'PROVEN LOCKED')
        if key(live) == key(b): tot['b9_same_as_served'] += 1
        elif lockedLive and not lockedB and b.get('pr11') and b['pr11'].get('reason'): tot['b9_withheld'] += 1; reasons[b['pr11']['reason']] += 1; perwin[a['ticker']][b['pr11']['reason']] += 1
        elif lockedLive and not lockedB: tot['b9_withheld_other'] += 1; dis.append(('withheld-no-reason', a['ticker'], tau, b['state'], b.get('soft')))
        else: tot['b9_other_mismatch'] += 1; dis.append(('other', a['ticker'], tau, key(live), key(b)))
        # offline rule on the engine's own recorded fields vs the engine's admission (LOCKED seconds inside 120 s)
        if lockedLive and 0 < tau <= 120:
            g = b['geo']; cushion = abs(g['gap']) / b['strike'] * 1e4; h = min(120, max(1, math.ceil(tau - 1e-9))); R = cushion * 60.0 / h if h <= 59 else cushion
            floor_ok = R >= RSTAR[h] - 1e-9; official_ok = (b['ref'] == 'OFFICIAL') if tau <= 60 else True; recon = floor_ok and official_ok
            tot['rule_rows'] += 1
            if recon == lockedB: tot['rule_agree'] += 1
            else:
                tot['rule_disagree'] += 1; pr = b.get('pr11') or {}
                dis.append(('rule', a['ticker'], tau, 'recon_admit' if recon else 'recon_withhold', 'engine_locked' if lockedB else 'engine_withheld:' + str(pr.get('reason')), 'R %.2f R* %s h %d engine h %s R %s nMissing %s filledLive %s' % (R, RSTAR[h], h, pr.get('h'), pr.get('R'), pr.get('nMissing'), g.get('filledLive'))))
P('D3 rows %d | I2 replay parity with the served state: %d of %d (mismatch %d)' % (tot['rows'], tot['i2_parity'], tot['rows'], tot['i2_mismatch']))
P('build 9 vs served: identical %d; LOCKED withheld by PR11 %d (reasons %s); withheld without a PR11 reason %d; other differences %d' % (tot['b9_same_as_served'], tot['b9_withheld'], dict(reasons), tot['b9_withheld_other'], tot['b9_other_mismatch']))
P('offline rule (gap, tau, reference) vs engine admission at served-LOCKED seconds inside 120 s: agree %d of %d, disagree %d' % (tot['rule_agree'], tot['rule_rows'], tot['rule_disagree']))
for d in dis[:40]: P('  ' + ' | '.join(str(x) for x in d))
P('per window withheld reasons: ' + json.dumps({k: dict(v) for k, v in perwin.items()}))
open(OUTP, 'w').write('\n'.join(out) + '\n'); print('\n'.join(out[:6]))
