#!/usr/bin/env python3
"""Build feature files, tables.txt and rules.txt from per-chunk entry extracts.
Usage: python3 -I build.py <entries_dir> <out_dir>
"""
import sys, os, json, collections, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stats import clopper_pearson, quantile, median, fmt_rate, fmt_ci, binom_test_two_sided_ge

E, OUT = sys.argv[1], sys.argv[2]
RULES = ['R_disp', 'R_exact', 'R_lock', 'R_01', 'R_pfc']

# ---------- load ----------
wins = []
for fn in sorted(os.listdir(E)):
    if fn.endswith('.ndjson'):
        with open(os.path.join(E, fn)) as f:
            for ln in f:
                wins.append(json.loads(ln))
fam = collections.defaultdict(dict)
for w in wins:
    fam[w['family']][w['ticker']] = w
# de-duplicated market set: prefer usdc, fall back to usdt
dedup = dict(fam['usdt']); dedup.update(fam['usdc'])
n_from_usdc = sum(1 for w in dedup.values() if w['family'] == 'usdc')
SETS = collections.OrderedDict([
    ('dedup', list(dedup.values())),
    ('usdc', list(fam['usdc'].values())),
    ('usdt', list(fam['usdt'].values())),
])
for k in SETS: SETS[k].sort(key=lambda w: (w['closeTs'], w['ticker']))

# ---------- derived per-entry fields ----------
def side_sign(side): return 1 if side == 'UP' else -1

def enrich(w, e):
    """Add derived fields knowable at entry plus loss classification refinements."""
    s = side_sign(e['side'])
    strike = w['strike']
    e['c_eff_usd'] = round(e['cushion_usd'] + s * e['mu'], 2)            # basis-adjusted cushion: sc(gap + mu)
    e['c_eff_bps'] = round(e['c_eff_usd'] / strike * 1e4, 4)
    e['mu_signed_usd'] = round(s * e['mu'], 2)                            # mu in the direction of the call (+ helps the call)
    ac = e['cushion_usd']; am = abs(e['mu'])
    e['basis_reliance'] = 'c<=0 (feed on other side)' if ac <= 0 else ('0<c<=|mu|' if ac <= am else 'c>|mu|')
    # realized basis at the final trace row (tau=0.25): official - feed_final = marginUsd - gap_final
    if e['final_c_usd'] is not None:
        gap_final = s * e['final_c_usd']
        e['realized_basis_usd'] = round(w['marginUsd'] - gap_final, 2)
        e['basis_err_usd'] = round(e['realized_basis_usd'] - e['mu'], 2)  # realized minus estimated
    else:
        e['realized_basis_usd'] = None; e['basis_err_usd'] = None
    # refined loss classes
    if e['won']:
        e['loss_class_refined'] = None
    else:
        post_max_c = None
        # we only stored min/final; reconstruct 'feed ever on called side at/after entry' from entry cushion, final and min
        ever_called_side = (e['cushion_usd'] > 0) or (e['final_c_usd'] is not None and e['final_c_usd'] > 0)
        if e['crossed'] and ever_called_side:
            e['loss_class_refined'] = 'reversal (feed crossed strike after entry)'
        elif e['cushion_usd'] <= 0:
            e['loss_class_refined'] = 'basis (feed on other side at entry, lock carried by mu)'
        else:
            e['loss_class_refined'] = 'basis (feed stayed on called side)'
    return e

for w in wins:
    for r in RULES:
        if w['entries'][r]: enrich(w, w['entries'][r])

# ---------- bins ----------
def tau_bin(t):
    return '120' if t >= 119 else '90-119' if t >= 90 else '60-89' if t >= 60 else '30-59' if t >= 30 else '<30'
TAU_ORDER = ['120', '90-119', '60-89', '30-59', '<30']
def cush_bin(b):
    return '<5' if b < 5 else '5-10' if b < 10 else '10-20' if b < 20 else '20-40' if b < 40 else '>=40'
CUSH_ORDER = ['<5', '5-10', '10-20', '20-40', '>=40']
def cush_bin_fine(b):
    return '<=0' if b <= 0 else '0-2.5' if b < 2.5 else '2.5-5' if b < 5 else '5-10' if b < 10 else '10-20' if b < 20 else '20-40' if b < 40 else '>=40'
