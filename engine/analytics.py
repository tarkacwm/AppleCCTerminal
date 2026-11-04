from __future__ import annotations
from datetime import datetime, timezone
import math
import numpy as np
import pandas as pd
from .pricing import call_delta, invert_iv


def realized_vol(close: pd.Series) -> dict:
    values=pd.to_numeric(close, errors='coerce').dropna()
    daily=np.log(values/values.shift(1)).dropna()
    out={}
    for n in (10,20,60,252):
        out[n]=float(daily.iloc[-n:].std(ddof=1)*math.sqrt(252)) if len(daily)>=n else float('nan')
    return out


def quote_mid(bid:float,ask:float)->float:
    return (bid+ask)/2 if np.isfinite(bid) and np.isfinite(ask) and ask>=bid and bid>0 else float('nan')


def prepare_chain(frame:pd.DataFrame,spot:float,expiration:str, rate:float,yield_:float, now:datetime|None=None)->pd.DataFrame:
    out=frame.copy()
    now=now or datetime.now(timezone.utc)
    # Expiration at 4 pm New York. Explicit DST conversion via pandas.
    cutoff=pd.Timestamp(f'{expiration} 16:00',tz='America/New_York').tz_convert('UTC')
    t=max((cutoff-pd.Timestamp(now)).total_seconds(),0)/ (365*24*3600)
    out['expiration']=expiration
    out['dte']=round(t*365,3)
    for col in ('strike','bid','ask','volume','openInterest','impliedVolatility'):
        if col not in out: out[col]=np.nan
        out[col]=pd.to_numeric(out[col],errors='coerce')
    out['mid']=[quote_mid(b,a) for b,a in zip(out.bid,out.ask)]
    out['spread_pct']=(out.ask-out.bid)/out.mid
    out['otm_pct']=out.strike/spot-1
    out['market_iv']=out.impliedVolatility.where(out.impliedVolatility.between(0.015,4.0))
    out['derived_iv']=[invert_iv(spot,k,t,rate,m,yield_) if np.isfinite(m) else float('nan') for k,m in zip(out.strike,out.mid)]
    # Source IV primary; derived IV for diagnostic only. For invalid source IV, derived IV is used and flagged.
    out['used_iv']=out.market_iv.combine_first(out.derived_iv)
    out['iv_source']=np.where(out.market_iv.notna(),'Yahoo quoted IV',np.where(out.derived_iv.notna(),'Mid-price inversion','Unavailable'))
    out['delta']=[call_delta(spot,k,t,rate,v,yield_) if np.isfinite(v) else np.nan for k,v in zip(out.strike,out.used_iv)]
    out['quote_age_hours']=np.nan
    if 'lastTradeDate' in out:
        trade_dt=pd.to_datetime(out.lastTradeDate,errors='coerce',utc=True)
        out['quote_age_hours']=(pd.Timestamp(now)-trade_dt).dt.total_seconds()/3600
    # lastTradeDate refers to last trade, NOT bid/ask quote timestamp.
    out['contractSymbol']=out.get('contractSymbol',pd.Series(index=out.index,dtype=str))
    return out


def stress_cost(spot:float,strike:float,iv:float,t:float,rate:float,yield_:float,premium:float,shock:float,days_forward:float=0)->float:
    """Buyback debit minus original premium per share after instantaneous price shock.
    Held IV constant; does not include bid/ask friction.
    """
    from .pricing import bs_call
    t=max(t-days_forward/365,0)
    return bs_call(spot*(1+shock),strike,t,rate,iv,yield_)-premium
