import json, math, collections, datetime, random, glob, statistics as st
random.seed(7)
D='/tmp/claude-0/-home-user/97d7fe1d-a1f3-5240-8215-edf8d0a9a961/scratchpad/round4/cand/'
RP='/tmp/claude-0/-home-user/97d7fe1d-a1f3-5240-8215-edf8d0a9a961/scratchpad/incident_20261114T0015Z/replay_pub/out_full_mu/'
E=json.load(open(D+'eval_pr10.json')); C=json.load(open(D+'cells.json'))
FIT,TEST,ALL=C['FIT'],C['TEST'],C['ALL']
test=E['test']; live=E['live']
ut=lambda s: datetime.datetime.fromtimestamp(s, datetime.timezone.utc).strftime('%Y-%m-%d %H:%M')
print('SPLIT constant 1788566400 =', ut(1788566400), '| 2026-09-01T00Z =', 1788220800)
nw=0; strikes={}; nfit=0
for f in sorted(glob.glob(RP+'usdc_*.ndjson')):
    if '.sum.' in f or '.loser.' in f: continue
    for l in open(f):
        r=json.loads(l); strikes[r['ticker']]=r['strike']
        if 1788220800<=r['closeTs']<1788566400: nw+=1
print('windows closing Sep 1-4 UTC (FIT by code, TEST by declaration):', nw)
cts=[v['closeTs'] for v in test.values()]; print('TEST closeTs range', ut(min(cts)), '->', ut(max(cts)), 'n', len(cts))
CB=[0,2.5,5,7.5,10,12.5,15,17.5,20,22.5,25,27.5,30,32.5,35,37.5,40,50,75,1e9]
def cbin(c):
    for lo,hi in zip(CB,CB[1:]):
        if lo<=c<hi: return '%g-%g'%(lo,hi if hi<1e9 else 999)
def grp(bk): return 'quiet' if bk<=1 else 'normal' if bk<=3 else 'active'
def hround(tau): return int(min(120,max(20,10*math.ceil(tau/10-1e-9))))
def key_of(tau,bk,c): return '%d|%s|%s'%(hround(tau),grp(bk),cbin(c))
def hyp_le(x,N,K,n): return sum(math.comb(K,i)*math.comb(N-K,n-i) for i in range(0,x+1))/math.comb(N,n)
def hyp_pmf(i,N,K,n): return math.comb(K,i)*math.comb(N-K,n-i)/math.comb(N,n)
def binom_ge(k,n,p):
    if p<=0: return 1.0 if k==0 else 0.0
    return 1-sum(math.comb(n,i)*p**i*(1-p)**(n-i) for i in range(0,k))
