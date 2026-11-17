"""PR11 on the live production rows with executable offers from the tape books.
Rule (frozen in PR11_DECLARATION.md): at each second in the final 120 s the engine is LOCKED/PROVEN LOCKED with pFlip <= 0.002 (exact) or < 0.0025
(displayed), h = 60 - n if n >= 1 else ceil(tau) (capped 1..120), R = |gap|/strike*1e4 * (60/(60-n) if n >= 1 else 1); admitted iff R >= RSTAR[h].
Executable: the newest tape book received at most 3000 ms before the row (obTs), best ask on the called side <= 99.9 c with size >= 10 contracts.
Reports per window: baseline first LOCKED second (exact) and its offer; PR11 first admitted second and its offer; PR11 first admitted AND executable
second; outcomes. usage: python3 -I live_exec.py <rstar.json> <rows dir> <markets dir> <tape_all.ndjson> <out.txt>"""
import sys, json, glob, os, math, collections, bisect
rstar_f, rowsdir, mkdir, tape, outp = sys.argv[1:6]
RST = json.load(open(rstar_f)); RSTAR = {int(k): v for k, v in RST['rstar'].items()}
books = collections.defaultdict(list)
for l in open(tape):
    try: r = json.loads(l)
    except Exception: continue
    if r.get('k') != 'd' or not r.get('ob') or not r.get('kal'): continue
    books[r['kal']['ticker']].append((r.get('obTs') or r['ts'], r['ob']))
for tk in books: books[tk].sort()
BT = {tk: [b[0] for b in B] for tk, B in books.items()}
def offer(tk, ts, side):
    B = books.get(tk)
    if not B: return None
    i = bisect.bisect_right(BT[tk], ts) - 1
    if i < 0 or ts - B[i][0] > 3000: return None
    ob = B[i][1]; other = ob.get('no') if side == 'UP' else ob.get('yes')
    lv = sorted(((round(100 - p, 2), s) for p, s in (other or []) if s > 0), key=lambda x: x[0])
    return {'ask': lv[0][0] if lv else None, 'size': lv[0][1] if lv else 0, 'age': ts - B[i][0]}
def execok(o): return o is not None and o['ask'] is not None and o['ask'] <= 99.9 and o['size'] >= 10
def hR(r):
    n = r.get('n') or 0; tau = r['tau']
    if n >= 1 and tau <= 60:
        h = max(1, 60 - n); R = abs(r['gap']) / r['strike'] * 1e4 * 60.0 / h
    else:
        h = min(120, max(1, math.ceil(tau - 1e-9))); R = abs(r['gap']) / r['strike'] * 1e4
    return h, R
res = []
for p in sorted(glob.glob(rowsdir + '/*.ndjson')):
    tk = os.path.basename(p)[:-7]; mp = mkdir + '/' + tk + '.json'
    if not os.path.exists(mp): continue
    m = json.load(open(mp))
    if m.get('result') not in ('yes', 'no'): continue
    truth = 'UP' if m['result'] == 'yes' else 'DOWN'
    rows = sorted((json.loads(x) for x in open(p) if x.strip()), key=lambda r: -r['tau'])
    w = {'tk': tk, 'truth': truth, 'books': tk in books}
    for rule, adm in (('exact', lambda pf: pf <= 0.002), ('disp', lambda pf: pf < 0.0025)):
        base = None; pr = None; prx = None; basex = None; nadm = 0; nadmx = 0
        for r in rows:
            tau = r['tau']
            if not (0 < tau <= 120) or r.get('gap') is None or not r.get('strike'): continue
            if r.get('state') not in ('LOCKED', 'PROVEN LOCKED') or r.get('pFlip') is None or not adm(r['pFlip']): continue
            side = 'UP' if r['gap'] > 0 else 'DOWN'; o = offer(tk, r['ts'], side); h, R = hR(r)
            rec = {'tau': tau, 'side': side, 'cushion': abs(r['gap']) / r['strike'] * 1e4, 'h': h, 'R': R, 'rstar': RSTAR[h], 'pf': r['pFlip'], 'n': r.get('n') or 0, 'offer': o, 'lost': side != truth}
            if base is None: base = rec
            if basex is None and execok(o): basex = rec
            if R >= RSTAR[h]:
                nadm += 1
                if pr is None: pr = rec
                if execok(o): nadmx += 1
                if prx is None and execok(o): prx = rec
        w[rule] = {'base': base, 'basex': basex, 'pr11': pr, 'pr11x': prx, 'admitted_s': nadm, 'admitted_exec_s': nadmx}
    res.append(w)
