import json, collections
from datetime import datetime, timezone
def iso(ms): return datetime.fromtimestamp(ms/1000,timezone.utc).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
rows=[json.loads(l) for l in open('tape_snapshot.ndjson') if l.strip()]; rows.sort(key=lambda r:r['ts'])
def budget(tau): return max(750,min(3000,100*tau))
L=[r for r in rows if r['out']['state'] in ('LOCKED','PROVEN LOCKED')]
print('LOCKED/PROVEN rows',len(L))
print('LOCKED with ageMs > staleBudgetMs(tau)=clamp(100*tau,750,3000):',sum(1 for r in L if r['ageMs']>budget((r['kal']['closeMs']-r['ts'])/1000)))
print('LOCKED with ageMs > 2500 (LOCK_VENUE_QUOTE_MAX_MS / INDEX_STALE_MS):',sum(1 for r in L if r['ageMs']>2500))
print('LOCKED with bookAge > 1500 (MAX_BOOK_AGE_MS):',sum(1 for r in L if r['ts']-r['obTs']>1500),[ (iso(r['ts']),r['out']['action']) for r in L if r['ts']-r['obTs']>1500])
print('LOCKED with BRTI receipt age > 2500 (BRTI_STALE_MS):',[(iso(r['ts']),r['ts']-r['brti']['last']['localTs'],r['out']['action']) for r in L if r['ts']-r['brti']['last']['localTs']>2500])
print('LOCKED with BRTI source age (ts-skew-sourceTs) > 2500:',sum(1 for r in L if (r['ts']-r['skew']['est'])-r['brti']['last']['sourceTs']>2500))
print('LOCKED with |skew|>1000:',sum(1 for r in L if abs(r['skew']['est'])>1000))
print('LOCKED with liveIdx null:',sum(1 for r in L if not r['liveIdx']),' all rows liveIdx null:',sum(1 for r in rows if not r['liveIdx']),' rows with <3 venues used:',sum(1 for r in rows if r['liveIdx'] and len(r['liveIdx']['used'])<3),collections.Counter(tuple(r['liveIdx']['used']) for r in rows if r['liveIdx']).most_common(4))
print('LOCKED with rest=true:',sum(1 for r in L if r['rest']))
# DATA UNRELIABLE causes (approx from inputs)
du=[r for r in rows if r['out']['state']=='DATA UNRELIABLE']
c=collections.Counter()
for r in du:
    tau=(r['kal']['closeMs']-r['ts'])/1000
    if r['ageMs']>budget(tau): c['ageMs>budget']+=1
    elif abs(r['skew']['est'])>1000: c['skew>1000']+=1
    elif not r['liveIdx']: c['no liveIdx']+=1
    else: c['other']+=1
print('DATA UNRELIABLE rows',len(du),dict(c))
# TRADE NOW rows: tau and book age
T=[r for r in rows if r['out'].get('action')=='TRADE NOW']
import statistics
print('TRADE NOW rows',len(T),'tau min/median/max',min((r['kal']['closeMs']-r['ts'])/1000 for r in T),statistics.median((r['kal']['closeMs']-r['ts'])/1000 for r in T),max((r['kal']['closeMs']-r['ts'])/1000 for r in T),'bookAge max',max(r['ts']-r['obTs'] for r in T))
# context of the two WS reconnects
for lo,hi in ((1794755615000,1794755628000),(1794757210000,1794757228000)):
    print('\n-- context',iso(lo),'-',iso(hi))
    for r in rows:
        if lo<=r['ts']<=hi:
            l=r['brti']['last']; print(' ',iso(r['ts'])[11:],r['out']['state'],'seq',l['seq'],'sourceTs',iso(l['sourceTs'])[11:19],'localTs',iso(l['localTs'])[11:],'brtiAge',r['ts']-l['localTs'],'send->local',l['localTs']-l['sendingTs'],'ageMs',r['ageMs'],'skew',r['skew']['est'])
# health-only: kalshi stale episode start
print('\nkalshi stale episode: lastAt',iso(1794739086899),'lastMs 234124 -> record not renewed from about',iso(1794739086899-234124-6000),'to',iso(1794739086899))
# rows during that period?
print('tape rows between those times:',sum(1 for r in rows if 1794739086899-240124<=r['ts']<=1794739086899))
# which window would it be: close
print('window close for 02:38 UTC:',iso(((1794739086899//900000)+1)*900000))
# per-second tape rows before stale: any gap in rows in the window closing at 02:45?
w=[r for r in rows if r['kal']['closeMs']==((1794739086899//900000)+1)*900000]
print('rows in window closing 02:45 UTC Nov 15:',len(w), 'first',iso(w[0]['ts']) if w else None)
