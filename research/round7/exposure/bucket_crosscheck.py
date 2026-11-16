"""Cross-check of the unconditional exceedance against the trace data: P(leader loses) at 90 <= tau <= 120 by engine sigma bucket x cushion bin,
for ALL rows (any state) and for LOCKED pf<=0.002 rows, window-level (a window counted once per cell at its first row in the cell). FIT 2026 traces."""
import sys, json, gzip, glob, collections
RP = sys.argv[1]
CB = [('<10', 0, 10), ('10-15', 10, 15), ('15-20', 15, 20), ('20-30', 20, 30), ('30-45', 30, 45), ('>=45', 45, 1e9)]
def cb(g): return next(n for n, lo, hi in CB if lo <= g < hi)
win = {}
for f in glob.glob(RP + '/out_full_mu/usdc_0[1-8].ndjson'):
    for l in open(f):
        if l.strip():
            r = json.loads(l)
            if r.get('truth') and r.get('strike'): win[r['ticker']] = (r['truth'], float(r['strike']))
allc = collections.defaultdict(lambda: [set(), set()]); lk = collections.defaultdict(lambda: [set(), set()])
for f in sorted(glob.glob(RP + '/out_full_mu/usdc_0[1-8].trace.ndjson.gz')):
    for l in gzip.open(f, 'rt'):
        r = json.loads(l); tk = r['tk']
        if tk not in win or not (90 <= r['tau'] <= 120) or r.get('gap') is None or r.get('bk') is None: continue
        ce = r['gap'] + (r.get('mu') or 0)
        if ce == 0: continue
        g = abs(ce) / win[tk][1] * 1e4; lost = ('UP' if ce > 0 else 'DOWN') != win[tk][0]
        c = allc[(cb(g), r['bk'])]; c[0].add(tk)
        if lost: c[1].add(tk)
        if r.get('st') in ('LOCKED', 'PROVEN LOCKED') and r.get('pf') is not None and r['pf'] <= 0.002:
            c = lk[(cb(g), r['bk'])]; c[0].add(tk)
            if lost: c[1].add(tk)
bks = list(range(7))
for name, table in (('ALL ROWS (any state), 90-120 s: windows (lost windows) = P(the leader at that cushion/bucket loses)', allc), ('LOCKED pf<=0.002 rows, 90-120 s', lk)):
    print(name); print('  cushion  ' + ''.join('%-18s' % ('bk=%d' % b) for b in bks))
    for n, _, _ in CB: print('  %-8s' % n + ''.join('%-18s' % ('%d (%d) %.2f%%' % (len(table[(n, b)][0]), len(table[(n, b)][1]), 100 * len(table[(n, b)][1]) / len(table[(n, b)][0])) if (n, b) in table else '-') for b in bks))
