"""AAPL covered call research dashboard. Read-only; no broker orders."""
from __future__ import annotations
from datetime import datetime, date, timedelta, timezone
import io
import math
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st
from engine.data import fetch_market, fetch_options, demo_market, demo_chain, demo_expirations
from engine.analytics import realized_vol,prepare_chain,stress_cost
from engine.pricing import target_strike, call_delta, ceil_strike
from engine.scoring import score_chain, position_flag
from engine.portfolio import projected_paydown,summarize_journal

st.set_page_config(page_title='AAPL Option Management Terminal',page_icon='📈',layout='wide')
st.title('AAPL | Covered-Call Management Terminal')
st.caption('Research and risk monitoring • no trade execution • Yahoo options quotes may be delayed or stale')

@st.cache_data(ttl=300,show_spinner=False)
def market_data(ticker): return fetch_market(ticker)

@st.cache_data(ttl=300,show_spinner=False)
def options_data(ticker,expiry): return fetch_options(ticker,expiry)

with st.sidebar:
    st.header('Portfolio & data')
    mode=st.radio('Source',['Yahoo Finance','Synthetic demonstration'],index=0)
    ticker=st.text_input('Symbol','AAPL').strip().upper()
    shares=st.number_input('Shares owned',min_value=100,value=100000,step=100)
    overwrite=st.slider('Maximum overwrite (%)',0,100,100)/100
    loan=st.number_input('Margin balance ($)',min_value=0.0,value=0.01,step=100000.0)
    loan_rate=st.number_input('Annual margin rate (%)',0.0,25.0,4.85,.05)/100
    st.header('Model assumptions')
    target_delta=st.slider('Target entry delta',.01,.30,.05,.01)
    max_delta=st.slider('Maximum entry delta',.01,.40,.10,.01)
    rate=st.number_input('Short-term risk-free rate (%)',0.0,20.0,4.0,.1)/100
    div_yield=st.number_input('Dividend yield (%)',0.0,15.0,.35,.05)/100
    option_tax=st.number_input('Option gain tax reserve (%)',0.0,60.0,40.0,1.0)/100
    fee=st.number_input('Annual advisory fee (%)',0.0,5.0,.80,.05)/100
    st.header('Expiration selection')
    min_dte=st.number_input('Minimum calendar DTE for new writes',min_value=0,max_value=365,value=0,step=1,help='0 includes same-day expiry, if it has not passed the market cutoff.')
    max_dte=st.number_input('Maximum calendar DTE for new writes',min_value=0,max_value=365,value=45,step=1)
    st.caption('0–2 DTE contracts are high gamma-risk. Longer expirations are available too; controls do not execute trades.')
    st.header('Trade safeguards')
    min_otm=st.number_input('Min upside cushion (%)',0.0,25.0,5.0,.5)/100
    min_oi=st.number_input('Minimum open interest',0,20000,100,50)
    max_spread=st.number_input('Max bid/ask spread (%)',1.0,100.0,25.0,1.0)/100
    min_yield=st.number_input('Min gross annualized premium (%)',0.0,100.0,5.0,1.0)/100
    earnings_days=st.number_input('Calendar days to next earnings (manual)',0,365,60)
    exdiv=st.number_input('Days to next ex-dividend (manual; 999 unknown)',0,999,999)
    extra_sale=st.number_input('Annual gross share-sale cash applied to loan ($)',min_value=0.0,value=0.0,step=100000.0)
    st.caption('Capital-gains taxes on stock sales assumed funded externally. Confirm exact tax/fee basis and loan cash-flow mechanics.')
    if st.button('Clear Yahoo data cache'):
        market_data.clear();options_data.clear();st.rerun()

try:
    if mode=='Yahoo Finance': spot,hist,expirations=market_data(ticker)
    else:
        spot,hist=demo_market();expirations=demo_expirations()
except Exception as exc:
    st.error(f'Yahoo data unavailable: {exc}. Switch to Synthetic demonstration to explore the model.');st.stop()

if not expirations:
    st.error('No expirations available. Try the synthetic demonstration mode.');st.stop()

