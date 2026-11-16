import json, collections
from datetime import datetime, timezone
base='/tmp/claude-0/-home-user/97d7fe1d-a1f3-5240-8215-edf8d0a9a961/scratchpad/incident_20261114T0015Z/owner_evidence/'
def iso(ms): return datetime.fromtimestamp(ms/1000,timezone.utc).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
def pct(xs,p):
    xs=sorted(xs); k=(len(xs)-1)*p; f=int(k); c=min(f+1,len(xs)-1); return xs[f]+(xs[c]-xs[f])*(k-f)
t=json.load(open(base+'tape.json'))
rows=t['rows']; print('owner tape rows:',len(rows),'records field:',t['records'],'samples',t['samples'],'dropped',t['dropped'])
sh=collections.Counter(tuple(sorted(r.keys())) for r in rows)
for k,v in sh.most_common(): print(v,k)
k_rows=[r for r in rows if r.get('k')!='s']
print('non-sample rows:',len(k_rows),'k values:',collections.Counter(r.get('k') for r in rows))
tss=sorted(r['ts'] for r in k_rows)
print('ts range',iso(tss[0]),iso(tss[-1]))
tick=collections.Counter(r['kal']['ticker'] for r in k_rows); print('tickers:',tick)
# shape of brti
print('brti sample:',json.dumps(k_rows[0]['brti'])[:400])
print('row0 keys:',sorted(k_rows[0].keys()))
print('skew/rest/ageMs/obTs present:',[k in k_rows[0] for k in ('skew','rest','ageMs','obTs','idx','liveIdx')])
# metrics over the whole owner tape (300 rows)
src2recv=[];send2local=[];brtiAge=[];ageMs=[];bookAge=[];gaps=[]
for r in k_rows:
    l=(r.get('brti') or {}).get('last')
    if l: src2recv.append(l['receivedAt']-l['sourceTs']); send2local.append(l['localTs']-l['sendingTs']); brtiAge.append(r['ts']-l['localTs'])
    ageMs.append(r['ageMs']); bookAge.append(r['ts']-r['obTs'])
for a,b in zip(tss,tss[1:]): gaps.append(b-a)
def summ(n,xs): print(f"{n}: n={len(xs)} min={min(xs)} p50={pct(xs,.5):.0f} p95={pct(xs,.95):.0f} max={max(xs)}")
summ('owner tape src->recv',src2recv); summ('owner tape send->local',send2local); summ('owner tape brtiAge',brtiAge); summ('owner tape ageMs',ageMs); summ('owner tape bookAge',bookAge); summ('owner tape row gaps',gaps)
print('gaps>1500:',[(iso(a),b-a) for a,b in zip(tss,tss[1:]) if b-a>1500])
print('\n== window B rows 00:13:25-00:13:40 ==')
print('ts | tau | state | side | pFlip | brti.value | src->recv | recv->send | send->local | brtiAge | seq | amended | ageMs | bookAge | idx | liveIdx | skew | rest | grade | warnings | hard')
win=[r for r in k_rows if 1794622405000<=r['ts']<=1794622420999]
print('rows in window:',len(win))
for r in sorted(k_rows,key=lambda r:r['ts']):
    if 1794622395000<=r['ts']<=1794622425999:
        l=r['brti']['last']; o=r['out']
        print(iso(r['ts']),round((r['kal']['closeMs']-r['ts'])/1000,1),o['state'],o.get('side'),round(o.get('pFlip',0),5),l['value'],l['receivedAt']-l['sourceTs'],l['sendingTs']-l['receivedAt'],l['localTs']-l['sendingTs'],r['ts']-l['localTs'],l['seq'],l['amended'],r['ageMs'],r['ts']-r['obTs'],round(r['idx']['value'],2),round(r['liveIdx']['value'],2) if r.get('liveIdx') else None,r['skew']['est'],r['rest'],r['quality']['grade'],r['quality']['warnings'],o.get('hard') or o.get('reasons'))
# seq checks within owner tape
srt=sorted(k_rows,key=lambda r:r['ts'])
same=0;dec=0;jump=[]
for a,b in zip(srt,srt[1:]):
    la=a['brti']['last']; lb=b['brti']['last']; ds=lb['seq']-la['seq']; dt=(b['ts']-a['ts'])/1000
    if ds==0: same+=1
    if ds<0: dec+=1
    if ds>dt+1.5: jump.append((iso(a['ts']),ds,dt))
