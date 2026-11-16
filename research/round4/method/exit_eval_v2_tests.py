"""Synthetic tests for exit_eval_v2.py (no data files touched). Run: python3 -I exit_eval_v2_tests.py
Covers: book_exit full fill; partial fill with the remainder valued at settlement (winner and loser; and the original's behaviour with
the flag off); empty ladder -> unpriced; no book / late book / book-before-target never used; print_exit fallback ordering;
price_exit precedence and --books-only; fee rounding (frozen formula vs exact cents, with the known float cases documented)."""
import importlib.util, os, sys, math
HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('exit_eval_v2', os.path.join(HERE, 'exit_eval_v2.py')); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
def reset(flags=None):
    for k in m.OPT: m.OPT[k] = False if k != 'as_of' else None
    for k in (flags or {}): m.OPT[k] = flags[k]
    m.BOOKS.clear(); m.BOOK_TS.clear(); m.FEECHK.update({'n': 0, 'mismatch': 0, 'cases': []})
def books(tk, *items):   # items: (obTs, ob)
    m.BOOKS[tk] = [(obTs, obTs + 0.4, ob) for obTs, ob in items]; m.index_books()
def close(a, b, eps=1e-9): return a is not None and b is not None and abs(a - b) <= eps
n_pass = 0
def ok(cond, name):
    global n_pass
    assert cond, 'FAIL: ' + name
    n_pass += 1; print('PASS', name)

# 1. full fill, both sides, best bid first, lag reported
reset(); books('TK', (1000.0, {'yes': [[98, 100], [99, 50]], 'no': [[1, 30], [2, 40]]}))
x = m.book_exit('TK', 'UP', 999.6, 10)
ok(x['src'] == 'book' and close(x['price'], 99.0) and x['filled'] == 10 and x['best'] == 99 and x['bestSize'] == 50 and close(x['bookLagS'], 0.4), 'book_exit full fill UP: 10 at the best YES bid 99, lag +0.4 s')
y = m.book_exit('TK', 'DOWN', 999.6, 10)
ok(close(y['price'], 2.0) and y['best'] == 2, 'book_exit full fill DOWN: NO bids in held-side cents, best 2')
z = m.book_exit('TK', 'UP', 999.6, 100)
ok(close(z['price'], (50 * 99 + 50 * 98) / 100) and z['filled'] == 100 and 'remainder' not in z, 'book_exit walks the ladder: 100 = 50@99 + 50@98, average 98.5')
hold10 = (100 - 99.8) - m.fee(99.8, 10)
ok(close(m.net_of({'price': 99.0, 'src': 'book'}, 99.8, 10, hold10), round(99.0 - 99.8 - 0.1 - 0.1, 3)), 'net_of frozen formula: 99.0 - 99.8 - entry fee 0.1 - exit fee 0.1 = -1.0')
ok(close(m.net_of({'price': 52.0, 'src': 'book'}, 99.4, 10, None), -49.3), 'net_of reproduces the recorded Nov 15 loss exit: 52.0 vs ask 99.4 -> -49.3')

