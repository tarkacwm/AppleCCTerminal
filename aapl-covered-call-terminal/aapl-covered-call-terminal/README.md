# AAPL Covered-Call Management Terminal

A GitHub-ready **Streamlit research dashboard** for managing a concentrated, low-basis AAPL position and evaluating a covered-call overlay against a margin-paydown objective.

**This application does not place trades, access accounts, or guarantee assignment prevention.** Yahoo Finance's OPRA options quotes are typically delayed and may be stale or unavailable. Do not use it as a real-time trading or compliance system.

## Included

- Yahoo Finance stock history and calls chains via `yfinance`; synthetic demo fallback
- 10/20/60/252-day annualized realized volatility and strike-level Yahoo quoted market IV
- Midpoint-inverted IV as a **flagged** fallback when the source IV is invalid
- Dividend-adjusted Black-Scholes call delta, reverse-delta strike targeting (5/7/10 delta)
- Match theoretical strike to an actual listed strike, then recalculate delta using its own quoted IV
- Filters: delta, OTM headroom, earnings, liquidity, spread, annualized premium, expiration
- Transparent 0–100 premium-versus-risk heuristic score and 3/5/10/15% rally stress buyback cost
- Existing short-call monitor with close/roll review flags and buyback economics
- Weekly margin projection, fee allocation, tax cash reserves, CSV exports
- Closed option-trade journal upload with realized premium versus close debit calculations
- Unit tests

## Deploy to Streamlit Community Cloud

1. Create a new GitHub repository (private recommended for proprietary workflows).
2. Upload **all files and directories from this project**, preserving the folder structure.
3. Go to https://share.streamlit.io/ and choose **Create app** / **Deploy**.
4. Select your GitHub repository, branch `main`, and main file `app.py`.
5. Deploy. No API key is needed for the Yahoo prototype.
6. Start in **Synthetic demonstration** mode to validate the UI. Switch to **Yahoo Finance** to request current published option quotes.

## Run locally

```bash
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Run tests:

```bash
pytest -q
```

## Score definition

A **heuristic** bounded 0–100 score, not a modeled probability or an expected net return:

| Component | Points |
| --- | ---: |
| After-tax premium annualized, saturates at 10% | 35 |
| Delta closeness to target | 25 |
| Upside cushion, saturates at 10% OTM | 15 |
| Bid/ask spread quality | 10 |
| Open interest | 5 |
| Net premium / +10% instantaneous rally buyback loss | 10 |

Eligible contracts must also pass hard filters. A higher score is **not** a guarantee of a better trade. The +10% rally stress assumes current IV remains fixed and ignores actual spreads/slippage; it is **not** a worst-case loss bound. Use calibrated thresholds and validate with historical option quotes before production use.

## Important model assumptions and limitations

- Delta is **not** the probability of assignment. The U.S. equity call is American-style; early exercise can occur, especially around ex-dividend dates. Black-Scholes here is an approximation.
- Yahoo `impliedVolatility` is the **anchor** whenever valid. Model inversion from mid quote is a diagnostic fallback. Vendor fields and bid/ask can be stale, crossed, wide or inconsistent.
- Yahoo OPRA options data is often **15 minutes delayed**, so bid/ask is not an executable live quote. `lastTradeDate` is the timestamp of the last trade, **not** the displayed quote's timestamp.
- The risk-free rate should be a short-term tenor matched to options expiration, not the 10-year Treasury.
- Dividend yield is a continuous-yield approximation. Actual ex-dividend dates and discrete dividends matter.
- Margin projection assumes a constant representative net weekly option cash amount. It does not account for future repricing, lack of premiums, call assignment, position changes, losses from rollbacks, or strike scarcity. Tax reservations on positive premiums are simplistic; actual option tax rules and loss netting can differ.
- **Annual advisory fee assumption** is allocated to covered notional in strike scanner by time outstanding. Client agreements may instead specify a fee on the **entire AAPL position**, in which case margin cash-flow calculations need to be adjusted accordingly. Enter fee terms consistent with the actual agreement.
- Investment-interest deduction and covered-call taxation require qualified tax review (including tracing, investment-income limitation, qualified covered calls, straddles, constructive sales and holding periods). The app does **not** assume tax benefits are immediately cash available for principal repayment.
- One should implement licensed streaming option quotes, a real database, alerts, historical option-chain backtests, authenticated user access and broker-compliance review before using in a client operational process.

## Project layout

```
app.py                   Streamlit UI
engine/data.py           Yahoo + synthetic adapters
engine/pricing.py        Black-Scholes + reverse delta + IV inversion
engine/analytics.py      Realized vol, chain metrics, rally shock math
engine/scoring.py        Eligibility, transparent heuristic score and monitors
engine/portfolio.py      Debt amortization and option trade journal
tests/                   Unit tests
.streamlit/config.toml   Theme
requirements.txt         Dependencies
```
