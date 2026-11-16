import json, math, glob, collections
D='/tmp/claude-0/-home-user/97d7fe1d-a1f3-5240-8215-edf8d0a9a961/scratchpad/round4/cand/'
E=json.load(open(D+'eval_pr10.json')); C=json.load(open(D+'cells.json')); FIT,TEST=C['FIT'],C['TEST']
for label,res in (('TEST',E['test']),('LIVE',E['live'])):
  for rule in ('exact','disp'):
    P=[(tk,v[rule]) for tk,v in res.items() if v[rule]['prod']]; adm=[(tk,x) for tk,x in P if x['cand']]
    miss=[(tk,x) for tk,x in adm if x['cand']['p_emp'] is None]
    print('%s %s: admitted %d; admitted with cell ABSENT from FIT (floor silently 0): %d, cells %s, losses among them %d'%(label,rule,len(adm),len(miss),sorted(set(x['cand']['cell'] for tk,x in miss)),sum(1 for tk,x in miss if x['cand_won'] is False)))
    up=[FIT[x['cand']['cell']]['upper95'] for tk,x in adm if x['cand']['cell'] in FIT]
    print('   A4 restated: in cells whose FIT upper95 > 1%%: %d of %d (%.1f%%); > 0.5%%: %d (%.1f%%); min FIT n %d'%(sum(1 for u in up if u>0.01),len(up),100*sum(1 for u in up if u>0.01)/len(up),sum(1 for u in up if u>0.005),100*sum(1 for u in up if u>0.005)/len(up),min(FIT[x['cand']['cell']]['n'] for tk,x in adm if x['cand']['cell'] in FIT)))
    used=set(x['cand']['cell'] for tk,x in adm if x['cand']['cell'] in FIT); nT=sum(TEST[c]['n'] for c in used if c in TEST); kT=sum(TEST[c]['k'] for c in used if c in TEST); nF=sum(FIT[c]['n'] for c in used); kF=sum(FIT[c]['k'] for c in used)
    print('   used cells pooled: FIT %d/%d = %.3f%%; TEST %d/%d = %.3f%%'%(kF,nF,100*kF/nF,kT,nT,100*kT/nT))
    bind=sum(1 for tk,x in adm if (x['cand']['p_emp'] or 0)>x['cand']['pf']); print('   admitted entries with p_emp > pf at admission: %d'%bind)
print('\nFIT cells with k=0: smoothed <= 0.2%% needs n >= 249; upper95 <= 1%% needs n >= %d'%math.ceil(math.log(0.025)/math.log(0.99)))
for c in ('90|active|17.5-20','100|active|17.5-20','110|active|17.5-20'):
    f=FIT.get(c); print(' ',c,'FIT k/n/rate',f and (f['k'],f['n'],round(100*f['rate'],2)))