vols=realized_vol(hist.Close)
expiry_choices=sorted(e for e in expirations if (date.fromisoformat(e)-date.today()).days>=0)
if not expiry_choices: st.error('No remaining expirations returned by the data source.');st.stop()
st.subheader('Market context')
a,b,c,d,e=st.columns(5)
a.metric('Spot price',f'${spot:,.2f}')
b.metric('10D realized vol',f'{vols[10]:.1%}' if np.isfinite(vols[10]) else 'N/A')
c.metric('20D realized vol',f'{vols[20]:.1%}' if np.isfinite(vols[20]) else 'N/A')
d.metric('60D realized vol',f'{vols[60]:.1%}' if np.isfinite(vols[60]) else 'N/A')
e.metric('252D realized vol',f'{vols[252]:.1%}' if np.isfinite(vols[252]) else 'N/A')
st.caption(f'Data source: {mode}; retrieved/cached in session; refresh cache manually. Last historical bar: {hist.index[-1]}. Last trade time is not a quote timestamp.')

st.caption('Choose **any available expiration**, including same-day or next-day contracts when listed. Available dates depend on the underlying and data source.')
filtered_expirations=[e for e in expiry_choices if min_dte <= (date.fromisoformat(e)-date.today()).days <= max_dte]
if min_dte>max_dte: st.warning('Minimum DTE exceeds maximum DTE. Adjust the sidebar range.')
default_expirations=filtered_expirations[:min(3,len(filtered_expirations))]
selection=st.multiselect('Expirations to scan (all listed dates)',expiry_choices,default=default_expirations,help='The sidebar DTE window defines eligibility, not which expiration dates you may inspect.')
frames=[];fails=[]
for exp in selection:
    try:
        raw=options_data(ticker,exp) if mode=='Yahoo Finance' else demo_chain(spot,exp,rate,div_yield)
        frames.append(prepare_chain(raw,spot,exp,rate,div_yield))
    except Exception as exc: fails.append(f'{exp}: {exc}')
for fail in fails:st.warning(f'Could not load {fail}')
if not frames:
    st.warning('No option chains loaded. Adjust expirations or use demonstration data.');st.stop()
chain=pd.concat(frames,ignore_index=True)
scored=score_chain(chain,spot,shares,overwrite,rate,div_yield,option_tax,fee,target_delta,max_delta,min_otm,min_oi,max_spread,min_yield,earnings_days,min_dte=max(float(min_dte),0.001),max_dte=max_dte+0.999)

scanner,voltab,monitor,margin,journal=st.tabs(['Strike scanner','Volatility & stress','Position monitor','Margin & tax','Trade journal'])
with scanner:
    st.subheader('Market-IV-anchored option ranking')
    valid=scored[scored.eligible]
    st.metric('Eligible candidates',len(valid))
    if any(chain.dte < 3): st.warning('Short-dated (0–2 DTE) options have sharply elevated gamma/assignment and execution risk. Check live bid/ask and expiry cutoff before acting. A low entry delta does not mean a position will stay low risk.')
    if len(valid):
        top=valid.iloc[0]
        st.success(f"Highest-ranked research candidate: {top.expiration} ${top.strike:,.2f} call • delta {top.delta:.3f} • score {top.score:.1f}/100 • estimated net premium ${top.net_premium:,.0f}")
    else: st.info('No contracts pass every filter. Do not force a trade; check the reason column.')
    cols=['expiration','contractSymbol','strike','dte','otm_pct','delta','market_iv','derived_iv','iv_source','bid','ask','mid','spread_pct','openInterest','annualized_gross_yield','net_premium','stress_5pct','stress_10pct','premium_risk_efficiency','score','decision','reason']
    st.dataframe(scored[cols],use_container_width=True,hide_index=True,column_config={'otm_pct':st.column_config.NumberColumn(format='%.2f'),'delta':st.column_config.NumberColumn(format='%.3f'),'score':st.column_config.NumberColumn(format='%.1f')})
    st.download_button('Download scored chain CSV',scored.to_csv(index=False).encode(),'aapl_scored_chain.csv','text/csv')
    st.caption('Score = premium (35) + delta proximity (25) + OTM cushion (15) + spread (10) + open interest (5) + +10% shock efficiency (10). Heuristic; not an expected-return estimate.')
    st.caption('IV: Yahoo strike-level quoted IV is primary. When unavailable, Black-Scholes inversion from valid bid/ask midpoint is used and flagged. Poor/zero quotes are excluded.')
