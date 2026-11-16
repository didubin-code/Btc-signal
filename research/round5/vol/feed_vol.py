"""Which feed's volatility is the right scale for settlement risk? Per window (final 300 s, 1 Hz tape rows): realised 1-s return
volatility (bps/sqrt s) of (i) the live composite index the engine uses (liveIdx), (ii) the official BRTI print (brti.last.value,
the settlement index itself), (iii) the Binance BTCUSDC 1-s close (the replay's proxy) over the same seconds. Also 5-s returns
(less microstructure noise). usage: python3 -I feed_vol.py <tape_all.ndjson> <sec dir with usdc/YYYY-MM-DD.f64> <out.txt>"""
import sys, json, math, collections, datetime as dt, os
import numpy as np
tape, secdir, outp = sys.argv[1:4]
rows = collections.defaultdict(list); shape = None
for l in open(tape):
    try: r = json.loads(l)
    except Exception: continue
    if r.get('k') != 'd': continue
    if shape is None: shape = {k: (list(v.keys()) if isinstance(v, dict) else type(v).__name__) for k, v in r.items()}
    tk = (r.get('kal') or {}).get('ticker'); b = ((r.get('brti') or {}).get('last') or {})
    li = r.get('liveIdx'); li = li.get('value') if isinstance(li, dict) else li
    rows[tk].append((r['ts'], li, b.get('value'), b.get('sourceTs')))
days = {}
def binance(ts_ms):
    d = dt.datetime.fromtimestamp(ts_ms / 1000, dt.timezone.utc); key = d.strftime('%Y-%m-%d')
    if key not in days:
        f = os.path.join(secdir, 'usdc', key + '.f64'); days[key] = np.fromfile(f, dtype='<f8') if os.path.exists(f) else None
    a = days[key]
    if a is None: return None
    i = d.hour * 3600 + d.minute * 60 + d.second; v = a[i]
    return float(v) if np.isfinite(v) and v > 0 else None
def rvol(series, step=1):
    s = np.array([x for x in series], dtype=float)
    if len(s) < 30: return None
    r = np.diff(np.log(s[::step])) * 1e4; return float(np.sqrt(np.mean(r * r)) / math.sqrt(step))
out = []; P = out.append
P('FEED VOLATILITY on the same seconds (tape rows, final 300 s per window; bps per sqrt(s); realised RMS of log returns)')
P('row shape: ' + json.dumps(shape)[:600])
res = []
for tk, R in rows.items():
    R.sort(); n = len(R)
    if n < 200: continue
    live = [x[1] for x in R if x[1]]; brti = [x[2] for x in R if x[2]]
    bn = [binance(x[0]) for x in R]; bn = [v for v in bn if v]
    if len(live) < 200 or len(brti) < 200: continue
    e = {'tk': tk, 'n': n, 'live1': rvol(live), 'brti1': rvol(brti), 'bn1': rvol(bn) if len(bn) >= 200 else None, 'live5': rvol(live, 5), 'brti5': rvol(brti, 5), 'bn5': rvol(bn, 5) if len(bn) >= 200 else None}
    res.append(e)
P('windows with live and BRTI series: %d; with Binance too: %d' % (len(res), sum(1 for e in res if e['bn1'])))
def q(v, p): v = sorted(v); return v[int(p * (len(v) - 1))] if v else float('nan')
for step in ('1', '5'):
    P('  %s-s returns:' % step)
    for a, b in (('brti', 'live'), ('bn', 'live'), ('bn', 'brti')):
        ratios = [e[a + step] / e[b + step] for e in res if e.get(a + step) and e.get(b + step)]
        P('    sigma %-5s / sigma %-5s: median %.3f (p10 %.3f, p90 %.3f, n=%d)' % (a, b, q(ratios, .5), q(ratios, .1), q(ratios, .9), len(ratios)))
    P('    levels: live median %.3f | BRTI median %.3f | Binance median %.3f' % (q([e['live' + step] for e in res if e['live' + step]], .5), q([e['brti' + step] for e in res if e['brti' + step]], .5), q([e['bn' + step] for e in res if e['bn' + step]], .5)))
# the two loss windows
for tk in ('KXBTC15M-26NOV131915-15', 'KXBTC15M-26NOV151330-30'):
    e = next((x for x in res if x['tk'] == tk), None)
    if e: P('  %s: live1 %.3f brti1 %.3f bn1 %s | live5 %.3f brti5 %.3f bn5 %s' % (tk, e['live1'], e['brti1'], ('%.3f' % e['bn1']) if e['bn1'] else '-', e['live5'], e['brti5'], ('%.3f' % e['bn5']) if e['bn5'] else '-'))
open(outp, 'w').write('\n'.join(out) + '\n'); print('\n'.join(out))
