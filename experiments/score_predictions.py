"""Score the blind account predictions.

The right test is not "who posted about this topic" but "would watching the
accounts I named have caught it" -- so this searches FROM each predicted
handle in the window before the repricing, and gates whatever it finds.

Retweets are included. An earlier topic-wide sweep excluded them and missed
Fabrizio Romano's post 16 minutes ahead of the Guardiola repricing, which
was a self-retweet -- and was the signal.
"""
from __future__ import annotations
import datetime as dt, json, os, sys, time, urllib.parse, urllib.request
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from polybuyer.model import normalise_many
from polybuyer.netio import Fetcher
from polybuyer.newsdesk.config import load
from polybuyer.newsdesk.gate import decide
from polybuyer.newsdesk.llm import ask
from polybuyer.sources import market_tape
from polybuyer.tape import Tape

B = os.environ["X_BEARER_TOKEN"]
# (fragment, [predicted handles], rules gloss)
PRED = [
 ("Graham Platner", ["GrahamPlatner","politico","AP"], "Resolves YES if Graham Platner withdraws from the race."),
 ("SHEIN IPO", ["Reuters","business","FT"], "Resolves YES if SHEIN lists publicly before 2027."),
 ("SpaceX or OpenAI IPO", ["elonmusk","sama","OpenAI","SpaceX"], "Resolves YES on whichever of SpaceX or OpenAI IPOs first."),
 ("Binance launch stock tokens", ["binance","_RichardTeng","cz_binance"], "Resolves YES if Binance launches stock tokens in 2026."),
 ("Infrared launch a token", ["InfraredFinance","infrared_fi"], "Resolves YES if Infrared launches a token."),
 ("Pep Guardiola", ["FabrizioRomano","ManCity","David_Ornstein"], "Resolves YES if Guardiola ceases to be Man City manager."),
 ("Tria launch a token", ["tria","useTria","triaprotocol"], "Resolves YES if Tria launches a token."),
 ("GRVT launch a token", ["grvt_io","GRVT_official"], "Resolves YES if GRVT launches a token."),
 ("Keith Kellogg visit", ["generalkellogg","ZelenskyyUa","StateDept"], "Resolves YES if Keith Kellogg visits Ukraine."),
 ("Bitmine", ["BitMNR","fundstrat","fundstratTom"], "Resolves YES if Bitmine announces holdings above 5M ETH."),
]

def repricing(f,cid):
    t=market_tape(f,cid); trs=normalise_many(t.trades)
    if len(trs)<20: return None
    tp=Tape(cid,trs)
    for tr in tp.trades:
        if tr.ref_price>=0.90:
            n=tp.median_price(tr.ts,tr.ts+6*3600)
            if n is not None and n>=0.85: return tr.ts
    return None

def frm(h,a,b,n=20):
    p=urllib.parse.urlencode({"query":f"from:{h}","max_results":n,"start_time":a,
                              "end_time":b,"tweet.fields":"created_at"})
    r=urllib.request.Request(f"https://api.x.com/2/tweets/search/all?{p}",
                             headers={"Authorization":f"Bearer {B}"})
    for k in range(3):
        try:
            with urllib.request.urlopen(r,timeout=30) as x:
                return json.loads(x.read().decode()).get("data",[]) or []
        except Exception as e:
            if "429" in str(e): time.sleep(5*(k+1)); continue
            return []
    return []

def main():
    s=load(); f=Fetcher(cache_dir=".polycache")
    mkts=json.load(open("/tmp/claude-0/-home-user-Polybuyer/"
                        "92cecb2d-4fa2-57e6-b25a-7bfae31c1f90/scratchpad/blind.json"))
    hits=misses=0; rows=[]
    for frag,handles,rules in PRED:
        m=next((x for x in mkts if frag.lower() in x["q"].lower()),None)
        if not m: continue
        ts=repricing(f,m["cid"])
        if ts is None:
            print(f"\n### {frag}: no clean repricing"); continue
        t=dt.datetime.fromtimestamp(ts,dt.timezone.utc)
        a=(t-dt.timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
        b=t.strftime("%Y-%m-%dT%H:%M:%SZ")
        print(f"\n### {frag}  repriced {t:%Y-%m-%d %H:%M}")
        best=None; n=0
        for h in handles:
            for p in frm(h,a,b):
                n+=1
                r=ask({"question":m["q"],"rules":rules},p["text"],h,s.openai_key,s.gate_model)
                act,_=decide(r.result,1)
                if act in ("fire","corroborate"):
                    pt=dt.datetime.strptime(p["created_at"],"%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=dt.timezone.utc)
                    if best is None or pt<best[0]: best=(pt,h,p["text"],act)
            time.sleep(1.2)
        if best:
            hits+=1
            lead=(t-best[0]).total_seconds()/60
            print(f"  HIT  @{best[1]} {lead:.0f}m ahead ({best[3]}) [{n} posts scanned]")
            print(f"       {' '.join(best[2].split())[:88]}")
        else:
            misses+=1
            print(f"  miss ({n} posts scanned across {len(handles)} predicted accounts)")
        rows.append({"market":m["q"],"hit":bool(best),"scanned":n,
                     "lead_min":(t-best[0]).total_seconds()/60 if best else None,
                     "handle":best[1] if best else None})
    print(f"\n{'='*70}\nBLIND TEST: {hits} hit / {hits+misses} scored")
    json.dump(rows,open("experiments/prediction_score.json","w"),indent=1)

if __name__=="__main__": main()
