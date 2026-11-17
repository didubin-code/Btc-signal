"""Split a /predictions pull (rows of the server's per-second prediction log) into per-ticker row files in the
scoreboard format, keeping only windows whose final 120 s are completely inside the pull.
usage: python3 -I split_predictions.py <predictions.json> <out dir>"""
import sys, json, collections, os
d = json.load(open(sys.argv[1])); rows = d['rows']; by = collections.defaultdict(list)
for r in rows: by[r['ticker']].append(r)
kept = []; dropped = []
for t, rs in sorted(by.items()):
    rs.sort(key=lambda r: r['ts']); in120 = [r for r in rs if 0 < r['tau'] <= 120]
    if len(in120) >= 115 and max(r['tau'] for r in in120) >= 119 and min(r['tau'] for r in in120) <= 1.5:
        with open(os.path.join(sys.argv[2], t + '.ndjson'), 'w') as f:
            for r in rs: f.write(json.dumps(r) + '\n')
        kept.append(t)
    else: dropped.append((t, len(in120)))
print('pull n', d.get('n'), 'dropped by server', d.get('dropped'), 'rows', len(rows), 'windows kept', len(kept), kept[:1], kept[-1:], 'incomplete', dropped)
