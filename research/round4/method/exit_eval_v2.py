"""PR9 evaluation, version 2 (round 4, 2026-11-16). A copy of round3/exec/exit_eval.py (frozen, left untouched) with corrections that
are each switchable by a flag and OFF by default. With every flag off the numbers reproduce the original exactly: the text output then
differs only by the '## ' header/verdict lines added here, the JSON only by added fields.
usage: python3 -I exit_eval_v2.py <set: live|replay> <out.json> [--fill-remainder] [--books-only] [--exact-entry] [--min-book-lag]
Inputs (read-only): live production rows (r30/live/scoreboard/rows, results in .../markets), Kalshi prints (round3/kalshi_trades),
1 Hz order books (round3/tape/tape_all.ndjson: 'ob' = BIDS of each side, 'obTs' = the book's own timestamp), replay series (round3/series).
For every displayed entry: hold outcome and, for each trigger and delay, the exit price (book bid preferred, else prints) and the net.
Prices in cents of the HELD side (NO prices = 100 - yes for a DOWN hold).
Flags (each default OFF):
  --fill-remainder  when the recorded ladder cannot fill the whole size, the unfilled remainder is valued at the hold's settlement
                    (100 c per contract for a winner, 0 for a loser); exit fee on the filled part only; nets and totals for sizes 10,
                    100 and 1000 (the original reports the net at size 10 only and prices a partial fill as if the whole size filled).
  --books-only      an exit priced only from trade prints is UNPRICED (a print shows a trade at a price, not depth for our size);
                    in the all-entries line an unpriced exit counts as the hold outcome: the win for a winner, the full loss for a loss.
  --exact-entry     entry rule pFlip <= 0.002 (the exact 0.20 % line) instead of pFlip < 0.0025 (the rounded "about 0.2 %" reading);
                    replay set: the entry row is re-derived from the series on the recorded entry side (first LOCK row with tau <= 120).
  --min-book-lag    report each book exit's own lag (book timestamp minus target time) in the text output with a lag distribution and
                    the check 0 <= lag <= 2.5 s; the refusal of books more than 2.5 s late is unconditional, as in the original.
  --as-of <UTC>     data-window selector, not a correction: the live set as it was on disk at that time (ISO 8601, e.g.
                    2026-11-15T18:42:00Z): markets closing at or before it whose rows file AND result file were last modified at or
                    before it. The scoreboard directory keeps growing (backfills), so this pins the set the recorded run saw."""
import json, glob, os, sys, bisect, math, datetime, collections, statistics as st, argparse
from fractions import Fraction
SC = '/tmp/claude-0/-home-user/97d7fe1d-a1f3-5240-8215-edf8d0a9a961/scratchpad'; R3 = SC + '/round3'
OPT = {'fill_remainder': False, 'books_only': False, 'exact_entry': False, 'min_book_lag': False, 'as_of': None}   # v2: flags, all OFF by default
MON = {'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6, 'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12}
def close_ts(tk):   # frozen (original lines 9-13)
    s = tk.split('-')[1]; y, m, d, hh, mm = 2000 + int(s[:2]), MON[s[2:5]], int(s[5:7]), int(s[7:9]), int(s[9:11])
    local = datetime.datetime(y, m, d, hh, mm, tzinfo=datetime.timezone.utc).timestamp()
    edt = local + 4 * 3600                       # EDT (UTC-4) until 2026-11-01 06:00 UTC, EST (UTC-5) after
    return (edt) if edt < 1793512800 else (local + 5 * 3600)
def iso2s(t):   # frozen
    return datetime.datetime.strptime(t[:26].rstrip('Z') if '.' in t else t.rstrip('Z'), '%Y-%m-%dT%H:%M:%S.%f' if '.' in t else '%Y-%m-%dT%H:%M:%S').replace(tzinfo=datetime.timezone.utc).timestamp()
def load_prints(tk):   # frozen
    f = '%s/kalshi_trades/%s.ndjson' % (R3, tk)
    if not os.path.exists(f): return None
    P = []
    for l in open(f):
        l = l.strip()
        if l:
            r = json.loads(l); P.append((iso2s(r['created_time']), float(r['yes_price_dollars']) * 100, float(r['count_fp']), r['taker_side']))
    P.sort(key=lambda x: x[0]); return P
