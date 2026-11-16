import json, collections
from datetime import datetime, timezone
def iso(ms): return datetime.fromtimestamp(ms/1000,timezone.utc).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
def pct(xs,p):
    xs=sorted(xs); k=(len(xs)-1)*p; f=int(k); c=min(f+1,len(xs)-1); return xs[f]+(xs[c]-xs[f])*(k-f)
def summ(n,xs):
    if not xs: print(n,'no data'); return
    print(f"{n}: n={len(xs)} min={min(xs):.0f} p50={pct(xs,.5):.0f} p95={pct(xs,.95):.0f} p99={pct(xs,.99):.0f} max={max(xs):.0f}")
print('brief ts 1794622405000 =',iso(1794622405000),'; 00:13:25 UTC Nov 14 =',int(datetime(2026,11,14,0,13,25,tzinfo=timezone.utc).timestamp()*1000))
LO,HI=1794615205000,1794615220999
base='/tmp/claude-0/-home-user/97d7fe1d-a1f3-5240-8215-edf8d0a9a961/scratchpad/incident_20261114T0015Z/owner_evidence/'
own=[json.loads(l) for l in open('tape_snapshot.ndjson') if l.strip()]
owner=json.load(open(base+'tape.json'))['rows']
def rows_in(rs,lo,hi): return sorted([r for r in rs if lo<=r['ts']<=hi],key=lambda r:r['ts'])
a=rows_in(own,LO,HI); b=rows_in(owner,LO,HI)
print('rows in 00:13:25-40: tape_all',len(a),'owner tape',len(b))
# compare
ka={r['ts']:r for r in a}; kb={r['ts']:r for r in b}
same=sum(1 for t in ka if t in kb and json.dumps(ka[t],sort_keys=True)==json.dumps(kb[t],sort_keys=True))
print('identical rows (same ts, same JSON):',same,'of',len(ka))
print('tape_all rows at brief ts range 02:13:25-40:',len(rows_in(own,1794622405000,1794622420999)),'owner:',len(rows_in(owner,1794622405000,1794622420999)))
src=b if b else a
print('\n== window B (owner tape rows; identical in tape_all) 00:13:20-00:13:45 ==')
print('ts | tau | state | side | pFlip | pFlipCons | brti.value | src->recv | recv->send | send->local | brtiAge | seq | amended | ageMs | bookAge | idx | liveIdx | skew | rest | grade')
for r in rows_in(owner,LO-5000,HI+5000):
    l=r['brti']['last']; o=r['out']
    print(iso(r['ts'])[11:],round((r['kal']['closeMs']-r['ts'])/1000,1),o['state'],o.get('side'),round(o.get('pFlip',0),5),round(o.get('pFlipCons',0),5),l['value'],l['receivedAt']-l['sourceTs'],l['sendingTs']-l['receivedAt'],l['localTs']-l['sendingTs'],r['ts']-l['localTs'],l['seq'],l['amended'],r['ageMs'],r['ts']-r['obTs'],round(r['idx']['value'],2),round(r['liveIdx']['value'],2) if r.get('liveIdx') else None,r['skew']['est'],r['rest'],r['quality']['grade'])
w=rows_in(owner,LO,HI)
print('\nwindow B summary: brtiAge max',max(r['ts']-r['brti']['last']['localTs'] for r in w),'ageMs max',max(r['ageMs'] for r in w),'bookAge max',max(r['ts']-r['obTs'] for r in w),'send->local max',max(r['brti']['last']['localTs']-r['brti']['last']['sendingTs'] for r in w),'src->recv max',max(r['brti']['last']['receivedAt']-r['brti']['last']['sourceTs'] for r in w))
sq=[r['brti']['last']['seq'] for r in w]; print('seq sequence:',sq,'amended:',[r['brti']['last']['amended'] for r in w].count(True))
# LOCKED run before the incident: last LOCKED row, first REVERSAL WARNING row
pre=rows_in(owner,1794615000000,1794615300000)
lastL=[r for r in pre if r['out']['state']=='LOCKED']; firstRW=[r for r in pre if r['out']['state']=='REVERSAL WARNING']
print('last LOCKED row:',iso(lastL[-1]['ts']) if lastL else None,'first REVERSAL WARNING row:',iso(firstRW[0]['ts']) if firstRW else None)
tr=None
for r in pre:
    if tr and tr!=r['out']['state']: print(' transition',iso(r['ts'])[11:],tr,'->',r['out']['state'],'pFlip',round(r['out']['pFlip'],5),'brti',r['brti']['last']['value'],'liveIdx',round(r['liveIdx']['value'],2) if r.get('liveIdx') else None)
    tr=r['out']['state']
# BRTI messages around the window (owner brti-messages.json): arrival pattern of seq values
m=json.load(open(base+'brti-messages.json'))
msgs=[json.loads(s) for s in m['messages']]
print('\nBRTI relay messages 00:13:20-00:13:45 (time, received_at-time, sending-received, seq):')
for x in msgs:
    inner=json.loads(x['msg']['data']); t=inner['time']
    if LO-5000<=t<=HI+5000: print(' ',iso(t)[11:],x['msg']['received_at']-t,x['sending_ts_ms']-x['msg']['received_at'],x['seq'])
