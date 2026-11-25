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
# Gap filling. If a member's source prices stop before the latest session (e.g. the
# source lagging after a stock split), fetch only the missing sessions: first from
# Yahoo Finance, then from Stooq for anything Yahoo also lacks. Source rows are never
# overridden, and any session still missing is flagged on the page.
import io, urllib.request, datetime as _dt
src_last={t:max((i for i,v in enumerate(ser[t]) if v is not None),default=None) for t in members}
stale=[t for t in members if src_last[t] is not None and src_last[t]<len(dates)-1]
filled={}
def _put(t,i,cl,hh,ll,vv,ratio):
    ser[t][i]=cl*ratio; hi[t][i]=hh*ratio; lo[t][i]=ll*ratio; vo[t][i]=int((vv or 0)/ratio)   # shares on the same scale
    filled.setdefault(t,[]).append(str(dates[i].date()))
# The backup sources split-adjust their whole history, while the source's last rows may
# predate a split (that is often why it lags). So each backup is put on the source's scale
# by matching its close on the source's last session: a split shows as no jump at all,
# and a backup without that overlap session is not used.
def _scale(t,closes):
    k=src_last[t]; b=closes.get(k)
    return ser[t][k]/b if b else None
for t in stale:
    start,end=dates[src_last[t]].date(),dates[-1].date()     # from the overlap session
    try:
        import yfinance as yf
        df=yf.download(t,start=str(start),end=str(end+_dt.timedelta(days=1)),auto_adjust=False,progress=False,actions=False,multi_level_index=False)
        got={}
        for d_,row in (df.iterrows() if df is not None else []):
            i=idx.get(d_.to_pydatetime().replace(tzinfo=None))
            if i is not None and row['Close']==row['Close']: got[i]=row
        ratio=_scale(t,{i:float(r_['Close']) for i,r_ in got.items()})
        if ratio is None and got: print('gap fill (yahoo): no overlap session to scale',t)
        for i,row in got.items():
            if ratio and ser[t][i] is None:
                _put(t,i,float(row['Close']),float(row['High']),float(row['Low']),row['Volume'],ratio)
    except Exception as e:
        print('gap fill (yahoo) failed:',t,type(e).__name__,e)
    if any(ser[t][i] is None for i in range(src_last[t]+1,len(dates))):
        try:
            url=f"https://stooq.com/q/d/l/?s={t.lower()}.us&d1={start:%Y%m%d}&d2={end:%Y%m%d}&i=d"
            txt=urllib.request.urlopen(url,timeout=20).read().decode()
            if not txt.startswith('Date'): print('gap fill (stooq) reply:',t,txt[:80].replace(chr(10),' '))
            got={}
            for row in csv.DictReader(io.StringIO(txt)):
                try: i=idx.get(_dt.datetime.strptime(row['Date'],'%Y-%m-%d'))
                except (KeyError,ValueError): continue
                if i is not None: got[i]=row
            ratio=_scale(t,{i:float(r_['Close']) for i,r_ in got.items()})
            if ratio is None and got: print('gap fill (stooq): no overlap session to scale',t)
            for i,row in got.items():
                if ratio and ser[t][i] is None:
                    _put(t,i,float(row['Close']),float(row['High']),float(row['Low']),float(row.get('Volume') or 0),ratio)
        except Exception as e:
            print('gap fill (stooq) failed:',t,type(e).__name__,e)
    left=[str(dates[i].date()) for i in range(src_last[t]+1,len(dates)) if ser[t][i] is None]
    print('gap fill',t,'filled',sorted(filled.get(t,[])),'still missing',left)
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
    rec={'t':t,'n':n,'s':sec,'i':ind,'c':rnd(s),'v':[int(float(f'{x/1000:.3g}')) if x else 0 for x in vo[t]]}  # volume in thousands
    if src_last[t] is not None and any(x is None for x in s[src_last[t]+1:]):
        rec['md']=[str(dates[i].date()) for i in range(src_last[t]+1,len(dates)) if s[i] is None]   # sessions no source had
        print('missing',t,rec['md'])
    if t in filled: rec['gf']=sorted(filled[t])
    # NR7: sessions in the last 10 whose high-low range is the narrowest of the 7 sessions ending there
    rg=[(x-y) if x is not None and y is not None else None for x,y in zip(hi[t],lo[t])]
    nr=[str(dates[j].date()) for j in range(len(dates)-10,len(dates))
        if rg[j] is not None and None not in rg[j-6:j] and rg[j]<min(rg[j-6:j]) and (src_last[t] is None or j<=src_last[t] or t in filled)]
    if nr: rec['nr']=nr
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
