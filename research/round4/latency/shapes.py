import json, sys, collections
from datetime import datetime, timezone
path = sys.argv[1]
shapes = collections.Counter()
ksets = {}
n=0; bad=0
tsmin=None; tsmax=None
brti_shapes = collections.Counter()
lastshapes = collections.Counter()
kshape = collections.Counter()
idxshape = collections.Counter()
win_a=0; win_b=0
days = collections.Counter()
for line in open(path):
    line=line.strip()
    if not line: continue
    try:
        r=json.loads(line)
    except Exception as e:
        bad+=1; continue
    n+=1
    keys=tuple(sorted(r.keys()))
    shapes[keys]+=1
    ts=r.get('ts')
    if isinstance(ts,(int,float)):
        if tsmin is None or ts<tsmin: tsmin=ts
        if tsmax is None or ts>tsmax: tsmax=ts
        if 1794767304000<=ts<=1794767314999: win_a+=1
        if 1794622405000<=ts<=1794622420999: win_b+=1
        days[datetime.fromtimestamp(ts/1000,timezone.utc).strftime('%Y-%m-%d')]+=1
    b=r.get('brti')
    if isinstance(b,dict):
        brti_shapes[tuple(sorted(b.keys()))]+=1
        l=b.get('last')
        if isinstance(l,dict): lastshapes[tuple(sorted(l.keys()))]+=1
        else: lastshapes[repr(type(l))]+=1
    else:
        brti_shapes[repr(type(b))]+=1
    k=r.get('kal')
    kshape[tuple(sorted(k.keys())) if isinstance(k,dict) else repr(type(k))]+=1
    i=r.get('idx')
    idxshape[tuple(sorted(i.keys())) if isinstance(i,dict) else repr(type(i))]+=1
print("rows",n,"bad",bad)
print("ts range",tsmin,tsmax, datetime.fromtimestamp(tsmin/1000,timezone.utc), datetime.fromtimestamp(tsmax/1000,timezone.utc))
print("rows in window A (Nov15 18:28:24-34):",win_a," window B (Nov14 00:13:25-40):",win_b)
print("days:",dict(days))
print("top-level shapes:")
for k,v in shapes.most_common(): print(v,k)
print("brti shapes:")
for k,v in brti_shapes.most_common(): print(v,k)
print("brti.last shapes:")
for k,v in lastshapes.most_common(): print(v,k)
print("kal shapes:")
for k,v in kshape.most_common(): print(v,k)
print("idx shapes:")
for k,v in idxshape.most_common(): print(v,k)
