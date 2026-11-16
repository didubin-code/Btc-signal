"""respond_v2.py: the response rule of RUNBOOK_I2 section 5 for readings taken when nobody was watching (--past), with the
ATTRIBUTION of an episode to the release's added behaviours corrected (2026-11-16). Version 1 (ops/respond.py) is unchanged and
its recorded outputs stand. What changed, and only this: in v1 the test "a copy was refused by the identity guard during the
episode" was approximated by "the identity counter moved between the two /health copies", an interval of 6 hours at the
6-hourly readings. The identity guard refuses copies at a steady background rate (about 25 per hour, in every interval since
the deploy), so that test was met in every interval whether or not an episode occurred, and the table's "keep the release
once" branch could never be reached. In v2 the identity increment is measured over the smallest interval of /health copies
(6-hourly copies and hourly snapshots) that covers the episode, compared with the background rate estimated from all other
intervals, and counts as "acted" only when the excess over the background expectation is at least MIN_EXCESS and at least
3 standard errors. A stated wait, an age-guard or settlement-guard refusal (normally zero) and the order-book arrangement
count as in v1. Missing counters still give R7u (revert). A hold already used still gives R5 (revert). Nothing else changed.
usage: python3 -I respond_v2.py --past --prev-health FILE --cur-health FILE --watch-dir DIR [--hold-file F] [--snapshots-glob G ...] [--json]"""
import json, sys, os, glob, time, argparse, statistics as st, importlib.util
HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('respond_v1', os.path.join(HERE, 'respond.py')); v1 = importlib.util.module_from_spec(spec); spec.loader.exec_module(v1)
MIN_EXCESS = 20          # at least this many identity refusals above the background expectation over the covering interval
MIN_SE = 3.0             # and at least this many standard errors above it
def _g(h, *k): return v1._num(h, *k)
def load_snapshots(globs):
    snaps = []
    for g in globs:
        for f in glob.glob(g):
            try: d = json.load(open(f))
            except Exception: continue
            if not isinstance(d, dict) or 'kalshi' not in d: continue
            snaps.append({'t': d.get('ts', 0) / 1000.0, 'boot': v1._num_s(d, 'v28', 'boot'), 'identity': _g(d, 'kalshi', 'marketRecord', 'rejected', 'identity'), 'f': f})
    snaps.sort(key=lambda s: s['t']); return snaps
def identity_attribution(snaps, ep_start, ep_end, boot):
    """Returns (acted: True/False/None, text, evidence) from the identity counter over the smallest covering interval."""
    S = [s for s in snaps if s['boot'] == boot and s['identity'] is not None]
    if len(S) < 2: return None, 'fewer than two /health copies of this process carry the identity counter', {}
    before = [s for s in S if s['t'] <= ep_start]; after = [s for s in S if s['t'] >= ep_end]
    if not before or not after: return None, 'no /health copy on both sides of the episode', {}
    a, b = before[-1], after[0]; cover = b['t'] - a['t']; inc = b['identity'] - a['identity']
    # background: per-hour rates of all other consecutive intervals of this process at least 20 min long
    rates = []
    for x, y in zip(S, S[1:]):
        if y['t'] <= a['t'] or x['t'] >= b['t']:
            dt = y['t'] - x['t']
            if dt >= 1200 and y['identity'] >= x['identity']: rates.append((y['identity'] - x['identity']) / dt * 3600)
    if len(rates) < 3: return None, 'fewer than three background intervals to estimate the identity guard\'s normal rate', {'coverS': cover, 'increment': inc}
    mean = st.mean(rates); sd = st.pstdev(rates); hours = cover / 3600
    expected = mean * hours; se = max(sd * (hours ** 0.5), (expected ** 0.5))   # at least Poisson
    excess = inc - expected
    ev = {'coverS': round(cover), 'coverFromUtc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(a['t'])), 'coverToUtc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(b['t'])), 'increment': inc,
          'backgroundPerHour': {'mean': round(mean, 1), 'sd': round(sd, 1), 'n': len(rates), 'max': round(max(rates), 1)}, 'expected': round(expected, 1), 'excess': round(excess, 1), 'excessSE': round(excess / se, 2) if se else None}
    acted = excess >= MIN_EXCESS and (se and excess / se >= MIN_SE)
    txt = 'identity guard +%d over the %.0f-min interval covering the episode against an expected %.0f (background %.1f/h, n %d): excess %+.0f (%.1f s.e.) -> %s' % (inc, cover / 60, expected, mean, len(rates), excess, excess / se if se else 0, 'ACTED' if acted else 'background rate, not shown to have acted')
    return acted, txt, ev
