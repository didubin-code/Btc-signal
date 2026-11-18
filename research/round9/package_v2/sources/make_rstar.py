"""Frozen threshold tables R*(h), h = 1..120, from the full per-horizon exceedance table: the smallest integer R (bps) with Q_all(R,h) <= theta,
Q two-sided over 2023-10-02..2026-09-01. Writes rstar_<theta>.json with the table, its provenance and per-year Q at the chosen R.
usage: python3 -I make_rstar.py <q_full.json> <outdir>"""
import sys, json, hashlib, os
d = json.load(open(sys.argv[1])); od = sys.argv[2]; H = d['H']; ex = d['exceed']; tot = d['totals']
for theta, name in ((0.002, '0.200'), (0.001, '0.100'), (0.0005, '0.050'), (0.00025, '0.025')):
    tab = {}; peryear = {}
    for h in H:
        e = ex['%d|all' % h]; n = tot['%d|all' % h]; R = next(R for R in range(len(e)) if e[R] <= theta * n); tab[h] = R
        peryear[h] = {y: (ex['%d|%s' % (h, y)][R] / tot['%d|%s' % (h, y)]) for y in ('y2023', 'y2024', 'y2025', 'y2026')}
    # enforce monotone non-decreasing in h (the settlement mean over a longer horizon cannot be safer); record any adjustment
    adj = []
    for h in H[1:]:
        if tab[h] < tab[h - 1]: adj.append((h, tab[h], tab[h - 1])); tab[h] = tab[h - 1]
    out = {'theta_two_sided': theta, 'source': os.path.basename(sys.argv[1]), 'from': d['from'], 'to': d['to'], 'seconds': tot['1|all'],
           'definition': 'R*(h) = smallest integer R (bps of price) such that the fraction of seconds t in the source period with |mean(settlement-type prints over horizon h) - p[t]| / p[t] >= R bps is <= theta; h <= 60: mean of the next h prints; h > 60: mean of the 60 prints ending at t + h; monotone non-decreasing in h enforced',
           'monotone_adjustments': adj, 'rstar': {str(h): tab[h] for h in H}, 'q_at_rstar_by_year': {str(h): peryear[h] for h in H}}
    p = os.path.join(od, 'rstar_%s.json' % name); json.dump(out, open(p, 'w'), indent=0, sort_keys=True)
    print('theta %s%%: %s sha256 %s | R*(h) h=1 %d, 5 %d, 10 %d, 20 %d, 30 %d, 45 %d, 60 %d, 75 %d, 90 %d, 105 %d, 120 %d | adjustments %s' % (name, os.path.basename(p), hashlib.sha256(open(p, 'rb').read()).hexdigest(), tab[1], tab[5], tab[10], tab[20], tab[30], tab[45], tab[60], tab[75], tab[90], tab[105], tab[120], adj))