BOOKS = collections.defaultdict(list); BOOK_TS = {}
def index_books():   # v2: sorted once; BOOK_TS holds the per-ticker list of book timestamps the original rebuilt on every call (same bisect result)
    for v in BOOKS.values(): v.sort(key=lambda b: b[0])
    BOOK_TS.clear(); BOOK_TS.update({tk: [b[0] for b in v] for tk, v in BOOKS.items()})
def load_books(path=R3 + '/tape/tape_all.ndjson'):   # frozen content (original lines 25-30)
    BOOKS.clear()
    if os.path.exists(path):
        for l in open(path):
            r = json.loads(l); tk = (r.get('kal') or {}).get('ticker')
            if tk and r.get('ob') and r.get('obTs'): BOOKS[tk].append((r['obTs'] / 1000, r['ts'] / 1000, r['ob']))
    index_books()
def fee(p, n):   # frozen: Kalshi taker fee, cents per contract, order rounded up to the cent
    return math.ceil(0.07 * n * (p / 100) * (1 - p / 100) * 100) / n
def fee_exact(p, n):   # v2 diagnostic only: the same formula in exact rational arithmetic (never used for a reported number)
    pf = Fraction(str(round(p, 6))) / 100; nn = Fraction(str(round(n, 3)))
    return math.ceil(Fraction(7, 100) * nn * pf * (1 - pf) * 100) / n
FEECHK = {'n': 0, 'mismatch': 0, 'cases': []}
def fee_checked(p, n):   # v2: returns the frozen fee, counts float-rounding disagreements with the exact value
    f = fee(p, n); FEECHK['n'] += 1
    if abs(f - fee_exact(p, n)) > 1e-9:
        FEECHK['mismatch'] += 1
        if len(FEECHK['cases']) < 10: FEECHK['cases'].append((p, n, f * n, fee_exact(p, n) * n))
    return f
def book_lookup(tk, t):
    """v2 helper (same rule as original line 36-37): index of the first book whose OWN timestamp is at or after t, its lag, a status."""
    bs = BOOKS.get(tk)
    if not bs: return None, None, 'no-book'
    i = bisect.bisect_left(BOOK_TS[tk], t)
    if i >= len(bs): return None, None, 'no-book-after'
    lag = bs[i][0] - t
    if lag > 2.5: return None, lag, 'book-late'
    return i, lag, 'ok'
def book_exit(tk, side, t, size, settle=None):
    """frozen walk of the recorded bid ladder (original lines 33-45). v2 --fill-remainder: an unfilled remainder is valued at `settle`
    (100 for a winner, 0 for a loser) and reported separately; 'price' is then the effective proceeds per contract over the whole size."""
    i, lag, status = book_lookup(tk, t)
    if i is None: return None   # no book for the ticker, or first book at/after t more than 2.5 s late (unconditional, as original)
    bs = BOOKS[tk]; ob = bs[i][2]; lad = sorted(ob.get('yes' if side == 'UP' else 'no') or [], key=lambda x: -x[0])
    if not lad: return {'price': None, 'filled': 0, 'src': 'book-empty', 'bookLagS': round(bs[i][0] - t, 2)}
    left = size; cash = 0.0
    for p, q in lad:
        take = min(left, q); cash += take * p; left -= take
        if left <= 0: break
    filled = size - left
    out = {'price': round(cash / filled, 3) if filled else None, 'filled': round(filled, 1), 'best': lad[0][0], 'bestSize': round(lad[0][1], 1), 'src': 'book', 'bookLagS': round(bs[i][0] - t, 2)}
    if OPT['fill_remainder'] and left > 0 and settle is not None and filled > 0:
        out['avgFilled'] = out['price']; out['remainder'] = round(left, 1); out['settle'] = settle
        out['price'] = round((cash + left * settle) / size, 3); out['src'] = 'book+settle'
    return out
def print_exit(P, side, t):   # frozen
    """lowest held-side price among taker-sell prints in [t, t+2]; else first print after t (within 10 s)."""
    if not P: return None
    held = (lambda yp: yp if side == 'UP' else 100 - yp)
    sells = [held(p) for (ts, p, q, s) in P if t <= ts <= t + 2 and ((side == 'UP' and s == 'no') or (side == 'DOWN' and s == 'yes'))]
    if sells: return {'price': min(sells), 'src': 'prints-sell', 'n': len(sells)}
    later = [(ts, held(p)) for (ts, p, q, s) in P if t <= ts <= t + 10 and ((side == 'UP' and s == 'no') or (side == 'DOWN' and s == 'yes'))]
    if later: return {'price': later[0][1], 'src': 'prints-next-sell', 'lagS': round(later[0][0] - t, 2)}
    return {'price': None, 'src': 'no-sell-print'}
