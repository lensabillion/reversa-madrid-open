import json,glob,math
from datetime import datetime
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, brier_score_loss
from sklearn.ensemble import HistGradientBoostingClassifier
rows=[]
for f in glob.glob('hist/*.json'):
    d=json.load(open(f))
    for r in d['rows']:
        r['_leg']=d['leg']; r['_tipo']=d['tipo']; rows.append(r)
START={'V':'1993-06-29','VI':'1996-03-27','VII':'2000-04-05','VIII':'2004-04-02','IX':'2008-04-01','X':'2011-12-13','XI':'2016-01-13','XII':'2016-07-19','XIII':'2019-05-21','XIV':'2019-12-03','XV':'2023-08-17'}
# governing party group name fragment per legislature (ex-ante at filing; XII switches 2018-06-02)
GOV={'V':'Socialista','VI':'Popular','VII':'Popular','VIII':'Socialista','IX':'Socialista','X':'Popular','XI':None,'XII':'Popular','XIII':None,'XIV':'Socialista','XV':'Socialista'}
MAJ={'VII':1,'X':1}
def gov_group(leg,date):
    if leg=='XII' and date>=datetime(2018,6,2): return 'Socialista'
    return GOV[leg]
def label(r):
    s=(r.get('resultado_tram') or '').strip()
    if not s: return None
    return 1 if s.startswith('Aprobado') else 0
X,y,legs,base=[],[],[],[]
for r in rows:
    if r['_tipo'] not in ('121','122'): continue
    l=label(r)
    if l is None: continue
    try: fd=datetime.strptime(r['fecha_presentado'],'%d/%m/%Y')
    except: continue
    leg=r['_leg']; a=(r.get('autor') or '')
    days=(fd-datetime.strptime(START[leg],'%Y-%m-%d')).days
    g=gov_group(leg,fd)
    is_gov=1 if r['_tipo']=='121' else 0
    n_auth=a.count('<br')+1
    feats=[is_gov,
           1 if (g and ('Grupo Parlamentario '+g in a or 'Grupo '+g in a)) else 0,
           min(n_auth,5),
           1 if a.strip().startswith('Comisi') else 0,
           days/365.0,
           max(0,days/365.0-3.0),
           1 if 'Orgánica' in (r.get('titulo') or '') else 0,
           MAJ.get(leg,0)]
    feats += [is_gov*feats[4], is_gov*feats[5], is_gov*feats[7]]
    X.append(feats); y.append(l); legs.append(leg); base.append(is_gov)
X=np.array(X,float); y=np.array(y); legs=np.array(legs); base=np.array(base,float)
print('n',len(y),'pos rate',y.mean().round(3))
res=[]
for test in ['V','VI','VII','VIII','IX','X','XII','XIV','XV']:
    tr=legs!=test; te=legs==test
    if y[te].min()==y[te].max(): continue
    lr=LogisticRegression(max_iter=2000,C=1.0).fit(X[tr],y[tr])
    gb=HistGradientBoostingClassifier(max_depth=3,learning_rate=0.05,max_iter=300).fit(X[tr],y[tr])
    p=lr.predict_proba(X[te])[:,1]; q=gb.predict_proba(X[te])[:,1]
    # baseline as probability: use training base rates per class (calibrated version of the rule)
    pg=y[tr][base[tr]==1].mean(); pb=y[tr][base[tr]==0].mean()
    pbase=np.where(base[te]==1,pg,pb)
    res.append((test,te.sum(),
        roc_auc_score(y[te],base[te]), brier_score_loss(y[te],base[te]), brier_score_loss(y[te],pbase),
        roc_auc_score(y[te],p), brier_score_loss(y[te],p),
        roc_auc_score(y[te],q), brier_score_loss(y[te],q)))
print('leg   n   | rule AUC  rule Brier(0/1)  rule Brier(rates) | logit AUC Brier | GBM AUC Brier')
for t in res: print(f"{t[0]:5}{t[1]:4}  |  {t[2]:.3f}    {t[3]:.3f}          {t[4]:.3f}       |  {t[5]:.3f}  {t[6]:.3f} |  {t[7]:.3f}  {t[8]:.3f}")
