#!/usr/bin/env python3
"""PR11 release watch (read-only on the archived /tape rows; no production access).
Classifies every window since the deploy from the decision rows and reports, per run:
  implementation checks  C1 served LOCKED/PROVEN LOCKED inside 120 s with pr11Admit false   (gate violation)
                         C2 served LOCKED/PROVEN LOCKED inside 120 s from the PR11 build with no pr11Admit field (row/field defect)
                         C3 TRADE NOW while the state is not LOCKED/PROVEN LOCKED              (contradictory instruction)
  recording              first qualified entry per window (state LOCKED/PROVEN inside 120 s with pr11Admit true, earliest second), its side,
                         tau, best ask; PROVEN LOCKED rows (conditional exceptions) and whether admitted; withheld seconds (HIGH CONFIDENCE
                         with flip risk <= 0.2 % inside 120 s and pr11Admit false); outcome (settlement from the strike chain: the next
                         window's strike / prevSettled.official); data gaps in the final 120 s; mixed-build / restarted windows (a boot
                         marker or the deploy inside the window's final 300 s); unobserved intervals (tape discontinuities > 90 s)
  cadence                heartbeat file; a run more than 65 min after the previous one is logged as a missed check
usage: pr11_watch.py --tape tape_all.ndjson [--tape more.ndjson ...] --deploy-ms <ms> --out <dir> [--build-from-ms <ms>] [--now-ms <ms>]
       pr11_watch.py --selftest
Rows before --deploy-ms are pre-release (I2) rows: counted, never scored. Nothing is ever filled in: a window without rows is 'unobserved'."""
import sys, json, os, time, argparse, tempfile
LOCK_MAX_FLIP = 0.002
def load_rows(paths):
    rows, boots = [], []
    for p in paths:
        with open(p) as f:
            for l in f:
                l = l.strip()
                if not l: continue
                try: o = json.loads(l)
                except Exception: continue
                k = o.get('k')
                if k == 'd' and o.get('kal') and o.get('out'): rows.append(o)
                elif k == 'boot' and o.get('ts'): boots.append(o['ts'])
    rows.sort(key=lambda r: r['ts']); boots = sorted(set(boots))
    # de-duplicate exact repeats (an archive built from overlapping pulls)
    out, seen = [], set()
    for r in rows:
        key = (r['ts'], r['kal'].get('ticker'))
        if key in seen: continue
        seen.add(key); out.append(r)
    return out, boots
def best_ask(r, side):
    ob = r.get('ob') or {}
    lv = ob.get('yes') if side == 'UP' else ob.get('no')
    if not lv: return None
    try:
        asks = [x for x in lv if isinstance(x, (list, tuple)) and len(x) >= 2]
        if not asks: return None
        a = min(asks, key=lambda x: x[0]); return {'cents': a[0], 'size': a[1]}
    except Exception: return None