def net_of(x, ask, n, hold_n):
    """net per contract (cents) at size n for an exit record x: frozen formula (original line 122) unless the record carries an unfilled
    remainder (--fill-remainder): then cash = filled part at its average + remainder at settlement, exit fee on the filled part only."""
    if x.get('price') is None: return None
    if x['src'] == 'settled': return round(hold_n, 3)
    if x.get('remainder'):
        f = x['filled']; cash = f * x['avgFilled'] + x['remainder'] * x['settle']
        return round((cash - n * ask - n * fee_checked(ask, n) - fee_checked(x['avgFilled'], f) * f) / n, 3)
    return round(x['price'] - ask - fee_checked(ask, n) - fee_checked(x['price'], n), 3)
def price_exit(tk, side, t, P, won, close):
    """v2: one exit at target time t, same precedence as original lines 118-121: book bid (first book at or after t by its own timestamp,
    at most 2.5 s late) else prints, 'settled' when t is at or after the close. --books-only: no price from prints."""
    settle = 100 if won else 0
    bx = book_exit(tk, side, t, 10, settle); px = print_exit(P, side, t)
    i, lag, status = book_lookup(tk, t)
    if bx is not None and bx.get('price') is None: status = 'book-empty'
    out = {'bookStatus': status}
    if bx and bx.get('price') is not None:
        out['price'], out['src'], out['bookLagS'] = bx['price'], bx['src'], bx['bookLagS']
        if bx.get('remainder'): out.update({'avgFilled': bx['avgFilled'], 'filled': bx['filled'], 'remainder': bx['remainder'], 'settle': bx['settle']})
    elif OPT['books_only']:
        out['price'] = None; out['src'] = 'unpriced:' + status + ('+print' if px and px.get('price') is not None else '')
        if px and px.get('price') is not None: out['printPrice'], out['printSrc'] = px['price'], px['src']
    else:
        out['price'] = px['price'] if px else None; out['src'] = px['src'] if px else 'none'
    if t >= close: out['price'], out['src'] = settle, 'settled'
    return out
