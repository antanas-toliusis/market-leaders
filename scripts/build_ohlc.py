"""Build ohlc.json: daily open, high and low for every stock in data.json, on the same
dates and the same adjusted scale as data.json's closes, for drawing candles. The page
loads it only when a chart is opened.

Sessions the daily build filled from a backup source have no open/high/low here, so
they are drawn from the close alone (null in this file).
"""
import duckdb, json, os

daily = json.load(open('data.json'))
dates = daily['dates']
idx = {d: i for i, d in enumerate(dates)}
tick = [s['t'] for s in daily['stocks']] + list(daily['bench'])   # benchmarks too, for the index chart
rows = duckdb.sql(f"""select ticker, strftime(date, '%Y-%m-%d'), adj_close, open, high, low, close
                      from 'data/prices.parquet'
                      where date >= '{dates[0]}' and date <= '{dates[-1]}'
                        and ticker in ({','.join(repr(t) for t in tick)})""").fetchall()
n = len(dates)
o = {t: [None] * n for t in tick}; h = {t: [None] * n for t in tick}; l = {t: [None] * n for t in tick}
for t, d, adj, op, hi, lo, cl in rows:
    i = idx.get(d)
    if i is None or adj is None or not cl:
        continue
    f = adj / cl                                   # same adjustment as the close
    o[t][i] = op * f if op else None
    h[t][i] = hi * f if hi else None
    l[t][i] = lo * f if lo else None
r4 = lambda x: None if x is None else float(f"{x:.4g}")   # 4 significant figures: within about 0.05% of the price
out = {'asOf': daily['asOf'], 's': {t: {'o': [r4(x) for x in o[t]], 'h': [r4(x) for x in h[t]],
                                        'l': [r4(x) for x in l[t]]} for t in tick}}
json.dump(out, open('ohlc.json', 'w'), separators=(',', ':'))
print('ohlc', len(tick), 'stocks', n, 'sessions', 'size', os.path.getsize('ohlc.json'))
