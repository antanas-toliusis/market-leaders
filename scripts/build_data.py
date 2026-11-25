import duckdb, csv, json, os, sys
sys.path.insert(0, os.path.dirname(__file__))
from setups import scan
c=duckdb.connect()
members=[r[0] for r in c.sql("""select ticker from 'data/membership_intervals.parquet' where "end" is null""").fetchall()]
meta={}
for r in csv.DictReader(open('data/constituents.csv')):
    meta[r['Symbol'].replace('.','-')]=(r['Security'],r['GICS Sector'],r['GICS Sub-Industry'])
bench=['SPY','RSP','QQQ']
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
counts={}
for t in members:
    s=ser[t]
    if sum(v is not None for v in s)<60: print('short',t); 
    n,sec,ind=meta.get(t,(t,'Unknown','Unknown'))
    rec={'t':t,'n':n,'s':sec,'i':ind,'c':rnd(s)}
    H=[x if x is not None else y for x,y in zip(hi[t],s)]; Lw=[x if x is not None else y for x,y in zip(lo[t],s)]
    st=scan(s,H,Lw,vo[t],out['dates']) if None not in s[-230:] else {}
    if st: rec['st']=st
    for k in st: counts[k]=counts.get(k,0)+1
    out['stocks'].append(rec)
json.dump(out,open('data.json','w'),separators=(',',':'))
print('setups',counts);print(len(out['stocks']),os.path.getsize('data.json'),out['asOf'],out['dates'][0])
