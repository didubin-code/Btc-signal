import json, sys, collections, statistics
from datetime import datetime, timezone, timedelta
path=sys.argv[1]
rows=[]
for line in open(path):
    line=line.strip()
    if line: rows.append(json.loads(line))
rows.sort(key=lambda r:r['ts'])
# dedupe exact duplicate ts rows (pull overlaps)
dedup=[]; seen=set(); dup=0
for r in rows:
    k=(r['ts'],r['kal']['ticker'])
    if k in seen: dup+=1; continue
    seen.add(k); dedup.append(r)
rows=dedup
print("rows after sort/dedupe:",len(rows),"duplicates dropped:",dup)
def iso(ms): return datetime.fromtimestamp(ms/1000,timezone.utc).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
def pct(xs,p):
    xs=sorted(xs); 
    if not xs: return None
    k=(len(xs)-1)*p; f=int(k); c=min(f+1,len(xs)-1)
    return xs[f]+(xs[c]-xs[f])*(k-f)
def summ(name,xs,note=''):
    xs=[x for x in xs if x is not None]
    if not xs: print(f"{name}: no data"); return
    print(f"{name}: n={len(xs)} min={min(xs):.0f} p50={pct(xs,.5):.0f} p95={pct(xs,.95):.0f} p99={pct(xs,.99):.0f} max={max(xs):.0f} {note}")
src2recv=[];recv2send=[];send2local=[];recv2local=[];src2local=[];brtiAge=[];ageMs=[];bookAge=[];idxAge=[];skew=[];skewn=[]
ob_vs_idx=[]
amended=0; brti_disabled=0; brti_none=0
states=collections.Counter(); actions=collections.Counter(); grades=collections.Counter()
problems=collections.Counter(); warnings=collections.Counter()
stale_age=[]; stale_book=[]; rest_rows=[]
locked_age_gt=collections.Counter(); locked_rows=0; locked_book_gt=0; locked_brti_gt=0; tradenow=0; tradenow_book_gt=0
hc_rows=0
dupe_brti=0
for r in rows:
    ts=r['ts']; b=r['brti']; l=b.get('last') if b else None
    if not b or not b.get('enabled'): brti_disabled+=1
    if l:
        src2recv.append(l['receivedAt']-l['sourceTs']); recv2send.append(l['sendingTs']-l['receivedAt'])
        send2local.append(l['localTs']-l['sendingTs']); recv2local.append(l['localTs']-l['receivedAt'])
        src2local.append(l['localTs']-l['sourceTs']); brtiAge.append(ts-l['localTs'])
        if l.get('amended'): amended+=1
    else: brti_none+=1
    ageMs.append(r['ageMs']); bookAge.append(ts-r['obTs']) ; idxAge.append(ts-r['idx']['ts'])
    skew.append(r['skew']['est']); skewn.append(r['skew']['n'])
    st=r['out']['state']; states[st]+=1; actions[r['out'].get('action')]+=1; grades[r['quality']['grade']]+=1
    for p in r['quality']['problems']: problems[p.split(' ')[0]+' '+p.split(' ')[1] if ' ' in p else p]+=1
    for w in r['quality']['warnings']: warnings[' '.join(w.split(' ')[:2])]+=1
    if r['ageMs']>2000: stale_age.append(r)
    if ts-r['obTs']>2500: stale_book.append(r)
    if r['rest']: rest_rows.append(r)
    if st=='LOCKED':
        locked_rows+=1
        if r['ageMs']>2500: locked_age_gt['ageMs>2500 (INDEX_STALE_MS/LOCK_VENUE_QUOTE_MAX_MS)']+=1
        if r['ageMs']>3000: locked_age_gt['ageMs>3000 (VENUE_STALE_MS)']+=1
        if ts-r['obTs']>1500: locked_book_gt+=1
        if l and ts-l['localTs']>2500: locked_brti_gt+=1
    if r['out'].get('action')=='TRADE NOW':
        tradenow+=1
        if ts-r['obTs']>1500: tradenow_book_gt+=1