TRIG = {'T1': 0.005, 'T2': 0.01, 'T3': 0.02, 'T4': 0.10}
DELAYS = [1, 2, 3, 5]; SIZES = [10, 100, 1000]
def build_entries(which, STATS):
    entries = []
    rule = (lambda pf: pf <= 0.002) if OPT['exact_entry'] else (lambda pf: pf < 0.0025)   # v2 --exact-entry
    if which == 'live':
        D = SC + '/r30/live/scoreboard'
        mk = {os.path.basename(p).split('.json')[0]: json.load(open(p)) for p in glob.glob(D + '/markets/*')}
        mkmt = {os.path.basename(p).split('.json')[0]: os.path.getmtime(p) for p in glob.glob(D + '/markets/*')}
        for p in sorted(glob.glob(D + '/rows/*.ndjson')):
            tk = os.path.basename(p)[:-7]; m = mk.get(tk)
            if OPT['as_of'] is not None and (close_ts(tk) > OPT['as_of'] or os.path.getmtime(p) > OPT['as_of'] or mkmt.get(tk, float('inf')) > OPT['as_of']):
                STATS['after-as-of'] += 1; continue   # v2 --as-of: the data on disk as of that time (close, rows file and result file)
            if not m or m.get('result') not in ('yes', 'no'): continue
            win = 'UP' if m['result'] == 'yes' else 'DOWN'; c = close_ts(tk)
            rs = sorted((json.loads(x) for x in open(p) if x.strip()), key=lambda r: -r['tau'])
            cand = (lambda f: next((i for i, r in enumerate(rs) if 0 < r['tau'] <= 120 and r.get('state') in ('LOCKED', 'PROVEN LOCKED') and r.get('pFlip') is not None and f(r['pFlip'])), None))
            ei = cand(rule); e0 = cand(lambda pf: pf < 0.0025)
            if e0 is not None: STATS['entry-' + ('dropped' if ei is None else ('kept' if ei == e0 else 'moved'))] += 1
            if ei is None: continue
            e = rs[ei]; side = e['side']
            ser = [(c - r['tau'], ((r['pFlip'] if r.get('side') == side else 1 - r['pFlip']) if (r.get('pFlip') is not None and r.get('state') not in ('DATA UNRELIABLE', 'AWAITING SETTLEMENT')) else None), r.get('state')) for r in rs[ei:] if 0 < r['tau'] <= 300]
            entries.append({'tk': tk, 'side': side, 'won': side == win, 'tEntry': c - e['tau'], 'tauEntry': e['tau'], 'ask': e.get('ask'), 'pf': e['pFlip'], 'series': ser, 'close': c, 'rows': rs})
    else:
        for f in glob.glob(R3 + '/series/usdt_1*.ndjson'):
            for l in open(f):
                m = json.loads(l)
                if m['entryTau'] is None or not os.path.exists('%s/kalshi_trades/%s.ndjson' % (R3, m['tk'])): continue
                c = m['closeTs']; side = m['side']; eTau, ePf = m['entryTau'], m['entryPf']
                if OPT['exact_entry']:   # v2: re-derive the entry on the recorded entry side; s[1] is that side's risk, s[2] the state
                    rows = sorted(m['series'], key=lambda s: -s[0])
                    hit = next((s for s in rows if 0 < s[0] <= 120 and s[2] in ('LOCK', 'PROV') and s[1] is not None and s[1] <= 0.002), None)
                    if hit is None: STATS['entry-dropped'] += 1; continue
                    STATS['entry-kept' if abs(hit[0] - eTau) < 1e-9 else 'entry-moved'] += 1; eTau, ePf = hit[0], hit[1]
                else: STATS['entry-kept'] += 1
                ser = [(c - s[0], (s[1] if s[2] not in ('DATA', 'AWAI') else None), s[2]) for s in m['series'] if 0 < s[0] <= eTau]   # s[1] is already the entry side's risk
                entries.append({'tk': m['tk'], 'side': side, 'won': side == m['truth'], 'tEntry': c - eTau, 'tauEntry': eTau, 'ask': None, 'pf': ePf, 'series': ser, 'close': c})
    return entries
