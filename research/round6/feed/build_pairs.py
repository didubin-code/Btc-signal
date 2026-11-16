"""Paired per-second feed dataset from the tapes (final 300 s of each window; Nov 13-16). Series per second s (UTC integer second):
 brti[s]  = the official BRTI print whose source second is s (dedup by seq; a print missing for s is left absent, never repeated)
 comp[s]  = production's composite index at the decision tick in second s (liveIdx.value; first tick of the second)
 ring[s]  = production's 1 Hz index-ring sample taken in second s ('s' rows, where the tape carries them)
 bn[s]    = Binance BTCUSDC 1-s close (archive; Nov 13-15)
Also per decision row: brti source age at the tick, print receipt latency, venues used, dispersion.
usage: python3 -I build_pairs.py <out.json> <tape files...>"""
import sys, json, os, collections, datetime as dt
import numpy as np
outp = sys.argv[1]; files = sys.argv[2:]
brti = {}; comp = {}; ring = {}; meta = collections.Counter(); win = {}; seqs = {}
lat = []; ages = []; disp = []; venues = collections.Counter(); reuse = 0; drows = 0; amended = 0
for f in files:
    for l in open(f):
        try: r = json.loads(l)
        except Exception: continue
        k = r.get('k')
        if k == 's':
            t = r.get('t'); v = r.get('v')
            if isinstance(t, (int, float)) and v: ring.setdefault(int(t // 1000), float(v))
        elif k == 'd':
            drows += 1; ts = r['ts']; s = ts // 1000
            li = (r.get('liveIdx') or {}); v = li.get('value')
            if v: comp.setdefault(s, float(v)); venues[len(li.get('used') or [])] += 1
            if li.get('dispersionBps') is not None: disp.append(float(li['dispersionBps']))
            b = ((r.get('brti') or {}).get('last') or {})
            if b.get('value') and b.get('sourceTs'):
                ss = int(b['sourceTs'] // 1000); sq = b.get('seq')
                if sq in seqs: reuse += 1
                else:
                    seqs[sq] = ss; brti.setdefault(ss, float(b['value']))
                    if b.get('localTs'): lat.append(b['localTs'] - b['sourceTs'])
                    if b.get('amended'): amended += 1
                ages.append(ts - b['sourceTs'])
            tk = (r.get('kal') or {}).get('ticker'); cm = (r.get('kal') or {}).get('closeMs')
            if tk and cm: win[tk] = cm
# Binance
days = {}; secdir = '/tmp/claude-0/-home-user/97d7fe1d-a1f3-5240-8215-edf8d0a9a961/scratchpad/round4/replay_live/data/sec/usdc'
bn = {}
for s in list(comp.keys()):
    d = dt.datetime.fromtimestamp(s, dt.timezone.utc); key = d.strftime('%Y-%m-%d')
    if key not in days:
        p = os.path.join(secdir, key + '.f64'); days[key] = np.fromfile(p, dtype='<f8') if os.path.exists(p) else None
    a = days[key]
    if a is not None:
        v = a[d.hour * 3600 + d.minute * 60 + d.second]
        if np.isfinite(v) and v > 0: bn[s] = float(v)
json.dump({'brti': brti, 'comp': comp, 'ring': ring, 'bn': bn, 'win': win,
           'meta': {'decisionRows': drows, 'brtiPrintsUnique': len(brti), 'printReuseRows': reuse, 'amended': amended, 'compSeconds': len(comp), 'ringSeconds': len(ring), 'binanceSeconds': len(bn),
                    'printLatencyMs_p50_p95_p99': [float(np.percentile(lat, p)) for p in (50, 95, 99)] if lat else None, 'brtiSourceAgeAtTickMs_p50_p95': [float(np.percentile(ages, p)) for p in (50, 95)] if ages else None,
                    'venuesUsedCounts': dict(venues), 'dispersionBps_p50_p95': [float(np.percentile(disp, p)) for p in (50, 95)] if disp else None}}, open(outp, 'w'))
print(json.dumps(json.load(open(outp))['meta'], indent=0))
