# Real versus lookalike amendments to GDPR Article 26(1), compared with Amazon's lobby paper.
# Downloads the LobbyPlag data files on first run (github.com/lobbyplag/lobbyplag-data).
# Similarity is Python difflib's character ratio: 0 = nothing in common, 1 = identical.
import difflib,json,os,urllib.request
BASE="https://raw.githubusercontent.com/lobbyplag/lobbyplag-data/master/data/"
for name in ("amendments.json","proposals.json","plags.json"):
    if not os.path.exists(name): urllib.request.urlretrieve(BASE+name,name)
amendments=json.load(open("amendments.json")); by_uid={a["uid"]:a for a in amendments}
proposals={p["uid"]:p for p in json.load(open("proposals.json"))}
verified=[p for p in json.load(open("plags.json")) if p["verified"]]
def english(a): return next((t for t in a.get("text",[]) if t.get("lang")=="en"),None)
def whole(t): return (t.get("old","")+" "+t.get("new","")).lower()
def changes(t): return " ".join((t.get("ins") or [])+(t.get("del") or [])).lower()
def sim(a,b): return difflib.SequenceMatcher(None,a,b).ratio()
article="a26p1"
real=[p for p in verified if article in p["relations"]]
print("Verified copies of a lobby paper on Article 26(1):")
for p in real:
    a=by_uid[p["amendment"]]; print(f"  {a['committee'].upper()} {a['number']} by {', '.join(a['authors'])} <- {proposals[p['proposal']]['doc']}")
anchor=next(p for p in real if by_uid[p["amendment"]]["number"]==616)
lobby=proposals[anchor["proposal"]]["text"]
print("\nAmazon's inserted text:",lobby.get("ins"))
copied={p["amendment"] for p in verified}
rows=[("verified copy",by_uid[anchor["amendment"]])]
rows+=[("not checked",a) for a in amendments if article in (a.get("relations") or []) and a["uid"] not in copied and english(a) and (english(a).get("ins") or english(a).get("del"))]
print("\nkind           amendment     whole text  changes only  inserted text")
for kind,a in rows:
    t=english(a)
    print(f"{kind:14} {a['committee'].upper()} {a['number']:<8} {sim(whole(t),whole(lobby)):10.2f}  {sim(changes(t),changes(lobby)):12.2f}  {[s.strip()[:70] for s in t.get('ins') or []][:1]}")