def score(entries):
    res = []
    for e in entries:
        P = load_prints(e['tk']); side = e['side']
        held = (lambda yp: yp if side == 'UP' else 100 - yp)
        # entry price: recorded ask (live) or the lowest held-side ask-side print within 2 s of entry (replay-joined), else 99.8 default marked
        ask = e['ask']; asksrc = 'row'
        if ask is None and P:
            buys = [held(p) for (ts, p, q, s) in P if e['tEntry'] <= ts <= e['tEntry'] + 2 and ((side == 'UP' and s == 'yes') or (side == 'DOWN' and s == 'no'))]
            if buys: ask = max(buys); asksrc = 'prints-buy'
            else:
                anyp = [held(p) for (ts, p, q, s) in P if e['tEntry'] <= ts <= e['tEntry'] + 10]
                if anyp: ask = anyp[0]; asksrc = 'prints-next'
        if ask is None and e.get('rows'):
            nxt = next((r.get('ask') for r in e['rows'] if r.get('ask') is not None and e['tauEntry'] - 5 <= r['tau'] < e['tauEntry']), None)
            if nxt is not None: ask = nxt; asksrc = 'row+5s'
        if ask is None:
            res.append({'tk': e['tk'], 'side': side, 'won': e['won'], 'tauEntry': e['tauEntry'], 'ask': None, 'askSrc': 'none', 'pf': e['pf'], 'hold': None, 'trig': {}, 'hasBook': e['tk'] in BOOKS, 'hasPrints': bool(P), 'excluded': 'no entry price'}); continue
        hold = ((100 - ask) if e['won'] else -ask) - fee_checked(ask, 10)   # entry fee on both arms
        holdN = {str(n): round(((100 - ask) if e['won'] else -ask) - fee_checked(ask, n), 3) for n in SIZES}   # v2: per-size hold (n = 10 is the original's)
        rec = {'tk': e['tk'], 'side': side, 'won': e['won'], 'tauEntry': e['tauEntry'], 'ask': ask, 'askSrc': asksrc, 'pf': e['pf'], 'hold': round(hold, 3), 'holdN': holdN, 'trig': {}, 'hasBook': e['tk'] in BOOKS, 'hasPrints': bool(P)}
        # collapse time (losses): first held-side print below 95 after entry
        if P:
            bel = [ts for (ts, p, q, s) in P if ts > e['tEntry'] and held(p) < 95]
            rec['firstBelow95'] = round(bel[0] - e['tEntry'], 2) if bel else None
        ser = e['series']
        # T5: deteriorating (doubled within 3.5 s and > 0.2 %)
        det_t = None
        for i in range(1, len(ser)):
            t, f, s = ser[i]
            if f is None: continue
            ref = next((x for x in ser[:i] if x[0] >= t - 3.5 and x[1] is not None), None)
            if ref and f > 2 * ref[1] and f > 0.002: det_t = t; break
        for name, thr in list(TRIG.items()) + [('T5', None)]:
            if name == 'T5': tt = det_t; ftrig = None
            else:
                hit = next((x for x in ser[1:] if x[1] is not None and x[1] >= thr), None); tt = hit[0] if hit else None; ftrig = hit[1] if hit else None
            if tt is None: rec['trig'][name] = None; continue
            d_out = {'tTrig': round(tt - e['tEntry'], 2), 'pfTrig': ftrig, 'leadToBelow95': (round(rec['firstBelow95'] - (tt - e['tEntry']), 2) if rec.get('firstBelow95') is not None else None), 'delays': {}}
            for d in DELAYS:
                t = tt + d
                x = price_exit(e['tk'], side, t, P, e['won'], e['close'])
                net = net_of(x, ask, 10, hold)
                sizes = {}
                for n in SIZES:
                    b = book_exit(e['tk'], side, t, n, 100 if e['won'] else 0)
                    if b:
                        sizes[str(n)] = {'avg': b.get('avgFilled', b.get('price')), 'filled': b.get('filled')}
                        if b.get('remainder'): sizes[str(n)].update({'remainder': b['remainder'], 'settle': b['settle'], 'eff': b['price']})
                    if OPT['fill_remainder']:   # v2: per-size net; a print-priced exit is applied to every size (depth unverified)
                        if t >= e['close']: xs = {'price': 100 if e['won'] else 0, 'src': 'settled'}
                        elif b and b.get('price') is not None: xs = dict(b)
                        else: xs = {'price': x['price'] if not str(x['src']).startswith('unpriced') else None, 'src': x['src']}
                        sizes.setdefault(str(n), {})
                        sizes[str(n)]['src'] = xs['src']; sizes[str(n)]['net'] = net_of(xs, ask, n, holdN[str(n)])
                ex = {'price': x['price'], 'src': x['src'], 'net': net, 'sizes': sizes or None}
                for k in ('bookLagS', 'bookStatus', 'printPrice', 'printSrc', 'remainder', 'avgFilled', 'filled', 'settle'):
                    if k in x: ex[k] = x[k]
                d_out['delays'][str(d)] = ex
            rec['trig'][name] = d_out
        res.append(rec)
    return res
