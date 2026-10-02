# Filing-to-BOE days for approved bills in legislatures XII, XIV and XV.
# Inputs: hist/*.json from scan.py, and the BOE consolidated-legislation list of laws
# (rango 1300 Ley and 1290 Ley Orgánica, 2016-2026), downloaded on first run.
import json,glob,re,difflib,statistics,os,urllib.parse,urllib.request
from datetime import datetime, timedelta
BOE_FILE='boe_laws_2016_2026.json'
if not os.path.exists(BOE_FILE):
    q={"query":{"query_string":{"query":"rango@codigo:1300 or rango@codigo:1290"},"range":{"fecha_publicacion":{"gte":"20160101","lte":"20261002"}}}}
    url="https://www.boe.es/datosabiertos/api/legislacion-consolidada?"+urllib.parse.urlencode({"query":json.dumps(q),"limit":"-1"})
    req=urllib.request.Request(url,headers={"Accept":"application/json","User-Agent":"Mozilla/5.0"})
    json.dump(json.load(urllib.request.urlopen(req,timeout=120))['data'],open(BOE_FILE,'w'),ensure_ascii=False)
END={'XII':'2019-03-05','XIV':'2023-05-30','XV':'2026-10-02'}
START={'XII':'2016-07-19','XIV':'2019-12-03','XV':'2023-08-17'}
laws=[x for x in json.load(open(BOE_FILE)) if x['ambito']['codigo']=='1']
def norm(t): return re.sub(r'\s+',' ',re.sub(r'[^a-záéíóúñü0-9 /]','',t.lower())).strip()
def core_law(t): return norm(re.sub(r'^Ley( Orgánica)? \d+/\d{4}, de \d+ de \w+,\s*','',t,flags=re.I))
def core_bill(t):
    t=re.sub(r'^(Proyecto|Proposición) de Ley( Orgánica)?\s*','',t,flags=re.I)
    return norm(re.sub(r'\(procedente del Real Decreto-ley.*?\)','',t,flags=re.I))
def nums(t): return set(re.findall(r'\d+/\d{4}',t))
res=[]
for f in glob.glob('hist/*.json'):
    d=json.load(open(f)); leg=d['leg']
    if leg not in END or d['tipo'] not in ('121','122','124'): continue
    lo=datetime.strptime(START[leg],'%Y-%m-%d'); hi=datetime.strptime(END[leg],'%Y-%m-%d')+timedelta(days=120)
    for r in d['rows']:
        if not (r.get('resultado_tram') or '').startswith('Aprobado'): continue
        fd=datetime.strptime(r['fecha_presentado'],'%d/%m/%Y'); cb=core_bill(r['titulo']); best=None
        for L in laws:
            pd=datetime.strptime(L['fecha_publicacion'],'%Y%m%d')
            if not (fd<pd<=hi): continue
            cl=core_law(L['titulo'])
            if nums(cb) and nums(cl) and not (nums(cb)&nums(cl)): continue
            s=difflib.SequenceMatcher(None,cb,cl).ratio()
            if not best or s>best[0]: best=(s,L,pd)
        if best and best[0]>=0.85:
            res.append(dict(leg=leg,tipo=d['tipo'],days=(best[2]-fd).days,rdl='procedente del Real Decreto' in r['titulo'],budget='Presupuestos Generales' in r['titulo']))
ds=sorted(x['days'] for x in res); m=statistics.median(ds)
print('matched',len(res),'median',m,'MAE of median',round(statistics.mean(abs(x-m) for x in ds)))
