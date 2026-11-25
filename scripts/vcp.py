"""Volatility Contraction Pattern (VCP) detection, after Mark Minervini.

A VCP is a base in an uptrend where each pullback is shallower than the one
before it (e.g. 25% -> 12% -> 5%), volume dries up, and price tightens just
under a pivot high. This is a rules-based approximation: it flags candidates
to look at on a chart, not confirmed setups.
"""

ZIGZAG_PCT = 0.04     # minimum swing to count as a pivot
BASE_MAX_DAYS = 130   # look for the base within ~6 months
BASE_MIN_DAYS = 25    # a base needs some width (about 5 weeks)
MIN_FIRST = 0.10      # first contraction at least 10% deep
MAX_FIRST = 0.40      # ...and no deeper than 40%
MAX_LAST = 0.12       # final contraction no deeper than 12%
MIN_CONTRACTIONS = 2
PIVOT_BELOW = 0.08    # close no more than 8% under the pivot...
PIVOT_ABOVE = 0.03    # ...and no more than 3% above it (fresh breakout)
VOL_DRY = 0.85        # 10-day avg volume below 85% of 50-day avg


def _sma(a, n):
    return sum(a[-n:]) / n if len(a) >= n else None


def _zigzag(high, low, pct):
    """Alternating swing pivots [(i, price, 'H'|'L')] from daily highs and lows.
    The open leg is closed off, so a pullback still in progress counts too."""
    piv, up, hi_i, lo_i = [], None, 0, 0
    for i in range(1, len(high)):
        if up is None:
            if high[i] > high[hi_i]: hi_i = i
            if low[i] < low[lo_i]: lo_i = i
            if hi_i > lo_i and high[hi_i] >= low[lo_i] * (1 + pct):
                piv.append((lo_i, low[lo_i], 'L')); up = True
            elif lo_i > hi_i and low[lo_i] <= high[hi_i] * (1 - pct):
                piv.append((hi_i, high[hi_i], 'H')); up = False
        elif up:
            if high[i] > high[hi_i]: hi_i = i
            elif low[i] <= high[hi_i] * (1 - pct):
                piv.append((hi_i, high[hi_i], 'H')); up = False; lo_i = i
        else:
            if low[i] < low[lo_i]: lo_i = i
            elif high[i] >= low[lo_i] * (1 + pct):
                piv.append((lo_i, low[lo_i], 'L')); up = True; hi_i = i
    if up:
        piv.append((hi_i, high[hi_i], 'H'))
        if hi_i < len(low) - 1:
            j = min(range(hi_i + 1, len(low)), key=lambda k: low[k])
            piv.append((j, low[j], 'L'))
    elif up is False:
        piv.append((lo_i, low[lo_i], 'L'))
    return piv


def detect(close, high, low, vol):
    """Return a dict describing the VCP, or None. Inputs are oldest-first, same length."""
    n = len(close)
    if n < 220 or any(v is None for v in close[-220:]):
        return None
    c = close[-1]
    s50, s150, s200 = _sma(close, 50), _sma(close, 150), _sma(close, 200)
    s200_prev = sum(close[-220:-20]) / 200
    hi52, lo52 = max(high[-252:]), min(low[-252:])
    # Stage 2 uptrend (Minervini trend template, slightly relaxed)
    if not (c > s50 and c > s150 and s150 > s200 and s200 >= s200_prev):
        return None
    if c < lo52 * 1.25 or c < hi52 * 0.75:
        return None

    H, L = high[-BASE_MAX_DAYS:], low[-BASE_MAX_DAYS:]
    piv = _zigzag(H, L, ZIGZAG_PCT)
    highs = [p for p in piv if p[2] == 'H']
    if not highs:
        return None
    # base starts at the highest swing high that still has room for contractions
    start = max((p for p in highs if p[0] <= len(H) - BASE_MIN_DAYS), key=lambda p: p[1], default=None)
    if start is None:
        return None
    seq = [p for p in piv if p[0] >= start[0]]
    if seq[0][2] != 'H':
        return None
    depths, pivot_hi = [], None
    for a, b in zip(seq, seq[1:]):
        if a[2] == 'H' and b[2] == 'L':
            depths.append((a[1] - b[1]) / a[1])
            pivot_hi = a
    if len(depths) < MIN_CONTRACTIONS or depths[-1] > MAX_LAST:
        return None
    # Major contractions: the deepest pullback in the base, then the deepest one
    # after it, and so on. Small wiggles inside a bigger swing are ignored, and a
    # step only counts if it is clearly shallower (at most 85% of the previous).
    chain, i = [], 0
    while i < len(depths):
        j = max(range(i, len(depths)), key=lambda k: depths[k])
        if not chain or depths[j] <= chain[-1] * 0.85:
            chain.append(depths[j])
        i = j + 1
    if len(chain) < MIN_CONTRACTIONS:
        return None
    if not (MIN_FIRST <= chain[0] <= MAX_FIRST) or chain[-1] > chain[0] * 0.6:
        return None
    depths = chain
    pivot = pivot_hi[1]
    if not (pivot * (1 - PIVOT_BELOW) <= c <= pivot * (1 + PIVOT_ABOVE)):
        return None
    v10, v50 = _sma(vol, 10), _sma(vol, 50)
    if not v50 or v10 / v50 > VOL_DRY:
        return None
    return {
        'd': [round(x * 100, 1) for x in depths],   # contraction depths, %
        'p': round(pivot, 2),                        # pivot (buy point)
        'pd': round((c / pivot - 1) * 100, 1),       # close vs pivot, %
        'vr': round(v10 / v50, 2),                   # 10d / 50d volume
        'bd': len(H) - start[0],                     # base length, days
    }
