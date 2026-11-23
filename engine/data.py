"""Yahoo adapter; cached in UI. Demo generation is intentionally labeled synthetic."""
import datetime as dt
import json
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import numpy as np
import pandas as pd
from .pricing import bs_call


def parse_yahoo_expirations(payload):
    """Return listed dates from Yahoo v7 options response; never invent expirations."""
    results = payload.get('optionChain', {}).get('result') or []
    if not results:
        return []
    out = []
    for timestamp in (results[0].get('expirationDates') or []):
        try:
            out.append(dt.datetime.fromtimestamp(int(timestamp), dt.timezone.utc).date().isoformat())
        except (ValueError, TypeError, OverflowError):
            continue
    return sorted(set(out))


def _direct_yahoo_options(ticker: str, epoch: int | None = None):
    """Best-effort public Yahoo v7 endpoint fallback; provider may deny cloud IPs."""
    failures = []
    for host in ('query1.finance.yahoo.com', 'query2.finance.yahoo.com'):
        url = f'https://{host}/v7/finance/options/{ticker}'
        if epoch is not None:
            url += f'?date={epoch}'
        req = Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (compatible; AAPLResearchDashboard/1.0)',
            'Accept': 'application/json',
        })
        try:
            with urlopen(req, timeout=9) as response:
                payload = json.load(response)
            results = payload.get('optionChain', {}).get('result') or []
            if results:
                return results[0]
            failures.append(f'{host}: empty optionChain.result')
        except HTTPError as exc:
            failures.append(f'{host}: HTTP {exc.code}')
        except (URLError, TimeoutError, ValueError, OSError) as exc:
            failures.append(f'{host}: {type(exc).__name__}: {str(exc)[:90]}')
    raise RuntimeError('; '.join(failures))


def fetch_market(ticker: str):
    try:
        import yfinance as yf
    except ImportError as exc:
        raise RuntimeError('yfinance is missing. Check requirements.txt and redeploy.') from exc
    t = yf.Ticker(ticker)
    hist = t.history(period='2y', interval='1d', auto_adjust=True)
    if hist.empty:
        raise RuntimeError('No price history returned by Yahoo')
    spot = float(hist.Close.iloc[-1])
    errors = []
    try:
        expirations = list(t.options)
    except Exception as exc:
        expirations = []
        errors.append(f'yfinance expirations: {type(exc).__name__}: {str(exc)[:160]}')
    if not expirations:
        try:
            expirations = parse_yahoo_expirations({'optionChain': {'result': [_direct_yahoo_options(ticker)]}})
        except Exception as exc:
            errors.append(f'direct Yahoo endpoints: {exc}')
    if not expirations:
        raise RuntimeError('Yahoo returned no listed option expirations. ' + ' | '.join(errors + ['Yahoo may restrict options access from Streamlit Cloud IP addresses. Use CSV upload mode.']))
    return spot, hist, expirations


def fetch_options(ticker: str, expiration: str):
    try:
        import yfinance as yf
    except ImportError as exc:
        raise RuntimeError('yfinance is missing. Check requirements.txt and redeploy.') from exc
    errors = []
    try:
        chain = yf.Ticker(ticker).option_chain(expiration)
        if chain.calls is not None and not chain.calls.empty:
            return chain.calls.copy()
        errors.append('yfinance returned an empty call chain')
    except Exception as exc:
        errors.append(f'yfinance: {type(exc).__name__}: {str(exc)[:160]}')
    try:
        epoch = int(dt.datetime.combine(dt.date.fromisoformat(expiration), dt.time(0), dt.timezone.utc).timestamp())
        result = _direct_yahoo_options(ticker, epoch)
        chains = result.get('options') or []
        calls = chains[0].get('calls') or [] if chains else []
        if calls:
            return pd.DataFrame(calls)
        errors.append('direct Yahoo endpoint returned no calls')
    except Exception as exc:
        errors.append(f'direct Yahoo: {exc}')
    raise RuntimeError('; '.join(errors) + '. Use CSV upload mode if provider blocks cloud requests.')


def load_chain_csv(source):
    """Accept Yahoo-style options CSV with expiration dates and quote fields."""
    data = pd.read_csv(source)
    aliases = {'expiry': 'expiration', 'expirationdate': 'expiration',
               'implied_volatility': 'impliedVolatility', 'iv': 'impliedVolatility',
               'open_interest': 'openInterest', 'oi': 'openInterest',
               'contract_symbol': 'contractSymbol', 'last_trade_date': 'lastTradeDate'}
    for col in list(data.columns):
        key = col.strip().lower().replace(' ', '_')
        if key in aliases and aliases[key] not in data.columns:
            data = data.rename(columns={col: aliases[key]})
    required = {'expiration', 'strike', 'bid', 'ask'}
    absent = required - set(data.columns)
    if absent:
        raise ValueError('CSV missing required columns: ' + ', '.join(sorted(absent)))
    data['expiration'] = pd.to_datetime(data.expiration, errors='coerce').dt.strftime('%Y-%m-%d')
    for col in ('strike','bid','ask'):
        data[col] = pd.to_numeric(data[col], errors='coerce')
    data = data.dropna(subset=['expiration','strike','bid','ask'])
    data = data[(data.strike > 0) & (data.bid >= 0) & (data.ask >= data.bid)]
    if data.empty:
        raise ValueError('CSV contains no valid call rows with expiration, strike, bid and ask')
    for col, default in [('impliedVolatility', np.nan), ('openInterest', 0), ('volume', 0)]:
        if col not in data: data[col] = default
    if 'contractSymbol' not in data:
        data['contractSymbol'] = 'CSV-' + data['expiration'] + '-' + data['strike'].astype(str)
    return data


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