# 2. partial fill: original behaviour (flag off) vs --fill-remainder (winner and loser)
reset(); books('TK', (1000.0, {'yes': [[99, 6]], 'no': []}))
x = m.book_exit('TK', 'UP', 1000.0, 10, settle=100)
ok(x['src'] == 'book' and close(x['price'], 99.0) and x['filled'] == 6 and 'remainder' not in x, 'flag off: partial fill 6 of 10 reported at the average of the FILLED part (99.0), no remainder (original behaviour)')
ok(close(m.net_of(x, 99.8, 10, hold10), -1.0), 'flag off: net prices all 10 contracts at 99.0 -> -1.0 (the defect the flag corrects)')
reset({'fill_remainder': True}); books('TK', (1000.0, {'yes': [[99, 6]], 'no': []}))
w = m.book_exit('TK', 'UP', 1000.0, 10, settle=100)
ok(w['src'] == 'book+settle' and close(w['avgFilled'], 99.0) and w['filled'] == 6 and w['remainder'] == 4 and w['settle'] == 100 and close(w['price'], 99.4), 'fill-remainder, winner: 6@99 + 4 at settlement 100 -> effective 99.4')
# cash 594 + 400 = 994; entry 10*99.8 = 998 + entry fee 1 c (ceil 0.1397); exit fee on 6 filled: ceil(0.07*6*0.99*0.01*100 = 0.4158) = 1 c
ok(close(m.net_of(w, 99.8, 10, hold10), round((994 - 998 - 1 - 1) / 10, 3)), 'fill-remainder, winner: net = (994 - 998 - 1 - 1)/10 = -0.6 c/contract, exit fee on the filled part only')
l = m.book_exit('TK', 'UP', 1000.0, 10, settle=0)
ok(l['src'] == 'book+settle' and close(l['price'], 59.4) and l['remainder'] == 4 and l['settle'] == 0, 'fill-remainder, loser: 6@99 + 4 at settlement 0 -> effective 59.4')
ok(close(m.net_of(l, 99.8, 10, (-99.8) - m.fee(99.8, 10)), round((594 - 998 - 1 - 1) / 10, 3)), 'fill-remainder, loser: net = (594 - 998 - 1 - 1)/10 = -40.6 c/contract')
books('TK', (1000.0, {'yes': [[99, 600], [98, 300]], 'no': []}))
b = m.book_exit('TK', 'UP', 1000.0, 1000, settle=100)
ok(b['filled'] == 900 and b['remainder'] == 100 and close(b['avgFilled'], round((600 * 99 + 300 * 98) / 900, 3)) and close(b['price'], round((600 * 99 + 300 * 98 + 100 * 100) / 1000, 3)), 'fill-remainder at size 1000: 600@99 + 300@98 + 100 at settlement (averages rounded to 3 decimals as in the original)')
f = m.book_exit('TK', 'UP', 1000.0, 100, settle=100)
ok(f['src'] == 'book' and 'remainder' not in f and close(f['price'], 99.0), 'fill-remainder: a complete fill is unchanged (src book, no remainder)')

# 3. empty ladder -> unpriced; no book, late book, book before the target never used; 2.5 s boundary
for flags in ({}, {'fill_remainder': True}):
    reset(flags); books('TK', (1000.0, {'yes': [], 'no': [[1, 5]]}))
    e = m.book_exit('TK', 'UP', 1000.0, 10, settle=100)
    ok(e['price'] is None and e['src'] == 'book-empty' and e['filled'] == 0, 'empty held-side ladder -> unpriced (book-empty), flags %s' % (flags or 'off'))
reset(); books('TK', (999.0, {'yes': [[90, 100]], 'no': []}), (1001.0, {'yes': [[80, 100]], 'no': []}))
u = m.book_exit('TK', 'UP', 1000.0, 10)
ok(close(u['price'], 80.0) and close(u['bookLagS'], 1.0), 'a book whose own timestamp precedes the target (999.0) is never used; the first book at/after 1000.0 is 1001.0 (lag +1.0)')
ok(m.book_exit('OTHER', 'UP', 1000.0, 10) is None, 'no book for the ticker -> None (caller falls back to prints)')
books('TK', (1003.0, {'yes': [[90, 100]], 'no': []}))
ok(m.book_exit('TK', 'UP', 1000.0, 10) is None and m.book_lookup('TK', 1000.0)[2] == 'book-late', 'first book 3.0 s after the target is refused (> 2.5 s)')
books('TK', (1002.5, {'yes': [[90, 100]], 'no': []}))
ok(m.book_exit('TK', 'UP', 1000.0, 10) is not None, 'a book exactly 2.5 s after the target is accepted (boundary as in the original)')
reset({'min_book_lag': True}); books('TK', (1000.4, {'yes': [[90, 100]], 'no': []}))
ok(close(m.book_exit('TK', 'UP', 1000.0, 10)['bookLagS'], 0.4), '--min-book-lag: lag carried on the record (numbers unchanged)')

