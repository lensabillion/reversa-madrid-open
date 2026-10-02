import json,glob,collections
from datetime import datetime
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
exec(open('experiment.py').read().split("print('n'")[0])  # reuse feature construction (X, y, legs, base)
names=['government bill','signed by governing party group','number of signing groups (cap 5)','committee-authored','years since legislature start','years beyond 3rd year','organic law (title)','majority government','gov x years','gov x years beyond 3','gov x majority']
sc=StandardScaler().fit(X); lr=LogisticRegression(max_iter=3000).fit(sc.transform(X),y)
print('Standardized logistic coefficients (positive = more likely to become law):')
for n,c in sorted(zip(names,lr.coef_[0]),key=lambda t:-abs(t[1])): print(f'  {c:+.2f}  {n}')
# group bills breakdown
g=X[:,0]==0
for lab,mask in [('group bill, signed by governing party',g&(X[:,1]==1)),('group bill, NOT signed by governing party',g&(X[:,1]==0)&(X[:,3]==0)),('group bill, 2+ signing groups',g&(X[:,2]>=2)),('group bill, single group',g&(X[:,2]==1)&(X[:,3]==0)),('committee-authored',g&(X[:,3]==1))]:
    print(f'{lab:45} pass rate {100*y[mask].mean():5.1f}%  (n={mask.sum()})')
gv=X[:,0]==1
for lab,mask in [('gov bill, filed in years 0-3',gv&(X[:,5]==0)),('gov bill, filed after year 3',gv&(X[:,5]>0)),('gov bill, majority government',gv&(X[:,7]==1)),('gov bill, minority government',gv&(X[:,7]==0))]:
    print(f'{lab:45} pass rate {100*y[mask].mean():5.1f}%  (n={mask.sum()})')
