"""Reproduce rows' sigma from the tape's 1 Hz ring samples with the server's exact ringRmsVol/m25SigmaBps/inflation; ring vs tick RMS with dt."""
import sys, json, math, glob, bisect, collections
import numpy as np
SP = '/tmp/claude-0/-home-user/97d7fe1d-a1f3-5240-8215-edf8d0a9a961/scratchpad'
tapes = [SP + '/incident_20261114T0015Z/own_capture_2/tape_since_boot.ndjson', SP + '/round3/tape/pull_20261115T014056Z.ndjson', SP + '/round3/tape/_new.ndjson']
def q(v, p): v = sorted(v); return v[int(p * (len(v) - 1))] if v else float('nan')
def rms(x): x = np.asarray(x, float); return math.sqrt(np.mean(x * x)) if len(x) else float('nan')
def ringRmsVol(L, now, ring):
    cut = now - L * 1000 - 500; s2 = 0.0; n = 0; prev = None
    for p in ring:
        if p[0] < cut: prev = p; continue
        if prev and prev[1] > 0 and p[0] > prev[0]:
            dtt = max(0.25, (p[0] - prev[0]) / 1000.0); r = (p[1] - prev[1]) / prev[1] * 1e4 / math.sqrt(dtt)
            if prev[0] >= cut: s2 += r * r; n += 1
        prev = p
    return (math.sqrt(s2 / n), n) if n >= max(5, L // 3) else (None, n)
def var_units(tau, W=60):
    t = max(0.0, tau); d = sorted(t - off for off in range(W) if t - off > 1e-9); n = len(d)
    return sum(d[i] * (2 * (n - 1 - i) + 1) for i in range(n)) / (W * W), n
def infl(tau, age_ms):
    units, n = var_units(tau); a = max(0, age_ms) / 1000.0; nLock = 60 - n
    stale = a * (min(60, n + min(nLock, a)) / 60) ** 2
    return math.sqrt((units + stale) / units) if units > 0 else 1.0
rows = []
for f in sorted(glob.glob(SP + '/r30/live/scoreboard/rows/*.ndjson')):
    for l in open(f):
        if l.strip(): rows.append(json.loads(l))
rows.sort(key=lambda r: r['ts']); row_by_sec = {}
for r in rows: row_by_sec.setdefault(r['ts'] // 1000, r)
for tp in tapes:
    ring = []; d = {}
    for l in open(tp):
        try: o = json.loads(l)
        except Exception: continue
        if o.get('k') == 's': ring.append((o['t'], o['v']))
        elif o.get('k') == 'd': d.setdefault(o['ts'] // 1000, o)
    ring = sorted(set(ring)); ts_ring = [p[0] for p in ring]
    dts = np.diff(ts_ring) / 1000.0
    print(tp.split('/')[-1], 'ring samples', len(ring), 'dt p1/p50/p99/max', q(list(dts), .01), q(list(dts), .5), q(list(dts), .99), max(dts), 'phase ms p50', q([t % 1000 for t in ts_ring], .5))
    # (A) reproduce rows sigma: rows in this tape's ring span, with ring history >= 900 s available
    rep = []; rep120 = []; warm = 0; cold = 0; parts = []
    for s, o in sorted(d.items()):
        r = row_by_sec.get(s)
        if not r or not r.get('sigma') or o.get('ageMs') is None: continue
        now = r['ts']
        if now - ts_ring[0] < 905 * 1000: cold += 1; continue
        i = bisect.bisect_right(ts_ring, now); sub = ring[max(0, i - 1000):i]
        v120, n120 = ringRmsVol(120, now, sub); v900, n900 = ringRmsVol(900, now, sub)
        if v120 is None or v900 is None: cold += 1; continue
        warm += 1; sig = math.sqrt((v120 * v120 + v900 * v900) / 2) * 1.03 * infl(r['tau'], o['ageMs'])
        rep.append(r['sigma'] / sig); parts.append((v120 / v900))
    if rep: print('  rows sigma / reproduced(ring, x1.03 x infl): n=%d median %.4f p5 %.4f p95 %.4f | skipped (ring < 905 s or not warm) %d | v120/v900 median %.3f' % (len(rep), q(rep, .5), q(rep, .05), q(rep, .95), cold, q(parts, .5)))
    # (B) ring vs tick composite 1-s RMS on the same seconds, with and without dt normalisation
    comp = {s: (o['ts'], o['liveIdx']['value']) for s, o in d.items() if (o.get('liveIdx') or {}).get('value')}
    rs = {int(t // 1000): (t, v) for t, v in ring}
    ss = [s for s in comp if s + 1 in comp and s in rs and s + 1 in rs]
    rc = [1e4 * math.log(comp[s + 1][1] / comp[s][1]) / math.sqrt((comp[s + 1][0] - comp[s][0]) / 1000.0) for s in ss]
    rr = [1e4 * math.log(rs[s + 1][1] / rs[s][1]) / math.sqrt((rs[s + 1][0] - rs[s][0]) / 1000.0) for s in ss]
    rc0 = [1e4 * math.log(comp[s + 1][1] / comp[s][1]) for s in ss]; rr0 = [1e4 * math.log(rs[s + 1][1] / rs[s][1]) for s in ss]
    print('  ring/tick 1-s RMS: n=%d with dt %.4f | without dt %.4f | tick phase ms p50 %.0f ring phase p50 %.0f' % (len(ss), rms(rr) / rms(rc), rms(rr0) / rms(rc0), q([comp[s][0] % 1000 for s in ss], .5), q([rs[s][0] % 1000 for s in ss], .5)))
    # (C) 1-s RMS of the SAME composite at the two phases, compared to values interpolated: is the tick series smoother because the tick is later in the second?
    # nearest-second ring sample vs tick: the difference series
    dd = [1e4 * math.log(comp[s][1] / rs[s][1]) for s in ss]
    print('  tick - ring same second: RMS %.3f bps, mean %.4f' % (rms(dd), float(np.mean(dd))))