print('owner tape: same-seq consecutive',same,'seq decreases',dec,'seq jumps',jump[:5],'amended rows',sum(1 for r in k_rows if r['brti']['last']['amended']))
print('states in owner tape:',collections.Counter(r['out']['state'] for r in k_rows))
# LOCKED coexisting with old inputs in the owner tape
print('owner LOCKED rows with ageMs>2500:',sum(1 for r in k_rows if r['out']['state']=='LOCKED' and r['ageMs']>2500),'bookAge>1500:',sum(1 for r in k_rows if r['out']['state']=='LOCKED' and r['ts']-r['obTs']>1500),'brtiAge>2500:',sum(1 for r in k_rows if r['out']['state']=='LOCKED' and r['ts']-r['brti']['last']['localTs']>2500))
# incident signals: page poll cadence (via=radar) and first REVERSAL WARNING served
s=json.load(open(base+'incident-signals.json'))
sig=s.get('signals') or s.get('rows') or s
print('\nincident-signals keys:',list(s.keys()) if isinstance(s,dict) else type(s),'n',len(sig))
print('signal keys:',sorted(sig[0].keys()))
rad=sorted([x for x in sig if x.get('via')=='radar'],key=lambda x:x['ts'])
bg=sorted([x for x in sig if x.get('via')!='radar'],key=lambda x:x['ts'])
print('via=radar',len(rad),'bg',len(bg),'radar ts range',iso(rad[0]['ts']),iso(rad[-1]['ts']))
g=[b['ts']-a['ts'] for a,b in zip(rad,rad[1:]) if b['ts']-a['ts']<5000]
summ('page poll interval seen by server (via=radar gaps <5s)',g)
print('poll gap histogram (50ms bins):',sorted(collections.Counter(min(x//50*50,1500) for x in g).items()))
gb=[b['ts']-a['ts'] for a,b in zip(bg,bg[1:]) if b['ts']-a['ts']<5000]
summ('bg signal gaps',gb)
# state transitions in bg vs first radar-served state
def firsts(lst,label):
    prev=None
    for x in lst:
        if x['state']!=prev:
            if 1794622380000<=x['ts']<=1794622430000: print(label,iso(x['ts']),x['state'],x.get('side'),x.get('pFlip'),'inputAge',x.get('inputAgeMs'),'tau',x.get('tau'))
            prev=x['state']
firsts(bg,'BG   '); firsts(rad,'RADAR')
# the via=radar signals in window: how many served per second 00:13:25-40
cnt=collections.Counter(int(x['ts']//1000) for x in rad if 1794622405000<=x['ts']<=1794622420999)
print('radar polls per second in window B:',[(iso(k*1000)[11:19],v) for k,v in sorted(cnt.items())])
# own capture signals_n5000: poll cadence
s2=json.load(open('/tmp/claude-0/-home-user/97d7fe1d-a1f3-5240-8215-edf8d0a9a961/scratchpad/incident_20261114T0015Z/own_capture/signals_n5000.json'))['signals']
rad2=sorted([x for x in s2 if x.get('via')=='radar'],key=lambda x:x['ts'])
print('own capture radar range',iso(rad2[0]['ts']),iso(rad2[-1]['ts']),len(rad2))
g2=[b['ts']-a['ts'] for a,b in zip(rad2,rad2[1:]) if b['ts']-a['ts']<5000]
summ('own capture page poll interval (via=radar gaps <5s)',g2)
print('own capture gap histogram:',sorted(collections.Counter(min(x//50*50,1500) for x in g2).items()))
# predictions.ndjson cadence
pr=[json.loads(l) for l in open(base+'predictions.ndjson') if l.strip()]
print('predictions rows',len(pr),'keys',sorted(pr[0].keys()))
pts=sorted(p['ts'] for p in pr if 'ts' in p)
pg=[b-a for a,b in zip(pts,pts[1:])]
if pg: summ('prediction-log gaps',pg); print('range',iso(pts[0]),iso(pts[-1]))