def pois_ge(k,lam): return 1-sum(math.exp(-lam)*lam**i/math.factorial(i) for i in range(0,k))
def day(ts): return datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).strftime('%Y-%m-%d')
def analyse(res,label,use_strike=True):
  for rule in ('exact','disp'):
    P=[(tk,v[rule],v) for tk,v in res.items() if v[rule]['prod']]
    adm=[x for x in P if x[1]['cand']]; wh=[x for x in P if not x[1]['cand']]
    cand_only=[tk for tk,v in res.items() if v[rule]['cand'] and not v[rule]['prod']]
    N=len(P); K=sum(1 for x in P if x[1]['prod_won'] is False); n=len(adm)
    k_adm_prod=sum(1 for x in adm if x[1]['prod_won'] is False); k_adm_cand=sum(1 for x in adm if x[1]['cand_won'] is False); k_wh=sum(1 for x in wh if x[1]['prod_won'] is False)
    print('\n#### %s rule %s: prod entries %d losses %d | admitted %d (prod-loss %d, cand-loss %d) | withheld %d losses %d | cand-only windows %d'%(label,rule,N,K,n,k_adm_prod,k_adm_cand,len(wh),k_wh,len(cand_only)))
    diff=[(tk,x['prod']['side'],x['cand']['side'],x['prod_won'],x['cand_won']) for tk,x,_ in adm if x['prod_won']!=x['cand_won']]
    if diff: print('  admitted entries where prod and cand outcomes differ:',diff)
    p1=hyp_le(k_adm_prod,N,K,n); obs=hyp_pmf(k_adm_prod,N,K,n); p2=sum(hyp_pmf(i,N,K,n) for i in range(0,K+1) if hyp_pmf(i,N,K,n)<=obs+1e-15)
    print('  P(<=%d losses in a random %d-of-%d subset | %d losses) = %.5f (= one-sided Fisher withheld-vs-admitted; two-sided %.5f); expected %.2f'%(k_adm_prod,n,N,K,p1,p2,K*n/N))
    print('  loss rates: withheld %d/%d = %.3f%% ; admitted %d/%d = %.3f%% ; ratio %.1f ; Bonferroni x28: %.4f'%(k_wh,len(wh),100*k_wh/max(1,len(wh)),k_adm_prod,n,100*k_adm_prod/max(1,n),(k_wh/max(1,len(wh)))/max(1e-9,k_adm_prod/max(1,n)),min(1,28*p1)))
    # withheld entries vs production's own claim
    print('  withheld entries vs production claim 0.2%%: expected %.2f, observed %d, P(>=obs) = %.4f'%(0.002*len(wh),k_wh,binom_ge(k_wh,len(wh),0.002)))
    # day-stratified permutation
    bydays=collections.defaultdict(list)
    for tk,x,v in P: bydays[day(v['closeTs']) if 'closeTs' in v else tk[9:16]].append((x['cand'] is None, x['prod_won'] is False))
    lossdays=collections.Counter(d for d,l in bydays.items() for w,lo in l if lo)
    print('  loss days:',dict(lossdays),'| withheld-loss days:',dict(collections.Counter(d for d,l in bydays.items() for w,lo in l if lo and w)))
    R=20000; cnt=0
    for _ in range(R):
        tot=0
        for d,l in bydays.items():
            nwh=sum(1 for w,lo in l if w)
            if nwh==0: continue
            losses=[lo for w,lo in l]
            if not any(losses): continue
            idx=random.sample(range(len(l)),nwh); tot+=sum(1 for i in idx if losses[i])
        if tot>=k_wh: cnt+=1
    print('  day-stratified permutation (withheld labels shuffled within day): P(withheld losses >= %d) = %.4f'%(k_wh,cnt/R))
    # day cluster bootstrap of the rate difference
    days=list(bydays); diffs=[]
    for _ in range(4000):
        s=[bydays[random.choice(days)] for _ in days]
        nw_=sum(1 for l in s for w,lo in l if w); kw_=sum(1 for l in s for w,lo in l if w and lo); na_=sum(1 for l in s for w,lo in l if not w); ka_=sum(1 for l in s for w,lo in l if (not w) and lo)
        diffs.append(kw_/max(1,nw_)-ka_/max(1,na_))
    diffs.sort(); print('  day-cluster bootstrap of (withheld rate - admitted rate): 95%% CI [%.3f%%, %.3f%%], P(diff<=0) = %.4f'%(100*diffs[int(0.025*len(diffs))],100*diffs[int(0.975*len(diffs))],sum(1 for d in diffs if d<=0)/len(diffs)))
    # classes
    def cls(x,tk):
        tau=x['prod']['tau']; c=x['prod']['c_bps']; usd=c*strikes.get(tk,0)/1e4 if use_strike else None
        return tau, c, usd
    for name,cond in (('tau<30',lambda t,c,u: t<30),('tau>=30',lambda t,c,u: t>=30),('owner class tau>=30 & cushion>=50 USD',lambda t,c,u: t>=30 and (u if u is not None else c*65000/1e4)>=50),('tau>=30 & cushion<50 USD',lambda t,c,u: t>=30 and (u if u is not None else c*65000/1e4)<50)):
        sub=[(tk,x) for tk,x,v in P if cond(*cls(x,tk))]
        pl=sum(1 for tk,x in sub if x['prod_won'] is False); ca=[(tk,x) for tk,x in sub if x['cand']]; cl=sum(1 for tk,x in ca if x['cand_won'] is False); whl=[tk[-14:] for tk,x in sub if not x['cand'] and x['prod_won'] is False]
        print('  class %-40s: prod %5d entries %2d losses | cand %5d entries %2d losses | coverage %.1f%% | withheld %d | prevented %s'%(name,len(sub),pl,len(ca),cl,100*len(ca)/max(1,len(sub)),len(sub)-len(ca),whl))
    # withheld composition
    taus=[x['prod']['tau'] for tk,x,v in wh]; cs=[x['prod']['c_bps'] for tk,x,v in wh]
    if wh: print('  withheld entries: tau median %.1f, share <30 s %.1f%%, cushion median %.1f bps, share <5 bps %.1f%%'%(st.median(taus),100*sum(1 for t in taus if t<30)/len(taus),st.median(cs),100*sum(1 for c in cs if c<5)/len(cs)))
    # reference class: floor implied for withheld entries vs observed
    fl=[x['first_withheld']['disp'] for tk,x,v in wh if x['first_withheld']]
    if fl: print('  floor implied for withheld entries at the production moment: mean %.2f%%, median %.2f%%, sum %.1f expected losses vs observed %d'%(100*st.mean(fl),100*st.median(fl),sum(fl),k_wh))
    # expected under floor / under pf for admitted
    ef=sum((x['cand']['cell_fit_rate'] or 0) for tk,x,v in adm); ep=sum(x['cand']['pf'] for tk,x,v in adm); epp=sum(x['prod']['pf'] for tk,x,v in P)
    print('  admitted entries: expected losses under FIT cell rate %.2f, under production pf %.2f, observed %d | all production entries: sum pf %.2f vs observed %d'%(ef,ep,k_adm_cand,epp,K))
    # delays
    dl=[x['prod']['tau']-x['cand']['tau'] for tk,x,v in adm]; nz=[d for d in dl if d>1e-6]
    if dl: print('  delays: same-moment %.1f%%, delayed %d: median %.1f s, p90 %.1f, max %.1f, >60 s %d'%(100*(len(dl)-len(nz))/len(dl),len(nz),st.median(nz) if nz else 0,sorted(nz)[int(0.9*len(nz))] if nz else 0,max(nz) if nz else 0,sum(1 for d in nz if d>60)))
    # production entries grouped by cell: observed vs FIT rate
    bycell=collections.defaultdict(lambda:[0,0,0])
    for tk,x,v in P:
        k=key_of(x['prod']['tau'],x['prod']['bk'],x['prod']['c_bps']); bycell[k][0]+=1; bycell[k][1]+=int(x['prod_won'] is False); bycell[k][2]+=int(x['cand'] is None)
    rows=sorted(bycell.items(),key=lambda kv:-kv[1][2])
    print('  top withheld cells (prod entries, prod losses, withheld | FIT k/n rate | TEST k/n rate):')
    for k,(ne,nl,nwh) in rows[:8]:
        f=FIT.get(k,{}); t=TEST.get(k,{}); print('    %-22s %5d %2d %5d | FIT %s/%s %.2f%% | TEST %s/%s %.2f%%'%(k,ne,nl,nwh,f.get('k'),f.get('n'),100*f.get('rate',0),t.get('k'),t.get('n'),100*t.get('rate',0)))
    print('  cells of production losses (cell: prod entries, losses, withheld | FIT | TEST):')
    for k,(ne,nl,nwh) in sorted(bycell.items()):
        if nl: f=FIT.get(k,{}); t=TEST.get(k,{}); print('    %-22s %5d %2d %5d | FIT %s/%s %.2f%% | TEST %s/%s %.2f%%'%(k,ne,nl,nwh,f.get('k'),f.get('n'),100*f.get('rate',0),t.get('k'),t.get('n'),100*t.get('rate',0)))
    # A4
    used=collections.defaultdict(int)
    for tk,x,v in adm: used[x['cand']['cell']]+=1
    flagged=[(x['cand']['cell'],TEST.get(x['cand']['cell'],{}).get('k'),TEST.get(x['cand']['cell'],{}).get('n')) for tk,x,v in adm if x['cand']['cell_test'] is not None and x['cand']['cell_test']>0.01]
    print('  A4: %d admitted entries in cells with smoothed TEST rate > 1%%; by (k_TEST, n_TEST):'%len(flagged), sorted(collections.Counter((k,n) for c,k,n in flagged).items()))
    print('  A4: used cells %d; max FIT smoothed rate among admitted %.3f%%; cells with k_FIT=0: %d'%(len(used),100*max((x['cand']['cell_fit_rate'] or 0) for tk,x,v in adm),sum(1 for c in used if FIT.get(c,{}).get('k')==0)))
    exceed=[];sig_up=[];sig_sm=[];sumk=0;sume_sm=0;sume_raw=0;ent_sig=0
    for c,ne in used.items():
        f=FIT.get(c); t=TEST.get(c)
        if not f or not t: continue
        sumk+=t['k']; sume_sm+=t['n']*f['rate']; sume_raw+=t['n']*f['k']/f['n']
        if t['k']/t['n']>f['upper95']: exceed.append((c,ne,f['k'],f['n'],t['k'],t['n']))
        if binom_ge(t['k'],t['n'],f['upper95'])<0.05: sig_up.append((c,ne,f['k'],f['n'],t['k'],t['n']))
        if binom_ge(t['k'],t['n'],f['rate'])<0.05: sig_sm.append((c,ne,f['k'],f['n'],t['k'],t['n'])); ent_sig+=ne
    print('  A4 stability: cells whose raw TEST rate > FIT upper95: %d of %d (author: 9 of 91): %s'%(len(exceed),len(used),[(c,ne,'FIT %d/%d'%(kf,nf),'TEST %d/%d'%(kt,nt)) for c,ne,kf,nf,kt,nt in exceed]))
    print('  A4 stability: cells with P(Bin(n_T, FIT upper95) >= k_T) < 0.05: %d (expected <= %.1f); with p0 = FIT smoothed rate: %d cells, %d admitted entries'%(len(sig_up),0.05*len(used),len(sig_sm),ent_sig))
    print('  A4 pooled over used cells: TEST losses %d vs expected %.1f under FIT smoothed (Poisson P(>=) = %.4f), %.1f under FIT raw'%(sumk,sume_sm,pois_ge(sumk,sume_sm),sume_raw))
    print('  A4: TEST/FIT rate ratio pooled over used cells = %.2f'%(sumk/max(1e-9,sume_raw)))
