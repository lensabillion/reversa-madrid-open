import json, time, urllib.request, urllib.parse, sys, os
URL = "https://www.congreso.es/es/busqueda-de-iniciativas?p_p_id=iniciativas&p_p_lifecycle=2&p_p_state=normal&p_p_mode=view&p_p_resource_id=filtrarListado&p_p_cacheability=cacheLevelPage"
OUT = "hist"
os.makedirs(OUT, exist_ok=True)
def fetch(leg, tipo, page):
    data = urllib.parse.urlencode({"_iniciativas_legislatura": leg, "_iniciativas_tipo": tipo, "_iniciativas_paginaActual": page}).encode()
    req = urllib.request.Request(URL, data=data, headers={"User-Agent": "Mozilla/5.0 (research; hackathon prep)"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))
legs = sys.argv[1].split(",")
tipos = sys.argv[2].split(",")
for leg in legs:
    for tipo in tipos:
        path = os.path.join(OUT, f"{leg}_{tipo}.json")
        if os.path.exists(path): continue
        rows, page, total = [], 1, None
        while True:
            try:
                d = fetch(leg, tipo, page)
            except Exception as e:
                print("ERR", leg, tipo, page, e); break
            total = int(d.get("iniciativas_encontradas") or 0)
            lst = d.get("lista_iniciativas") or {}
            if not lst: break
            rows.extend(lst.values())
            if len(rows) >= total: break
            page += 1
            time.sleep(0.4)
        json.dump({"leg": leg, "tipo": tipo, "total": total, "rows": rows}, open(path, "w"), ensure_ascii=False)
        print(leg, tipo, "total", total, "got", len(rows), flush=True)