def summary(which, res):
    # summary: P2 on the SAME subset for hold and policy (entries whose exit is priced), plus a pessimistic variant where an unpriced
    # unnecessary exit is charged 1.0 c below the entry ask (and an unpriced loss exit counts as the hold outcome).
    # v2 --books-only: the all-entries line counts every unpriced exit as the hold outcome (win for a winner, full loss for a loss).
    L = ['PR9 %s set: %d entries (%d excluded: no entry price), %d lost; hold total over scored entries %.1f c/contract' % (which, len(res), sum(1 for r in res if r.get('excluded')), sum(1 for r in res if r['hold'] is not None and not r['won']), sum(r['hold'] for r in res if r['hold'] is not None))]
    scored = [r for r in res if r['hold'] is not None]
    for name in ['T1', 'T2', 'T3', 'T5', 'T4']:
        fired = [r for r in scored if r['trig'].get(name)]
        for d in DELAYS:
            sub_h = sub_p = 0.0; n_sub = 0; unpriced = 0; costs = []; saved = []; pess = 0.0; ashold = 0.0
            for r in scored:
                tr = r['trig'].get(name)
                if not tr: sub_h += r['hold']; sub_p += r['hold']; pess += r['hold']; ashold += r['hold']; n_sub += 1; continue
                x = tr['delays'][str(d)]
                if x['net'] is None:
                    unpriced += 1; pess += (r['hold'] - 1.0 - fee(r['ask'], 10) if r['won'] else r['hold']); ashold += r['hold']; continue
                sub_h += r['hold']; sub_p += x['net']; pess += x['net']; ashold += x['net']; n_sub += 1
                (costs if r['won'] else saved).append(x['net'] - r['hold'])
            allline = ('all entries, unpriced = hold outcome (win for a winner, full loss for a loss): policy %.1f c vs hold %.1f [original pessimistic formula %.1f]' % (ashold, sum(r['hold'] for r in scored), pess)) if OPT['books_only'] else ('pessimistic all entries: policy %.1f c vs hold %.1f' % (pess, sum(r['hold'] for r in scored)))
            L.append('  %s d=%ds: fired in %d of %d (%.1f %%), priced %d, unpriced %d | same-subset (%d entries): hold %.1f c, policy %.1f c, difference %+.1f | %s | unnecessary exits priced: n %d, cost median %s c, mean %s, worst %s | losses exited (gain vs hold): %s' % (
                name, d, len(fired), len(scored), 100 * len(fired) / max(1, len(scored)), len(fired) - unpriced, unpriced, n_sub, sub_h, sub_p, sub_p - sub_h, allline,
                len(costs), ('%.2f' % st.median(costs)) if costs else '—', ('%.2f' % (sum(costs) / len(costs))) if costs else '—', ('%.2f' % min(costs)) if costs else '—', ['%+.1f' % s_ for s_ in saved]))
    if OPT['fill_remainder']:   # v2: per-size totals (size 10 repeats the line above when no fill is partial)
        for n in SIZES:
            for name in ['T1', 'T2', 'T3', 'T5', 'T4']:
                for d in DELAYS:
                    sub_h = sub_p = 0.0; n_sub = 0; unpriced = 0; costs = []; saved = []; nbook = npart = nprint = 0
                    for r in scored:
                        tr = r['trig'].get(name); hn = r['holdN'][str(n)]
                        if not tr: sub_h += hn; sub_p += hn; n_sub += 1; continue
                        s_ = (tr['delays'][str(d)]['sizes'] or {}).get(str(n), {})
                        if s_.get('net') is None: unpriced += 1; continue
                        nbook += s_['src'] in ('book', 'book+settle'); npart += s_['src'] == 'book+settle'; nprint += str(s_['src']).startswith('prints')
                        sub_h += hn; sub_p += s_['net']; n_sub += 1
                        (costs if r['won'] else saved).append(s_['net'] - hn)
                    L.append('  [size %d] %s d=%ds: same-subset (%d entries): hold %.1f c, policy %.1f c, difference %+.1f | priced %d (book %d, of which partial fills with remainder at settlement %d; prints %d, depth unverified), unpriced %d | unnecessary exits priced: n %d, cost median %s c, mean %s, worst %s | losses exited (gain vs hold): %s' % (
                        n, name, d, n_sub, sub_h, sub_p, sub_p - sub_h, nbook + nprint, nbook, npart, nprint, unpriced, len(costs), ('%.2f' % st.median(costs)) if costs else '—', ('%.2f' % (sum(costs) / len(costs))) if costs else '—', ('%.2f' % min(costs)) if costs else '—', ['%+.1f' % s_ for s_ in saved]))
    lagtxt = (lambda x: (',lag+%.2fs' % x['bookLagS']) if OPT['min_book_lag'] and x.get('bookLagS') is not None and x['src'] != 'settled' else '')
    for r in scored:
        if not r['won']:
            L.append('LOSS %s side %s entry tau %.1f ask %s (%s) pf %.4f firstBelow95 %s | ' % (r['tk'], r['side'], r['tauEntry'], r['ask'], r['askSrc'], r['pf'], r.get('firstBelow95')) + ' | '.join('%s@%+.1fs lead %s: ' % (k, v['tTrig'], v['leadToBelow95']) + ', '.join('d%s %s(%s%s)' % (d, x['price'], x['src'][:9], lagtxt(x)) for d, x in v['delays'].items()) for k, v in r['trig'].items() if v))
    return L
