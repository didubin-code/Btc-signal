import json, collections, glob, os, statistics as st
SC='/tmp/claude-0/-home-user/97d7fe1d-a1f3-5240-8215-edf8d0a9a961/scratchpad'
first={}; allmu=collections.defaultdict(list); n=0
for l in open(SC+'/round3/tape/tape_all.ndjson'):
    try: r=json.loads(l)
    except Exception: continue
    k=r.get('kal') or {}; tk=k.get('ticker'); mu=r.get('basisMu')
    if tk and mu is not None:
        n+=1; tau=(k['closeMs']-r['ts'])/1000 if k.get('closeMs') and r.get('ts') else None
        if tk not in first: first[tk]=(mu,tau)
        allmu[tk].append(mu)
print('tape rows with basisMu', n, 'tickers', len(first))
mus=[m for m,t in first.values()]; taus=[t for m,t in first.values() if t is not None]
print('first basisMu per ticker: zero in %d, quantiles %s'%(sum(1 for m in mus if m==0), [round(sorted(mus)[int(q*len(mus))],2) for q in (0.05,0.25,0.5,0.75,0.95)]))
print('tau of first row: quantiles', [round(sorted(taus)[int(q*len(taus))],1) for q in (0.05,0.25,0.5,0.75,0.95)])
rng=[max(v)-min(v) for v in allmu.values()]; print('within-ticker basisMu range: median %.2f p90 %.2f max %.2f USD'%(st.median(rng), sorted(rng)[int(0.9*len(rng))], max(rng)))
mk={os.path.basename(p)[:-5]: json.load(open(p)) for p in glob.glob(SC+'/r30/live/scoreboard/markets/*.json')}
live=[tk for tk,m in mk.items() if m.get('result') in ('yes','no')]
print('live settled tickers', len(live), 'with tape basisMu', sum(1 for t in live if t in first), 'without (default -3.4 USD)', sum(1 for t in live if t not in first))
for tk in ('KXBTC15M-26NOV131915-15','KXBTC15M-26NOV151330-30'): print(tk, first.get(tk), 'n rows', len(allmu.get(tk,[])), 'range', (min(allmu[tk]),max(allmu[tk])) if tk in allmu else None)