# 4. print_exit fallback ordering (ts, yes cents, qty, taker_side); taker 'no' = a sale of YES into the YES bid
reset()
P = sorted([(100.2, 50.0, 1, 'yes'), (100.5, 99.0, 1, 'no'), (101.5, 98.5, 1, 'no'), (102.0, 99.5, 1, 'no'), (104.0, 97.5, 1, 'yes'), (108.0, 97.0, 1, 'no')])
r = m.print_exit(P, 'UP', 100.0)
ok(r['src'] == 'prints-sell' and close(r['price'], 98.5) and r['n'] == 3, 'prints: lowest taker-sell print in [t, t+2] (98.5 of 99.0/98.5/99.5); the buy print at 50 is ignored')
r = m.print_exit(P, 'UP', 103.0)
ok(r['src'] == 'prints-next-sell' and close(r['price'], 97.0) and close(r['lagS'], 5.0), 'prints: no sell in [t, t+2] -> first taker-sell within 10 s (108.0, lag 5.0); the buy print at 104 is ignored')
r = m.print_exit(P, 'UP', 200.0)
ok(r['price'] is None and r['src'] == 'no-sell-print', 'prints: nothing within 10 s -> no-sell-print')
ok(m.print_exit([], 'UP', 100.0) is None and m.print_exit(None, 'UP', 100.0) is None, 'prints: no prints file -> None')
r = m.print_exit(sorted([(100.5, 3.0, 1, 'yes'), (101.0, 2.0, 1, 'no')]), 'DOWN', 100.0)
ok(r['src'] == 'prints-sell' and close(r['price'], 97.0), 'DOWN hold: sells are taker-YES prints, held price 100 - yes (97.0); the taker-NO print is ignored')

# 5. price_exit precedence and --books-only
reset(); books('TK', (1000.0, {'yes': [], 'no': [[1, 5]]}))
Pz = [(1000.5, 94.8, 1, 'no')]
x = m.price_exit('TK', 'UP', 1000.0, Pz, True, 2000.0)
ok(x['src'] == 'prints-sell' and close(x['price'], 94.8) and x['bookStatus'] == 'book-empty', 'flag off: empty book ladder falls back to the print (94.8), as the original')
reset({'books_only': True}); books('TK', (1000.0, {'yes': [], 'no': [[1, 5]]}))
x = m.price_exit('TK', 'UP', 1000.0, Pz, True, 2000.0)
ok(x['price'] is None and x['src'] == 'unpriced:book-empty+print' and close(x['printPrice'], 94.8) and m.net_of(x, 99.8, 10, hold10) is None, '--books-only: a print-only exit is UNPRICED (print kept for reference)')
x = m.price_exit('NOBOOK', 'UP', 1000.0, Pz, True, 2000.0)
ok(x['price'] is None and x['src'] == 'unpriced:no-book+print', '--books-only: no book at all -> unpriced')
books('TK', (1000.0, {'yes': [[99, 50]], 'no': []}))
x = m.price_exit('TK', 'UP', 1000.0, Pz, True, 2000.0)
ok(x['src'] == 'book' and close(x['price'], 99.0), '--books-only: a book-priced exit is unchanged')
x = m.price_exit('TK', 'UP', 2000.0, Pz, False, 2000.0)
ok(x['src'] == 'settled' and x['price'] == 0 and close(m.net_of(x, 99.4, 10, -99.5), -99.5), 'target at/after the close -> settled at the outcome, net = hold')

# 6. fee rounding: frozen formula vs exact cents
reset()
ok(close(m.fee(99.8, 10), 0.1) and close(m.fee(99.9, 10), 0.1) and close(m.fee(52.0, 10), 1.8) and close(m.fee(50.0, 10), 1.8) and close(m.fee(99.9, 1000), 0.007), 'fee: 99.8/10 -> 1 c order (0.1 c/contract); 52.0/10 -> 17.47 -> 18 c; 50/10 -> 17.5 -> 18 c; 99.9/1000 -> 6.99 -> 7 c')
mism10 = [p / 10 for p in range(1, 1000) if abs(m.fee(p / 10, 10) - m.fee_exact(p / 10, 10)) > 1e-9]
ok(mism10 == [], 'fee: at size 10 the frozen float formula equals exact cents for every price 0.1..99.9')
mism = sorted((n, p) for n in (100, 1000) for p in range(1, 100) if abs(m.fee(float(p), n) - m.fee_exact(float(p), n)) > 1e-9)
ok(mism == [(100, 10), (100, 20), (100, 40), (100, 50), (100, 60), (100, 70), (100, 80), (1000, 70)], 'fee: documented float defect at sizes 100/1000 for round prices (e.g. n 100 p 10: exact 63 c, frozen 64 c); frozen formula kept, counted in the run header')
print('ALL %d TESTS PASSED' % n_pass)