CUSHF_ORDER = ['<=0', '0-2.5', '2.5-5', '5-10', '10-20', '20-40', '>=40']
def dc_bin(d):
    if d is None: return 'n/a (no 20 s history)'
    return '< -5' if d < -5 else '-5..-1' if d < -1 else '-1..+1' if d <= 1 else '+1..+5' if d <= 5 else '> +5'
DC_ORDER = ['< -5', '-5..-1', '-1..+1', '+1..+5', '> +5', 'n/a (no 20 s history)']
def mu_bin(m):
    return '< -20' if m < -20 else '-20..-10' if m < -10 else '-10..-3' if m < -3 else '-3..+3' if m <= 3 else '> +3'
MU_ORDER = ['< -20', '-20..-10', '-10..-3', '-3..+3', '> +3']
def sfl_bin(x):
    if x is None: return 'n/a'
    return '<10' if x < 10 else '10-30' if x <= 30 else '>30'
SFL_ORDER = ['<10', '10-30', '>30', 'n/a']
def streak_bin(x):
    return '1-2' if x <= 2 else '3-5' if x <= 5 else '6-10' if x <= 10 else '>10'
STREAK_ORDER = ['1-2', '3-5', '6-10', '>10']
# sig quintile cuts from the de-duplicated R_disp entries (fixed for all tables)
sig_all = sorted(w['entries']['R_disp']['sig'] for w in SETS['dedup'] if w['entries']['R_disp'])
SIG_CUTS = [quantile(sig_all, q) for q in (0.2, 0.4, 0.6, 0.8)]
def sig_bin(s):
    for i, c in enumerate(SIG_CUTS):
        if s < c: return 'Q%d' % (i + 1)
    return 'Q5'
SIG_ORDER = ['Q1', 'Q2', 'Q3', 'Q4', 'Q5']
def ceff_usd_bin(u):
    return '<5 USD' if u < 5 else '5-10 USD' if u < 10 else '10-20 USD' if u < 20 else '20-50 USD' if u < 50 else '>=50 USD'
CEFFU_ORDER = ['<5 USD', '5-10 USD', '10-20 USD', '20-50 USD', '>=50 USD']
def rel_bin(e): return e['basis_reliance']
REL_ORDER = ['c<=0 (feed on other side)', '0<c<=|mu|', 'c>|mu|']

