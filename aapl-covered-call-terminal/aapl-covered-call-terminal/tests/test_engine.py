from datetime import datetime,timezone,timedelta
import math
import numpy as np
import pandas as pd
from engine.pricing import bs_call, call_delta, target_strike, invert_iv, ceil_strike
from engine.analytics import prepare_chain, realized_vol
from engine.scoring import score_chain,position_flag
from engine.portfolio import projected_paydown,summarize_journal


def test_reverse_delta():
    spot=311.33;t=7/365;r=.04;vol=.30;q=.0035
    for target in (.05,.07,.10,.15):
        strike=target_strike(spot,t,r,vol,q,target)
        assert abs(call_delta(spot,strike,t,r,vol,q)-target)<1e-8

def test_iv_inversion():
    market=bs_call(300,315,7/365,.04,.30,.0035)
    assert abs(invert_iv(300,315,7/365,.04,market,.0035)-.30)<1e-6

def test_bad_iv():
    assert math.isnan(invert_iv(300,330,7/365,.04,-1))

def test_rounded_strike():
    assert ceil_strike(323.9,[320,325,330])==325

def test_realized_vol():
    prices=pd.Series(np.exp(np.cumsum(np.linspace(-.01,.01,300))))
    output=realized_vol(prices)
    assert all(np.isfinite(v) for v in output.values())

def test_option_chain_scoring():
    expiration=(datetime.now(timezone.utc)+timedelta(days=7)).date().isoformat()
    frame=pd.DataFrame([dict(strike=330,bid=.65,ask=.75,openInterest=1500,volume=100,impliedVolatility=.4,lastTradeDate=datetime.now(timezone.utc))])
    prepared=prepare_chain(frame,300,expiration,.04,.0035)
    ranked=score_chain(prepared,300,106000,.70,.04,.0035,.4,.008,.05,.20,.05,100,.30,.01,90)
    assert len(ranked)==1
    assert ranked.iloc[0].gross_premium>0
    assert ranked.iloc[0].score>=0

def test_position_monitor():
    assert position_flag(332,330,.70,1,90)[0]=='REVIEW CLOSE / ROLL'
    assert position_flag(300,330,.04,7,90)[0]=='OK / MONITOR'

def test_margin_amortization():
    df=projected_paydown(1000,.05,300,1)
    assert df.end.iloc[-1]==0
    assert (df.end>=0).all()

def test_journal_loss():
    row=pd.DataFrame([dict(entry_price=.71,exit_price=4.15,contracts=700)])
    out=summarize_journal(row,.4)
    assert out.realized_option_pl.iloc[0]==-240800.0 or abs(out.realized_option_pl.iloc[0]+240800)<.01
    assert out.illustrative_tax_reserve.iloc[0]==0


def test_short_dated_expiration_can_be_scanned():
    """One-day options should be eligible when controls permit them."""
    expiration=(datetime.now(timezone.utc)+timedelta(days=1)).date().isoformat()
    now=datetime.now(timezone.utc)
    frame=pd.DataFrame([dict(strike=315.0,bid=.10,ask=.12,openInterest=5000,volume=400,
        impliedVolatility=.55,lastTradeDate=now)])
    prepared=prepare_chain(frame,300,expiration,.04,.0035,now=now)
    ranked=score_chain(prepared,300,106000,.7,.04,.0035,.4,.008,.05,.20,.05,100,.40,.001,90,
                       min_dte=.001,max_dte=2.999)
    assert 0 < ranked.dte.iloc[0] < 3
    assert bool(ranked.eligible.iloc[0])


def test_zero_time_to_expiration_is_not_eligible():
    expiry=(datetime.now(timezone.utc)-timedelta(days=1)).date().isoformat()
    raw=pd.DataFrame([dict(strike=330.0,bid=.10,ask=.12,openInterest=1000,volume=100,
        impliedVolatility=.50)])
    prepared=prepare_chain(raw,300,expiry,.04,.0035)
    ranked=score_chain(prepared,300,106000,.7,.04,.0035,.4,.008,.05,.20,.05,100,.40,.001,90,
                       min_dte=.001,max_dte=2.999)
    assert not bool(ranked.eligible.iloc[0])
