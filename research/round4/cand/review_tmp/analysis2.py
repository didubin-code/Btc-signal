import json, math, glob, collections
D='/tmp/claude-0/-home-user/97d7fe1d-a1f3-5240-8215-edf8d0a9a961/scratchpad/round4/cand/'
RP='/tmp/claude-0/-home-user/97d7fe1d-a1f3-5240-8215-edf8d0a9a961/scratchpad/incident_20261114T0015Z/replay_pub/out_full_mu/'
E=json.load(open(D+'eval_pr10.json')); C=json.load(open(D+'cells.json')); FIT,TEST=C['FIT'],C['TEST']
strikes={}
for f in sorted(glob.glob(RP+'usdc_*.ndjson')):
    if '.sum.' in f or '.loser.' in f: continue
    for l in open(f): r=json.loads(l); strikes[r['ticker']]=r['strike']
def hyp_ge(x,N,K,n): return sum(math.comb(K,i)*math.comb(N-K,n-i) for i in range(x,min(K,n)+1))/math.comb(N,n)
test=E['test']; rule='exact'
P=[(tk,v[rule]) for tk,v in test.items() if v[rule]['prod']]
def usd(tk,x): return x['prod']['c_bps']*strikes[tk]/1e4
classes={'all':lambda tk,x: True,'tau<30':lambda tk,x: x['prod']['tau']<30,'tau>=30':lambda tk,x: x['prod']['tau']>=30,'owner (tau>=30, >=50 USD)':lambda tk,x: x['prod']['tau']>=30 and usd(tk,x)>=50,'tau>=30, <50 USD':lambda tk,x: x['prod']['tau']>=30 and usd(tk,x)<50,'tau>=30, active regime (bk>=4)':lambda tk,x: x['prod']['tau']>=30 and x['prod']['bk']>=4,'tau>=30, bk<=3':lambda tk,x: x['prod']['tau']>=30 and x['prod']['bk']<=3}
print('class-restricted hypergeometric: P(>= observed prevented | random withholding of the same size)')
for name,c in classes.items():
    sub=[(tk,x) for tk,x in P if c(tk,x)]; N=len(sub); K=sum(1 for tk,x in sub if x['prod_won'] is False); n=sum(1 for tk,x in sub if not x['cand']); k=sum(1 for tk,x in sub if (not x['cand']) and x['prod_won'] is False)
    spf=sum(x['prod']['pf'] for tk,x in sub)
    print('  %-32s N=%5d losses=%2d withheld=%4d prevented=%d  p=%.4f | production sum pf %.2f vs %d observed (O/E %.2f)'%(name,N,K,n,k,hyp_ge(k,N,K,n) if K else 1.0,spf,K,K/spf if spf else 0))
# A4: admitted entries whose cell's FIT upper95 > 1 % (data cannot bound the true rate below 1 %)
adm=[(tk,x) for tk,x in P if x['cand']]
up=[FIT[x['cand']['cell']]['upper95'] for tk,x in adm if x['cand']['cell'] in FIT]
print('\nA4 restated: admitted entries %d; in cells whose FIT upper95 > 1%%: %d (%.1f%%); > 0.5%%: %d; FIT n of their cells: min %d'%(len(adm),sum(1 for u in up if u>0.01),100*sum(1 for u in up if u>0.01)/len(up),sum(1 for u in up if u>0.005),min(FIT[x['cand']['cell']]['n'] for tk,x in adm)))
# TEST pooled rate in used cells
used=set(x['cand']['cell'] for tk,x in adm); nT=sum(TEST[c]['n'] for c in used if c in TEST); kT=sum(TEST[c]['k'] for c in used if c in TEST); nF=sum(FIT[c]['n'] for c in used); kF=sum(FIT[c]['k'] for c in used)
print('used cells: FIT pooled %d/%d = %.3f%%; TEST pooled %d/%d = %.3f%% (exact 95%% CI upper %.3f%%)'%(kF,nF,100*kF/nF,kT,nT,100*kT/nT, 100*(1-0.025**(1/nT)) if kT==0 else 0))
# what the smoothing does: for k=0 cells, smoothed rate <= 0.2 % iff n >= 249; TEST rate > 1 % iff n <= 48
print('smoothing: k=0 passes 0.2%% iff n>=249 (0.5/250=%.4f); k=0 TEST>1%% iff n<=48; k=1 TEST>1%% iff n<=148; k=2 iff n<=248'%(0.5/250))
# cell for Nov 15 under round-down during 92.6-101.6 s
for c in ('90|active|17.5-20','100|active|17.5-20','110|active|17.5-20','100|active|15-20','110|active|15-20'):
    f=FIT.get(c); print(' ',c,'FIT',f and (f['k'],f['n'],round(100*f['rate'],2)))
# calibration of production by tau class on TEST (sum pf vs observed) and candidate's floor by class
for name,c in classes.items():
    sub=[(tk,x) for tk,x in P if c(tk,x) and x['cand']]
    ef=sum(x['cand']['cell_fit_rate'] or 0 for tk,x in sub); ep=sum(x['cand']['pf'] for tk,x in sub); k=sum(1 for tk,x in sub if x['cand_won'] is False)
    print('  admitted in %-32s n=%5d losses=%d | E under floor %.2f, under pf %.2f'%(name,len(sub),k,ef,ep))
# how many admitted entries had the floor binding (p_emp > pf) at admission
bind=sum(1 for tk,x in adm if (x['cand']['p_emp'] or 0)>x['cand']['pf']); print('admitted entries where p_emp > pf at admission (floor displayed): %d of %d'%(bind,len(adm)))
# economics proxy: withheld entries' production pf sum vs losses