# ---------- feature files ----------
FEAT_KEYS = None
for rule in ('R_disp', 'R_exact'):
    path = os.path.join(OUT, 'features_%s.ndjson' % rule)
    n = 0
    with open(path, 'w') as f:
        for setname in ('usdc', 'usdt'):
            for w in SETS[setname]:
                e = w['entries'][rule]
                if not e: continue
                row = collections.OrderedDict()
                row['ticker'] = w['ticker']; row['closeTs'] = w['closeTs']
                row['closeUTC'] = datetime.datetime.fromtimestamp(w['closeTs'], datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
                row['family'] = w['family']; row['chunk'] = w['chunk']
                row['in_dedup'] = (dedup[w['ticker']]['family'] == w['family'])
                row['truth'] = w['truth']; row['strike'] = w['strike']; row['official'] = w['official']
                row['marginUsd'] = w['marginUsd']; row['marginBps'] = w['marginBps']
                row['rule'] = rule
                for k, v in e.items(): row[k] = v
                row['tau_bin'] = tau_bin(e['tau']); row['cushion_bin'] = cush_bin(e['cushion_bps']); row['dc20_bin'] = dc_bin(e['dc20_bps'])
                row['sig_bin'] = sig_bin(e['sig']); row['mu_bin'] = mu_bin(e['mu']); row['sfl_bin'] = sfl_bin(e['secs_since_first_locked'])
                f.write(json.dumps(row) + '\n'); n += 1
    print('wrote', path, n, 'rows')

# ---------- tables ----------
L = []
def P(s=''): L.append(s)

def table(ents, keyfn, order, title, show_class=False):
    groups = collections.OrderedDict((k, []) for k in order)
    for e in ents:
        k = keyfn(e)
        if k not in groups: groups[k] = []
        groups[k].append(e)
    P('  %s' % title)
    P('  %-28s %8s %7s %12s %22s %9s %7s%s' % ('bin', 'entries', 'losses', 'loss rate', '95% CI (exact)', 'E=sum pf', 'O/E', '   reversal/basis' if show_class else ''))
    for k, g in groups.items():
        n = len(g); k_loss = sum(1 for e in g if not e['won']); E_ = sum(e['pf'] for e in g)
        extra = ''
        if show_class:
            rv = sum(1 for e in g if not e['won'] and e['loss_class'] == 'reversal'); bs = k_loss - rv
            extra = '   %d/%d' % (rv, bs)
        P('  %-28s %8d %7d %12s %22s %9.2f %7s%s' % (k, n, k_loss, fmt_rate(k_loss, n), fmt_ci(k_loss, n) if n else 'n/a', E_, ('%.2f' % (k_loss / E_)) if E_ > 0 else 'n/a', extra))
    P()

P('# TABLES  (generated by scripts/build.py)')
P('# Entry rule: first trace row with tau <= 120 (the engine\'s "120 s left" row is tau=119.25), state LOCKED or PROVEN LOCKED,')
P('#   and the rule\'s pf condition. R_disp: pf < 0.0025; R_exact: pf <= 0.002. won = entry side == truth. E = sum of pf at entry.')
P('# Bins: tau "120" = entry at the first scanned row (tau=119.25, window already locked when the final 120 s begin);')
P('#   cushion = feed-only side-signed cushion in bps of strike (gap if UP else -gap; mu NOT included);')
P('#   dc20 = entry cushion minus cushion 20 s earlier (bps), n/a when the trace has no row 20 s before entry (entry tau > 104.25);')
P('#   sig quintile cuts (from de-duplicated R_disp entries): %s;' % ', '.join('%.4f' % c for c in SIG_CUTS))
P('#   mu = basis estimate (USD) as carried in the trace (engine locks on sign(gap + mu)); secs since first LOCKED uses the')
P('#   window-level firstLocked.tau from the .ndjson (may precede the 125-s trace).')
P('# Loss classes (task definition): reversal = lost and feed-only signed cushion < 0 at some row after entry; basis = lost, never < 0.')
P('#   NOTE: an entry whose feed-only cushion is already <= 0 at entry (lock carried by mu) counts as "reversal" under this strict')
P('#   definition even though the feed never crossed after entry; the refined classification below separates these.')
P('# 95% CI = Clopper-Pearson exact binomial interval for the loss rate.')
P()
P('De-duplicated set: %d markets (%d taken from usdc, %d from usdt). usdc family: %d windows; usdt family: %d windows.' % (
    len(dedup), n_from_usdc, len(dedup) - n_from_usdc, len(fam['usdc']), len(fam['usdt'])))
P('Every ticker is present in both families, so the de-duplicated set is identical to the usdc family; the usdt tables are the')
P('same markets seen through the BTC/USDT feed (a robustness check, NOT an independent sample).')
P()

for setname, ws in SETS.items():
    for rule in ('R_disp', 'R_exact'):
        ents = [w['entries'][rule] for w in ws if w['entries'][rule]]
        n = len(ents); k = sum(1 for e in ents if not e['won']); E_ = sum(e['pf'] for e in ents)
        P('=' * 110)
        Ec = sum(e['pfc'] for e in ents)
        P('SET=%s  RULE=%s   windows=%d  entries=%d (%.1f%% of windows)  losses=%d  loss rate %s  95%% CI %s  E=%.2f  O/E=%.2f  [E_pfc=%.2f O/E_pfc=%.2f]' % (
            setname, rule, len(ws), n, 100 * n / len(ws), k, fmt_rate(k, n), fmt_ci(k, n), E_, k / E_ if E_ else float('nan'), Ec, k / Ec if Ec else float('nan')))
        if setname == 'usdc':
            P('  (identical to the de-duplicated set: all tickers exist in both families and dedup prefers usdc)')
            P()
            continue
        rv = sum(1 for e in ents if not e['won'] and e['loss_class'] == 'reversal')
        P('  loss classes (strict task definition): reversal=%d basis=%d' % (rv, k - rv))
        rc = collections.Counter(e['loss_class_refined'] for e in ents if not e['won'])
        P('  loss classes (refined): %s' % '; '.join('%s=%d' % (a, b) for a, b in sorted(rc.items())))
        P()
        table(ents, lambda e: tau_bin(e['tau']), TAU_ORDER, 'by tau at entry (seconds left)', show_class=True)
        table(ents, lambda e: cush_bin(e['cushion_bps']), CUSH_ORDER, 'by feed-only cushion at entry (bps)')
        table(ents, lambda e: cush_bin_fine(e['cushion_bps']), CUSHF_ORDER, 'by feed-only cushion at entry (bps), finer at the low end')
        table(ents, lambda e: cush_bin(e['c_eff_bps']), CUSH_ORDER, 'by basis-adjusted cushion at entry (bps of strike; sc(gap+mu), the quantity the engine locks on)')
        table(ents, lambda e: ceff_usd_bin(e['c_eff_usd']), CEFFU_ORDER, 'by basis-adjusted cushion at entry in USD (basis error is a USD quantity)')
        table(ents, rel_bin, REL_ORDER, 'by basis reliance at entry (feed-only cushion c vs |mu|)')
        table(ents, lambda e: dc_bin(e['dc20_bps']), DC_ORDER, 'by pre-entry 20 s cushion change (bps)')
        table(ents, lambda e: dc_bin(e['dc10_bps']) if e['dc10_bps'] is not None else 'n/a (no 10 s history)', DC_ORDER[:-1] + ['n/a (no 10 s history)'], 'by pre-entry 10 s cushion change (bps)')
        table(ents, lambda e: sig_bin(e['sig']), SIG_ORDER, 'by sig quintile (Q1 lowest)')
        table(ents, lambda e: 'bk=%d' % e['bk'], ['bk=%d' % i for i in range(7)], 'by volatility bucket bk')
        table(ents, lambda e: 'bk changed in prev 30 s' if e['bk_changed_30'] else ('bk unchanged' if e['bk_changed_30'] is False else 'n/a'), ['bk unchanged', 'bk changed in prev 30 s', 'n/a'], 'by bk change in the previous 30 s')
        table(ents, lambda e: 'soft>0' if e['soft'] > 0 else 'soft=0', ['soft=0', 'soft>0'], 'by soft gate count at entry')
        table(ents, lambda e: 'hard>0' if e['hard'] > 0 else 'hard=0', ['hard=0', 'hard>0'], 'by hard gate count at entry')
        table(ents, lambda e: mu_bin(e['mu']), MU_ORDER, 'by mu (basis estimate, USD)')
        table(ents, lambda e: 'mu helps call (signed mu > 0)' if e['mu_signed_usd'] > 0 else ('mu = 0' if e['mu_signed_usd'] == 0 else 'mu opposes call (signed mu < 0)'), ['mu helps call (signed mu > 0)', 'mu = 0', 'mu opposes call (signed mu < 0)'], 'by direction of mu relative to the called side')
        table(ents, lambda e: sfl_bin(e['secs_since_first_locked']), SFL_ORDER, 'by seconds since the window\'s first LOCKED row')
        table(ents, lambda e: streak_bin(e['lock_streak_s']), STREAK_ORDER, 'by uninterrupted same-side LOCKED streak at entry (s, within trace)')
        table(ents, lambda e: 'prev-30s max entry-side risk >= 0.05' if (e['max_risk_prev30'] or 0) >= 0.05 else ('prev-30s max risk in [0.005,0.05)' if (e['max_risk_prev30'] or 0) >= 0.005 else 'prev-30s max risk < 0.005 (or no history)'), ['prev-30s max risk < 0.005 (or no history)', 'prev-30s max risk in [0.005,0.05)', 'prev-30s max entry-side risk >= 0.05'], 'by maximum entry-side risk in the 30 s before entry')
        table(ents, lambda e: datetime.datetime.fromtimestamp(e['_closeTs'], datetime.timezone.utc).strftime('%Y-%m') if '_closeTs' in e else 'n/a', [], 'by month (closeTs UTC)') if False else None
        # month table needs closeTs: build separately
        bym = collections.OrderedDict()
        for w in ws:
            e = w['entries'][rule]
            if not e: continue
            m = datetime.datetime.fromtimestamp(w['closeTs'], datetime.timezone.utc).strftime('%Y-%m')
            bym.setdefault(m, []).append(e)
        P('  by month (closeTs UTC)')
        P('  %-28s %8s %7s %12s %22s %9s %7s' % ('bin', 'entries', 'losses', 'loss rate', '95% CI (exact)', 'E=sum pf', 'O/E'))
        for m, g in bym.items():
            n_ = len(g); k_ = sum(1 for e in g if not e['won']); E2 = sum(e['pf'] for e in g)
            P('  %-28s %8d %7d %12s %22s %9.2f %7s' % (m, n_, k_, fmt_rate(k_, n_), fmt_ci(k_, n_), E2, ('%.2f' % (k_ / E2)) if E2 else 'n/a'))
        P()
        # loss class by tau bin (both definitions)
        P('  loss class by tau bin (strict task definition / refined); "silent" = loss whose entry-side risk never reached 0.005 after entry;')
        P('  E_pfc = sum of pfc (margin-inclusive flip risk) at entry, O/E_pfc = losses / E_pfc')
        P('  %-10s %8s %7s %10s %7s | %-30s %-28s %-14s %-7s | %8s %8s' % ('tau bin', 'entries', 'losses', 'reversal', 'basis', 'refined: reversal(crossed)', 'basis(feed other side@entry)', 'basis(stayed)', 'silent', 'E_pfc', 'O/E_pfc'))
        for tb in TAU_ORDER:
            g = [e for e in ents if tau_bin(e['tau']) == tb]; ls = [e for e in g if not e['won']]
            rv = sum(1 for e in ls if e['loss_class'] == 'reversal')
            r1 = sum(1 for e in ls if e['loss_class_refined'].startswith('reversal'))
            r2 = sum(1 for e in ls if 'other side' in e['loss_class_refined'])
            r3 = sum(1 for e in ls if 'stayed' in e['loss_class_refined'])
            sil = sum(1 for e in ls if (e['max_risk'] is None) or e['max_risk'] < 0.005)
            Ec = sum(e['pfc'] for e in g)
            P('  %-10s %8d %7d %10d %7d | %-30d %-28d %-14d %-7d | %8.2f %8s' % (tb, len(g), len(ls), rv, len(ls) - rv, r1, r2, r3, sil, Ec, ('%.2f' % (len(ls) / Ec)) if Ec else 'n/a'))
        P()
        # <30 s disproportion test
        g30 = [e for e in ents if e['tau'] < 30]; k30 = sum(1 for e in g30 if not e['won'])
        share_e = len(g30) / n if n else 0; share_l = k30 / k if k else 0
        pval = binom_test_two_sided_ge(k30, k, share_e) if k else None
        P('  <30 s-left class: %.1f%% of entries (%d/%d) but %.1f%% of losses (%d/%d); exact one-sided binomial P(X>=%d | n=%d, p=%.3f) = %.2e' % (
            100 * share_e, len(g30), n, 100 * share_l, k30, k, k30, k, share_e, pval if pval is not None else float('nan')))
        E30 = sum(e['pf'] for e in g30)
        P('  <30 s-left class O/E = %d / %.2f = %.2f ; rest O/E = %d / %.2f = %.2f' % (k30, E30, k30 / E30 if E30 else float('nan'), k - k30, E_ - E30, (k - k30) / (E_ - E30) if E_ - E30 else float('nan')))
        P()

# ---------- extra: per-month realized basis error (dedup, R_disp) ----------
P('=' * 110)
P('Realized basis check (de-duplicated set, R_disp entries): realized basis = official - feed at tau 0.25 = marginUsd - final gap;')
P('basis error = realized basis - mu (USD). Positive error means the official index came in higher than the estimate predicted.')
P('  %-8s %8s %9s %9s %9s %9s %9s %9s   %s' % ('month', 'entries', 'mu p50', 'real p50', 'err p05', 'err p50', 'err p95', '|err|p95', 'losses'))
for m, g in sorted(collections.defaultdict(list, {datetime.datetime.fromtimestamp(w['closeTs'], datetime.timezone.utc).strftime('%Y-%m'): None for w in SETS['dedup']}).items()):
    pass
for setname in ('dedup', 'usdt'):
    P('  [SET=%s]' % setname)
    bym = collections.defaultdict(list)
    for w in SETS[setname]:
        e = w['entries']['R_disp']
        if e and e['basis_err_usd'] is not None:
            bym[datetime.datetime.fromtimestamp(w['closeTs'], datetime.timezone.utc).strftime('%Y-%m')].append(e)
    for m, g in sorted(bym.items()):
        errs = [e['basis_err_usd'] for e in g]
        P('  %-8s %8d %9.2f %9.2f %9.2f %9.2f %9.2f %9.2f   %d' % (m, len(g), median([e['mu'] for e in g]), median([e['realized_basis_usd'] for e in g]),
            quantile(errs, 0.05), median(errs), quantile(errs, 0.95), quantile([abs(x) for x in errs], 0.95), sum(1 for e in g if not e['won'])))
    allerr = [abs(e['basis_err_usd']) for g in bym.values() for e in g]
    P('  all months: |basis error| p50=%.2f p90=%.2f p95=%.2f p99=%.2f USD (n=%d)' % (quantile(allerr, 0.5), quantile(allerr, 0.9), quantile(allerr, 0.95), quantile(allerr, 0.99), len(allerr)))
    # losses: basis-adjusted cushion vs realized basis error
    ls = [w['entries']['R_disp'] for w in SETS[setname] if w['entries']['R_disp'] and not w['entries']['R_disp']['won']]
    P('  losses (%d): basis-adjusted cushion at entry USD: median=%.2f, n with c_eff<10 USD=%d, <20 USD=%d | |basis error| median=%.2f, n with |err|>=c_eff=%d' % (
        len(ls), median([e['c_eff_usd'] for e in ls]), sum(1 for e in ls if e['c_eff_usd'] < 10), sum(1 for e in ls if e['c_eff_usd'] < 20),
        median([abs(e['basis_err_usd']) for e in ls if e['basis_err_usd'] is not None]), sum(1 for e in ls if e['basis_err_usd'] is not None and abs(e['basis_err_usd']) >= e['c_eff_usd'])))
    for cls in sorted(set(e['loss_class_refined'] for e in ls)):
        g = [e for e in ls if e['loss_class_refined'] == cls]
        P('    %-62s n=%2d  c_eff_usd median=%6.2f  |basis err| median=%6.2f  silent(max risk<0.005)=%d' % (cls, len(g), median([e['c_eff_usd'] for e in g]),
            median([abs(e['basis_err_usd']) for e in g if e['basis_err_usd'] is not None]) if any(e['basis_err_usd'] is not None for e in g) else float('nan'), sum(1 for e in g if e['max_risk'] is None or e['max_risk'] < 0.005)))
    P()
with open(os.path.join(OUT, 'tables.txt'), 'w') as f: f.write('\n'.join(L) + '\n')
print('wrote tables.txt', len(L), 'lines')

# ---------- rules.txt ----------
R = []
def Q(s=''): R.append(s)
Q('# RULES  (generated by scripts/build.py)')
Q('# De-duplicated set (= usdc family; every ticker exists in both families). Entry = first trace row with tau <= 120')
Q('# (tau=119.25 is the engine\'s "120 s left" row), state LOCKED/PROVEN LOCKED and the rule condition:')
Q('#   R_disp pf<0.0025 | R_exact pf<=0.002 | R_lock any LOCKED row | R_01 pf<=0.001 | R_pfc pfc<=0.001.')
Q('# 95% CI = Clopper-Pearson exact. E = sum of pf at entry (given for all rules; the task asks for it on R_disp/R_exact).')
Q()
for setname in SETS:
    ws = SETS[setname]
    Q('SET=%s (%d windows)' % (setname, len(ws)) + ('   [identical to dedup]' if setname == 'usdc' else ''))
    Q('  %-8s %8s %7s %12s %24s %10s %7s %12s %10s %12s' % ('rule', 'entries', 'losses', 'loss rate', '95% CI (exact)', 'E=sum pf', 'O/E', 'median tau', 'share win', 'median cush'))
    for rule in RULES:
        ents = [w['entries'][rule] for w in ws if w['entries'][rule]]
        n = len(ents); k = sum(1 for e in ents if not e['won']); E_ = sum(e['pf'] for e in ents)
        Q('  %-8s %8d %7d %12s %24s %10.2f %7.2f %12.2f %9.1f%% %9.1f bps' % (rule, n, k, fmt_rate(k, n), fmt_ci(k, n), E_, k / E_ if E_ else float('nan'),
            median([e['tau'] for e in ents]), 100 * n / len(ws), median([e['cushion_bps'] for e in ents])))
    Q()
    if setname == 'usdc': continue
    # R_disp cross table by tau bin
    ents = [w['entries']['R_disp'] for w in ws if w['entries']['R_disp']]
    Q('  R_disp entries by tau bin (SET=%s)' % setname)
    Q('  %-10s %8s %7s %12s %24s %10s %7s %10s %8s' % ('tau bin', 'entries', 'losses', 'loss rate', '95% CI (exact)', 'E=sum pf', 'O/E', 'reversal', 'basis'))
    for tb in TAU_ORDER:
        g = [e for e in ents if tau_bin(e['tau']) == tb]; k_ = sum(1 for e in g if not e['won']); E2 = sum(e['pf'] for e in g)
        rv = sum(1 for e in g if not e['won'] and e['loss_class'] == 'reversal')
        Q('  %-10s %8d %7d %12s %24s %10.2f %7s %10d %8d' % (tb, len(g), k_, fmt_rate(k_, len(g)), fmt_ci(k_, len(g)), E2, ('%.2f' % (k_ / E2)) if E2 else 'n/a', rv, k_ - rv))
    Q()
    # no-entry-under-30 variant
    v = [e for e in ents if e['tau'] >= 30]; kv = sum(1 for e in v if not e['won']); Ev = sum(e['pf'] for e in v)
    Q('  R_disp variant "no entry under 30 s left" (drop entries whose first qualifying row has tau < 30; such windows get no entry):')
    Q('    entries=%d (%.1f%% of windows; %d entries dropped) losses=%d loss rate %s 95%% CI %s E=%.2f O/E=%.2f median tau=%.2f' % (
        len(v), 100 * len(v) / len(ws), n - len(v) if False else len(ents) - len(v), kv, fmt_rate(kv, len(v)), fmt_ci(kv, len(v)), Ev, kv / Ev if Ev else float('nan'), median([e['tau'] for e in v])))
    # also other cut-offs for context
    for cut in (10, 20, 45, 60):
        v2 = [e for e in ents if e['tau'] >= cut]; k2 = sum(1 for e in v2 if not e['won']); E3 = sum(e['pf'] for e in v2)
        Q('    (context) no entry under %2d s: entries=%d losses=%d loss rate %s 95%% CI %s O/E=%.2f' % (cut, len(v2), k2, fmt_rate(k2, len(v2)), fmt_ci(k2, len(v2)), k2 / E3 if E3 else float('nan')))
    Q()
    # same for R_exact for completeness
    ents2 = [w['entries']['R_exact'] for w in ws if w['entries']['R_exact']]
    v = [e for e in ents2 if e['tau'] >= 30]; kv = sum(1 for e in v if not e['won']); Ev = sum(e['pf'] for e in v)
    Q('  R_exact variant "no entry under 30 s left": entries=%d losses=%d loss rate %s 95%% CI %s E=%.2f O/E=%.2f' % (len(v), kv, fmt_rate(kv, len(v)), fmt_ci(kv, len(v)), Ev, kv / Ev if Ev else float('nan')))
    Q()
    # overlap of losses between rules
    Q('  Loss tickers by rule (SET=%s):' % setname)
    for rule in RULES:
        ls = sorted(w['ticker'] for w in ws if w['entries'][rule] and not w['entries'][rule]['won'])
        Q('    %-8s %d: %s' % (rule, len(ls), ' '.join(ls)))
    Q()
# cross-family agreement on R_disp losses
lu = set(w['ticker'] for w in SETS['usdc'] if w['entries']['R_disp'] and not w['entries']['R_disp']['won'])
lt = set(w['ticker'] for w in SETS['usdt'] if w['entries']['R_disp'] and not w['entries']['R_disp']['won'])
Q('R_disp losses: usdc=%d usdt=%d in both feeds=%d usdc-only=%d usdt-only=%d' % (len(lu), len(lt), len(lu & lt), len(lu - lt), len(lt - lu)))
Q('  usdc-only: %s' % ' '.join(sorted(lu - lt)))
Q('  usdt-only: %s' % ' '.join(sorted(lt - lu)))
with open(os.path.join(OUT, 'rules.txt'), 'w') as f: f.write('\n'.join(R) + '\n')
print('wrote rules.txt', len(R), 'lines')
