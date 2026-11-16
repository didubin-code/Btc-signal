"""Sudden-move frequency by month from the Binance BTCUSDC 1-s closes (engine-independent): non-overlapping 20-s moves of at least
15 bps and 10 bps, counted per day; plus the share of minutes whose 20-s moves exceed 15 bps after a calm preceding 60 s (< 5 bps range).
usage: python3 -I jumps.py <sec dir> <out.txt>"""
import sys, os, glob, numpy as np, collections
secdir, outp = sys.argv[1:3]
bym = collections.defaultdict(lambda: [0, 0, 0, 0])   # days, jumps15, jumps10, jumps15_after_calm
for f in sorted(glob.glob(os.path.join(secdir, 'usdc', '2026-*.f64'))):
    day = os.path.basename(f)[:-4]; a = np.fromfile(f, dtype='<f8')
    if len(a) != 86400 or not np.isfinite(a).all() or (a <= 0).any(): continue
    m = day[:7]; bym[m][0] += 1
    lg = np.log(a) * 1e4
    mv = np.abs(lg[20:] - lg[:-20])                     # 20-s move in bps at each end second
    # non-overlapping counting: scan, skip 20 s after a counted jump
    def count(th, calm=False):
        c = 0; i = 0; n = len(mv)
        while i < n:
            if mv[i] >= th:
                ok = True
                if calm:
                    s0 = i + 20 - 80; s1 = i + 20 - 20     # the 60 s before the move's start (indices in lg)
                    if s0 < 0: ok = False
                    else: seg = lg[s0:s1]; ok = (seg.max() - seg.min()) < 5
                if ok: c += 1
                i += 20
            else: i += 1
        return c
    bym[m][1] += count(15); bym[m][2] += count(10); bym[m][3] += count(15, calm=True)
out = ['SUDDEN MOVES per day (Binance BTCUSDC 1-s closes; non-overlapping 20-s moves)', '  month     days  >=15bps/day  >=10bps/day  >=15bps after a calm 60 s (<5 bps range)/day']
for m in sorted(bym):
    d, j15, j10, jc = bym[m]; out.append('  %s   %3d   %8.2f    %8.2f    %8.2f' % (m, d, j15 / d, j10 / d, jc / d))
open(outp, 'w').write('\n'.join(out) + '\n'); print('\n'.join(out))
