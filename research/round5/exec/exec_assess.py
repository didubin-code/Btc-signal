"""R5-4: opportunity and execution on the live record (observer primary-rule entries, Nov 2-16). Subsets, recorded prices/sizes/
freshness, losses per subset, hypothetical results under stated assumptions. usage: python3 -I exec_assess.py <cohorts.json> <out.txt>"""
import sys, json, math, random, statistics as st, collections
L = json.load(open(sys.argv[1]))['live']; outp = sys.argv[2]
def fee_cents_per_contract(ask_cents, C):   # server default (lines 1429-1431): ceil(7 * C * P * (1 - P)) cents per order / C, P in dollars
    P = ask_cents / 100.0; return math.ceil(7 * C * P * (1 - P) - 1e-9) / C
def pnl(e, C):
    if e['ask'] is None or e['won'] is None: return None
    f = fee_cents_per_contract(e['ask'], C)
    return (100 - e['ask'] - f) if e['won'] else (-e['ask'] - f)
out = []; P = out.append
P('LIVE OPPORTUNITY AND EXECUTION (observer primary rule v1, production rows; %d entries %s .. %s)' % (len(L), L[0]['close'], L[-1]['close']))
P('Definitions: "offer" = the observer\'s recorded best ask on the called side from the last Kalshi book received BEFORE the signal (never after; stale > 3 s = unavailable);')
P('  "no offer" = the called side had no ask (empty ladder) or the book was unavailable; size = contracts at that best ask as recorded (sizeAtAsk); freshness = bookAgeMs.')
P('  Fee: the production default (Kalshi taker 0.07: ceil(7 * C * P * (1-P)) cents per order, divided by C contracts; 1 contract at 99.8 c pays 1 c, 100 contracts pay 0.02 c each).')
P('  Hypothetical result = buy C contracts at the recorded best ask at the signal if size >= C, hold to settlement; +(100 - ask) - fee per contract if won, -(ask) - fee if lost. Historical, not a forecast.')
subsets = collections.OrderedDict()
subsets['all qualifying entries'] = L
subsets['offer recorded (any price)'] = [e for e in L if e['ask'] is not None]
subsets['offer <= 99.9 c'] = [e for e in L if e['ask'] is not None and e['ask'] <= 99.9]
subsets['offer <= 99.9 c and size >= 10 contracts'] = [e for e in L if e['ask'] is not None and e['ask'] <= 99.9 and (e['size'] or 0) >= 10]
subsets['offer <= 99.9 c and size >= 100 contracts'] = [e for e in L if e['ask'] is not None and e['ask'] <= 99.9 and (e['size'] or 0) >= 100]
subsets['offer <= 99.5 c'] = [e for e in L if e['ask'] is not None and e['ask'] <= 99.5]
subsets['no offer recorded'] = [e for e in L if e['ask'] is None]
P(''); P('A. SUBSETS: entries, losses, price and freshness')
for name, S in subsets.items():
    asks = sorted(e['ask'] for e in S if e['ask'] is not None); ages = sorted(e['bookAge'] for e in S if e['bookAge'] is not None); sizes = sorted(e['size'] for e in S if e['size'] is not None)
    q = lambda v, p: v[int(p * (len(v) - 1))] if v else float('nan')
    P('  %-46s n=%4d lost=%d | ask median %.1f (p10 %.1f, p90 %.1f) | share >= 99.5: %s | size median %s contracts | bookAge median %s ms (p90 %s) | $1000 fillable: %d of %d' % (
        name, len(S), sum(1 for e in S if e['won'] is False), q(asks, .5), q(asks, .1), q(asks, .9), ('%.0f %%' % (100 * sum(1 for a in asks if a >= 99.5) / len(asks))) if asks else '-',
        ('%.0f' % q(sizes, .5)) if sizes else '-', ('%.0f' % q(ages, .5)) if ages else '-', ('%.0f' % q(ages, .9)) if ages else '-', sum(1 for e in S if e['fillable']), sum(1 for e in S if e['fillable'] is not None)))
P(''); P('B. BY SECONDS LEFT (offer availability and losses)')
for lab, lo, hi in [('0-29.99', 0, 29.999), ('30-59.99', 30, 59.999), ('60-89.99', 60, 89.999), ('90-120', 90, 120)]:
    S = [e for e in L if lo <= e['tau'] <= hi]; O = [e for e in S if e['ask'] is not None and e['ask'] <= 99.9]
    P('  tau %-9s entries %4d (lost %d) | with offer <= 99.9: %4d (%.0f %%; lost %d) | no offer: %3d | ask median among offers %s' % (lab, len(S), sum(1 for e in S if e['won'] is False), len(O), 100 * len(O) / max(1, len(S)), sum(1 for e in O if e['won'] is False), sum(1 for e in S if e['ask'] is None), ('%.1f' % st.median([e['ask'] for e in O])) if O else '-'))
P(''); P('C. HYPOTHETICAL RESULTS (cents per contract, summed over the subset; day-block bootstrap 90 %% interval over the %d calendar days; one entry per window)' % len({e['close'][:10] for e in L}))
random.seed(20261116)
for name in ['offer recorded (any price)', 'offer <= 99.9 c', 'offer <= 99.9 c and size >= 10 contracts', 'offer <= 99.9 c and size >= 100 contracts', 'offer <= 99.5 c']:
    S = subsets[name]
    for C in (1, 10, 100):
        E = [e for e in S if (e['size'] or 0) >= C]; vals = [pnl(e, C) for e in E]; vals = [v for v in vals if v is not None]
        if not vals: P('  %-46s C=%3d: no fillable entries' % (name, C)); continue
        days = collections.defaultdict(list)
        for e, v in zip([e for e in E if pnl(e, C) is not None], vals): days[e['close'][:10]].append(v)
        dk = list(days); boots = []
        for _ in range(4000):
            smp = [random.choice(dk) for _ in dk]; boots.append(sum(sum(days[d]) for d in smp) / sum(len(days[d]) for d in smp))
        boots.sort()
        P('  %-46s C=%3d: fillable entries %4d, lost %d, total %+8.1f c/contract, mean %+.3f c per entry (90 %% day-bootstrap %+.3f .. %+.3f), fees %.3f c/entry, gross wins %+.1f, gross losses %+.1f' % (
            name, C, len(vals), sum(1 for e in E if e['won'] is False), sum(vals), sum(vals) / len(vals), boots[int(0.05 * len(boots))], boots[int(0.95 * len(boots))],
            sum(fee_cents_per_contract(e['ask'], C) for e in E) / len(E), sum(100 - e['ask'] for e in E if e['won']), -sum(e['ask'] for e in E if e['won'] is False)))
P(''); P('D. BREAK-EVEN (arithmetic, not a forecast): at ask a cents the win pays 100 - a - fee and the loss costs a + fee; the loss frequency at which the sum is zero is (100 - a - fee) / 100.')
for a in (99.0, 99.5, 99.8, 99.9):
    for C in (1, 100): P('  ask %.1f c, C=%d: fee %.3f c/contract -> break-even loss frequency %.3f %% (1 in %.0f)' % (a, C, fee_cents_per_contract(a, C), 100 - a - fee_cents_per_contract(a, C), 100 / max(1e-9, 100 - a - fee_cents_per_contract(a, C))))
P(''); P('E. THE THREE LOSSES: ' + ' | '.join('%s tau %.1f ask %s size %s bookAge %s fillable %s' % (e['tk'][-14:], e['tau'], e['ask'], e['size'], e['bookAge'], e['fillable']) for e in L if e['won'] is False))
open(outp, 'w').write('\n'.join(out) + '\n'); print('\n'.join(out))
