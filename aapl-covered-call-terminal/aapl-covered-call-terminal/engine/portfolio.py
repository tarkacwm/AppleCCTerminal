"""Illustrative finance and option journal, not a tax return or trade accounting engine."""
import pandas as pd


def projected_paydown(balance:float,rate:float,weekly_net_premium:float,years:int=8,extra_annual_sale:float=0.0):
    rows=[]
    for wk in range(1,years*52+1):
        if balance<=0: break
        beg=balance
        interest=beg*rate/52
        sale=extra_annual_sale if wk%52==0 else 0
        paid=min(beg+interest,max(0,weekly_net_premium)+sale)
        balance=max(0,beg+interest-paid)
        rows.append(dict(week=wk,begin=beg,interest=interest,option_net=max(0,weekly_net_premium),sale=sale,payment=paid,end=balance))
    return pd.DataFrame(rows)


def summarize_journal(df:pd.DataFrame, tax_rate:float, fee_rate:float=0):
    """Rows are complete closed trades. P/L based on sell and buyback * contracts * 100."""
    if df.empty: return pd.DataFrame()
    out=df.copy()
    out['gross_credit']=out.entry_price*out.contracts*100
    out['close_debit']=out.exit_price*out.contracts*100
    out['realized_option_pl']=out.gross_credit-out.close_debit
    # Only positive net realized option P/L is taxed here; loss utilization requires tax preparer.
    out['illustrative_tax_reserve']=out.realized_option_pl.clip(lower=0)*tax_rate
    out['net_after_reserve']=out.realized_option_pl-out.illustrative_tax_reserve
    return out