print("\n== upstream (BRTI relay) ==")
summ("BRTI sourceTs->receivedAt (CF publish -> relay receipt)",src2recv,"UPSTREAM")
summ("BRTI receivedAt->sendingTs (relay internal)",recv2send,"UPSTREAM")
summ("BRTI sendingTs->localTs (relay -> our socket, incl. clock skew)",send2local,"UPSTREAM+skew")
summ("BRTI receivedAt->localTs",recv2local,"UPSTREAM+skew")
summ("BRTI sourceTs->localTs (total source->our receipt)",src2local,"UPSTREAM+skew")
print("\n== ours ==")
summ("BRTI age at decision ts-localTs",brtiAge,"OURS (tick phase + 1 Hz source)")
summ("live-index input age at decision ageMs",ageMs,"OURS (quote age; oldest venue input)")
summ("index own age ts-idx.ts",idxAge,"OURS")
summ("book age at decision ts-obTs",bookAge,"OURS (Kalshi book poll/WS)")
summ("skew.est (ms)",skew,"clock skew estimate vs index source")
print("skew.n values:",collections.Counter(skewn).most_common(5))
print("brti disabled rows:",brti_disabled,"brti.last None:",brti_none,"amended=true rows:",amended)
print("states:",dict(states)); print("actions:",dict(actions)); print("grades:",dict(grades))
print("problems:",dict(problems)); print("warnings:",dict(warnings))
# cadence gaps within same ticker
gaps=[]; big=[]; 
by_t=collections.defaultdict(list)
for r in rows: by_t[r['kal']['ticker']].append(r)
for t,rs in by_t.items():
    rs.sort(key=lambda r:r['ts'])
    for a,bq in zip(rs,rs[1:]):
        g=bq['ts']-a['ts']; gaps.append(g)
        if g>1500: big.append((t,a['ts'],g))
print("\n== cadence ==")
summ("gap between consecutive rows (same ticker)",gaps)
print("gaps >1.5s:",len(big)); 
for t,ts,g in sorted(big,key=lambda x:-x[2])[:25]: print("  ",t,iso(ts),f"gap {g} ms")
print("windows (tickers):",len(by_t))
rowsper=collections.Counter(len(v) for v in by_t.values()); print("rows per ticker:",sorted(rowsper.items())[:10],"...",sorted(rowsper.items())[-5:])
# seq checks
print("\n== BRTI seq ==")
seqdec=0; seqjump=[]; same=0
for t,rs in by_t.items():
    for a,bq in zip(rs,rs[1:]):
        la=a['brti']['last']; lb=bq['brti']['last']
        if not la or not lb: continue
        ds=lb['seq']-la['seq']; dt=(bq['ts']-a['ts'])/1000
        if ds<0: seqdec+=1
        if ds==0: same+=1
        if ds>dt+1.5: seqjump.append((t,iso(a['ts']),ds,dt,la['sourceTs'],lb['sourceTs']))
