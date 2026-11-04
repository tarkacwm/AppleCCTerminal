"""European approximation for short-dated American equity calls.

Do not interpret delta as an assignment probability. Early exercise is possible.
"""
import math
from scipy.stats import norm
from scipy.optimize import brentq


def bs_call(spot: float, strike: float, t: float, rate: float, iv: float, yield_: float = 0.0) -> float:
    if spot <= 0 or strike <= 0 or t < 0 or iv < 0:
        raise ValueError('Invalid pricing input')
    if t == 0:
        return max(spot-strike, 0)
    if iv == 0:
        return max(spot*math.exp(-yield_*t)-strike*math.exp(-rate*t), 0)
    d1 = (math.log(spot/strike)+(rate-yield_+0.5*iv**2)*t)/(iv*math.sqrt(t))
    d2 = d1-iv*math.sqrt(t)
    return spot*math.exp(-yield_*t)*norm.cdf(d1)-strike*math.exp(-rate*t)*norm.cdf(d2)


def call_delta(spot: float, strike: float, t: float, rate: float, iv: float, yield_: float=0.0) -> float:
    if t<=0 or iv<=0:
        return float(spot>strike) if spot != strike else 0.5
    d1=(math.log(spot/strike)+(rate-yield_+0.5*iv**2)*t)/(iv*math.sqrt(t))
    return float(math.exp(-yield_*t)*norm.cdf(d1))


def target_strike(spot: float, t: float, rate: float, iv: float, yield_: float, delta: float) -> float:
    """Invert dividend-adjusted Black-Scholes call delta to theoretical strike."""
    if not (spot>0 and t>0 and iv>0 and 0<delta<math.exp(-yield_*t)):
        raise ValueError('Invalid target strike inputs')
    z=norm.ppf(delta*math.exp(yield_*t))
    return float(spot*math.exp((rate-yield_+0.5*iv**2)*t-z*iv*math.sqrt(t)))


def invert_iv(spot: float, strike: float, t: float, rate: float, market_price: float, yield_:float=0.0) -> float:
    """Compute European-equivalent implied vol; nan if price outside no-arbitrage interval."""
    if t<=0 or market_price<=0:
        return float('nan')
    low=max(0, spot*math.exp(-yield_*t)-strike*math.exp(-rate*t))
    high=spot*math.exp(-yield_*t)
    if not(low < market_price < high):
        return float('nan')
    try:
        return float(brentq(lambda v:bs_call(spot,strike,t,rate,v,yield_)-market_price,1e-5,6.0))
    except ValueError:
        return float('nan')


def ceil_strike(theoretical: float, increments: list[float]) -> float:
    eligible=sorted(float(x) for x in increments if math.isfinite(float(x)) and x>=theoretical)
    return eligible[0] if eligible else float('nan')
