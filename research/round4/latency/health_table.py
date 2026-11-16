import json, glob, os
from datetime import datetime, timezone
base='/tmp/claude-0/-home-user/97d7fe1d-a1f3-5240-8215-edf8d0a9a961/scratchpad/'
files=sorted(glob.glob(base+'r30/live/health/health_*.json'))+sorted(glob.glob(base+'round3/tape/health/health_*.json'))+[base+'incident_20261114T0015Z/own_capture/health.json',base+'incident_20261114T0015Z/owner_evidence/health.json']
def find(o,key,path=''):
    out=[]
    if isinstance(o,dict):
        for k,v in o.items():
            if k==key: out.append((path+'.'+k,v))
            out+=find(v,key,path+'.'+k)
    elif isinstance(o,list):
        for i,v in enumerate(o): out+=find(v,key,path+f'[{i}]')
    return out
first=True
agg={}
rows=[]
for f in files:
    try: d=json.load(open(f))
    except Exception as e: print(f,'ERR',e); continue
    if first:
        print('latency key paths:',[p for p,_ in find(d,'latency')]); 
        lat=find(d,'latency')
        if lat: print(json.dumps(lat[0][1])[:1500])
        first=False
    lat=find(d,'latency'); lat=lat[0][1] if lat else {}
    v=d.get('venues',{}); k=d.get('kalshi',{}); b=d.get('brti',{})
    row={'file':os.path.basename(f),'up':d.get('uptimeSec'),'skew':d.get('clockSkewMs'),
         'cbAge':v.get('coinbase',{}).get('quoteAgeMs'),'krAge':v.get('kraken',{}).get('quoteAgeMs'),'bsAge':v.get('bitstamp',{}).get('quoteAgeMs'),
         'recon':tuple(v.get(n,{}).get('reconnects') for n in ('coinbase','kraken','bitstamp')),
         'idxAge':d.get('index',{}).get('ageMs'),'kalAge':k.get('ageMs'),'kalLat':k.get('latencyMs'),'bookAge':k.get('book',{}).get('ageMs'),
         'brtiAge':b.get('lastMsgAgeMs'),'brtiGaps':b.get('seqGaps'),'brtiState':b.get('state'),'rest':d.get('restFallbackActive'),
         'staleEp':(k.get('stale',{}).get('other',{}).get('episodes'),k.get('stale',{}).get('other',{}).get('maxMs'),k.get('stale',{}).get('lastAt')),
         'ticks':d.get('background',{}).get('ticks'),'kalWs':k.get('wsState'),
         'ia':lat.get('decisionIndexInputAgeMs'),'ba':lat.get('decisionBookAgeMs'),'bg':lat.get('bgSnapshotMs'),'rc':lat.get('radarComputeMs'),'crt':lat.get('clientRoundTripMs'),'csa':lat.get('clientSignalAgeAtDisplayMs')}
    rows.append(row)
print()
print("file | upSec | skew | quoteAge cb/kr/bs | reconnects | idxAge | kalAge | kalLat | bookAge | brtiMsgAge | seqGaps | brtiState | rest | kalStale(ep,max,lastAt) | ticks | kalWs")
for r in rows:
    print(f"{r['file']} | {r['up']} | {r['skew']} | {r['cbAge']}/{r['krAge']}/{r['bsAge']} | {r['recon']} | {r['idxAge']} | {r['kalAge']} | {r['kalLat']} | {r['bookAge']} | {r['brtiAge']} | {r['brtiGaps']} | {r['brtiState']} | {r['rest']} | {r['staleEp']} | {r['ticks']} | {r['kalWs']}")
print()
print("file | decisionIndexInputAgeMs p50/p95/p99/max | decisionBookAgeMs p50/p95/p99/max | bgSnapshotMs p50/p95/max | radarComputeMs p50/p95/max | clientRoundTripMs p50/p95/p99/max | clientSignalAgeAtDisplayMs p50/p95/p99/max")
def f4(x,keys=('p50','p95','p99','max')):
    if not x: return 'n/a'
    return '/'.join(str(x.get(k)) for k in keys)+f" (n={x.get('n')})"
for r in rows:
    print(f"{r['file']} | {f4(r['ia'])} | {f4(r['ba'])} | {f4(r['bg'],('p50','p95','max'))} | {f4(r['rc'],('p50','p95','max'))} | {f4(r['crt'])} | {f4(r['csa'])}")
# aggregate across files
import statistics
for key,label in (('skew','clockSkewMs'),('cbAge','coinbase quoteAgeMs'),('krAge','kraken quoteAgeMs'),('bsAge','bitstamp quoteAgeMs'),('idxAge','index.ageMs'),('kalAge','kalshi.ageMs'),('kalLat','kalshi.latencyMs'),('bookAge','kalshi.book.ageMs'),('brtiAge','brti.lastMsgAgeMs')):
    xs=[r[key] for r in rows if isinstance(r[key],(int,float))]
    if xs: print(f"{label}: n={len(xs)} min={min(xs)} median={statistics.median(xs)} max={max(xs)}")
for key,label in (('ia','decisionIndexInputAgeMs'),('ba','decisionBookAgeMs'),('crt','clientRoundTripMs'),('csa','clientSignalAgeAtDisplayMs'),('bg','bgSnapshotMs'),('rc','radarComputeMs')):
    for p in ('p50','p95','p99','max'):
        xs=[r[key][p] for r in rows if r[key] and p in r[key]]
        if xs: print(f"{label}.{p} across copies: min={min(xs)} median={statistics.median(xs)} max={max(xs)}")
