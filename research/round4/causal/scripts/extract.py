#!/usr/bin/env python3
"""Per-chunk extraction of entries, entry-time features and post-entry dynamics.
Usage: python3 -I extract.py <datadir> <chunk> <outdir>
Writes <outdir>/<chunk>.ndjson (one row per window) and <outdir>/<chunk>.log

Conventions (verified by conventions.py):
 - trace rows are contiguous per ticker, tau strictly decreasing on a 1-s grid 124.25 .. 0.25;
 - the engine's fixed[T] equals the trace row at tau = T - 0.75, i.e. "state at T s left" is the
   latest row with tau <= T. The "final 120 s" scan therefore starts at the first row with tau <= 120
   (tau = 119.25) and runs downward.
 - side-signed cushion c = gap if side == UP else -gap (USD); cushion bps = c / strike * 1e4.
 - entry-side risk of a later row = pf if row.side == entry side else 1 - pf.
"""
import sys, json, gzip, os, math

D, CH, OUTDIR = sys.argv[1], sys.argv[2], sys.argv[3]
FAMILY = CH.split('_')[0]
LOCKED = ('LOCKED', 'PROVEN LOCKED')
SCAN_TAU = 120.0
RULES = [
    ('R_disp',  lambda r: r['pf'] < 0.0025),
    ('R_exact', lambda r: r['pf'] <= 0.002),
    ('R_lock',  lambda r: True),
    ('R_01',    lambda r: r['pf'] <= 0.001),
    ('R_pfc',   lambda r: r['pfc'] <= 0.001),
]

def sc(r, side):
    return r['gap'] if side == 'UP' else -r['gap']

def risk(r, side):
    return r['pf'] if r['side'] == side else 1.0 - r['pf']

def rnd(x, n=6):
    return None if x is None else round(x, n)

def analyse(win, rows, log):
    """rows: list of trace rows for one ticker, tau descending."""
    strike = win['strike']
    truth = win['truth']
    # sanity: order
    for a, b in zip(rows, rows[1:]):
        if b['tau'] >= a['tau']:
            log.append('ORDER tk=%s' % win['ticker']); break
    by_tau = {r['tau']: r for r in rows}
    trace_first_locked = next((r['tau'] for r in rows if r['st'] in LOCKED), None)
    fl = win.get('firstLocked') or None
    scan_idx = [i for i, r in enumerate(rows) if r['tau'] <= SCAN_TAU]
    out = {}
    for name, cond in RULES:
        ent = None
        for i in scan_idx:
            r = rows[i]
            if r['st'] in LOCKED and cond(r):
                ent = i; break
        if ent is None:
            out[name] = None; continue
        e = rows[ent]; side = e['side']; etau = e['tau']
        c = sc(e, side)
        rec = {
            'tau': etau, 'side': side, 'st': e['st'],
            'pf': e['pf'], 'pfc': e['pfc'],
            'cushion_usd': rnd(c, 2), 'cushion_bps': rnd(c / strike * 1e4, 4),
            'sig': e['sig'], 'bk': e['bk'], 'soft': e['soft'], 'hard': e['hard'], 'mu': e['mu'],
            'mu_bps': rnd(e['mu'] / strike * 1e4, 4),
        }
        # pre-entry cushion change (entry side used for both rows)
        for lag in (10, 20):
            r0 = by_tau.get(etau + lag)
            if r0 is None:
                rec['dc%d_usd' % lag] = None; rec['dc%d_bps' % lag] = None
            else:
                d = c - sc(r0, side)
                rec['dc%d_usd' % lag] = rnd(d, 2); rec['dc%d_bps' % lag] = rnd(d / strike * 1e4, 4)
        # bk change in previous 30 s
        hist = [r for r in rows if etau < r['tau'] <= etau + 30]
        rec['bk_hist_s'] = len(hist)
        rec['bk_changed_30'] = any(r['bk'] != e['bk'] for r in hist) if hist else None
        rec['bk_30_ago'] = hist[0]['bk'] if hist else None
        # sig change over previous 30 s (ratio) - extra, knowable at entry
        rec['sig_30_ago'] = hist[0]['sig'] if hist else None
        # max pf over the previous 30 s on the entry side (how recently was the lock in doubt)
        rec['max_risk_prev30'] = rnd(max((risk(r, side) for r in hist), default=None)) if hist else None
        # seconds since first LOCKED (window-level, from .ndjson firstLocked; may precede the trace)
        rec['first_locked_tau'] = fl['tau'] if fl else None
        rec['first_locked_side'] = fl['side'] if fl else None
        rec['secs_since_first_locked'] = rnd(fl['tau'] - etau, 2) if fl else None
        rec['trace_first_locked_tau'] = trace_first_locked
        rec['secs_since_trace_first_locked'] = rnd(trace_first_locked - etau, 2) if trace_first_locked is not None else None
        # uninterrupted LOCKED streak (same side) ending at entry, within the trace
        streak = 1; j = ent - 1; censored = False
        while j >= 0 and rows[j]['st'] in LOCKED and rows[j]['side'] == side:
            streak += 1; j -= 1
        if j < 0: censored = True
        rec['lock_streak_s'] = streak; rec['lock_streak_censored'] = censored
        rec['entry_is_scan_start'] = (ent == scan_idx[0])
        # post-entry dynamics
        post = rows[ent + 1:]
        rec['n_post'] = len(post)
        if post:
            cs = [sc(r, side) for r in post]
            rk = [risk(r, side) for r in post]
            imin = min(range(len(post)), key=lambda k: cs[k])
            imax = max(range(len(post)), key=lambda k: rk[k])
            rec['min_c_usd'] = rnd(cs[imin], 2); rec['min_c_bps'] = rnd(cs[imin] / strike * 1e4, 4); rec['min_c_tau'] = post[imin]['tau']
            rec['max_risk'] = rnd(rk[imax]); rec['max_risk_tau'] = post[imax]['tau']
            for thr, key in ((0.005, 't_risk_005'), (0.01, 't_risk_01'), (0.10, 't_risk_10'), (0.5, 't_risk_50')):
                rec[key] = next((post[k]['tau'] for k in range(len(post)) if rk[k] >= thr), None)
            rec['crossed'] = any(x < 0 for x in cs)
            rec['touched_zero'] = any(x == 0 for x in cs)
            rec['t_cross'] = next((post[k]['tau'] for k in range(len(post)) if cs[k] < 0), None)
            rec['t_unlock_state'] = next((r['tau'] for r in post if r['st'] not in LOCKED or r['side'] != side), None)
            rec['t_side_flip'] = next((r['tau'] for r in post if r['side'] != side), None)
            rec['n_post_locked_same_side'] = sum(1 for r in post if r['st'] in LOCKED and r['side'] == side)
            rec['n_post_warning'] = sum(1 for r in post if r['st'] == 'REVERSAL WARNING')
            last = post[-1]
            rec['final_side'] = last['side']; rec['final_st'] = last['st']
            rec['final_c_usd'] = rnd(cs[-1], 2); rec['final_c_bps'] = rnd(cs[-1] / strike * 1e4, 4); rec['final_risk'] = rnd(rk[-1])
        else:
            for k in ('min_c_usd', 'min_c_bps', 'min_c_tau', 'max_risk', 'max_risk_tau', 't_risk_005', 't_risk_01', 't_risk_10', 't_risk_50',
                      't_cross', 't_unlock_state', 't_side_flip', 'final_side', 'final_st', 'final_c_usd', 'final_c_bps', 'final_risk'):
                rec[k] = None
            rec['crossed'] = False; rec['touched_zero'] = False; rec['n_post_locked_same_side'] = 0; rec['n_post_warning'] = 0
        rec['won'] = (side == truth)
        rec['loss_class'] = None if rec['won'] else ('reversal' if rec['crossed'] else 'basis')
        out[name] = rec
    # window-level extras
    return {
        'ticker': win['ticker'], 'closeTs': win['closeTs'], 'family': FAMILY, 'chunk': CH,
        'truth': truth, 'strike': strike, 'official': win['official'], 'marginUsd': win['marginUsd'],
        'marginBps': rnd(win['marginUsd'] / strike * 1e4, 4),
        'dataUnreliable': win.get('dataUnreliable'),
        'firstLocked_tau': fl['tau'] if fl else None, 'firstLocked_side': fl['side'] if fl else None,
        'firstLocked_correct': fl['correct'] if fl else None,
        'trace_rows': len(rows), 'trace_tau_max': rows[0]['tau'], 'trace_tau_min': rows[-1]['tau'],
        'trace_first_locked_tau': trace_first_locked,
        'any_locked_in_scan': any(rows[i]['st'] in LOCKED for i in scan_idx),
        'entries': out,
    }