analyse(test,'TEST')
analyse(live,'LIVE',use_strike=False)
# live random-withholding probability
N,K,n=283,2,22
print('\nLIVE: P(>=1 of the 2 losses falls in a random 22-of-283 withheld set) = %.3f'%(1-math.comb(N-K,n)/math.comb(N,n)))
print('\nKey cells (FIT k/n rate upper95 | TEST k/n rate | ALL k/n rate):')
for c in ['100|active|17.5-20','110|active|17.5-20','120|active|17.5-20','90|normal|15-17.5','100|normal|15-17.5','110|normal|15-17.5','100|active|15-17.5','20|quiet|0-2.5','40|active|2.5-5','70|active|10-12.5','50|active|5-7.5','30|active|0-2.5','80|normal|10-12.5','90|active|27.5-30','40|quiet|2.5-5','20|active|2.5-5']:
    f=FIT.get(c,{}); t=TEST.get(c,{}); a=ALL.get(c,{})
    print('  %-22s FIT %s/%s %.2f%% up %.2f%% | TEST %s/%s %.2f%% | ALL %s/%s %.2f%%'%(c,f.get('k'),f.get('n'),100*f.get('rate',0),100*f.get('upper95',0),t.get('k'),t.get('n'),100*t.get('rate',0),a.get('k'),a.get('n'),100*a.get('rate',0)))
# how many FIT cells admit under the exact rule (smoothed <= 0.2 %)
adm_cells=[c for c,v in FIT.items() if v['rate']<=0.002]; print('\nFIT cells with smoothed rate <= 0.2%% (admit under exact rule): %d of %d; of which k=0: %d; min n among them %d'%(len(adm_cells),len(FIT),sum(1 for c in adm_cells if FIT[c]['k']==0),min(FIT[c]['n'] for c in adm_cells)))
# losses in FIT in the owner's class cells (cushion >= 5 bps, h>=30) : how many k in total
kk=sum(v['k'] for c,v in FIT.items() if int(c.split('|')[0])>=30 and float(c.split('|')[2].split('-')[0])>=5); nn=sum(v['n'] for c,v in FIT.items() if int(c.split('|')[0])>=30 and float(c.split('|')[2].split('-')[0])>=5)
print('FIT leader-losses in cells h>=30 & cushion>=5 bps (all leaders, any pf): %d of %d'%(kk,nn))
