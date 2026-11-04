"""Transparent heuristic score. Research ranking, NOT a forecast of return or probability."""
import numpy as np
import pandas as pd
from .analytics import stress_cost


def score_chain(df:pd.DataFrame, spot:float, shares:int, overwrite:float, rate:float, div_yield:float,
                tax_rate:float, advisory_fee:float, target_delta:float, max_delta:float,
                min_otm:float, min_oi:int, max_spread:float, min_yield:float, earnings_days:int,
                min_dte:float=4, max_dte:float=14)->pd.DataFrame:
    x=df.copy()
    contracts=int(shares*overwrite//100)
    x['contracts']=contracts
    x['gross_premium']=x.mid*100*contracts
    # Fee on covered position value as annual expense, allocated by time to expiration.
    x['allocated_fee']=spot*100*contracts*advisory_fee*(x.dte/365)
    x['net_premium']=x.gross_premium*(1-tax_rate)-x.allocated_fee
    x['annualized_gross_yield']=x.mid/spot*365/x.dte.replace(0,np.nan)
    x['after_tax_annualized_yield']=x.net_premium/(spot*100*contracts)*365/x.dte.replace(0,np.nan) if contracts else 0.0
    for pct in (.03,.05,.10,.15):
        x[f'stress_{int(pct*100)}pct']= [stress_cost(spot,k,v,t/365,rate,div_yield,m,pct)*100*contracts
            if np.isfinite(v) and np.isfinite(m) else np.nan for k,v,t,m in zip(x.strike,x.used_iv,x.dte,x.mid)]
    # Risk denominator: positive buyback loss under +10% shock, not a statistical expected loss.
    x['buyback_loss_10pct']=x.stress_10pct.clip(lower=0)
    x['premium_risk_efficiency']=x.net_premium/(x.buyback_loss_10pct+np.maximum(1000,x.gross_premium*.05))
    x['eligible']=(x.mid.gt(0)&x.strike.gt(spot)&x.used_iv.notna()&x.delta.between(.001,max_delta)&
        x.otm_pct.ge(min_otm)&x.spread_pct.between(0,max_spread)&x.openInterest.fillna(0).ge(min_oi)&
        x.dte.between(min_dte,max_dte)&x.annualized_gross_yield.ge(min_yield)&x.net_premium.gt(0)&
        (earnings_days > x.dte + 3)&(contracts>0))
    # 0-100 weighted, documented rules; no magic alpha optimizer.
    prem=np.clip(x.after_tax_annualized_yield.fillna(0)/.10,0,1)*35
    delta=np.clip(1-np.abs(x.delta-target_delta)/max(max_delta,.01),0,1)*25
    cushion=np.clip(x.otm_pct.fillna(0)/.10,0,1)*15
    spread=np.clip(1-x.spread_pct.fillna(1)/max(max_spread,.01),0,1)*10
    oi=np.clip(x.openInterest.fillna(0)/max(min_oi*5,100),0,1)*5
    stress=np.clip(x.premium_risk_efficiency.fillna(0)/.35,0,1)*10
    x['score']=np.round(prem+delta+cushion+spread+oi+stress,1)
    x['decision']=np.where(x.eligible,'CANDIDATE','PASS / REVIEW')
    x['reason']=x.apply(lambda r: _reason(r,min_otm,max_delta,min_oi,max_spread,min_yield,earnings_days,min_dte,max_dte),axis=1)
    return x.sort_values(['eligible','score'],ascending=[False,False])


def _reason(r,min_otm,max_delta,min_oi,max_spread,min_yield,earnings_days,min_dte,max_dte):
    reasons=[]
    if not np.isfinite(r.mid) or r.mid<=0: reasons.append('No usable bid/ask')
    if not np.isfinite(r.used_iv): reasons.append('No viable market IV')
    if r.otm_pct<min_otm: reasons.append('OTM cushion too small')
    if pd.isna(r.delta) or r.delta>max_delta: reasons.append('Delta exceeds cap/unavailable')
    if pd.isna(r.spread_pct) or r.spread_pct>max_spread: reasons.append('Wide spread')
    if pd.isna(r.openInterest) or r.openInterest<min_oi: reasons.append('Low open interest')
    if not min_dte<=r.dte<=max_dte: reasons.append('Expiration outside window')
    if r.annualized_gross_yield<min_yield: reasons.append('Premium below hurdle')
    if earnings_days<=r.dte+3: reasons.append('Earnings within expiration buffer')
    return '; '.join(reasons) or 'Passes defined research filters'


def position_flag(spot:float,strike:float,delta:float,dte:float,earnings_days:int,exdiv_days:int|None=None)->tuple[str,str]:
    if spot>=strike or delta>=.25 or (strike/spot-1)<=.03 or (dte<=2 and (strike/spot-1)<=.05):
        return 'REVIEW CLOSE / ROLL', 'Price/delta/expiration threshold reached; early assignment is possible.'
    if exdiv_days is not None and exdiv_days<=dte and spot>=strike*.98:
        return 'REVIEW EX-DIVIDEND', 'Early exercise risk can rise before ex-dividend dates.'
    if delta>=.15 or (strike/spot-1)<=.06 or dte<=4 or earnings_days<=dte:
        return 'WATCH', 'Monitor price, options quote and calendar closely.'
    return 'OK / MONITOR', 'No model trigger; assignment cannot be ruled out.'
