"""R5-2: the exact production engine on replay inputs (usdc_12 trace, Binance BTCUSDC proxy) versus the live engine on live inputs
(production /predictions rows), second by second, on the common windows. usage: python3 -I rowcompare.py <trace.ndjson.gz> <rows dir> <markets dir> <out.txt>"""
import sys, json, gzip, glob, os, math, collections, statistics as st
tr, rowsdir, mkdir, outp = sys.argv[1:5]
rep = collections.defaultdict(dict)
with gzip.open(tr, 'rt') as f:
    for l in f:
        r = json.loads(l); rep[r['tk']][int(math.floor(r['tau']))] = r
live = {}; truth = {}
for p in glob.glob(rowsdir + '/*.ndjson'):
    tk = os.path.basename(p)[:-7]
    if tk not in rep: continue
    m = json.load(open(mkdir + '/' + tk + '.json')) if os.path.exists(mkdir + '/' + tk + '.json') else {}
    truth[tk] = 'UP' if m.get('result') == 'yes' else 'DOWN' if m.get('result') == 'no' else None
    d = {}
    for l in open(p):
        if not l.strip(): continue
        r = json.loads(l); s = int(math.floor(r['tau']))
        if s not in d: d[s] = r      # first row of each second
    live[tk] = d
common = sorted(set(live) & set(rep)); isL = lambda s: s in ('LOCKED', 'PROVEN LOCKED')
out = []; P = out.append
P('ROW-BY-ROW: common windows %d (replay chunk usdc_12, engine I2 == engine P exactly; live rows from production)' % len(common))
BINS = [('90-120', 90, 120), ('60-89', 60, 89), ('30-59', 30, 59), ('1-29', 1, 29)]
for lab, lo, hi in BINS:
    ratios = []; sigr = []; gapd = []; le = re_ = both = 0; bk_same = n = 0; cush_l = []; cush_r = []
    for tk in common:
        for s in range(lo, hi + 1):
            a = live[tk].get(s); b = rep[tk].get(s)
            if not a or not b: continue
            n += 1
            pa, pb = a.get('pFlip'), b.get('pf')
            if pa and pb and pa > 0 and pb > 0: ratios.append(pb / pa)
            if a.get('sigma') and b.get('sig'): sigr.append(b['sig'] / (a['sigma'] / 1.03))
            if a.get('gap') is not None and b.get('gap') is not None and a.get('strike'): gapd.append((b['gap'] + (b.get('mu') or 0)) - a['gap'])
            if a.get('regime') == b.get('bk'): bk_same += 1
            el = isL(a.get('state')) and pa is not None and pa <= 0.002; er = isL(b.get('st')) and pb is not None and pb <= 0.002
            le += el and not er; re_ += er and not el; both += el and er
    ratios.sort(); sigr.sort(); gapd.sort()
    q = lambda v, p: v[int(p * (len(v) - 1))] if v else float('nan')
    P('  bin %-7s seconds %6d | pf replay/live median %.2f (p10 %.2f, p90 %.2f) | raw sigma replay/live median %.3f (p10 %.3f p90 %.3f) | cushion(replay: gap+mu) - gap(live) USD median %+.1f (p10 %+.1f p90 %+.1f) | same bucket %.0f %% | entry-eligible seconds: both %d, live only %d, replay only %d' % (
        lab, n, q(ratios, .5), q(ratios, .1), q(ratios, .9), q(sigr, .5), q(sigr, .1), q(sigr, .9), q(gapd, .5), q(gapd, .1), q(gapd, .9), 100 * bk_same / max(1, n), both, le, re_))
# entries at [90,120]
def first_entry(d, keyst, keypf, lo=1, hi=120):
    for s in range(hi, lo - 1, -1):
        r = d.get(s)
        if r and isL(r.get(keyst)) and r.get(keypf) is not None and r[keypf] <= 0.002: return s, r
    return None, None
P(''); P('ENTRIES (exact rule, first eligible second in the final 120 s):')
cnt = collections.Counter(); lo_examples = []
for tk in common:
    sl, rl = first_entry(live[tk], 'state', 'pFlip'); sr, rr = first_entry(rep[tk], 'st', 'pf')
    l90 = sl is not None and sl >= 90; r90 = sr is not None and sr >= 90
    cnt['live entry'] += sl is not None; cnt['replay entry'] += sr is not None
    cnt['live [90,120]'] += l90; cnt['replay [90,120]'] += r90; cnt['both [90,120]'] += l90 and r90
    cnt['live [90,120], replay later (<90)'] += l90 and sr is not None and sr < 90; cnt['live [90,120], replay never'] += l90 and sr is None
    cnt['replay [90,120], live later'] += r90 and sl is not None and sl < 90; cnt['replay [90,120], live never'] += r90 and sl is None
    if l90 and not r90:
        b = rep[tk].get(sl) or {}
        lo_examples.append('%s live s=%d pf %.4f sigma %.3f gap %+.0f bk %s | replay at that second: st %s pf %s sig %s gap %s mu %s bk %s | replay first entry %s | result %s' % (tk[-14:], sl, rl['pFlip'], rl.get('sigma') or 0, rl.get('gap') or 0, rl.get('regime'), b.get('st'), b.get('pf'), b.get('sig'), b.get('gap'), b.get('mu'), b.get('bk'), sr, truth.get(tk)))
    if l90 and truth.get(tk) and rl['side'] != truth[tk]: cnt['live [90,120] LOST'] += 1
    if r90 and truth.get(tk) and rr['side'] != truth[tk]: cnt['replay [90,120] LOST'] += 1
for k, v in cnt.items(): P('  %s: %d' % (k, v))
P('  live [90,120] entries that are NOT replay [90,120] entries (first 25):'); out.extend('    ' + x for x in lo_examples[:25])
open(outp, 'w').write('\n'.join(out) + '\n'); print('\n'.join(out))
