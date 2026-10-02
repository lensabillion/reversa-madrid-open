# Monthly agreement between each group's majority position and PSOE's, legislature XV.
# Run from attic/congreso-api/data/v1/sessions (community clone of congreso.es votes).
import json,glob,collections
agree=collections.defaultdict(lambda:[0,0])
for f in sorted(glob.glob('*.json')):
    s=json.load(open(f)); month=s['date'][:7]; dep=s['deputies']
    for v in s['votings']:
        votes=v.get('votes') or ''
        if len(votes)!=len(dep): continue
        tally=collections.defaultdict(collections.Counter)
        for dp,c in zip(dep,votes):
            if c in 'YNA': tally[dp['group']][c]+=1
        pos={g:t.most_common(1)[0][0] for g,t in tally.items() if t}
        if 'GS' not in pos: continue
        for g,p in pos.items():
            if g!='GS': agree[(g,month)][0]+=p==pos['GS']; agree[(g,month)][1]+=1
for (g,m),(a,n) in sorted(agree.items()):
    if g=='GJxCAT': print(g,m,f'{100*a/n:.0f}%',n)