with voltab:
    st.subheader('Volatility term structure & strike engineering')
    available=chain[(chain.otm_pct>=-.03)&(chain.otm_pct<=.03)&chain.used_iv.notna()]
    if not available.empty:
        near=available.copy();near['distance']=abs(near.otm_pct)
        atm=near.sort_values('distance').groupby('expiration').first().reset_index()
        st.dataframe(atm[['expiration','strike','dte','market_iv','derived_iv','used_iv','iv_source']],hide_index=True)
        st.plotly_chart(px.line(atm,x='dte',y='used_iv',markers=True,title='Near-ATM IV term structure'),use_container_width=True)
    strike_rows=[]
    for exp,part in chain.groupby('expiration'):
        closest=part.iloc[(part.otm_pct.abs()).argsort()[:1]]
        if closest.empty:continue
        exp_iv=float(closest.used_iv.iloc[0]); t=float(closest.dte.iloc[0])/365
        if not np.isfinite(exp_iv) or t<=0:continue
        for delta_target in [.05,.07,.10]:
            k=target_strike(spot,t,rate,exp_iv,div_yield,delta_target)
            actual=ceil_strike(k,part.strike.tolist())
            actualrow=part[part.strike==actual]
            strike_rows.append(dict(expiration=exp,days=round(t*365,2),target_delta=delta_target,near_atm_iv=exp_iv,theoretical_strike=k,listed_strike=actual,
                 actual_delta=float(actualrow.delta.iloc[0]) if len(actualrow) else np.nan, actual_market_iv=float(actualrow.used_iv.iloc[0]) if len(actualrow) else np.nan))
    if strike_rows:
        st.dataframe(pd.DataFrame(strike_rows),hide_index=True,use_container_width=True)
        st.caption('First invert using near-ATM market IV, round upward to a listed strike, then verify against that strike’s own market IV and delta. Strike skew means actual delta need not equal target.')
    st.subheader('Risk stress comparison')
    st.caption('Assumes an immediate AAPL price shock with unchanged IV and unchanged time. Illustrative buyback mark, not a forecast or worst-case bound.')
    chart=scored[scored.eligible].head(12)
    if len(chart):
        melted=chart.melt(id_vars=['expiration','strike'],value_vars=['stress_3pct','stress_5pct','stress_10pct','stress_15pct'],var_name='shock',value_name='net_buyback_cost')
        melted['option']=melted.expiration+' / $'+melted.strike.astype(str)
        st.plotly_chart(px.bar(melted,x='option',y='net_buyback_cost',color='shock',barmode='group',title='Option loss (positive = cost), by underlying rally'),use_container_width=True)
