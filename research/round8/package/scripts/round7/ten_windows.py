"""Audit detail for the live windows with an executable PR11 entry (exact rule): every admitted second with an executable offer
(ask <= 99.9 c, size >= 10, book age <= 3 s), the first one, its size at the best ask, fillable contracts at <= 99.9 c (ladder), book age,
persistence (consecutive admitted+executable seconds from the first), availability after an action delay of 3/5/10 s (admitted and
executable at that later second), time left, and the contract-level result at the quoted ask with the default fee for C = 100 and 1000.
usage: python3 -I ten_windows.py <rstar.json> <rows dir> <markets dir> <tape_all.ndjson> <out.txt>"""
import sys, json, glob, os, math, collections, bisect
rstar_f, rowsdir, mkdir, tape, outp = sys.argv[1:6]
RS = {int(k): v for k, v in json.load(open(rstar_f))['rstar'].items()}
books = collections.defaultdict(list)
for l in open(tape):
    try: r = json.loads(l)
    except Exception: continue
    if r.get('k') != 'd' or not r.get('ob') or not r.get('kal'): continue
    books[r['kal']['ticker']].append((r['ts'], r.get('obTs') or r['ts'], r['ob']))
for tk in books: books[tk].sort()
BT = {tk: [b[0] for b in B] for tk, B in books.items()}
def book(tk, ts):
    B = books.get(tk)
    if not B: return None
    i = bisect.bisect_right(BT[tk], ts) - 1
    if i < 0 or ts - B[i][0] > 3000: return None
    return {'rowTs': B[i][0], 'obTs': B[i][1], 'ob': B[i][2]}
def asks(ob, side):
    other = ob.get('no') if side == 'UP' else ob.get('yes')
    return sorted(((round(100 - p, 2), s) for p, s in (other or []) if s > 0), key=lambda x: x[0])
def fee(a, C): return math.ceil(7 * C * (a / 100) * (1 - a / 100) - 1e-9) / C
def hR(r):
    n = r.get('n') or 0; tau = r['tau']
    if n >= 1 and tau <= 60: h = max(1, 60 - n); R = abs(r['gap']) / r['strike'] * 1e4 * 60.0 / h
    else: h = min(120, max(1, math.ceil(tau - 1e-9))); R = abs(r['gap']) / r['strike'] * 1e4
    return h, R
out = []; P = out.append
P('LIVE WINDOWS WITH AN EXECUTABLE PR11 ENTRY (exact rule; tape Nov 13-16). Executable = ask <= 99.9 c, size >= 10, book <= 3 s old at the row.')
tot = 0
for p in sorted(glob.glob(rowsdir + '/*.ndjson')):
    tk = os.path.basename(p)[:-7]; mp = mkdir + '/' + tk + '.json'
    if not os.path.exists(mp) or tk not in books: continue
    m = json.load(open(mp))
    if m.get('result') not in ('yes', 'no'): continue
    truth = 'UP' if m['result'] == 'yes' else 'DOWN'
    rows = sorted((json.loads(x) for x in open(p) if x.strip()), key=lambda r: -r['tau'])
    adm = []   # (tau, ts, side, cushion, R, rstar, ask, sizeBest, fillable999, bookAge, lost)
    admitted_any = []
    for r in rows:
        tau = r['tau']
        if not (0 < tau <= 120) or r.get('gap') is None or r.get('state') not in ('LOCKED', 'PROVEN LOCKED') or r.get('pFlip') is None or r['pFlip'] > 0.002: continue
        h, R = hR(r)
        if R < RS[h]: continue
        side = 'UP' if r['gap'] > 0 else 'DOWN'; admitted_any.append(tau)
        b = book(tk, r['ts'])
        if not b: adm.append((tau, r['ts'], side, abs(r['gap']) / r['strike'] * 1e4, R, RS[h], None, 0, 0, None, side != truth, r.get('state'))); continue
        lv = asks(b['ob'], side); best = lv[0] if lv else None
        fill = sum(s for a, s in lv if a <= 99.9)
        adm.append((tau, r['ts'], side, abs(r['gap']) / r['strike'] * 1e4, R, RS[h], best[0] if best else None, best[1] if best else 0, fill, r['ts'] - b['obTs'], side != truth, r.get('state')))
    ex = [a for a in adm if a[6] is not None and a[6] <= 99.9 and a[7] >= 10]
    if not ex: continue
    tot += 1
    first = ex[0]; exset = {round(a[0]) for a in ex}
    # persistence: consecutive seconds from the first executable admitted second
    run = 0; t = round(first[0])
    while t in exset: run += 1; t -= 1
    def at(delay):
        target = first[0] - delay
        c = min(adm, key=lambda a: abs(a[0] - target)) if adm else None
        if not c or abs(c[0] - target) > 0.6: return 'not admitted'
        if c[6] is None: return 'no ask'
        return ('%.1f x %.0f (fill<=99.9: %.0f)' % (c[6], c[7], c[8])) if (c[6] <= 99.9 and c[7] >= 10) else ('ask %.1f' % c[6])
    a = first[6]; res = {}
    for C in (100, 1000):
        f = fee(a, C); win = (100 - a) - f; loss = a + f; res[C] = (f, win, loss, win / (win + loss))
    P('%s result %s | PR11 admitted seconds %d (first %.1f s) | first executable admitted second: %.1f s left, side %s, state %s, cushion %.1f bps, R %.1f vs R* %d, ask %.1f c, size at best %.0f, fillable <= 99.9 c %.0f, book age %s ms, %s' % (
        tk, truth, len(admitted_any), admitted_any[0], first[0], first[2], first[11], first[3], first[4], first[5], first[6], first[7], first[8], first[9], 'LOST' if first[10] else 'won'))
    P('    executable admitted seconds: %d of %d admitted-with-book seconds; persistence from the first: %d consecutive s; after 3 s: %s; after 5 s: %s; after 10 s: %s' % (len(ex), len([x for x in adm if x[6] is not None or x[9] is not None]), run, at(3), at(5), at(10)))
    P('    at ask %.1f c: C=100 fee %.2f c -> win +%.2f c, loss -%.2f c, break-even loss rate %.3f %%; C=1000 fee %.3f c -> win +%.3f c, break-even %.3f %%' % (a, res[100][0], res[100][1], res[100][2], 100 * res[100][3], res[1000][0], res[1000][1], 100 * res[1000][3]))
P('windows with an executable PR11 entry: %d' % tot)
open(outp, 'w').write('\n'.join(out) + '\n'); print('\n'.join(out))