def analyse(rows, boots, deploy_ms, build_from_ms=None, now_ms=None):
    now_ms = now_ms or int(time.time() * 1000)
    build_from_ms = build_from_ms if build_from_ms is not None else deploy_ms
    W = {}
    settle_by_ticker = {}
    for r in rows:
        ps = r.get('prevSettled')
        if ps and ps.get('ticker') and ps.get('official') is not None: settle_by_ticker[ps['ticker']] = ps['official']
    pre_rows = 0
    for r in rows:
        if r['ts'] < deploy_ms: pre_rows += 1; continue
        k = r['kal']; tk = k.get('ticker'); close = k.get('closeMs'); strike = k.get('strike')
        if not tk or not close: continue
        tau = (close - r['ts']) / 1000.0
        if tau > 300 or tau < -5: continue
        w = W.setdefault(tk, {'ticker': tk, 'closeMs': close, 'strike': strike, 'rows': 0, 'rows120': 0, 'secs120': set(), 'first_qualified': None,
                             'proven_rows': 0, 'proven_admitted': 0, 'proven_not_admitted': 0, 'withheld_rows': 0, 'first_withheld_tau': None,
                             'locked_rows120': 0, 'C1': 0, 'C2': 0, 'C3': 0, 'C1_examples': [], 'trade_now_rows': 0, 'min_ts': r['ts'], 'max_ts': r['ts'],
                             'data_unreliable_rows120': 0})
        w['rows'] += 1; w['min_ts'] = min(w['min_ts'], r['ts']); w['max_ts'] = max(w['max_ts'], r['ts'])
        o = r['out']; st = o.get('state'); side = o.get('side'); pf = o.get('pFlip'); adm = o.get('pr11Admit', None); act = o.get('action')
        locked = st in ('LOCKED', 'PROVEN LOCKED')
        if act == 'TRADE NOW':
            w['trade_now_rows'] += 1
            if not locked: w['C3'] += 1
        if 0 < tau <= 120:
            w['rows120'] += 1; w['secs120'].add(int(tau))
            if st == 'DATA UNRELIABLE': w['data_unreliable_rows120'] += 1
            if locked:
                w['locked_rows120'] += 1
                if adm is False:
                    w['C1'] += 1
                    if len(w['C1_examples']) < 3: w['C1_examples'].append({'ts': r['ts'], 'tau': round(tau, 1), 'state': st, 'side': side})
                elif adm is None and r['ts'] >= build_from_ms: w['C2'] += 1
                elif adm is True and (w['first_qualified'] is None or tau > w['first_qualified']['tau']):
                    w['first_qualified'] = {'ts': r['ts'], 'tau': round(tau, 1), 'side': side, 'state': st, 'pFlip': pf, 'ask': best_ask(r, side), 'action': act}
            if st == 'PROVEN LOCKED':
                w['proven_rows'] += 1
                if adm is True: w['proven_admitted'] += 1
                elif adm is False: w['proven_not_admitted'] += 1
            if st == 'HIGH CONFIDENCE' and pf is not None and pf <= LOCK_MAX_FLIP and adm is False:
                w['withheld_rows'] += 1
                if w['first_withheld_tau'] is None or tau > w['first_withheld_tau']: w['first_withheld_tau'] = round(tau, 1)
    out = []
    for tk, w in sorted(W.items(), key=lambda x: x[1]['closeMs']):
        close = w['closeMs']; span_start = close - 300000
        mixed = any(span_start <= b <= close for b in boots) or (span_start <= deploy_ms <= close)
        coverage120 = len(w['secs120']) / 120.0
        settled = settle_by_ticker.get(tk)
        pending = close > now_ms - 90000
        result = None
        if settled is not None and w['strike'] is not None: result = 'UP' if settled >= w['strike'] else 'DOWN'
        fq = w['first_qualified']
        outcome = None
        if fq and result: outcome = 'WON' if fq['side'] == result else 'LOST'
        elif fq: outcome = 'PENDING' if pending or settled is None else None
        status = 'mixed-build' if mixed else ('incomplete' if (coverage120 < 0.95 and not pending) else ('pending' if pending else 'complete'))
        if w['rows120'] == 0 and not pending: status = 'unobserved-final-120' if not mixed else status
        rec = {k: v for k, v in w.items() if k not in ('secs120', 'min_ts', 'max_ts')}
        rec.update({'coverage120': round(coverage120, 3), 'missing_secs120': 120 - len(w['secs120']), 'status': status, 'settlement': settled, 'result': result,
                    'outcome': outcome, 'close_iso': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(close / 1000))})
        out.append(rec)
    # expected windows: one close every 15 min from the first close after the deploy to the last close at least 90 s ago; a window with no
    # rows at all is 'unobserved' (rows exist only inside a window's final 300 s, so raw row gaps of about 10 min are normal)
    first_close = (deploy_ms // 900000 + 1) * 900000
    last_close = ((now_ms - 90000) // 900000) * 900000
    expected = list(range(first_close, last_close + 1, 900000)) if last_close >= first_close else []
    have = set(w['closeMs'] for w in out)
    unobserved = [time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(c / 1000)) for c in expected if c not in have]
    gaps = unobserved
    comp = [w for w in out if w['status'] == 'complete']
    entries = [w for w in comp if w['first_qualified']]
    summary = {
        'rows_since_deploy': sum(w['rows'] for w in out), 'pre_release_rows_ignored': pre_rows, 'windows_since_deploy': len(out),
        'complete': len(comp), 'pending': sum(1 for w in out if w['status'] == 'pending'), 'incomplete': sum(1 for w in out if w['status'] == 'incomplete'),
        'mixed_build': sum(1 for w in out if w['status'] == 'mixed-build'), 'unobserved_final_120': sum(1 for w in out if w['status'] == 'unobserved-final-120'),
        'qualified_entries_complete_windows': len(entries), 'entries_won': sum(1 for w in entries if w['outcome'] == 'WON'), 'entries_lost': sum(1 for w in entries if w['outcome'] == 'LOST'),
        'entries_pending_or_unsettled': sum(1 for w in entries if w['outcome'] not in ('WON', 'LOST')),
        'qualified_entries_any_status': sum(1 for w in out if w['first_qualified']),
        'proven_rows': sum(w['proven_rows'] for w in out), 'proven_admitted': sum(w['proven_admitted'] for w in out), 'proven_not_admitted': sum(w['proven_not_admitted'] for w in out),
        'windows_with_withheld_seconds': sum(1 for w in out if w['withheld_rows']), 'withheld_rows': sum(w['withheld_rows'] for w in out),
        'C1_gate_violations': sum(w['C1'] for w in out), 'C2_missing_field': sum(w['C2'] for w in out), 'C3_trade_now_not_locked': sum(w['C3'] for w in out),
        'windows_with_data_gaps': sum(1 for w in out if w['missing_secs120'] > 0 and w['status'] in ('complete', 'incomplete')),
        'expected_windows': len(expected), 'unobserved_windows': gaps, 'lost_entries': [{'ticker': w['ticker'], 'close': w['close_iso'], 'entry': w['first_qualified'], 'settlement': w['settlement'], 'strike': w['strike']} for w in entries if w['outcome'] == 'LOST'],
        'C1_examples': [{'ticker': w['ticker'], 'ex': w['C1_examples']} for w in out if w['C1']][:5],
    }
    return out, summary
def heartbeat(outdir, now_ms):
    hb = os.path.join(outdir, 'heartbeat.json'); prev = None
    if os.path.exists(hb):
        try: prev = json.load(open(hb)).get('last_run_ms')
        except Exception: prev = None
    missed = prev is not None and now_ms - prev > 65 * 60000
    json.dump({'last_run_ms': now_ms, 'last_run_iso': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(now_ms / 1000)), 'previous_run_ms': prev, 'missed_check': bool(missed)}, open(hb, 'w'))
    return prev, missed
