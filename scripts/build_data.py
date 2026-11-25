import duckdb, csv, json, os, sys
sys.path.insert(0, os.path.dirname(__file__))
from setups import scan
from breakouts import replay
c=duckdb.connect()
members=[r[0] for r in c.sql("""select ticker from 'data/membership_intervals.parquet' where "end" is null""").fetchall()]
meta={}
for r in csv.DictReader(open('data/constituents.csv')):
    meta[r['Symbol'].replace('.','-')]=(r['Security'],r['GICS Sector'],r['GICS Sub-Industry'])
bench=['RSP','SPY']   # RSP (equal-weight S&P 500) is the site's benchmark
dates=[r[0] for r in c.sql("select distinct date from 'data/prices.parquet' where ticker='SPY' order by date desc limit 300").fetchall()][::-1]
d0=dates[0]
tick=members+bench
rows=c.sql(f"select ticker,date,adj_close,high,low,close,volume from 'data/prices.parquet' where date>='{d0}' and ticker in ({','.join(repr(t) for t in tick)}) order by ticker,date").fetchall()
idx={d:i for i,d in enumerate(dates)}
ser={t:[None]*len(dates) for t in tick}
hi={t:[None]*len(dates) for t in tick}; lo={t:[None]*len(dates) for t in tick}; vo={t:[0]*len(dates) for t in tick}
for t,d,p,h_,l_,cl,v in rows:
    if d in idx and p is not None:
        i=idx[d]; ser[t][i]=p
        f=p/cl if cl else 1.0          # put high/low on the adjusted scale
        hi[t][i]=(h_ or cl)*f; lo[t][i]=(l_ or cl)*f; vo[t][i]=v or 0
# Gap filling: if a member's prices stop before the latest session (e.g. the source
# lagging after a stock split), fetch only the missing sessions from Yahoo Finance.
# Never overrides source data; if the fetch fails the page flags the stock instead.
filled={}
stale=[t for t in members if ser[t][-1] is None and any(v is not None for v in ser[t])]
if stale:
    try:
        import yfinance as yf
        for t in stale:
            last=max(i for i,v in enumerate(ser[t]) if v is not None)
            start=dates[last+1].date(); end=(dates[-1]+__import__('datetime').timedelta(days=1)).date()
            df=yf.download(t,start=str(start),end=str(end),auto_adjust=False,progress=False,actions=False,multi_level_index=False)
            if df is None or df.empty: print('gap fill: no data for',t); continue
            # continue the source's adjusted scale from its last row
            src=c.sql(f"select adj_close/close from 'data/prices.parquet' where ticker='{t}' and close>0 order by date desc limit 1").fetchone()
            ratio=src[0] if src and src[0] else 1.0
            got=[]
            for d_,row in df.iterrows():
                i=idx.get(d_.to_pydatetime().replace(tzinfo=None))
                if i is None or ser[t][i] is not None or not row['Close']==row['Close']: continue
                ser[t][i]=float(row['Close'])*ratio; hi[t][i]=float(row['High'])*ratio; lo[t][i]=float(row['Low'])*ratio
                vo[t][i]=int(row['Volume'] or 0); got.append(str(dates[i].date()))
            if got: filled[t]=got; print('gap fill',t,got)
    except Exception as e:
        print('gap fill failed:',type(e).__name__,e)
miss=[t for t in members if t not in meta]
print('missing meta',miss)
out={'asOf':str(dates[-1].date()),'dates':[str(d.date()) for d in dates],'bench':{},'stocks':[]}
def rnd(a):
    # forward-fill and round to 4 sig-ish
    o=[];last=None
    for v in a:
        if v is None: v=last
        last=v
        o.append(None if v is None else float(f"{v:.5g}"))
    return o
for b in bench: out['bench'][b]=rnd(ser[b])
counts={};events=[];episodes={}
for t in members:
    s=ser[t]
    if sum(v is not None for v in s)<60: print('short',t); 
    n,sec,ind=meta.get(t,(t,'Unknown','Unknown'))
    rec={'t':t,'n':n,'s':sec,'i':ind,'c':rnd(s),**({'gf':filled[t]} if t in filled else {}),'v':[int(float(f'{x/1000:.3g}')) if x else 0 for x in vo[t]]}  # volume in thousands
    last=max((i for i,x in enumerate(s) if x is not None),default=-1)
    if 0<=last<len(dates)-1:
        rec['ld']=str(dates[last].date())   # prices stop early: the page flags it
        print('stale',t,rec['ld'])
    H=[x if x is not None else y for x,y in zip(hi[t],s)]; Lw=[x if x is not None else y for x,y in zip(lo[t],s)]
    st=scan(s,H,Lw,vo[t],out['dates']) if None not in s[-230:] else {}
    if st: rec['st']=st
    if None not in s[-290:]:
        ep,ev=replay(s,H,Lw,vo[t],out['dates'],days=60)
        for k,x in ep.items(): episodes[k]=episodes.get(k,0)+x
        for e in ev: e['t']=t; events.append(e)
    for k in st: counts[k]=counts.get(k,0)+1
    out['stocks'].append(rec)
# breakouts from setups: add the benchmark's (RSP) move since each breakout for context
spy=out['bench']['RSP']
for e in events:
    e['sp']=round((spy[-1]/spy[e.pop('bi')]-1)*100,1)
# One breakout per stock and setup per base: drop a later breakout through a pivot
# within 2% of an earlier one (the same base re-crossed), and same-day duplicates.
kept=[]
for e in sorted(events,key=lambda e:(e['bd'],e['fs'])):
    if any(k['t']==e['t'] and k['k']==e['k'] and (k['bd']==e['bd'] or abs(k['p']/e['p']-1)<=0.02) for k in kept):
        continue
    kept.append(e)
print('breakouts before/after de-duplication',len(events),len(kept))
events=kept
events.sort(key=lambda e:(e['bd'],e['t']),reverse=True)
out['bo']=events
out['ep']=episodes          # setup episodes started in the replay window
out['bow']=out['dates'][-60]  # first day of the replay window
print('episodes',episodes,'breakouts',len(events))
json.dump(out,open('data.json','w'),separators=(',',':'))
print('setups',counts);print(len(out['stocks']),os.path.getsize('data.json'),out['asOf'],out['dates'][0])
