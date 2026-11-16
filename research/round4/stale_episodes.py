"""Whole-window stale episodes from the server's own counters (kalshi.stale), read from every /health copy on file
(r30/live/health/health_*.json and round3/tape/health/health_*.json), reported SEPARATELY from the observer's final-300-s gaps.
An episode is accounted by the server when the market record is next renewed; lastAt is the renewal time, lastMs the time past
the 6 s gate, so the episode ran from lastAt - lastMs - 6000 ms to lastAt. usage: python3 -I stale_episodes.py [--since ISO]"""
import json, glob, sys, time
SC = '/tmp/claude-0/-home-user/97d7fe1d-a1f3-5240-8215-edf8d0a9a961/scratchpad'
since = None
if '--since' in sys.argv: since = time.mktime(time.strptime(sys.argv[sys.argv.index('--since') + 1], '%Y-%m-%dT%H:%M:%SZ')) - time.timezone
files = sorted(glob.glob(SC + '/r30/live/health/health_*.json') + glob.glob(SC + '/round3/tape/health/health_*.json'))
snaps = []
for f in files:
    try: d = json.load(open(f))
    except Exception: continue
    k = d.get('kalshi', {}); s = k.get('stale') or {}
    if not isinstance(s, dict) or 'other' not in s: continue
    snaps.append((d.get('ts', 0) / 1000.0, d.get('uptimeSec'), s, f))
snaps.sort()
episodes = {}   # keyed by (boot, lastAt): each distinct accounted episode
prev = None
for ts, up, s, f in snaps:
    for cause in ('refused', 'other'):
        c = s.get(cause) or {}
        n = c.get('episodes') or 0
        if prev is not None and prev[2].get(cause, {}).get('episodes', 0) == n: continue
        if n > 0 and s.get('lastCause') == cause and s.get('lastAt'):
            key = (cause, s['lastAt'])
            episodes[key] = {'cause': cause, 'endUtc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(s['lastAt'] / 1000)), 'pastGateS': round((s.get('lastMs') or 0) / 1000, 1),
                             'startUtc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime((s['lastAt'] - (s.get('lastMs') or 0) - 6000) / 1000)), 'seenInCopy': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(ts)),
                             'countThen': n, 'totalMsThen': c.get('totalMs'), 'maxMsThen': c.get('maxMs')}
        elif n > (prev[2].get(cause, {}).get('episodes', 0) if prev else 0):
            # episodes increased but the last one is of another cause: only the count is known
            episodes[(cause, 'unknown-%s' % ts)] = {'cause': cause, 'endUtc': 'unknown (between %s and %s)' % (time.strftime('%H:%M:%SZ', time.gmtime(prev[0])) if prev else '?', time.strftime('%H:%M:%SZ', time.gmtime(ts))), 'countThen': n, 'totalMsThen': c.get('totalMs'), 'maxMsThen': c.get('maxMs')}
    prev = (ts, up, s, f)
last = snaps[-1][2] if snaps else {}
eps = sorted(episodes.values(), key=lambda e: e['endUtc'])
if since is not None: eps = [e for e in eps if 'unknown' in e['endUtc'] or time.mktime(time.strptime(e['endUtc'], '%Y-%m-%dT%H:%M:%SZ')) - time.timezone >= since]
tot = {c: (last.get(c) or {}) for c in ('refused', 'other')}
print('WHOLE-WINDOW STALE EPISODES (server counters, independent of the observer): since the deploy: refused %d episodes (%.0f s, longest %.0f s), other %d episodes (%.0f s, longest %.0f s); copies read %d (latest %s)' % (
    tot['refused'].get('episodes', 0), (tot['refused'].get('totalMs') or 0) / 1000, (tot['refused'].get('maxMs') or 0) / 1000, tot['other'].get('episodes', 0), (tot['other'].get('totalMs') or 0) / 1000, (tot['other'].get('maxMs') or 0) / 1000, len(snaps), time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(snaps[-1][0])) if snaps else '-'))
for e in eps: print('  episode: cause %s, %s -> %s, %s s past the gate (first seen in the copy of %s)' % (e['cause'], e.get('startUtc', '?'), e['endUtc'], e.get('pastGateS', '?'), e.get('seenInCopy', '?')))
if not eps: print('  no episode in the selected period')
