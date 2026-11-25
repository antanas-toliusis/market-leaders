"""Chart-pattern detection for market leaders (O'Neil / Minervini / Morales-Kacher style).

Every detector takes oldest-first daily series of equal length (adjusted close, high,
low, volume; dates as 'YYYY-MM-DD') and returns a dict or None. Common fields:
  p   pivot / buy point          pd  close vs pivot, %
  bd  days the pattern spans (for drawing the pivot line)
These are rules-based approximations meant to surface candidates for a chart check.
"""
from datetime import date as _date

from vcp import detect as vcp


def _sma(a, n, end=None):
    end = len(a) if end is None else end
    return sum(a[end - n:end]) / n if end >= n else None


def _pd(c, p):
    return round((c / p - 1) * 100, 1)


def _uptrend(close):
    """Price above a rising 200-day, with the 50-day above the 200-day: the minimum for
    any base (the close may dip under the 50-day, e.g. a handle resting on it)."""
    s50, s200 = _sma(close, 50), _sma(close, 200)
    s200_prev = _sma(close, 200, len(close) - 20)
    return s50 and s200 and s200_prev and close[-1] > s200 and s50 > s200 and s200 >= s200_prev


def _cup(close, high, low, vol, *, h_days=(5, 25), h_depth=(0.03, 0.15), right_max=1.05,
         advance=1.25, near=(0.92, 1.05), vol_max=1.0, extra=None):
    """Shared cup-with-handle search. Returns the most recent valid cup or None.
    A cup: 25%+ advance into a left lip (local high), 12-35% deep, 30+ days, low in the
    middle 60% with a week or more in the bottom third (a U, not a V), right lip back
    near the left. The handle runs from the right lip to today and stays in the upper
    half of the cup. `extra(close, n, r_i)` can add conditions (e.g. support at an MA)."""
    n = len(close)
    if n < 230 or not _uptrend(close):
        return None
    c = close[-1]
    best = None
    for i in range(max(60, n - 280), n - 40):
        if high[i] != max(high[max(0, i - 10):i + 11]):
            continue
        left = high[i]
        if left < min(low[max(0, i - 120):i]) * advance:
            continue
        seg_end = n - h_days[0]
        if seg_end - i < 32:
            continue
        lo_i = min(range(i + 1, seg_end), key=lambda k: low[k])
        cup_low = low[lo_i]
        depth = (left - cup_low) / left
        if not (0.12 <= depth <= 0.35) or lo_i >= seg_end - 1:
            continue
        r_i = max(range(lo_i + 1, seg_end), key=lambda k: high[k])
        right = high[r_i]
        cup_days = r_i - i
        if cup_days < 30 or not (0.90 * left <= right <= right_max * left):
            continue
        if not (0.2 <= (lo_i - i) / cup_days <= 0.8):
            continue
        third = cup_low + (left - cup_low) / 3
        if sum(1 for k in range(i, r_i + 1) if close[k] <= third) < 5:
            continue
        hd = n - 1 - r_i
        if not (h_days[0] <= hd <= h_days[1]):
            continue
        h_low = min(low[r_i:])
        hdep = (right - h_low) / right
        if not (h_depth[0] <= hdep <= h_depth[1]):
            continue
        if h_low < cup_low + (left - cup_low) / 2:
            continue
        v_handle = sum(vol[r_i + 1:]) / hd
        v50 = _sma(vol, 50)
        if not v50 or v_handle > v50 * vol_max:
            continue
        pivot = right
        if not (pivot * near[0] <= c <= pivot * near[1]):
            continue
        more = extra(close, n, r_i) if extra else {}
        if more is None:
            continue
        cand = {'p': round(pivot, 2), 'pd': _pd(c, pivot), 'bd': n - i,
                'cd': round(depth * 100, 1), 'cw': round(cup_days / 5), 'hd': round(hdep * 100, 1),
                'hw': round(hd / 5, 1), 'vr': round(v_handle / v50, 2), **more}
        if best is None or i > best[0]:   # keep the most recent valid cup
            best = (i, cand)
    return best[1] if best else None


def cup_with_handle(close, high, low, vol, dates=None):
    """Classic: a 1-5 week handle 3-15% deep on lighter volume, close near the pivot."""
    return _cup(close, high, low, vol)


def _handle_at_ma(close, n, r_i):
    """The handle has pulled back to a rising 50-day average and is holding it: close
    within 3% below to 3% above the 50-day, the 50-day higher than 20 days ago, and no
    close more than 3% under the 50-day during the handle's last 10 sessions."""
    c, s50 = close[-1], _sma(close, 50)
    s50_prev = _sma(close, 50, n - 20)
    if not (s50 and s50_prev and s50 > s50_prev and 0.97 * s50 <= c <= 1.03 * s50):
        return None
    for j in range(max(r_i, n - 10), n):
        s50j = _sma(close, 50, j + 1)
        if s50j and close[j] < s50j * 0.97:
            return None
    return {'ma': '50d', 'md': _pd(c, s50)}


def cup_handle_at_ma(close, high, low, vol, dates=None):
    """A cup whose handle has drifted back to a rising 50-day and is holding it:
    handle 1-10 weeks, 3-18% deep, still in the upper half of the cup, close 2-18% under
    the pivot and within 3% of the 50-day without breaking below it."""
    return _cup(close, high, low, vol, h_days=(5, 50), h_depth=(0.03, 0.18), right_max=1.15,
                advance=1.20, near=(0.82, 0.98), vol_max=1.15, extra=_handle_at_ma)


