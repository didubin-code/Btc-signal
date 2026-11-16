"""Order-book precursor test (owner sections 4-5; hypothesis: in jump reversals the Kalshi book moves before the server's index).
Data: 1 Hz books in the tape for 107 windows (Nov 13-16), live rows for the displayed entry. For each window with a displayed entry
(pFlip < 0.0025, LOCKED, final 120 s): scan 1 Hz rows after entry while the server's entry-side risk is < 1 %: a SLIP = the held side's
best bid is >= 0.3 c below the maximum best bid of the previous 5 rows AND the top-of-book size is < 25 % of the median top size of the
previous 5 rows. Record whether a server risk step >= 1 % follows within 3 s / 10 s, the eventual outcome, and the best bid 1, 3 and
5 s after the slip (what selling on the slip would have fetched). Also the reverse: for every risk step >= 1 % after entry, was there a
slip in the 3 s before it (market led) or not (server led/same second)?"""
import json, glob, os, sys, statistics as st, bisect, collections
SC = '/tmp/claude-0/-home-user/97d7fe1d-a1f3-5240-8215-edf8d0a9a961/scratchpad'; L = SC + '/r30/live'; R3 = SC + '/round3'
books = collections.defaultdict(list)
for l in open(R3 + '/tape/tape_all.ndjson'):
    try: r = json.loads(l)
    except Exception: continue
    if r.get('k') != 'd' or not r.get('ob') or not r.get('obTs'): continue
    tk = (r.get('kal') or {}).get('ticker')
    if not tk: continue
    ob = r['ob']
    def best(side):
        lad = [(float(p), float(s)) for p, s in (ob.get(side) or []) if float(s) > 0]
        return max(lad) if lad else (None, None)
    yb, ys = best('yes'); nb, ns = best('no')
    out = r.get('out') or {}
    books[tk].append({'t': r['ts'] / 1000.0, 'yb': yb, 'ys': ys, 'nb': nb, 'ns': ns, 'pf': out.get('pFlip'), 'side': out.get('side'), 'st': out.get('state')})
for v in books.values(): v.sort(key=lambda x: x['t'])
mk = {os.path.basename(p)[:-5]: json.load(open(p)) for p in glob.glob(L + '/scoreboard/markets/*.json')}
def close_ts(tk):
    import datetime
    MON = {'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6, 'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12}
    s = tk.split('-')[1]; y, m, d, hh, mm = 2000 + int(s[:2]), MON[s[2:5]], int(s[5:7]), int(s[7:9]), int(s[9:11])
    return datetime.datetime(y, m, d, hh, mm, tzinfo=datetime.timezone.utc).timestamp() + 5 * 3600
slips = []; steps = []; nwin = 0
for tk, B in books.items():
    m = mk.get(tk)
    if not m or m.get('result') not in ('yes', 'no') or len(B) < 200: continue
    truth = 'UP' if m['result'] == 'yes' else 'DOWN'; c = close_ts(tk)
    # displayed entry from the tape's own decision rows (pf of the called side)
    ent = next((b for b in B if 0 < c - b['t'] <= 120 and b['st'] in ('LOCKED', 'PROVEN LOCKED') and b['pf'] is not None and b['pf'] < 0.0025), None)
    if not ent: continue
    nwin += 1; side = ent['side']; held_bid = (lambda b: b['yb'] if side == 'UP' else b['nb']); held_sz = (lambda b: b['ys'] if side == 'UP' else b['ns'])
    risk = lambda b: (b['pf'] if b['side'] == side else (1 - b['pf'])) if b['pf'] is not None else None
    after = [b for b in B if b['t'] > ent['t']]
    first_step = next((b for b in after if risk(b) is not None and risk(b) >= 0.01), None)
    for i, b in enumerate(after):
        if risk(b) is not None and risk(b) >= 0.01: break   # stop scanning slips once the server has stepped
        prev = [x for x in after[max(0, i - 5):i] if held_bid(x) is not None]
        if len(prev) < 3 or held_bid(b) is None: continue
        mx = max(held_bid(x) for x in prev); med_sz = st.median([held_sz(x) for x in prev if held_sz(x) is not None] or [0])
        if held_bid(b) <= mx - 0.3 and (held_sz(b) or 0) < 0.25 * med_sz:
            later = lambda d: next((held_bid(x) for x in after if x['t'] >= b['t'] + d and held_bid(x) is not None), None)
            step_in = next((x for x in after if x['t'] > b['t'] and risk(x) is not None and risk(x) >= 0.01), None)
            slips.append({'tk': tk, 'tau': c - b['t'], 'bid': held_bid(b), 'from': mx, 'size': held_sz(b), 'medsz': med_sz, 'won': side == truth, 'step_after_s': (step_in['t'] - b['t']) if step_in else None, 'bid1': later(1), 'bid3': later(3), 'bid5': later(5)})
    if first_step:
        pre = [x for x in after if first_step['t'] - 3 <= x['t'] < first_step['t'] and held_bid(x) is not None]
        before = [x for x in after if first_step['t'] - 8 <= x['t'] < first_step['t'] - 3 and held_bid(x) is not None]
        led = bool(pre and before and min(held_bid(x) for x in pre) <= max(held_bid(x) for x in before) - 0.3)
        steps.append({'tk': tk, 'tau': c - first_step['t'], 'risk': risk(first_step), 'won': side == truth, 'market_led': led, 'bid_at_step': held_bid(first_step), 'bid_3s_before': (max(held_bid(x) for x in before) if before else None)})
Ls = ['BOOK PRECURSOR TEST: %d windows with books and a displayed entry' % nwin]
Ls.append('SLIPS while the server still read < 1 %%: %d in %d windows; followed by a server step >= 1 %% within 3 s: %d, within 10 s: %d; windows won: %d of %d slips' % (len(slips), len(set(s['tk'] for s in slips)), sum(1 for s in slips if s['step_after_s'] is not None and s['step_after_s'] <= 3), sum(1 for s in slips if s['step_after_s'] is not None and s['step_after_s'] <= 10), sum(1 for s in slips if s['won']), len(slips)))
for s in slips: Ls.append('  slip %s tau %.0f: bid %.1f (from %.1f), size %.0f (median %.0f) | step after %s s | bid +1 s %s, +3 s %s, +5 s %s | won %s' % (s['tk'][-13:], s['tau'], s['bid'], s['from'], s['size'] or 0, s['medsz'], ('%.0f' % s['step_after_s']) if s['step_after_s'] is not None else 'none', s['bid1'], s['bid3'], s['bid5'], s['won']))
Ls.append('RISK STEPS >= 1 %% after a displayed entry: %d; market led (held bid fell >= 0.3 c in the 3 s before the step vs the 5 s before that): %d; server led or same second: %d' % (len(steps), sum(1 for s in steps if s['market_led']), sum(1 for s in steps if not s['market_led'])))
for s in steps: Ls.append('  step %s tau %.0f risk %.3f: bid at step %s, max bid 3-8 s before %s, market led %s, won %s' % (s['tk'][-13:], s['tau'], s['risk'], s['bid_at_step'], s['bid_3s_before'], s['market_led'], s['won']))
open(SC + '/round4/causal/book_precursor.txt', 'w').write('\n'.join(Ls) + '\n'); print('\n'.join(Ls))
