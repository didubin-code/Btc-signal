import json
from datetime import datetime, timezone
base='/tmp/claude-0/-home-user/97d7fe1d-a1f3-5240-8215-edf8d0a9a961/scratchpad/incident_20261114T0015Z/owner_evidence/'
def iso(ms): return datetime.fromtimestamp(ms/1000,timezone.utc).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
t=json.load(open(base+'tape.json'))
print('tape top keys:',list(t.keys()))
recs=t['records']; print('records:',len(recs), type(recs[0]).__name__)
r0=recs[0]
print('record keys:',sorted(r0.keys()) if isinstance(r0,dict) else r0)
print('record[0] (trunc):',json.dumps(r0)[:1800])
tss=[r.get('ts') for r in recs if isinstance(r,dict)]
tss=[x for x in tss if isinstance(x,(int,float))]
print('ts range:',min(tss),max(tss),iso(min(tss)),iso(max(tss)))
inwin=[r for r in recs if isinstance(r.get('ts'),(int,float)) and 1794622405000<=r['ts']<=1794622420999]
print('rows in window B:',len(inwin))
if inwin:
    print('window B record keys:',sorted(inwin[0].keys()))
    print('brti shape:',json.dumps(inwin[0].get('brti'))[:600])
    print('kal:',json.dumps(inwin[0].get('kal'))[:300],'obTs:',inwin[0].get('obTs'),'ageMs:',inwin[0].get('ageMs'),'skew:',inwin[0].get('skew'),'rest:',inwin[0].get('rest'))
    print('out:',json.dumps(inwin[0].get('out'))[:500])
    print('idx:',json.dumps(inwin[0].get('idx'))[:300])
# different shapes among records
import collections
sh=collections.Counter(tuple(sorted(r.keys())) for r in recs if isinstance(r,dict))
for k,v in sh.most_common(): print(v,k)
# brti messages
m=json.load(open(base+'brti-messages.json'))
print('brti-messages keys:',list(m.keys()),'n',m.get('n'))
msgs=[json.loads(s) for s in m['messages']]
print('first msg keys:',list(msgs[0].keys()), 'msg keys:',list(msgs[0]['msg'].keys()))
d=[]; 
for x in msgs:
    inner=json.loads(x['msg']['data']); d.append((inner['time'],x['msg']['received_at'],x['sending_ts_ms'],x['seq'],inner.get('type'),x.get('type')))
print('types:',collections.Counter(z[4] for z in d),collections.Counter(z[5] for z in d))
src2recv=[z[1]-z[0] for z in d]; recv2send=[z[2]-z[1] for z in d]
def pct(xs,p):
    xs=sorted(xs); k=(len(xs)-1)*p; f=int(k); c=min(f+1,len(xs)-1); return xs[f]+(xs[c]-xs[f])*(k-f)
print('msg time range',iso(d[0][0]),iso(d[-1][0]))
print(f"relay src->recv n={len(src2recv)} min={min(src2recv)} p50={pct(src2recv,.5)} p95={pct(src2recv,.95)} max={max(src2recv)}")
print(f"relay recv->send n={len(recv2send)} min={min(recv2send)} p50={pct(recv2send,.5)} p95={pct(recv2send,.95)} max={max(recv2send)}")
seqs=[z[3] for z in d]; print('seq gaps (diff!=1):',[(a,b) for a,b in zip(seqs,seqs[1:]) if b-a!=1][:10])
times=[z[0] for z in d]; print('time gaps !=1000:',[(iso(a),b-a) for a,b in zip(times,times[1:]) if b-a!=1000][:10])
# messages around 00:13:25-00:13:40
print('messages in window B:')
for z in d:
    if 1794622405000<=z[0]<=1794622420999: print(iso(z[0]),'recv+',z[1]-z[0],'send+',z[2]-z[1],'seq',z[3])
# any messages with amended / different type
print('local receive timestamp field present?', [k for k in msgs[0].keys()])