print("seq decreases:",seqdec,"same seq in consecutive rows (BRTI tick reused):",same,"seq jumps > elapsed+1.5:",len(seqjump))
for x in seqjump[:20]: print("  ",x)
# sourceTs cadence: is sourceTs always whole second? and sourceTs vs ts
frac=collections.Counter((r['brti']['last']['sourceTs']%1000) for r in rows if r['brti']['last'])
print("sourceTs ms fraction top:",frac.most_common(5))
# source age at decision
summ("BRTI source age at decision ts-sourceTs",[r['ts']-r['brti']['last']['sourceTs'] for r in rows if r['brti']['last']],"upstream+ours")
# ts fraction (tick phase)
print("decision ts ms-fraction top:",collections.Counter(r['ts']%1000//50*50 for r in rows).most_common(8))
print("\n== stale ==")
def episodes(rs,label):
    print(label,"rows:",len(rs))
    rs=sorted(rs,key=lambda r:r['ts']); eps=[]
    for r in rs:
        if eps and r['ts']-eps[-1][-1]['ts']<=2000: eps[-1].append(r)
        else: eps.append([r])
    print("  episodes:",len(eps))
    for e in eps[:40]:
        print("   ",e[0]['kal']['ticker'],iso(e[0]['ts']),"->",iso(e[-1]['ts']),"n=",len(e),"maxAge",max(x['ageMs'] for x in e),"maxBook",max(x['ts']-x['obTs'] for x in e),"states",collections.Counter(x['out']['state'] for x in e).most_common(3),"rest",sum(1 for x in e if x['rest']),"grades",collections.Counter(x['quality']['grade'] for x in e).most_common(2))
episodes(stale_age,"ageMs>2000")
episodes(stale_book,"bookAge>2500")
episodes(rest_rows,"rest=true")
print("\n== LOCKED vs gates ==")
print("LOCKED rows:",locked_rows,dict(locked_age_gt),"LOCKED with bookAge>1500:",locked_book_gt,"LOCKED with brtiAge>2500:",locked_brti_gt)
print("TRADE NOW rows:",tradenow,"TRADE NOW with bookAge>1500 (MAX_BOOK_AGE_MS):",tradenow_book_gt)
# identity check
print("\n== identity ==")
import re
bad=0; badlist=[]; after_close=0; before_open=0
EST=timezone(timedelta(hours=-5))
for r in rows:
    ts=r['ts']; k=r['kal']
    exp_close=((ts//900000)+1)*900000
    m=re.match(r'KXBTC15M-(\d\d)([A-Z]{3})(\d\d)(\d\d)(\d\d)-(\d\d)$',k['ticker'])
    ok=True
    if k['closeMs']!=exp_close: ok=False
    if m:
        d=datetime.fromtimestamp(k['closeMs']/1000,EST)
        mon=d.strftime('%b').upper()
        if not (m.group(1)==d.strftime('%y') and m.group(2)==mon and int(m.group(3))==d.day and int(m.group(4))==d.hour and int(m.group(5))==d.minute and int(m.group(6))==d.minute): ok=False
    else: ok=False
    if ts>=k['closeMs']: after_close+=1
    if ts<k['openMs']: before_open+=1
    if not ok: bad+=1; badlist.append((iso(ts),k['ticker'],k['closeMs'],exp_close))
print("rows whose kal.ticker/closeMs disagree with the window implied by ts:",bad, "rows with ts>=closeMs:",after_close,"ts<openMs:",before_open)
for x in badlist[:10]: print("  ",x)
print("ob.ticker != kal.ticker:",sum(1 for r in rows if r['ob'] and r['ob'].get('ticker')!=r['kal']['ticker']))
print("lock25.ticker != kal.ticker:",sum(1 for r in rows if r.get('lock25') and r['lock25'].get('ticker')!=r['kal']['ticker']))
print("tau at rows: min",min(r['kal']['closeMs']-r['ts'] for r in rows),"max",max(r['kal']['closeMs']-r['ts'] for r in rows))
print("strikeIssue non-null:",sum(1 for r in rows if r['strikeIssue']))
# window A table
print("\n== window A rows (1794767304000-1794767314999) ==")
print("ts | tau_s | state | side | pFlip | brti.value | src->recv | recv->send | send->local | brtiAge | seq | amended | ageMs | bookAge | idx.value | liveIdx | grade | warnings")
for r in rows:
    if 1794767304000<=r['ts']<=1794767314999:
        l=r['brti']['last']
        print(iso(r['ts']),(r['kal']['closeMs']-r['ts'])/1000,r['out']['state'],r['out'].get('side'),round(r['out'].get('pFlip',0),5),l['value'],l['receivedAt']-l['sourceTs'],l['sendingTs']-l['receivedAt'],l['localTs']-l['sendingTs'],r['ts']-l['localTs'],l['seq'],l['amended'],r['ageMs'],r['ts']-r['obTs'],round(r['idx']['value'],2),round(r['liveIdx']['value'],2) if r['liveIdx'] else None,r['quality']['grade'],r['quality']['warnings'])
# context rows around window A: 18:28:14 - 18:28:44
print("\n== window A context 18:28:14-18:28:44 (ts, state, pFlip, brti value, seq, idx) ==")
for r in rows:
    if 1794767294000<=r['ts']<=1794767324999:
        l=r['brti']['last']; print(iso(r['ts']),r['out']['state'],round(r['out'].get('pFlip',0),5),l['value'],l['seq'],round(r['idx']['value'],2),r['ageMs'],r['ts']-r['obTs'],r['ts']-l['localTs'])
json.dump({'n':len(rows)},open('metrics_meta.json','w'))
