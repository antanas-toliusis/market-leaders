"""Replay the setup scan over recent history and track what happened next.

For each of the last `days` sessions the scan runs on data up to that session
only (no look-ahead). Consecutive flagged days for the same stock and setup
form an episode. A breakout is the first close above the pivot (crossing up
from at or below it) within 20 sessions after the episode's last flagged day.
Pocket pivots are entry signals rather than bases, so they are not tracked here.
"""
from setups import scan

GAP = 5            # flagged days this close together belong to one episode
FOLLOW = 20        # sessions after the last flag in which a breakout still counts
STOP = 0.92        # a close more than 8% under the breakout close = failed (O'Neil's 7-8% rule)


def replay(close, high, low, vol, dates, days=60):
    n = len(close)
    flags = {}     # setup -> [(day, pivot)]
    for d in range(n - days, n):
        if d < 230:
            continue
        c = close[:d + 1]
        if None in c[-230:]:
            continue
        found = scan(c, high[:d + 1], low[:d + 1], vol[:d + 1], dates[:d + 1])
        for k, v in found.items():
            if k != 'pp':
                flags.setdefault(k, []).append((d, v['p']))
    episodes, events = {}, []
    for k, fl in flags.items():
        groups, cur = [], [fl[0]]
        for f in fl[1:]:
            if f[0] - cur[-1][0] > GAP:
                groups.append(cur)
                cur = [f]
            else:
                cur.append(f)
        groups.append(cur)
        episodes[k] = len(groups)
        for g in groups:
            ev = _breakout(close, vol, dates, g)
            if ev:
                ev['k'] = k
                events.append(ev)
    return episodes, events


def _event(close, vol, dates, first, j, p, late=False):
    """Breakout on session j at pivot p, bought at that day's close. Result with an 8%
    stop: exit at the first later close more than 8% under the buy price, otherwise
    hold to the latest close."""
    after = [x for x in close[j + 1:] if x is not None]
    now = close[-1] if close[-1] is not None else (after[-1] if after else close[j])
    v50 = sum(vol[j - 50:j]) / 50 if j >= 50 else 0
    stop_hit = next((x for x in after if x < close[j] * STOP), None)
    status = 'failed' if stop_hit is not None else ('holding' if now >= p else 'below')
    exit_px = stop_hit if stop_hit is not None else now
    ev = {
        'fs': dates[first], 'p': round(p, 2), 'bd': dates[j], 'bi': j,
        'bc': round(close[j], 2), 'bv': round(vol[j] / v50, 2) if v50 else None,
        'g': round((now / close[j] - 1) * 100, 1),
        'mg': round((max(after + [close[j]]) / close[j] - 1) * 100, 1),
        'r': round((exit_px / close[j] - 1) * 100, 1),
        'st': status,
    }
    if late:
        ev['late'] = 1
    return ev


def _breakout(close, vol, dates, group):
    n = len(close)
    first, last = group[0][0], group[-1][0]
    piv = dict(group)
    p = group[0][1]
    if first < 1 or close[first] is None or close[first - 1] is None:
        return None
    # Flagged only once the price was already above the pivot (the scan allows up to
    # +3-5%): the earliest a trader could act is that day's close, so count it there.
    if close[first] > p and close[first - 1] > p:
        return _event(close, vol, dates, first, first, p, late=True)
    for j in range(first, min(last + FOLLOW, n - 1) + 1):
        if j - 1 in piv:
            p = piv[j - 1]
        if close[j] is None or close[j - 1] is None:
            continue
        if close[j - 1] <= p < close[j]:
            return _event(close, vol, dates, first, j, p)
    return None
