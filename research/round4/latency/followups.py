import json, collections
from datetime import datetime, timezone
def iso(ms): return datetime.fromtimestamp(ms/1000,timezone.utc).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
def pct(xs,p):
    xs=sorted(xs); k=(len(xs)-1)*p; f=int(k); c=min(f+1,len(xs)-1); return xs[f]+(xs[c]-xs[f])*(k-f)
def summ(n,xs):
    if not xs: print(n,'no data'); return
    print(f"{n}: n={len(xs)} min={min(xs):.0f} p50={pct(xs,.5):.0f} p95={pct(xs,.95):.0f} p99={pct(xs,.99):.0f} max={max(xs):.0f}")
rows=[json.loads(l) for l in open('tape_snapshot.ndjson') if l.strip()]
rows.sort(key=lambda r:r['ts'])
# by tau bucket
for lo,hi in ((0,120),(120,300)):
    sel=[r for r in rows if lo< (r['kal']['closeMs']-r['ts'])/1000 <=hi]
    print(f"\n-- tau in ({lo},{hi}] s: n={len(sel)}")
    summ(' bookAge ts-obTs',[r['ts']-r['obTs'] for r in sel])
    summ(' ageMs',[r['ageMs'] for r in sel])
    summ(' brtiAge ts-localTs',[r['ts']-r['brti']['last']['localTs'] for r in sel])
    summ(' idx age ts-idx.ts',[r['ts']-r['idx']['ts'] for r in sel])
    print(' TRADE NOW rows:',sum(1 for r in sel if r['out'].get('action')=='TRADE NOW'),'LOCKED rows:',sum(1 for r in sel if r['out']['state']=='LOCKED'))
# BRTI late rows
print('\n-- rows with BRTI age > 2000 ms (ts-localTs):')
late=[r for r in rows if r['ts']-r['brti']['last']['localTs']>2000]
print('count',len(late))
for r in late: 
    l=r['brti']['last']; print(' ',iso(r['ts']),r['kal']['ticker'],'brtiAge',r['ts']-l['localTs'],'seq',l['seq'],'src->local',l['localTs']-l['sourceTs'],'state',r['out']['state'],'ageMs',r['ageMs'])
print('\n-- rows with sendingTs->localTs > 300 ms:')
sl=[r for r in rows if r['brti']['last']['localTs']-r['brti']['last']['sendingTs']>300]
print('count',len(sl))
# group into episodes
eps=[]
for r in sl:
    if eps and r['ts']-eps[-1][-1]['ts']<=3000: eps[-1].append(r)
    else: eps.append([r])
print('episodes',len(eps))
for e in eps: print('  ',iso(e[0]['ts']),'->',iso(e[-1]['ts']),'n',len(e),'max send->local',max(x['brti']['last']['localTs']-x['brti']['last']['sendingTs'] for x in e),'states',collections.Counter(x['out']['state'] for x in e).most_common(2),'maxAgeMs',max(x['ageMs'] for x in e))
print('\n-- rows with sourceTs->receivedAt > 200 ms (CF->Kalshi):',sum(1 for r in rows if r['brti']['last']['receivedAt']-r['brti']['last']['sourceTs']>200))
# seq decreases
print('\n-- BRTI seq decreases:')
by=collections.defaultdict(list)
for r in rows: by[r['kal']['ticker']].append(r)
for t,rs in by.items():
    for a,b in zip(rs,rs[1:]):
        if b['brti']['last']['seq']<a['brti']['last']['seq']:
            print(' ',iso(a['ts']),a['brti']['last']['seq'],'->',iso(b['ts']),b['brti']['last']['seq'],'sourceTs',a['brti']['last']['sourceTs'],b['brti']['last']['sourceTs'],'values',a['brti']['last']['value'],b['brti']['last']['value'])
# skew outliers
print('\n-- skew.est > 500:')
for r in rows:
    if r['skew']['est']>500: print(' ',iso(r['ts']),r['skew'],'ageMs',r['ageMs'],'state',r['out']['state'],'warn',r['quality']['warnings'])
# first-use delay per BRTI tick
print('\n-- decision latency after a BRTI tick (first tape row using each seq, ts - localTs):')
first={}
for r in rows:
    s=r['brti']['last']['seq']
    if s not in first: first[s]=r['ts']-r['brti']['last']['localTs']
summ(' first-use delay',list(first.values()))
# fraction of rows whose BRTI tick is the current second's tick
cur=sum(1 for r in rows if (r['ts']//1000)*1000==r['brti']['last']['sourceTs'])
prev=sum(1 for r in rows if (r['ts']//1000)*1000-1000==r['brti']['last']['sourceTs'])
print(' rows using the tick of the same second:',cur,'previous second:',prev,'older:',len(rows)-cur-prev)
# ageMs in DATA UNRELIABLE rows and the hard reasons
du=[r for r in rows if r['out']['state']=='DATA UNRELIABLE']
print('\n-- DATA UNRELIABLE rows:',len(du))
reasons=collections.Counter()
for r in du:
    for h in (r['out'].get('hard') or r['out'].get('reasons') or []): reasons[h[:70]]+=1
print(reasons.most_common(10))
print(' ageMs of DATA UNRELIABLE rows: min',min(r['ageMs'] for r in du),'max',max(r['ageMs'] for r in du))
# out keys
print('\nout keys:',sorted(rows[0]['out'].keys()))
# LOCKED rows with ageMs > 2000 (near gate) listing
print('\n-- LOCKED rows with ageMs>1500:')
for r in rows:
    if r['out']['state']=='LOCKED' and r['ageMs']>1500: print(' ',iso(r['ts']),'ageMs',r['ageMs'],'bookAge',r['ts']-r['obTs'],'pFlip',r['out'].get('pFlip'),'soft',(r['out'].get('soft') or [])[:2])
print('\n-- LOCKED rows with bookAge>1500:')
for r in rows:
    if r['out']['state']=='LOCKED' and r['ts']-r['obTs']>1500: print(' ',iso(r['ts']),'bookAge',r['ts']-r['obTs'],'action',r['out'].get('action'))
# windows: count rows per window & tau coverage; plus how many windows per day
print('\nwindows per day:',collections.Counter(datetime.fromtimestamp(r['kal']['closeMs']/1000,timezone.utc).strftime('%m-%d') for r in {r['kal']['ticker']:r for r in rows}.values()))