def main():
    log = []
    wins = {}
    with open(os.path.join(D, CH + '.ndjson')) as f:
        for ln in f:
            ln = ln.strip()
            if not ln: continue
            try:
                w = json.loads(ln)
            except Exception as ex:
                log.append('BAD_NDJSON %r' % ex); continue
            if w['ticker'] in wins: log.append('DUP_TICKER %s' % w['ticker'])
            wins[w['ticker']] = w
    tpath = os.path.join(D, CH + '.trace.ndjson.gz')
    outp = os.path.join(OUTDIR, CH + '.ndjson')
    n_out = 0; n_bad = 0; seen = set()
    if not os.path.exists(tpath):
        log.append('TRACE_MISSING %s' % tpath)
    else:
        cur = None; buf = []
        with open(outp, 'w') as fo, gzip.open(tpath, 'rt') as f:
            def flush():
                nonlocal n_out
                if cur is None: return
                if cur in seen: log.append('NONCONTIGUOUS tk=%s' % cur)
                seen.add(cur)
                w = wins.get(cur)
                if w is None: log.append('TRACE_TK_NOT_IN_NDJSON %s' % cur); return
                fo.write(json.dumps(analyse(w, buf, log), separators=(',', ':')) + '\n'); n_out += 1
            for ln in f:
                try:
                    r = json.loads(ln)
                except Exception:
                    n_bad += 1; continue
                if r['tk'] != cur:
                    flush(); cur = r['tk']; buf = [r]
                else:
                    buf.append(r)
            flush()
    missing = [tk for tk in wins if tk not in seen]
    log.append('SUMMARY chunk=%s windows=%d written=%d windows_without_trace=%d bad_trace_lines=%d' % (CH, len(wins), n_out, len(missing), n_bad))
    with open(os.path.join(OUTDIR, CH + '.log'), 'w') as f:
        f.write('\n'.join(log) + '\n')
    print(log[-1])

main()
