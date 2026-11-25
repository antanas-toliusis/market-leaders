"""Build weekly.json: about three years of weekly bars for every current S&P 500 member
and the RSP benchmark, loaded by the page only when a weekly view is opened.

A week is the ISO calendar week; its bar is the last close, highest high, lowest low
and total volume of the sessions traded that week, dated by the week's last session.
If the latest week has not ended on a Friday it is marked partial. Sessions that the
daily build filled from a backup source (see build_data.py) are taken from data.json.
"""
import duckdb, json, datetime as dt

WEEKS = 156
c = duckdb.connect()
daily = json.load(open('data.json'))
members = [s['t'] for s in daily['stocks']]
end = dt.date.fromisoformat(daily['asOf'])
start = end - dt.timedelta(weeks=WEEKS + 2)
tick = members + ['RSP']
rows = c.sql(f"""select ticker, date, adj_close, high, low, close, volume from 'data/prices.parquet'
                 where date >= '{start}' and date <= '{end}' and ticker in ({','.join(repr(t) for t in tick)})""").fetchall()
cal = sorted({r[1].date() for r in rows if r[0] == 'RSP'})
wk_of = {d: d.isocalendar()[:2] for d in cal}
weeks = []                      # [(year, week), last session date]
for d in cal:
    if weeks and weeks[-1][0] == wk_of[d]:
        weeks[-1][1] = d
    else:
        weeks.append([wk_of[d], d])
weeks = weeks[-WEEKS:]
widx = {w[0]: i for i, w in enumerate(weeks)}
partial = weeks[-1][1].weekday() < 4 and weeks[-1][1] == end   # current week still open

bars = {t: [None] * len(weeks) for t in tick}   # [close, high, low, vol, last_date]
def add(t, d, close, high, low, vol):
    i = widx.get(d.isocalendar()[:2])
    if i is None or close is None:
        return
    b = bars[t][i]
    if b is None:
        bars[t][i] = [close, high, low, vol or 0, d]
    else:
        if d >= b[4]:
            b[0], b[4] = close, d
        b[1], b[2], b[3] = max(b[1], high), min(b[2], low), b[3] + (vol or 0)

for t, d, adj, h, l, cl, v in rows:
    if adj is None or not cl:
        continue
    f = adj / cl
    add(t, d.date(), adj, (h or cl) * f, (l or cl) * f, v)

# sessions the daily build filled from a backup source (not in the parquet)
for s in daily['stocks']:
    for ds in s.get('gf', []):
        j = daily['dates'].index(ds)
        px, vk = s['c'][j], s['v'][j]
        if px is not None:
            add(s['t'], dt.date.fromisoformat(ds), px, px, px, vk * 1000)

r5 = lambda x: None if x is None else float(f"{x:.5g}")
r4 = lambda x: None if x is None else float(f"{x:.4g}")    # highs/lows: 4 significant figures is plenty
vk = lambda x: int(float(f"{x / 1000:.3g}")) if x else 0
out = {'asOf': daily['asOf'], 'weeks': [str(w[1]) for w in weeks], 'partial': partial, 's': {}}
for t in tick:
    b = bars[t]
    out['s'][t] = {'c': [r5(x[0]) if x else None for x in b], 'h': [r4(x[1]) if x else None for x in b],
                   'l': [r4(x[2]) if x else None for x in b], 'v': [vk(x[3]) if x else 0 for x in b]}
json.dump(out, open('weekly.json', 'w'), separators=(',', ':'))
import os
print('weekly', len(weeks), 'weeks', out['weeks'][0], '->', out['weeks'][-1], 'partial', partial,
      'size', os.path.getsize('weekly.json'))
