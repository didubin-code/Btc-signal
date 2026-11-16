"""Read-only pull of https://btc-pin-radar.onrender.com/tape?since=<last decision ts>&format=ndjson, appended to archive/<UTC day>.ndjson.
Sequence/gap check: the first new decision row more than 1.5 s after the stored cursor is logged in archive/GAPS.log (never filled).
Retention: files are never deleted here; prune by date if the repository grows beyond the owner's limit (about 100 MB a day with the
index samples, 35 MB a day without; gzip reduces both about tenfold). Failure: a non-200 or unparsable reply exits 1, which fails the
workflow run and triggers GitHub's failure e-mail to the repository owner; the cursor is not advanced. usage: python3 -I tape_pull.py <archive dir>"""
import sys, os, json, time, urllib.request, glob
D = sys.argv[1]; os.makedirs(D, exist_ok=True)
cur_f = os.path.join(D, 'CURSOR'); since = int(open(cur_f).read().strip()) if os.path.exists(cur_f) else 0
url = 'https://btc-pin-radar.onrender.com/tape?since=%d&format=ndjson' % since
with urllib.request.urlopen(urllib.request.Request(url, headers={'Accept': 'application/x-ndjson', 'User-Agent': 'tape-archive'}), timeout=90) as r:
    if r.status != 200: print('HTTP', r.status); sys.exit(1)
    text = r.read().decode('utf-8', 'replace')
rows = []
for l in text.split('\n'):
    if not l.strip(): continue
    try: rows.append(json.loads(l))
    except Exception: print('unparsable line'); sys.exit(1)
d = [x for x in rows if x.get('k') == 'd' and isinstance(x.get('ts'), int)]
if d:
    first, newest = min(x['ts'] for x in d), max(x['ts'] for x in d)
    if since and first - since > 1500:
        with open(os.path.join(D, 'GAPS.log'), 'a') as g: g.write('%s gap %d ms: cursor %d, first new row %d\n' % (time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), first - since, since, first))
    day = time.strftime('%Y-%m-%d', time.gmtime(newest / 1000))
    with open(os.path.join(D, day + '.ndjson'), 'a') as f:
        for x in rows: f.write(json.dumps(x, separators=(',', ':')) + '\n')
    open(cur_f, 'w').write(str(newest))
print('%s pull ok since=%d rows=%d decisions=%d newest=%d' % (time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), since, len(rows), len(d), newest if d else since))