def header(which, res, STATS):
    """v2, unconditional: run header with entry counts, exits by source per trigger and delay, book-lag check, fee check, and the
    mechanical reading of criteria P1-P4 at T2 d=3 (P5 is about the page, not evaluated here)."""
    scored = [r for r in res if r['hold'] is not None]; H = []
    H.append('## exit_eval_v2 %s set | flags: fill-remainder=%s books-only=%s exact-entry=%s min-book-lag=%s | as-of: %s | tape: %d tickers with books | entries with books %d, with prints %d' % (
        which, *['on' if OPT[k] else 'off' for k in ('fill_remainder', 'books_only', 'exact_entry', 'min_book_lag')],
        ('data on disk as of %s (%d markets closing or written later skipped)' % (datetime.datetime.fromtimestamp(OPT['as_of'], datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'), STATS['after-as-of'])) if OPT['as_of'] is not None else 'none (all markets on disk)',
        len(BOOKS), sum(1 for r in res if r['hasBook']), sum(1 for r in res if r['hasPrints'])))
    H.append('## entries %d: scored %d, excluded (no entry price) %d of which losses %d; losses scored %d | entry rule %s: markets with an entry under the original rule %d (kept %d, moved to a later row %d, dropped %d)' % (
        len(res), len(scored), sum(1 for r in res if r.get('excluded')), sum(1 for r in res if r.get('excluded') and not r['won']), sum(1 for r in scored if not r['won']),
        'pFlip <= 0.002' if OPT['exact_entry'] else 'pFlip < 0.0025', STATS['entry-kept'] + STATS['entry-moved'] + STATS['entry-dropped'], STATS['entry-kept'], STATS['entry-moved'], STATS['entry-dropped']))
    lags = []; neg = 0; late = collections.Counter(); srcs = collections.defaultdict(collections.Counter)
    for r in scored:
        for name, tr in r['trig'].items():
            if not tr: continue
            for d, x in tr['delays'].items():
                s = x['src']; cat = ('settled' if s == 'settled' else 'book' if s in ('book', 'book+settle') else 'prints' if s.startswith('prints') else 'unpriced')
                srcs[(name, d)][cat] += 1
                if cat == 'unpriced': srcs[(name, d)]['unpriced:' + s] += 1
                if cat == 'book': lags.append(x['bookLagS']); neg += x['bookLagS'] < 0
                if x.get('bookStatus') == 'book-late': late[(name, d)] += 1
    for name in ['T1', 'T2', 'T3', 'T5', 'T4']:
        for d in DELAYS:
            c = srcs[(name, str(d))]; tot = sum(v for k, v in c.items() if not k.startswith('unpriced:'))
            reasons = ', '.join('%s %d' % (k[9:], v) for k, v in sorted(c.items()) if k.startswith('unpriced:'))
            H.append('## exits %s d=%ds: fired %d | book %d | prints %d | settled %d | unpriced %d%s%s' % (name, d, tot, c['book'], c['prints'], c['settled'], c['unpriced'], (' (%s)' % reasons) if reasons else '', (' | books refused as >2.5 s late: %d' % late[(name, str(d))]) if late[(name, str(d))] else ''))
    H.append('## book-lag check (book own timestamp minus target time, all book-priced exits): n %d, min %s, median %s, max %s s; books used with a timestamp BEFORE the target: %d (must be 0); refusals of books >2.5 s late: %d' % (
        len(lags), ('%.2f' % min(lags)) if lags else '-', ('%.2f' % st.median(lags)) if lags else '-', ('%.2f' % max(lags)) if lags else '-', neg, sum(late.values())))
    if OPT['min_book_lag'] and lags:
        H.append('## book-lag distribution (s): ' + ', '.join('%s: %d' % (b, sum(1 for x in lags if lo <= x < hi)) for b, lo, hi in (('[0,0.5)', 0, 0.5), ('[0.5,1)', 0.5, 1), ('[1,1.5)', 1, 1.5), ('[1.5,2)', 1.5, 2), ('[2,2.5]', 2, 2.5001))))
    H.append('## fee check: %d fee evaluations, frozen float formula disagrees with exact cents in %d%s' % (FEECHK['n'], FEECHK['mismatch'], (' e.g. ' + ', '.join('p %.3f n %s: %.0f vs %.0f c' % c for c in FEECHK['cases'])) if FEECHK['cases'] else ''))
    # mechanical criteria at T2 d=3 (P1: any trigger, d=3)
    losses = [r for r in scored if not r['won']]; p1 = []
    for r in losses:
        best = None
        for k, v in r['trig'].items():
            if not v: continue
            x = v['delays']['3']
            if x['price'] is not None and x['src'] != 'settled' and (best is None or x['price'] > best[0]): best = (x['price'], k, x['src'])
        p1.append((r['tk'], best))
    H.append('## P1 (each loss exited at >= 90 c by some trigger at d=3): ' + ('; '.join('%s %s' % (tk[-11:], ('%.1f (%s %s) %s' % (b[0], b[1], b[2][:12], 'PASS' if b[0] >= 90 else 'FAIL')) if b else 'no priced exit FAIL') for tk, b in p1) if p1 else 'no losses') + ' => %s' % ('PASS' if p1 and all(b and b[0] >= 90 for _, b in p1) else 'FAIL'))
    def p234(size=None):
        sub_h = sub_p = 0.0; costs = []; nfired = 0; nunn = 0; npriced = 0; leads = []; notrig = 0
        for r in scored:
            tr = r['trig'].get('T2')
            hn = r['hold'] if size is None else r['holdN'][str(size)]
            if not tr:
                sub_h += hn; sub_p += hn
                if not r['won']: notrig += 1
                continue
            nfired += 1; nunn += r['won']
            x = tr['delays']['3']; net = x['net'] if size is None else ((x['sizes'] or {}).get(str(size), {}).get('net'))
            if not r['won']: leads.append(tr['leadToBelow95'])
            if net is None: continue
            npriced += x['src'] != 'settled'; sub_h += hn; sub_p += net   # a 'settled' exit (target at/after the close) is no market exit
            if r['won']: costs.append(hn - net)
        med = st.median(costs) if costs else None; rate = 100 * nunn / max(1, len(scored))   # rate: every unnecessary firing, priced or not
        tag = '' if size is None else ' size %d' % size
        if npriced == 0:
            out = ['## P2 (T2 d=3%s): NOT ASSESSABLE, no market-priced exit (fired %d, all unpriced or settled)' % (tag, nfired), '## P3 (T2 d=3%s): unnecessary exits %d of %d entries (%.1f %%), median cost NOT ASSESSABLE (none market-priced)' % (tag, nunn, len(scored), rate)]
        else:
            out = ['## P2 (T2 d=3%s, same-subset policy minus hold >= 0, %d fired of which %d priced): %+.1f c => %s' % (tag, nfired, npriced, sub_p - sub_h, 'PASS' if sub_p - sub_h >= 0 else 'FAIL'),
                   '## P3 (T2 d=3%s, unnecessary exits: median cost <= 1.0 c and <= 15 %% of entries): %d of %d entries (%.1f %%), priced %d, median cost %s c => %s' % (tag, nunn, len(scored), rate, len(costs), ('%.2f' % med) if med is not None else '-', ('PASS' if (med <= 1.0 and rate <= 15) else 'FAIL') if med is not None else 'NOT ASSESSABLE')]
        if size is None:
            ok = sum(1 for l in leads if l is not None and l >= 2); n = len(losses)
            out.append('## P4 (T2 precedes the first print < 95 c by >= 2 s in >= 2/3 of the losses): %d of %d losses (%d with no T2 step, %d with a step: leads %s) => %s' % (ok, n, notrig, len(leads), ['%s' % l for l in leads], 'PASS' if n and ok / n >= 2 / 3 else 'FAIL'))
        return out
    H += p234()
    if OPT['fill_remainder']:
        for n in SIZES: H += p234(n)
    H.append('## P5 (page implementation): not evaluated by this script')
    return H
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('which', choices=['live', 'replay']); ap.add_argument('out')
    for f in ('fill-remainder', 'books-only', 'exact-entry', 'min-book-lag'): ap.add_argument('--' + f, action='store_true')
    ap.add_argument('--as-of', default=None, help='live set: only markets closing at or before this UTC time (ISO 8601)')
    A = ap.parse_args()
    for k in ('fill_remainder', 'books_only', 'exact_entry', 'min_book_lag'): OPT[k] = bool(getattr(A, k))
    OPT['as_of'] = iso2s(A.as_of) if A.as_of else None
    which, outp = A.which, A.out
    load_books()
    STATS = collections.Counter()
    entries = build_entries(which, STATS)
    res = score(entries)
    json.dump({'set': which, 'n': len(res), 'flags': dict(OPT), 'entries': res}, open(outp, 'w'))
    L = summary(which, res); H = header(which, res, STATS)
    txt = '\n'.join(H + L) + '\n'
    open(outp.replace('.json', '.txt'), 'w').write(txt); print(txt, end='')
if __name__ == '__main__': main()