out = []; P = out.append
def summ(rule):
    W = [w for w in res]; WB = [w for w in res if w['books']]
    g = lambda w, k: w[rule][k]
    P('RULE %s: settled windows %d (with tape books %d)' % (rule, len(W), len(WB)))
    for name, key in (('baseline first LOCKED', 'base'), ('baseline first LOCKED with executable offer', 'basex'), ('PR11 first admitted', 'pr11'), ('PR11 first admitted with executable offer', 'pr11x')):
        E = [g(w, key) for w in (W if key in ('base', 'pr11') else WB) if g(w, key)]
        lost = sum(1 for e in E if e['lost']); taus = sorted(e['tau'] for e in E); cus = sorted(e['cushion'] for e in E)
        asks = sorted(e['offer']['ask'] for e in E if e['offer'] and e['offer']['ask'] is not None); sizes = sorted(e['offer']['size'] for e in E if e['offer'] and e['offer']['ask'] is not None)
        pct = lambda a, q: a[min(len(a) - 1, int(q * len(a)))] if a else float('nan')
        P('  %-46s: windows %4d  lost %d | tau p10/med/p90 %5.1f/%5.1f/%5.1f | cushion med %5.1f | ask med %5.1f (n %d, <=99.9: %d, <=99.8: %d, <=99.5: %d) | size med %.0f' % (name, len(E), lost, pct(taus, .1), pct(taus, .5), pct(taus, .9), pct(cus, .5), pct(asks, .5), len(asks), sum(1 for a in asks if a <= 99.9), sum(1 for a in asks if a <= 99.8), sum(1 for a in asks if a <= 99.5), pct(sizes, .5)))
    both = [w for w in WB if g(w, 'base')]; P('  of %d tape windows with a baseline LOCKED entry: baseline executable at its first second %d; PR11 admitted at some second %d; PR11 admitted AND executable at some second %d (%.0f%% of tape windows)' % (len(WB), sum(1 for w in WB if g(w, 'basex')), sum(1 for w in WB if g(w, 'pr11')), sum(1 for w in WB if g(w, 'pr11x')), 100 * sum(1 for w in WB if g(w, 'pr11x')) / max(1, len(WB))))
    P('  PR11 executable entries by time left: ' + ', '.join('%s: %d' % (b, sum(1 for w in WB if g(w, 'pr11x') and lo <= g(w, 'pr11x')['tau'] < hi)) for b, lo, hi in (('90-120', 90, 121), ('60-90', 60, 90), ('30-60', 30, 60), ('10-30', 10, 30), ('0-10', 0, 10))))
    P('  losses: baseline ' + '; '.join('%s tau %.1f cushion %.1f R %.1f (R* %d) ask %s' % (w['tk'], g(w, 'base')['tau'], g(w, 'base')['cushion'], g(w, 'base')['R'], g(w, 'base')['rstar'], (g(w, 'base')['offer'] or {}).get('ask')) for w in W if g(w, 'base') and g(w, 'base')['lost']) + ' | PR11 ' + ('; '.join('%s tau %.1f' % (w['tk'], g(w, 'pr11')['tau']) for w in W if g(w, 'pr11') and g(w, 'pr11')['lost']) or 'none'))
summ('exact'); summ('disp')
json.dump(res, open(outp.replace('.txt', '.json'), 'w'))
open(outp, 'w').write('\n'.join(out) + '\n'); print('\n'.join(out))
