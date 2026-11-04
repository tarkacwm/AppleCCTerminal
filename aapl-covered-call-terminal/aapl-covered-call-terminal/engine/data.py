"""Yahoo adapter; cached in UI. Demo generation is intentionally labeled synthetic."""
import datetime as dt
import numpy as np
import pandas as pd
import yfinance as yf
from .pricing import bs_call


def fetch_market(ticker: str):
    t=yf.Ticker(ticker)
    hist=t.history(period='2y',interval='1d',auto_adjust=True)
    if hist.empty: raise RuntimeError('No price history returned by Yahoo')
    spot=float(hist.Close.iloc[-1])
    expirations=list(t.options)
    return spot,hist,expirations


def fetch_options(ticker: str,expiration:str):
    chain=yf.Ticker(ticker).option_chain(expiration)
    if chain.calls is None or chain.calls.empty: raise RuntimeError('No call chain returned')
    return chain.calls.copy()


def demo_market():
    rng=np.random.default_rng(42)
    dates=pd.bdate_range(end=pd.Timestamp.today().normalize(),periods=510)
    daily=rng.normal(.0003,.23/np.sqrt(252),len(dates))
    close=300*np.exp(np.cumsum(daily))
    hist=pd.DataFrame({'Close':close},index=dates)
    return 300.0,hist


def demo_chain(spot,expiration,rate=.04,div_yield=.004):
    # Synthetic example; not real or executable quotes.
    now=pd.Timestamp.now(tz='UTC')
    expiry=pd.Timestamp(expiration+' 16:00',tz='America/New_York').tz_convert('UTC')
    t=max((expiry-now).total_seconds()/86400/365,.001)
    strikes=np.arange(round(spot*.92/5)*5,round(spot*1.20/5)*5+5,5)
    rows=[]
    for k in strikes:
        vol=.30+.04*max(0,k/spot-1)
        theoretical=bs_call(spot,k,t,rate,vol,div_yield)
        bid=max(0,round(theoretical-.04,2))
        ask=round(theoretical+.04,2)
        rows.append(dict(strike=float(k),bid=bid,ask=ask,impliedVolatility=vol,
            openInterest=500+int(abs(k-spot)),volume=120,lastTradeDate=now,
            contractSymbol=f'DEMO{expiration.replace("-","")}C{k:05.0f}'))
    return pd.DataFrame(rows)


def demo_expirations():
    today=dt.date.today()
    return [(today+dt.timedelta(days=i)).isoformat() for i in (0,1,2,3,4,5,7,10,14,21,30,45,60)]