# incident-signals (list)
s=json.load(open(base+'incident-signals.json'))
sig=s if isinstance(s,list) else (s.get('signals') or s.get('rows'))
print('\nincident-signals n',len(sig),'keys',sorted(sig[0].keys()))
rad=sorted([x for x in sig if x.get('via')=='radar'],key=lambda x:x['ts'])
bg=sorted([x for x in sig if x.get('via')!='radar'],key=lambda x:x['ts'])
print('via=radar',len(rad),'bg',len(bg),'radar range',iso(rad[0]['ts']),iso(rad[-1]['ts']),'bg range',iso(bg[0]['ts']),iso(bg[-1]['ts']))
g=[y['ts']-x['ts'] for x,y in zip(rad,rad[1:]) if y['ts']-x['ts']<5000]
summ('page poll interval seen by the server (via=radar consecutive gaps <5 s)',g)
print('histogram 50 ms bins:',sorted(collections.Counter(min(x//50*50,1500) for x in g).items()))
gb=[y['ts']-x['ts'] for x,y in zip(bg,bg[1:]) if y['ts']-x['ts']<5000]
summ('background signal gaps',gb)
print('bg gap histogram:',sorted(collections.Counter(min(x//50*50,1500) for x in gb).items())[:12])
def firsts(lst,label,lo,hi):
    prev=None
    for x in lst:
        if x['state']!=prev:
            if lo<=x['ts']<=hi: print(label,iso(x['ts'])[11:],x['state'],x.get('side'),'pFlip',x.get('pFlip'),'inputAge',x.get('inputAgeMs'),'tau',x.get('tau'),'status',x.get('status'))
            prev=x['state']
print('\nstate transitions 00:12:50-00:13:45 (bg = background tick signals, RADAR = served to the page):')
firsts(bg,'BG   ',1794615170000,1794615225000); firsts(rad,'RADAR',1794615170000,1794615225000)
# first served REVERSAL WARNING vs first bg REVERSAL WARNING
fb=[x for x in bg if x['state']=='REVERSAL WARNING' and x['ts']>=1794615170000]; fr=[x for x in rad if x['state']=='REVERSAL WARNING' and x['ts']>=1794615170000]
if fb and fr: print('first bg REVERSAL WARNING',iso(fb[0]['ts']),'first served REVERSAL WARNING',iso(fr[0]['ts']),'delta ms',fr[0]['ts']-fb[0]['ts'])
fb=[x for x in bg if x['state']=='HIGH CONFIDENCE' and 1794615200000<=x['ts']]; fr=[x for x in rad if x['state']=='HIGH CONFIDENCE' and 1794615200000<=x['ts']]
if fb and fr: print('first bg HIGH CONFIDENCE after 00:13:20',iso(fb[0]['ts']),'first served',iso(fr[0]['ts']),'delta ms',fr[0]['ts']-fb[0]['ts'])
cnt=collections.Counter(int(x['ts']//1000) for x in rad if LO<=x['ts']<=HI)
print('radar polls per second 00:13:25-40:',[(iso(k*1000)[11:19],v) for k,v in sorted(cnt.items())])
# own capture signals: poll cadence
s2=json.load(open('/tmp/claude-0/-home-user/97d7fe1d-a1f3-5240-8215-edf8d0a9a961/scratchpad/incident_20261114T0015Z/own_capture/signals_n5000.json'))['signals']
rad2=sorted([x for x in s2 if x.get('via')=='radar'],key=lambda x:x['ts'])
print('\nown capture via=radar range',iso(rad2[0]['ts']),iso(rad2[-1]['ts']),len(rad2))
g2=[y['ts']-x['ts'] for x,y in zip(rad2,rad2[1:]) if y['ts']-x['ts']<5000]
summ('own capture page poll interval',g2)
print('histogram:',sorted(collections.Counter(min(x//50*50,1500) for x in g2).items()))
# by tau regime
g_in=[y['ts']-x['ts'] for x,y in zip(rad2,rad2[1:]) if y['ts']-x['ts']<5000 and x.get('tau',999)<=120]
g_out=[y['ts']-x['ts'] for x,y in zip(rad2,rad2[1:]) if y['ts']-x['ts']<5000 and x.get('tau',0)>120]
summ(' poll interval tau<=120',g_in); summ(' poll interval tau>120',g_out)
pr=[json.loads(l) for l in open(base+'predictions.ndjson') if l.strip()]
print('\npredictions rows',len(pr),'keys',sorted(pr[0].keys())[:30])
pts=sorted(p['ts'] for p in pr if isinstance(p.get('ts'),(int,float)))
if pts:
    pg=[y-x for x,y in zip(pts,pts[1:])]; summ('prediction-log gaps',pg); print('range',iso(pts[0]),iso(pts[-1]))