with monitor:
    st.subheader('Manage an outstanding call')
    cc1,cc2,cc3=st.columns(3)
    with cc1: held_strike=st.number_input('Written strike',value=float(round(spot*1.07/5)*5),step=5.0)
    with cc2: held_credit=st.number_input('Original credit per share ($)',value=.71,min_value=0.0,step=.05)
    with cc3: held_contracts=st.number_input('Number of short contracts',value=int(shares*overwrite//100),min_value=0)
    cc4,cc5=st.columns(2)
    with cc4: held_exp=st.selectbox('Held option expiration',expiry_choices,index=0)
    with cc5: manual_buyback=st.number_input('Manual executable buyback price (optional, $)',value=0.0,min_value=0.0,step=.05)
    held_chain=chain[(chain.expiration==held_exp)&(abs(chain.strike-held_strike)<.01)]
    if held_chain.empty and held_exp not in selection:
        try:
            held_raw=options_data(ticker,held_exp) if mode=='Yahoo Finance' else demo_chain(spot,held_exp,rate,div_yield)
            held_full=prepare_chain(held_raw,spot,held_exp,rate,div_yield)
            held_chain=held_full[abs(held_full.strike-held_strike)<.01]
        except Exception as exc: st.caption(f'Held-contract quote unavailable: {exc}')
    if len(held_chain):
        r=held_chain.iloc[0]; held_delta=float(r.delta);held_dte=float(r.dte);buyback=float(r.ask) if not manual_buyback else manual_buyback
        quote_source='Yahoo ask (delayed/indicative)' if mode=='Yahoo Finance' and not manual_buyback else 'Manual / demo quote'
    else:
        held_dte=max((date.fromisoformat(held_exp)-date.today()).days,0)
        held_delta=float('nan');buyback=manual_buyback if manual_buyback else float('nan');quote_source='Manual only; no matching quote'
    flag,detail=position_flag(spot,held_strike,held_delta if np.isfinite(held_delta) else 0,held_dte,earnings_days,None if exdiv==999 else exdiv)
    st.warning(f'{flag}: {detail}') if flag.startswith('REVIEW') else st.info(f'{flag}: {detail}')
    d1,d2,d3,d4=st.columns(4)
    d1.metric('Current delta',f'{held_delta:.3f}' if np.isfinite(held_delta) else 'N/A')
    d2.metric('Upside headroom',f'{held_strike/spot-1:.2%}')
    d3.metric('Gross credit',f'${held_contracts*100*held_credit:,.0f}')
    d4.metric('Buyback P/L',f'${(held_credit-buyback)*100*held_contracts:,.0f}' if np.isfinite(buyback) else 'N/A')
    st.caption(f'Current buyback uses {quote_source}. American-style calls can be assigned before expiration; no threshold prevents assignment.')
    if np.isfinite(buyback):
        st.write(f'Buy-to-close estimated debit: **${buyback*100*held_contracts:,.0f}**, before commissions and slippage.')
with margin:
    st.subheader('Debt reduction and tax-reserve illustration')
    st.caption('Premium output assumes a representative candidate can be repeated weekly. Real premiums, IV, market price, fills and opportunity to trade vary; not a forecast.')
    top=scored[scored.eligible].head(1)
    weekly=float(top.net_premium.iloc[0])/(float(top.dte.iloc[0])/7) if len(top) else 0
    years=st.slider('Illustrative projection (years)',1,15,8)
    projection=projected_paydown(loan,loan_rate,weekly,years,extra_sale)
    if not projection.empty:
        aa,bb,cc=st.columns(3)
        aa.metric('Illustrative weekly net option cash',f'${weekly:,.0f}')
        bb.metric('Projected balance at horizon',f'${projection.end.iloc[-1]:,.0f}')
        cc.metric('Gross interest during projection',f'${projection.interest.sum():,.0f}')
        st.line_chart(projection.set_index('week')['end'])
        st.download_button('Download debt schedule',projection.to_csv(index=False).encode(),'margin_projection.csv','text/csv')
    st.markdown('**Tax methodology:** Option taxes are reserved on gross positive premiums in the projection. Actual taxable option gains/losses depend on expiration, buybacks, rolls, assignment and applicable tax rules. Advisory fees may not be personally deductible. Investment interest deductions depend on tracing and qualifying net investment income. Do not net investment-interest tax benefits against option taxes without tax review.')
with journal:
    st.subheader('Closed-trade journal (CSV upload)')
    st.caption('Required columns: entry_price, exit_price, contracts. One row per realized closed/expired option leg; premiums quoted per share. Expired options have exit_price = 0. Open trades should be monitored separately.')
    example=pd.DataFrame([dict(date='2026-11-04',symbol='AAPL',entry_price=.71,exit_price=4.15,contracts=700,notes='Example buyback')])
    st.download_button('Download journal template',example.head(0).to_csv(index=False).encode(),'trade_journal_template.csv','text/csv')
    uploaded=st.file_uploader('Upload journal CSV',type='csv')
    if uploaded:
        try:
            df=pd.read_csv(uploaded)
            required={'entry_price','exit_price','contracts'}
            if not required.issubset(df.columns): raise ValueError(f'Missing columns: {sorted(required-set(df.columns))}')
            for col in required: df[col]=pd.to_numeric(df[col],errors='raise')
            result=summarize_journal(df,option_tax)
            st.dataframe(result,use_container_width=True)
            st.metric('Realized option P/L',f'${result.realized_option_pl.sum():,.0f}')
            st.download_button('Download journal calculations',result.to_csv(index=False).encode(),'journal_results.csv','text/csv')
        except Exception as exc: st.error(f'Invalid journal: {exc}')

st.divider()
st.caption('Research only. No brokerage connection or automated orders. Do not use Yahoo quotes as real-time executable prices. Not tax, legal or investment advice; validate proposed trades and tax consequences with appropriate professionals.')