def selftest():
    import random
    random.seed(1)
    close0 = 1800000000000
    rows = []; boots = []
    def win(idx, strike, rows_spec, prev_official=None):
        close = close0 + idx * 900000; tk = 'KXBTC15M-SELFTEST-%02d' % idx
        for tau, st, side, pf, adm, act in rows_spec:
            ts = close - int(tau * 1000)
            r = {'k': 'd', 'ts': ts, 'kal': {'ticker': tk, 'closeMs': close, 'strike': strike}, 'out': {'state': st, 'side': side, 'pFlip': pf, 'action': act},
                 'ob': {'yes': [[99.9, 5000]], 'no': [[99.8, 7000]]}}
            if adm != 'absent': r['out']['pr11Admit'] = adm
            if prev_official is not None: r['prevSettled'] = {'ticker': 'KXBTC15M-SELFTEST-%02d' % (idx - 1), 'closeMs': close - 900000, 'official': prev_official}
            rows.append(r)
        return close
    full = lambda f: [(t, ) + f(t) for t in [x + 0.5 for x in range(119, -1, -1)]]
    # window 1: admitted LOCKED from 50 s, settles UP (next strike 100.5 >= strike 100) -> WON
    win(1, 100.0, full(lambda t: ('LOCKED', 'UP', 0.001, True, 'TRADE NOW') if t <= 50 else ('HIGH CONFIDENCE', 'UP', 0.0015, False, 'WAIT')))
    # window 2: withheld only; settles DOWN (strike chain) -> no entry
    win(2, 100.5, full(lambda t: ('HIGH CONFIDENCE', 'UP', 0.0012, False, 'WAIT')), prev_official=100.5)
    # window 3: contradiction C1 at 90..80 s (LOCKED with pr11Admit false) + C3 (TRADE NOW on HIGH)
    win(3, 99.0, full(lambda t: ('LOCKED', 'DOWN', 0.001, False, 'TRADE NOW') if 80 <= t <= 90 else ('HIGH CONFIDENCE', 'DOWN', 0.01, False, 'TRADE NOW' if t == 70.5 else 'WAIT')), prev_official=99.0)
    # window 4: PROVEN LOCKED admitted in the last 5 s, LOCKED admitted from 20 s; settles UP -> WON
    win(4, 98.0, full(lambda t: ('PROVEN LOCKED', 'UP', 0.0, True, 'LOCKED — TOO LATE') if t <= 5 else (('LOCKED', 'UP', 0.0005, True, 'TRADE NOW') if t <= 20 else ('LEANING', 'UP', 0.05, False, 'WAIT'))), prev_official=98.0)
    # window 5: mixed-build (boot inside the window)
    c5 = win(5, 99.5, full(lambda t: ('LOCKED', 'UP', 0.001, True, 'TRADE NOW') if t <= 60 else ('HIGH CONFIDENCE', 'UP', 0.003, False, 'WAIT')), prev_official=99.5); boots.append(c5 - 200000)
    # window 6: 40-s gap in the final 120 s -> incomplete
    win(6, 100.0, [(t, 'LOCKED', 'UP', 0.001, True, 'TRADE NOW') if t <= 40 else (t, 'HIGH CONFIDENCE', 'UP', 0.003, False, 'WAIT') for t in [x + 0.5 for x in range(119, -1, -1)] if not (50 <= t <= 90)], prev_official=100.0)
    # window 7: admitted LOCKED UP from 70 s, settles DOWN -> LOST (strike 101, settlement 100.2)
    win(7, 101.0, full(lambda t: ('LOCKED', 'UP', 0.0015, True, 'TRADE NOW') if t <= 70 else ('HIGH CONFIDENCE', 'UP', 0.0019, False, 'WAIT')), prev_official=101.0)
    # window 8: settlement row for window 7 (strike 100.2 = window 7's settlement) + C2 (LOCKED with the field absent from the PR11 build)
    win(8, 100.2, full(lambda t: ('LOCKED', 'DOWN', 0.001, 'absent', 'WAIT') if t <= 30 else ('TOSS-UP', 'DOWN', 0.3, 'absent', 'WAIT')), prev_official=100.2)
    # window 9: settlement row for window 8 (99.0 < 100.2 -> DOWN) ; pending (close in the future)
    now_ms = close0 + 9 * 900000 - 60000
    win(9, 99.0, [(100.5, 'LEANING', 'UP', 0.1, False, 'WAIT')], prev_official=99.0)
    # pre-release rows
    rows.append({'k': 'd', 'ts': close0 + 400000, 'kal': {'ticker': 'KXBTC15M-PRE', 'closeMs': close0 - 4900000, 'strike': 1}, 'out': {'state': 'LOCKED', 'side': 'UP', 'pFlip': 0.001, 'action': 'TRADE NOW'}})
    deploy_ms = close0 + 900000 - 400000   # just before window 1's final 300 s (window 1 closes at close0 + 900000)
    out, s = analyse(rows, boots, deploy_ms, build_from_ms=deploy_ms, now_ms=now_ms)
    exp = {'pre_release_rows_ignored': 1, 'windows_since_deploy': 9, 'mixed_build': 1, 'incomplete': 1, 'pending': 1, 'complete': 6,
           'qualified_entries_complete_windows': 3, 'entries_won': 2, 'entries_lost': 1, 'proven_rows': 5, 'proven_admitted': 5, 'C1_gate_violations': 10, 'C2_missing_field': 30, 'C3_trade_now_not_locked': 1,
           'windows_with_withheld_seconds': 3, 'unobserved_windows': []}
    bad = {k: (s.get(k), v) for k, v in exp.items() if s.get(k) != v}
    byt = {w['ticker'][-2:]: (w['status'], w['outcome'], w['first_qualified'] and w['first_qualified']['tau']) for w in out}
    print('SELFTEST', 'PASS' if not bad else 'FAIL', json.dumps(bad), json.dumps(byt))
    return 0 if not bad else 1
