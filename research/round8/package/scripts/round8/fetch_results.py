"""Kalshi finalized results for every window in the comparison that has no recorded result yet, plus an
independent re-check of a fixed random sample of the recorded ones. Read-only public GETs through curl.
usage: python3 -I fetch_results.py <tape_all.ndjson> <rows dirs comma> <markets dir> <out dir> <recheck n>"""
import sys, json, glob, os, subprocess, time, random, collections
tape, rowsdirs, mkdir, outdir, nre = sys.argv[1], sys.argv[2].split(','), sys.argv[3], sys.argv[4], int(sys.argv[5])
tk = set()
with open(tape) as f:
    for line in f:
        try: r = json.loads(line)
        except Exception: continue
        t = (r.get('kal') or {}).get('ticker')
        if t: tk.add(t)
for d in rowsdirs:
    for p in glob.glob(d + '/*.ndjson'): tk.add(os.path.basename(p)[:-7])
have = {}
for p in glob.glob(mkdir + '/*.json'):
    m = json.load(open(p)); have[os.path.basename(p)[:-5]] = m
need = sorted(t for t in tk if have.get(t, {}).get('result') not in ('yes', 'no'))
print('tickers', len(tk), 'recorded', len(have), 'to fetch', len(need))
def get(t):
    r = subprocess.run(['curl', '-sS', '-m', '25', 'https://api.elections.kalshi.com/trade-api/v2/markets/' + t], capture_output=True, text=True)
    if r.returncode != 0: return None, 'curl ' + r.stderr.strip()[:80]
    try: m = json.loads(r.stdout).get('market') or {}
    except Exception as e: return None, 'json ' + r.stdout[:80]
    return {'result': m.get('result'), 'strike': m.get('floor_strike'), 'official': m.get('expiration_value'), 'status': m.get('status'), 'close_time': m.get('close_time'), 'source': 'kalshi public api /markets/<ticker>', 'fetched': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}, None
ok = fail = 0
for t in need:
    m, err = get(t); time.sleep(0.35)
    if m is None or m['result'] not in ('yes', 'no'): fail += 1; print('FAIL', t, err or m); continue
    json.dump(m, open(os.path.join(outdir, t + '.json'), 'w')); ok += 1
print('fetched ok', ok, 'fail', fail)
random.seed(8); sample = random.sample(sorted(k for k, v in have.items() if v.get('result') in ('yes', 'no')), min(nre, len(have)))
mis = 0; checked = 0
for t in sample:
    m, err = get(t); time.sleep(0.35)
    if m is None: print('RECHECK FAIL', t, err); continue
    checked += 1; h = have[t]
    if m['result'] != h.get('result') or abs(float(m['official']) - float(h.get('official'))) > 0.005 or abs(float(m['strike']) - float(h.get('strike'))) > 0.005:
        mis += 1; print('MISMATCH', t, 'recorded', h, 'kalshi', m)
print('recheck', checked, 'mismatches', mis)
