"""Live settlement exposure from production rows (final 300 s, 1 Hz; fields tau, gap, n (known official prints), recAvg, strike, spot,
state, pFlip, side, ask) and executable offers from the tape books at the policy's entry second. R = gap * 60 / r in bps with
r = 60 - n (remaining prints) inside the settlement minute, R = gap before it. usage: python3 -I live_exposure.py <rows dir> <markets dir> <tape_all.ndjson> <out.txt>"""
import sys, json, glob, os, math, collections, bisect
rowsdir, mkdir, tape, outp = sys.argv[1:5]
books = collections.defaultdict(list)   # ticker -> [(ts, ob)]
for l in open(tape):
    try: r = json.loads(l)
    except Exception: continue
    if r.get('k') != 'd' or not r.get('ob'): continue
    books[r['kal']['ticker']].append((r['ts'], r['ob']))
for tk in books: books[tk].sort()
def offer(tk, ts, side):
    """best ask on the called side from the newest book received at or before ts (within 3 s): asks on the YES side are 100 - NO bids."""
    B = books.get(tk)
    if not B: return None
    i = bisect.bisect_right([b[0] for b in B], ts) - 1
    if i < 0 or ts - B[i][0] > 3000: return None
    ob = B[i][1]; other = ob.get('no') if side == 'UP' else ob.get('yes')
    if not other: return {'ask': None, 'size': 0, 'age': ts - B[i][0]}
    best = max(other, key=lambda x: x[0]); return {'ask': round(100 - best[0], 2), 'size': best[1], 'age': ts - B[i][0]}
TB = [('0-10', 0, 10), ('10-20', 10, 20), ('20-30', 20, 30), ('30-45', 30, 45), ('45-60', 45, 60), ('60-90', 60, 90), ('90-120', 90, 120.01)]
RB = [('<10', 0, 10), ('10-20', 10, 20), ('20-30', 20, 30), ('30-45', 30, 45), ('45-60', 45, 60), ('60-90', 60, 90), ('90-120', 90, 120), ('120-200', 120, 200), ('>=200', 200, 1e9)]
cell = collections.defaultdict(lambda: [0, 0]); RSTAR = [20, 30, 40, 60, 80, 100, 120, 160, 200]; entA = {r: {} for r in RSTAR}; entB = {r: {} for r in RSTAR}
isL = lambda s: s in ('LOCKED', 'PROVEN LOCKED'); nwin = 0
for p in sorted(glob.glob(rowsdir + '/*.ndjson')):
    tk = os.path.basename(p)[:-7]; m = json.load(open(mkdir + '/' + tk + '.json')) if os.path.exists(mkdir + '/' + tk + '.json') else {}
    if m.get('result') not in ('yes', 'no'): continue
    truth = 'UP' if m['result'] == 'yes' else 'DOWN'; nwin += 1
    rows = sorted((json.loads(x) for x in open(p) if x.strip()), key=lambda r: -r['tau'])
    for r in rows:
        tau = r['tau']
        if not (0 < tau <= 120) or r.get('gap') is None or not r.get('strike'): continue
        n = r.get('n') or 0; rem = max(1, 60 - n) if tau <= 60 else 60
        R = abs(r['gap']) / r['strike'] * 1e4 * (60.0 / rem if tau <= 60 else 1.0); leader = 'UP' if r['gap'] > 0 else 'DOWN'; lost = leader != truth
        tb = next(nm for nm, lo, hi in TB if lo <= tau < hi); rb = next(nm for nm, lo, hi in RB if lo <= R < hi); c = cell[(tb, rb)]; c[0] += 1; c[1] += int(lost)
        for rs in RSTAR:
            if R >= rs:
                if tk not in entA[rs]: entA[rs][tk] = (tau, leader, R, r['ts'], r.get('ask'), lost)
                if isL(r.get('state')) and r.get('pFlip') is not None and r['pFlip'] <= 0.002 and tk not in entB[rs]: entB[rs][tk] = (tau, leader, R, r['ts'], r.get('ask'), lost)
def cp_upper(k, n):
    if n == 0: return float('nan')
    lo, hi = 0.0, 1.0
    def cdf(p): return sum(math.exp(math.lgamma(n + 1) - math.lgamma(j + 1) - math.lgamma(n - j + 1) + j * math.log(p) + (n - j) * math.log(1 - p)) for j in range(k + 1)) if 0 < p < 1 else (1.0 if p <= 0 else 0.0)
    for _ in range(60):
        mid = (lo + hi) / 2
        if cdf(mid) > 0.05: lo = mid
        else: hi = mid
    return (lo + hi) / 2
out = []; P = out.append
P('LIVE SETTLEMENT EXPOSURE (production rows, %d settled windows Nov 12-16; official prints inside the settlement minute)' % nwin)
P('  tau \\ R      ' + ''.join('%-18s' % n for n, _, _ in RB))
for tn, _, _ in TB:
    line = '  %-11s ' % tn
    for rn, _, _ in RB:
        n, k = cell.get((tn, rn), [0, 0]); line += ('%d/%d' % (k, n)).ljust(18) if n else '-'.ljust(18)
    P(line)
P(''); P('POLICY ENTRIES on live windows (A: any state; B: and LOCKED pf <= 0.002) with the executable offer at the entry second from the tape books (windows on the tape only)')
P('  R*   | A: windows losses  median tau | offer known: n  offer<=99.9: n (%)  ask median  size median  | B: windows losses median tau | offer known: n  offer<=99.9: n (%)  ask median')
for rs in RSTAR:
    def summ(E):
        ks = sum(1 for v in E.values() if v[5]); taus = sorted(v[0] for v in E.values()); known = []; 
        for tk, v in E.items():
            o = offer(tk, v[3], v[1])
            if o is not None: known.append(o)
        ok = [o for o in known if o['ask'] is not None and o['ask'] <= 99.9]
        asks = sorted(o['ask'] for o in ok); sizes = sorted(o['size'] for o in ok)
        return len(E), ks, taus[len(taus) // 2] if taus else float('nan'), len(known), len(ok), (100 * len(ok) / len(known)) if known else float('nan'), asks[len(asks) // 2] if asks else float('nan'), sizes[len(sizes) // 2] if sizes else float('nan')
    a = summ(entA[rs]); b = summ(entB[rs])
    P('  %4d | %6d  %5d  %6.1f | %4d  %4d (%3.0f%%)  %5.1f  %8.0f | %6d  %5d  %6.1f | %4d  %4d (%3.0f%%)  %5.1f' % (rs, a[0], a[1], a[2], a[3], a[4], a[5], a[6], a[7], b[0], b[1], b[2], b[3], b[4], b[5], b[6]))
json.dump({'entriesA': {str(rs): {tk: list(v) for tk, v in E.items()} for rs, E in entA.items()}, 'entriesB': {str(rs): {tk: list(v) for tk, v in E.items()} for rs, E in entB.items()}}, open(outp.replace('.txt', '.json'), 'w'))
open(outp, 'w').write('\n'.join(out) + '\n'); print('\n'.join(out))