def flat_base(close, high, low, vol, dates=None):
    """At least 5 weeks moving sideways in a range no deeper than 15%, after an advance
    of 20%+, with the close within 5% either side of the top of the range (excluding
    today's bar)."""
    n = len(close)
    if n < 230 or not _uptrend(close):
        return None
    c = close[-1]
    # longest window ending today whose high-low range stays within 15%
    length, hi, lo = 0, 0.0, float('inf')
    for k in range(n - 1, max(0, n - 130) - 1, -1):
        h2, l2 = max(hi, high[k]), min(lo, low[k])
        if (h2 - l2) / h2 > 0.15:
            break
        hi, lo, length = h2, l2, length + 1
    if length < 25:
        return None
    start = n - length
    prior_low = min(low[max(0, start - 63):start]) if start > 0 else None
    if not prior_low or close[start] < prior_low * 1.20:
        return None
    # pivot: the top of the range before today, so a stock breaking out today shows
    # above its pivot rather than under its own intraday high
    pivot = max(high[start:n - 1]) if length > 1 else hi
    if not (pivot * 0.95 <= c <= pivot * 1.05):
        return None
    return {'p': round(pivot, 2), 'pd': _pd(c, pivot), 'bd': length,
            'dp': round((hi - lo) / hi * 100, 1), 'w': round(length / 5, 1)}


def high_tight_flag(close, high, low, vol, dates=None):
    """Price roughly doubles (90%+) in 3-8 weeks, then a flag of 2-5 weeks that pulls
    back no more than 25% and holds within 15% of the peak."""
    n = len(close)
    if n < 60:
        return None
    c = close[-1]
    p_i = max(range(n - 30, n - 3), key=lambda k: high[k])
    peak = high[p_i]
    if peak != max(high[n - 30:]):
        return None
    flag_days = n - 1 - p_i
    if not (10 <= flag_days <= 25):
        return None
    pole_lo_i = min(range(p_i - 40, p_i - 15), key=lambda k: low[k])
    gain = peak / low[pole_lo_i] - 1
    if gain < 0.90:
        return None
    flag_depth = (peak - min(low[p_i:])) / peak
    if not (0.05 <= flag_depth <= 0.25) or c < peak * 0.85:
        return None
    return {'p': round(peak, 2), 'pd': _pd(c, peak), 'bd': n - pole_lo_i,
            'g': round(gain * 100), 'fd': round(flag_depth * 100, 1), 'fw': round(flag_days / 5, 1)}


def pocket_pivot(close, high, low, vol, dates=None):
    """In the last 5 sessions: an up day whose volume beats every down-day volume of
    the 10 sessions before it, closing in the upper half of its range, above the 50-day
    and not extended more than 5% above the 10-day average."""
    n = len(close)
    if n < 60 or not _uptrend(close):
        return None
    for j in range(n - 1, n - 6, -1):
        if close[j] <= close[j - 1] or not vol[j]:
            continue
        downs = [vol[k] for k in range(j - 10, j) if close[k] < close[k - 1]]
        if not downs or vol[j] <= max(downs):
            continue
        rng = high[j] - low[j]
        if rng > 0 and (close[j] - low[j]) / rng < 0.5:
            continue
        s50, s10 = _sma(close, 50, j + 1), _sma(close, 10, j + 1)
        if close[j] < s50 or close[j] > s10 * 1.05:
            continue
        return {'p': round(high[j], 2), 'pd': _pd(close[-1], high[j]), 'bd': n - j,
                'dt': dates[j] if dates else None, 'vx': round(vol[j] / max(downs), 2),
                'ago': n - 1 - j}
    return None


def three_weeks_tight(close, high, low, vol, dates):
    """Three consecutive completed weekly closes within 1.5% of each other, in an
    uptrend that is up 20%+ over the prior three months. Pivot: the high of those weeks."""
    n = len(close)
    if n < 230 or not _uptrend(close):
        return None
    weeks = []   # (year, week) -> [first_idx, last_idx]
    for k, d in enumerate(dates):
        y, w, _ = _date.fromisoformat(d).isocalendar()
        if weeks and weeks[-1][0] == (y, w):
            weeks[-1][2] = k
        else:
            weeks.append([(y, w), k, k])
    # drop the current week unless it ended on a Friday
    if _date.fromisoformat(dates[-1]).weekday() < 4:
        weeks = weeks[:-1]
    if len(weeks) < 20:
        return None
    last3 = weeks[-3:]
    wc = [close[w[2]] for w in last3]
    tight = (max(wc) - min(wc)) / min(wc)
    if tight > 0.015:
        return None
    first = last3[0][1]
    if close[first] < min(low[max(0, first - 63):first]) * 1.20:
        return None
    pivot = max(high[last3[0][1]:last3[-1][2] + 1])
    c = close[-1]
    if not (pivot * 0.95 <= c <= pivot * 1.05):
        return None
    return {'p': round(pivot, 2), 'pd': _pd(c, pivot), 'bd': n - first,
            'tr': round(tight * 100, 2), 'wk': last3[-1][0][1]}


DETECTORS = {
    'vcp': lambda c, h, l, v, d: vcp(c, h, l, v),
    'cwh': cup_with_handle,
    'cwm': cup_handle_at_ma,
    'flat': flat_base,
    'htf': high_tight_flag,
    'pp': pocket_pivot,
    'twt': three_weeks_tight,
}


def scan(close, high, low, vol, dates):
    out = {}
    for key, fn in DETECTORS.items():
        try:
            r = fn(close, high, low, vol, dates)
        except (ValueError, ZeroDivisionError, TypeError):
            r = None
        if r:
            out[key] = r
    return out