def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--tape', action='append', default=[]); ap.add_argument('--deploy-ms', type=int); ap.add_argument('--build-from-ms', type=int)
    ap.add_argument('--now-ms', type=int); ap.add_argument('--out'); ap.add_argument('--selftest', action='store_true'); ap.add_argument('--label', default='')
    a = ap.parse_args()
    if a.selftest: sys.exit(selftest())
    if not a.tape or a.deploy_ms is None or not a.out: ap.error('--tape, --deploy-ms and --out are required')
    os.makedirs(a.out, exist_ok=True); now_ms = a.now_ms or int(time.time() * 1000)
    rows, boots = load_rows(a.tape)
    out, s = analyse(rows, boots, a.deploy_ms, a.build_from_ms, now_ms)
    prev, missed = heartbeat(a.out, now_ms)
    s['run_iso'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(now_ms / 1000)); s['previous_run_iso'] = prev and time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(prev / 1000)); s['missed_check'] = missed; s['label'] = a.label
    s['boots_since_deploy'] = [time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(b / 1000)) for b in boots if b >= a.deploy_ms]
    json.dump(out, open(os.path.join(a.out, 'windows.json'), 'w'))
    with open(os.path.join(a.out, 'runs.ndjson'), 'a') as f: f.write(json.dumps(s) + '\n')
    flags = []
    if s['C1_gate_violations']: flags.append('C1 GATE VIOLATION x%d' % s['C1_gate_violations'])
    if s['C2_missing_field']: flags.append('C2 MISSING pr11Admit x%d' % s['C2_missing_field'])
    if s['C3_trade_now_not_locked']: flags.append('C3 TRADE NOW NOT LOCKED x%d' % s['C3_trade_now_not_locked'])
    if s['entries_lost']: flags.append('ENTRY LOST x%d' % s['entries_lost'])
    if missed: flags.append('MISSED CHECK')
    if s['unobserved_windows']: flags.append('UNOBSERVED WINDOWS x%d' % len(s['unobserved_windows']))
    line = '%s PR11 WATCH %s | windows %d of %d expected (complete %d, pending %d, incomplete %d, mixed %d, no-final-120 %d, unobserved %d) | qualified entries %d: won %d lost %d pending %d | PROVEN rows %d (admitted %d) | withheld windows %d | C1 %d C2 %d C3 %d | %s' % (
        s['run_iso'], a.label, s['windows_since_deploy'], s['expected_windows'], s['complete'], s['pending'], s['incomplete'], s['mixed_build'], s['unobserved_final_120'], len(s['unobserved_windows']), s['qualified_entries_complete_windows'], s['entries_won'], s['entries_lost'], s['entries_pending_or_unsettled'], s['proven_rows'], s['proven_admitted'], s['windows_with_withheld_seconds'], s['C1_gate_violations'], s['C2_missing_field'], s['C3_trade_now_not_locked'], ('FLAGS: ' + '; '.join(flags)) if flags else 'no flags')
    with open(os.path.join(a.out, 'STATUS.txt'), 'a') as f: f.write(line + '\n')
    print(line)
    if s['lost_entries']: print('LOST ENTRIES:', json.dumps(s['lost_entries'])[:1500])
    if s['C1_examples']: print('C1 EXAMPLES:', json.dumps(s['C1_examples'])[:800])
    if s['unobserved_windows']: print('UNOBSERVED WINDOWS (no rows at all; nothing is filled in):', json.dumps(s['unobserved_windows'])[:800])
if __name__ == '__main__': main()