def decide_past_v2(prev, cur, live_samples, now, heavy_windows=0, hold_used=False, snaps=()):
    res = {'action': 'NONE', 'code': None, 'reasons': [], 'evidence': {}, 'nowUtc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(now)), 'holdUsed': bool(hold_used), 'version': 'v2 (2026-11-16): identity-guard attribution over the covering interval against its background rate'}
    def done(action, code, why): res.update({'action': action, 'code': code}); res['reasons'].append(why); return res
    same = prev is not None and v1._num_s(prev, 'v28', 'boot') == v1._num_s(cur, 'v28', 'boot'); boot = v1._num_s(cur, 'v28', 'boot')
    longest = {c: _g(cur, 'kalshi', 'stale', c, 'maxMs') for c in ('refused', 'other')}
    before = {c: (_g(prev, 'kalshi', 'stale', c, 'maxMs') if same else None) for c in ('refused', 'other')}
    new_long = [c for c in longest if longest[c] is not None and longest[c] >= v1.PAST_GATE_MS and (before[c] is None or longest[c] > before[c])]
    res['evidence'].update({'longestPastTheGateMs': longest, 'atThePreviousReadingMs': before, 'windowsMissingMoreThan90s': heavy_windows, 'comparedWithPreviousCopy': same})
    if not new_long and not heavy_windows: return done('NONE', None, 'no episode of %d s or more past the gate and no window missing more than %d s since the previous reading' % (v1.PAST_GATE_MS // 1000, v1.PAST_WINDOW_S))
    what = '; '.join((['an episode of %.0f s past the gate (%s)' % (longest[c] / 1000.0, c) for c in new_long]) + (['%d window(s) missing more than %d s' % (heavy_windows, v1.PAST_WINDOW_S)] if heavy_windows else []))
    if hold_used: return done('REVERT', 'R5', 'a hold was already used for this release, and since the previous reading: ' + what)
    cont, cwhy = v1.continuing(live_samples, now); res['evidence'].update({'continuing': cont, 'continuingWhy': cwhy})
    if cont: return done('REVERT', 'R6', what + '; and decisions are still being lost now: ' + cwhy)
    acted = []; missing = []; notes = []
    for name, path in (('a wait stated by Kalshi was obeyed', ('kalshi', 'refusals', 'statedWait', 'count')), ('a copy was refused by the age guard', ('kalshi', 'marketRecord', 'rejected', 'age')), ('a settlement record was refused', ('kalshi', 'marketRecord', 'rejected', 'settlement'))):
        y = _g(cur, *path); x = _g(prev, *path) if same else 0
        if y is None or x is None: missing.append(path[-1]); continue
        if y > x: acted.append('%s (%d more)' % (name, y - x))
    # identity guard: over the covering interval against its background
    ep_end = (_g(cur, 'kalshi', 'stale', 'lastAt') or 0) / 1000.0; ep_len = (_g(cur, 'kalshi', 'stale', 'lastMs') or 0) / 1000.0 + 6.0
    ep_start = ep_end - ep_len if ep_end else None
    yi = _g(cur, 'kalshi', 'marketRecord', 'rejected', 'identity'); xi = _g(prev, 'kalshi', 'marketRecord', 'rejected', 'identity') if same else 0
    if yi is None or xi is None: missing.append('identity')
    elif ep_start:
        allsn = list(snaps) + [{'t': (prev.get('ts', 0) / 1000.0) if prev else 0, 'boot': v1._num_s(prev, 'v28', 'boot') if prev else None, 'identity': xi, 'f': 'prev'}, {'t': cur.get('ts', 0) / 1000.0, 'boot': boot, 'identity': yi, 'f': 'cur'}]
        tp, tc = ((prev.get('ts', 0) / 1000.0) if prev else 0), cur.get('ts', 0) / 1000.0
        allsn = [s for s in allsn if s['t'] and (s['f'] in ('prev', 'cur') or (abs(s['t'] - tp) > 1 and abs(s['t'] - tc) > 1))]; allsn.sort(key=lambda s: s['t'])   # the copies passed in stand for their own moments
        ia, itxt, iev = identity_attribution(allsn, ep_start, ep_end, boot); res['evidence']['identity'] = iev; notes.append(itxt)
        if ia is True: acted.append('the identity guard refused copies far above its background rate during the covering interval (%s)' % itxt)
        elif ia is None: missing.append('identity attribution (' + itxt + ')')
    else: notes.append('identity +%d since the previous copy; the episode\'s time is not recorded (no lastAt), so it cannot be bounded' % (yi - xi)); missing.append('episode time')
    yb = _g(cur, 'kalshi', 'refused', 'orderbook'); ym = [_g(cur, 'kalshi', 'refused', k) for k in ('single', 'list')]
    xb = _g(prev, 'kalshi', 'refused', 'orderbook') if same else 0; xm = [(_g(prev, 'kalshi', 'refused', k) if same else 0) for k in ('single', 'list')]
    if yb is None or xb is None or any(v is None for v in ym + xm): missing.append('refusals by request type')
    elif yb - xb >= v1.BOOK_REFUSED_MIN and yb - xb > sum(ym) - sum(xm): acted.append('order-book requests were refused %d times against %d refused market-record requests' % (yb - xb, sum(ym) - sum(xm)))
    res['evidence'].update({'addedBehaviourActed': bool(acted) if not missing else None, 'addedBehaviourWhy': '; '.join(acted) or ('counters missing: ' + ', '.join(missing) if missing else 'none above background since the previous copy'), 'notes': notes})
    if missing and not acted: return done('REVERT', 'R7u', what + "; and it cannot be shown that the release's added behaviours did not act (%s)" % ', '.join(missing))
    if acted: return done('REVERT', 'R7', what + "; and one of the release's added behaviours acted in the episode's interval: " + '; '.join(acted))
    return done('HOLD', 'H1', what + '; decisions are being computed now (%s) and none of the release\'s added behaviours is shown to have acted (%s). One hold is used; any later finding of this kind is a revert' % (cwhy, '; '.join(notes)))
def main(argv):
    ap = argparse.ArgumentParser(); ap.add_argument('--past', action='store_true', required=True); ap.add_argument('--prev-health', default=''); ap.add_argument('--cur-health', required=True)
    ap.add_argument('--watch-dir', required=True); ap.add_argument('--hold-file', default=''); ap.add_argument('--heavy-windows', type=int, default=0); ap.add_argument('--now', type=float, default=None)
    ap.add_argument('--snapshots-glob', action='append', default=[]); ap.add_argument('--json', action='store_true'); ap.add_argument('--no-write-hold', action='store_true')
    a = ap.parse_args(argv); now = a.now if a.now is not None else time.time()
    samples = v1.load_ndjson(os.path.join(a.watch_dir, 'samples.ndjson'))
    hold_file = a.hold_file or os.path.join(a.watch_dir, 'HOLD_USED.json'); hold = os.path.exists(hold_file)
    prev = json.load(open(a.prev_health)) if a.prev_health and os.path.exists(a.prev_health) else None; cur = json.load(open(a.cur_health))
    snaps = load_snapshots(a.snapshots_glob)
    res = decide_past_v2(prev, cur, samples, now, heavy_windows=a.heavy_windows, hold_used=hold, snaps=snaps)
    if res['action'] == 'HOLD' and not a.no_write_hold: json.dump({'usedAt': now, 'usedAtUtc': res['nowUtc'], 'pastFinding': True, 'version': 'v2', 'reasons': res['reasons']}, open(hold_file, 'w'), indent=1)
    print(json.dumps(res, indent=1) if a.json else '%s%s  %s\nevidence: %s' % (res['action'], (' [' + res['code'] + ']') if res['code'] else '', ' | '.join(res['reasons']), json.dumps(res['evidence'])))
    return v1.CODES[res['action']]
if __name__ == '__main__': sys.exit(main(sys.argv[1:]))
